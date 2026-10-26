#!/usr/bin/env python3
"""Generate a repository index and a direct-download PLDMGR payload catalog.

Only genuine release assets (ELF files) are emitted as installable payloads.
Repository pages remain in repositories.json and are never disguised as binaries.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_URL = (
    "https://raw.githubusercontent.com/nexgen999/PS5-Repository-List/"
    "main/json/repos-database.json"
)
MIRROR_URL = (
    "https://raw.githubusercontent.com/itsPLK/ps5-payloads-mirror/"
    "main/payloads_v2.json"
)
MIRROR_ICONS_URL = (
    "https://raw.githubusercontent.com/itsPLK/ps5-payloads-mirror/"
    "main/icons.json"
)
OUT_DIR = Path(".")
USER_AGENT = "Repository-Catalog/2.1"
API_ROOT = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_URL_KEYS = (
    "url", "html_url", "repo_url", "repository_url", "github_url",
    "repository", "htmlUrl", "github"
)
NAME_KEYS = ("name", "repo_name", "repository_name", "title", "full_name", "fullName")
DESCRIPTION_KEYS = ("description", "desc", "summary", "about")
CATEGORY_KEYS = ("category", "categories", "type", "group")
OWNER_KEYS = ("owner", "author", "username", "user")

def get_first(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            # GitHub API-style owner object is handled separately where useful.
            if key == "owner":
                login = value.get("login") or value.get("name")
                if isinstance(login, str) and login.strip():
                    return login.strip()
        if isinstance(value, list) and value:
            strings = [str(v).strip() for v in value if isinstance(v, (str, int, float))]
            if strings:
                return ", ".join(strings)
    return None


def clean_github_url(value: Any) -> str | None:
    """Accept GitHub-hosted repository links only; reject every other forge/domain."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    match = re.match(r"^https://github\.com/([^/\s?#]+)/([^/\s?#]+)(?:\.git)?(?:/(?:tree|blob|releases|issues|actions|pulls|commits|wiki|projects|settings)(?:/.*)?)?/?(?:[?#].*)?$", value, re.I)
    if not match:
        return None
    owner, repo = match.group(1), re.sub(r"\.git$", "", match.group(2), flags=re.I)
    if repo.lower() in {"topics", "collections", "marketplace", "orgs", "users", "sponsors", "login", "signup", "explore"}:
        return None
    return f"https://github.com/{owner}/{repo}"


def walk_objects(value: Any):
    """Yield dictionaries recursively, including records nested by category."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                yield from walk_objects(child)


def repository_record(obj: dict[str, Any]) -> dict[str, Any] | None:
    # Prefer an actual URL present in the source. Do not construct one from a name.
    url = None
    for key in REPO_URL_KEYS:
        candidate = obj.get(key)
        if isinstance(candidate, str):
            url = clean_github_url(candidate)
            if url:
                break

    # Some databases store a nested repo object.
    if not url:
        for key in ("repo", "repository", "links"):
            nested = obj.get(key)
            if isinstance(nested, dict):
                for nested_key in REPO_URL_KEYS:
                    url = clean_github_url(nested.get(nested_key))
                    if url:
                        break
            if url:
                break

    if not url:
        return None

    name = get_first(obj, NAME_KEYS)
    if not name:
        name = url.rstrip("/").split("/")[-1]

    description = get_first(obj, DESCRIPTION_KEYS) or ""
    category = get_first(obj, CATEGORY_KEYS) or "Repositories"
    author = get_first(obj, OWNER_KEYS)
    avatar_url = obj.get("ownerAvatar") or obj.get("avatar_url") or obj.get("avatarUrl")
    if not isinstance(avatar_url, str):
        owner_obj = obj.get("owner")
        if isinstance(owner_obj, dict):
            avatar_url = owner_obj.get("avatar_url") or owner_obj.get("avatarUrl")
    if not isinstance(avatar_url, str) or not avatar_url.startswith("https://"):
        avatar_url = ""

    # Temporary avatar source is removed before writing public JSON.
    return {
        "name": name,
        "description": description,
        "repository_url": url,
        "category": category,
        "author": author or "",
        "_owner_avatar_url": avatar_url,
    }



def request_bytes(url: str, *, accept: str = "application/json", timeout: int = 12) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if GITHUB_TOKEN and url.startswith(API_ROOT):
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download_json(url: str) -> Any:
    return json.loads(request_bytes(url).decode("utf-8-sig"))


def canonical_repo(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.match(
        r"^https://github\.com/([^/\s?#]+)/([^/\s?#]+)(?:/(?:releases|tree|blob|issues|actions).*)?/?$",
        value.strip(), re.I
    )
    return f"{match.group(1)}/{match.group(2)}" if match else None


def is_direct_asset_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("https://") and bool(re.search(r"\.elf$", value.split("?")[0], re.I))



# Cache GitHub metadata so multiple payloads from the same project do not
# trigger duplicate API requests during a catalog build.
_REPO_METADATA_CACHE: dict[str, dict[str, Any] | None] = {}
_RELEASE_METADATA_CACHE: dict[str, dict[str, Any] | None] = {}


def get_repository_community_metadata(full_name: str) -> dict[str, Any] | None:
    """Fetch public repository popularity and last-push metadata."""
    key = full_name.casefold()
    if key in _REPO_METADATA_CACHE:
        return _REPO_METADATA_CACHE[key]
    try:
        data = download_json(f"{API_ROOT}/repos/{full_name}")
        if not isinstance(data, dict):
            _REPO_METADATA_CACHE[key] = None
            return None
        metadata = {
            "github_stars": data.get("stargazers_count"),
            "open_issues_count": data.get("open_issues_count"),
            "repository_updated_at": data.get("pushed_at") or data.get("updated_at"),
        }
        _REPO_METADATA_CACHE[key] = metadata
        return metadata
    except Exception as exc:
        print(f"NOTICE: community metadata unavailable for {full_name}: {exc}", file=sys.stderr)
        _REPO_METADATA_CACHE[key] = None
        return None


def get_download_count(asset_url: Any) -> int | None:
    """Return the GitHub Release download count for the exact published asset URL."""
    if not isinstance(asset_url, str):
        return None
    parsed = urllib.parse.urlsplit(asset_url)
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    try:
        download_index = parts.index("download")
    except ValueError:
        return None
    if len(parts) <= download_index + 2:
        return None
    owner, repo = parts[0], parts[1]
    tag = "/".join(parts[download_index + 1:-1])
    asset_name = parts[-1]
    full_name = f"{owner}/{repo}"
    cache_key = f"{full_name.casefold()}@{tag}"
    if cache_key not in _RELEASE_METADATA_CACHE:
        try:
            tag_path = urllib.parse.quote(tag, safe="")
            release = download_json(f"{API_ROOT}/repos/{full_name}/releases/tags/{tag_path}")
            _RELEASE_METADATA_CACHE[cache_key] = release if isinstance(release, dict) else None
        except Exception as exc:
            print(f"NOTICE: asset download count unavailable for {full_name} tag {tag}: {exc}", file=sys.stderr)
            _RELEASE_METADATA_CACHE[cache_key] = None
    release = _RELEASE_METADATA_CACHE[cache_key]
    if not isinstance(release, dict):
        return None
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_url_from_api = asset.get("browser_download_url")
        if asset_url_from_api == asset_url or asset.get("name") == asset_name:
            count = asset.get("download_count")
            return count if isinstance(count, int) and count >= 0 else None
    return None


def add_freshness_fields(record: dict[str, Any], date_field: str = "last_update") -> None:
    """Add age fields derived from a source-provided date; never invent a date."""
    raw = record.get(date_field)
    if not isinstance(raw, str) or not raw.strip():
        return
    try:
        updated = datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).date()
        today = datetime.now(timezone.utc).date()
        days = max(0, (today - updated).days)
        record["last_update_days"] = days
        record["last_update_months"] = round(days / 30.4375, 1)
    except ValueError:
        return


def get_latest_release(full_name: str) -> dict[str, Any] | None:
    """Find the newest public release with a direct ELF asset, including prereleases."""
    url = f"{API_ROOT}/repos/{full_name}/releases?per_page=10"
    try:
        data = download_json(url)
        if not isinstance(data, list):
            return None
        for release in data:
            if not isinstance(release, dict):
                continue
            assets = release.get("assets")
            if isinstance(assets, list) and any(
                isinstance(asset, dict) and is_direct_asset_url(asset.get("browser_download_url"))
                for asset in assets
            ):
                return release
        return None
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            if exc.code == 403:
                print(f"NOTICE: GitHub API limit/permission issue for {full_name}; keeping curated mirror data.", file=sys.stderr)
            return None
        print(f"NOTICE: release lookup failed for {full_name}: HTTP {exc.code}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"NOTICE: release lookup failed for {full_name}: {exc}", file=sys.stderr)
        return None


def payload_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """Stable logical identity: upstream repository plus normalized ELF filename."""
    repo = canonical_repo(payload.get("source")) or canonical_repo(payload.get("source_direct")) or ""
    filename = str(payload.get("filename") or "").strip().lower().rsplit("/", 1)[-1]
    filename = re.sub(r"\.elf$", "", filename, flags=re.I)
    # Strip release versions so mirrored and upstream copies of the same ELF match.
    filename = re.sub(r"[_-]v?\d+(?:[._-]\d+)*(?:[-_][a-z][a-z0-9._-]*)?$", "", filename)
    filename = re.sub(r"(?i)(?:^|[-_])ps5(?=$|[-_])", "", filename)
    filename = re.sub(r"[-_.]+", "-", filename).strip("-")
    return repo.lower(), filename


def payload_global_identity(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identify payloads without conflating independent publishers."""
    repo = canonical_repo(payload.get("source")) or canonical_repo(payload.get("source_direct")) or ""
    name = re.sub(r"\s*[·•]\s*NEW\s*$", "", str(payload.get("name") or ""), flags=re.I)
    name = re.sub(r"\s+", " ", name).strip().casefold()
    filename = str(payload.get("filename") or "").rsplit("/", 1)[-1].lower()
    filename = re.sub(r"\.elf$", "", filename)
    filename = re.sub(r"[_-]v?\d+(?:[._-]\d+)*(?:[-_][a-z][a-z0-9._-]*)?$", "", filename)
    filename = re.sub(r"[-_.]+", "-", filename).strip("-")
    version = str(payload.get("version") or "").strip().lower().removeprefix("v")
    return repo.lower(), name, filename, version


def payload_slug(value: Any) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return re.sub(r"[-_.]{2,}", "-", value).strip("-._") or "payload"


def normalize_project_name(value: Any) -> str:
    """Normalize labels for duplicate detection without using publisher as identity."""
    name = re.sub(r"\s*[·•]\s*NEW\s*$", "", str(value or ""), flags=re.I)
    name = re.sub(r"(?i)(?:^|\s|[-_])PS5(?=$|\s|[-_])", " ", name)
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def infer_category(*values: Any) -> str:
    """Assign consistent PLDMGR categories to payloads using their metadata."""
    text = " ".join(str(value or "") for value in values).lower()
    rules = [
        (("hen", "jailbreak", "exploit", "kernel", "payload loader", "homebrew enabler"), "System & Jailbreak"),
        (("ftp", "http", "network", "dns", "smb", "remote play", "web server", "websrv", "ps5upload"), "Networking & Servers"),
        (("loader", "autoload", "autoloader", "elfldr", "webkit"), "Loaders"),
        (("emulator", "linux", "retroarch", "vm "), "Emulators & Linux"),
        (("cheat", "trainer", "fps", "overlay", "mod menu", "patch"), "Game Tools & Mods"),
        (("save", "dumper", "dump", "backup", "file manager", "filesystem", "pkg-manager", "pkg manager"), "File & Package Management"),
        (("plugin", "daemon", "service", "mount", "shadowmount"), "Plugins & System Tools"),
    ]
    for keywords, category in rules:
        if any(word in text for word in keywords):
            return category
    return "Utilities & Tools"

def normalize_icon_data(value: Any) -> str:
    """Normalize icon data to PLDMGR's size/format limits."""
    if not isinstance(value, str) or not value.startswith("data:image/") or "," not in value:
        return ""
    header, encoded = value.split(",", 1)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return ""
    if len(value) <= 12_288 and header.startswith(("data:image/png;base64", "data:image/jpeg;base64", "data:image/svg+xml;base64")):
        # Even valid data URIs may contain oversized image dimensions; re-encode raster formats below.
        if header.startswith("data:image/svg+xml;base64"):
            return value
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(raw))
        image.thumbnail((64, 64), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        png = output.getvalue()
        png_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        if len(png_uri) <= 12_288:
            return png_uri
        # JPEG fallback for photographic icons; transparency is flattened on white.
        rgb = image.convert("RGB")
        for quality in (85, 70, 55, 40, 30):
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
            jpg_uri = "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
            if len(jpg_uri) <= 12_288:
                return jpg_uri
    except Exception:
        pass
    return ""


def add_avatar_icon(owner_avatar_url: str, icons: dict[str, str]) -> str:
    # A neutral embedded SVG keeps icon coverage complete when a repository
    # has no accessible avatar (including repositories on a self-hosted forge).
    fallback_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#252a34"/>'
        '<path d="M18 20h28v6H18zm0 9h28v6H18zm0 9h18v6H18z" fill="#e6edf3"/>'
        '<circle cx="46" cy="44" r="7" fill="#58a6ff"/>'
        '</svg>'
    )
    fallback_key = hashlib.sha256(fallback_svg.encode("utf-8")).hexdigest()
    fallback_data = "data:image/svg+xml;base64," + base64.b64encode(fallback_svg.encode("utf-8")).decode("ascii")
    icons.setdefault(fallback_key, fallback_data)

    if not owner_avatar_url.startswith("https://avatars.githubusercontent.com/"):
        return fallback_key
    try:
        raw = request_bytes(owner_avatar_url, accept="image/*", timeout=4)
        if not raw:
            return fallback_key
        key = hashlib.sha256(raw).hexdigest()
        mime = mimetypes.guess_type(owner_avatar_url.split("?")[0])[0] or "image/png"
        normalized = normalize_icon_data(f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}")
        if not normalized:
            return fallback_key
        icons.setdefault(key, normalized)
        return key
    except Exception as exc:
        print(f"NOTICE: could not fetch repository avatar: {exc}", file=sys.stderr)
        return fallback_key



def discover_github_repositories(existing_urls: set[str]) -> list[dict[str, Any]]:
    """Discover additional PS5-related repositories through GitHub repository search."""
    queries = [
        'ps5 payload in:name,description,readme',
        'ps5 homebrew in:name,description,readme',
        'ps5 jailbreak in:name,description,readme',
        'ps5 exploit in:name,description,readme',
        'ps5 elf in:name,description,readme',
        'ps5 in:name,description',
    ]
    discovered: list[dict[str, Any]] = []
    seen = {u.lower().rstrip("/") for u in existing_urls}
    capability_terms = (
        "payload", "homebrew", "jailbreak", "exploit", "etahen", "kstuff",
        "elf", "prospero", "ps5sdk", "ps5 sdk", "ps5-linux", "ps5 linux",
        "ps5 tool", "playstation 5"
    )
    for query in queries:
        endpoint = API_ROOT + "/search/repositories?" + urllib.parse.urlencode({
            "q": query, "sort": "updated", "order": "desc", "per_page": 100, "page": 1
        })
        try:
            response = download_json(endpoint)
            items = response.get("items", []) if isinstance(response, dict) else []
            if not isinstance(items, list):
                continue
        except Exception as exc:
            print(f"NOTICE: GitHub repository discovery query failed ({query}): {exc}", file=sys.stderr)
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("archived") is True:
                continue
            full_name = item.get("full_name")
            html_url = clean_github_url(item.get("html_url"))
            if not isinstance(full_name, str) or not html_url:
                continue
            key = html_url.lower().rstrip("/")
            if key in seen:
                continue
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            topics = item.get("topics") if isinstance(item.get("topics"), list) else []
            searchable = " ".join([
                full_name, str(item.get("description") or ""),
                " ".join(str(t) for t in topics)
            ]).lower()
            has_ps5_context = any(term in searchable for term in ("ps5", "playstation 5", "playstation5", "prospero"))
            has_payload_context = any(term in searchable for term in capability_terms)
            if not (has_ps5_context and has_payload_context):
                continue
            seen.add(key)
            discovered.append({
                "name": str(item.get("name") or full_name.split("/")[-1]),
                "description": str(item.get("description") or "Automatically discovered PS5-related GitHub repository."),
                "repository_url": html_url,
                "category": "PS5 Auto-discovered",
                "author": str(owner.get("login") or full_name.split("/")[0]),
                "_owner_avatar_url": str(owner.get("avatar_url") or ""),
                "discovery_source": "GitHub repository search",
                "discovered_at": datetime.now(timezone.utc).date().isoformat(),
            })
    print(f"Additional PS5-related repositories discovered via GitHub Search: {len(discovered)}")
    return discovered


def load_previous_payloads() -> list[dict[str, Any]]:
    """Load the last published feed so newly added entries can keep a short-lived NEW label."""
    try:
        previous = json.loads((OUT_DIR / "payloads_v2.json").read_text(encoding="utf-8"))
        items = previous.get("payloads", []) if isinstance(previous, dict) else []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def mark_recently_added_payloads(payloads: list[dict[str, Any]], previous_payloads: list[dict[str, Any]]) -> None:
    """Mark catalog additions for seven days; don't label ordinary version updates as new payloads."""
    previous_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for item in previous_payloads:
        identity = payload_identity(item)
        if identity[0] and identity[1]:
            previous_by_identity.setdefault(identity, item)

    now = datetime.now(timezone.utc)
    for payload in payloads:
        identity = payload_identity(payload)
        previous = previous_by_identity.get(identity)
        first_seen = previous.get("first_seen") if previous else None

        if not previous:
            first_seen = now.date().isoformat()
            payload["first_seen"] = first_seen
        elif isinstance(first_seen, str) and first_seen:
            payload["first_seen"] = first_seen
        else:
            # Existing catalog entries predate this feature; don't falsely mark them as new.
            payload.pop("first_seen", None)
            continue

        try:
            first_seen_date = datetime.fromisoformat(first_seen[:10]).date()
            age_days = (now.date() - first_seen_date).days
        except (TypeError, ValueError):
            age_days = 9999

        base_name = re.sub(r"\\s*[·•]\\s*NEW\\s*$", "", str(payload.get("name") or "Payload"), flags=re.I).rstrip()
        if 0 <= age_days < 7:
            payload["name"] = base_name + " · NEW"
        else:
            payload["name"] = base_name


def main() -> int:
    previous_payloads = load_previous_payloads()
    try:
        source_data = download_json(SOURCE_URL)
        mirror_data = download_json(MIRROR_URL)
        icons_data = download_json(MIRROR_ICONS_URL)
    except Exception as exc:
        print(f"ERROR: failed to download a required source: {exc}", file=sys.stderr)
        return 1

    icons = icons_data.get("icons", {}) if isinstance(icons_data, dict) else {}
    if not isinstance(icons, dict):
        icons = {}
    # PLDMGR rejects icon catalogs with oversized entries/catalogs. Normalize all upstream images.
    icons = {key: normalized for key, value in icons.items()
             if isinstance(key, str) and (normalized := normalize_icon_data(value))}

    repositories: list[dict[str, Any]] = []
    seen_repos: set[str] = set()
    for obj in walk_objects(source_data):
        record = repository_record(obj)
        if not record:
            continue
        key = record["repository_url"].lower()
        if key in seen_repos:
            continue
        seen_repos.add(key)
        repositories.append(record)

    if not repositories:
        print("ERROR: source parser found no repositories; refusing to overwrite outputs.", file=sys.stderr)
        return 2

    # Guard against silently dropping any valid repository from the source's primary list.
    source_repos = source_data.get("repos") if isinstance(source_data, dict) else None
    if isinstance(source_repos, list):
        expected_repo_urls = set()
        for source_obj in source_repos:
            if isinstance(source_obj, dict):
                source_record = repository_record(source_obj)
                if source_record:
                    expected_repo_urls.add(source_record["repository_url"].lower())
        missing_source_urls = expected_repo_urls - seen_repos
        if missing_source_urls:
            print(f"ERROR: parser omitted {len(missing_source_urls)} source repositories: {sorted(missing_source_urls)[:10]}", file=sys.stderr)
            return 7
        print(f"Source records: {len(source_repos)}; unique valid repositories retained: {len(expected_repo_urls)}")

    # Keep explicitly curated projects that may not yet appear in the upstream repository list.
    # These are repository metadata records; only verified direct ELF release assets become payloads.
    # Keep the curated list in source control so scheduled refreshes do not drop these entries.
    curated_path = OUT_DIR / "curated_repositories.json"
    try:
        curated_data = json.loads(curated_path.read_text(encoding="utf-8"))
        curated_records = curated_data.get("repositories", []) if isinstance(curated_data, dict) else []
    except (OSError, json.JSONDecodeError):
        curated_records = []
    for obj in curated_records:
        if not isinstance(obj, dict):
            continue
        record = repository_record(obj)
        if not record:
            continue
        key = record["repository_url"].lower().rstrip("/")
        if key not in seen_repos:
            repositories.append(record)
            seen_repos.add(key)
            target = repositories[-1]
        else:
            target = next(
                (item for item in repositories
                 if str(item.get("repository_url", "")).lower().rstrip("/") == key),
                None,
            )
        if target is not None:
            # Curated metadata intentionally overrides upstream labels/descriptions and
            # may add package links; retain automatically discovered payload fields unless
            # a curated value explicitly supplies the same field.
            target.update({k: v for k, v in record.items() if v not in (None, "")})
            target.update({
                k: v for k, v in obj.items()
                if k not in {"_owner_avatar_url"} and v not in (None, "")
            })

    # Expand beyond the two curated sources: search GitHub for newly created PS5 projects.
    # Search failures are non-fatal; the curated feeds still update as usual.
    known_urls = {str(record.get("repository_url") or "").lower().rstrip("/") for record in repositories}
    auto_discovered = discover_github_repositories(known_urls)
    for record in auto_discovered:
        url_key = str(record.get("repository_url") or "").lower().rstrip("/")
        if url_key and url_key not in known_urls:
            repositories.append(record)
            known_urls.add(url_key)

    # Make same-named repositories from different publishers distinguishable in the index.
    # Repository URL remains the identity; similar names from different owners are valid entries.
    repository_name_groups: dict[str, list[dict[str, Any]]] = {}
    for record in repositories:
        base_name = str(record.get("name") or "").strip()
        repository_name_groups.setdefault(normalize_project_name(base_name), []).append(record)
    for group in repository_name_groups.values():
        if len(group) < 2:
            continue
        repo_parts = []
        for record in group:
            full_name = canonical_repo(record.get("repository_url"))
            if full_name:
                parts = full_name.split("/")
            else:
                parsed = urllib.parse.urlsplit(str(record.get("repository_url") or ""))
                parts = [part for part in parsed.path.split("/") if part]
            repo_parts.append(parts)
        owner_counts: dict[str, int] = {}
        for parts in repo_parts:
            owner = parts[0] if parts else ""
            owner_counts[owner.casefold()] = owner_counts.get(owner.casefold(), 0) + 1
        for record, parts in zip(group, repo_parts):
            if len(parts) < 2:
                continue
            owner = parts[0]
            suffix = owner if owner_counts.get(owner.casefold(), 0) == 1 else "/".join(parts)
            record["name"] = str(record.get("name") or "Repository") + " — " + suffix

    mirror_payloads = mirror_data.get("payloads") if isinstance(mirror_data, dict) else None
    if not isinstance(mirror_payloads, list):
        print("ERROR: itsPLK mirror schema changed; expected payloads array.", file=sys.stderr)
        return 3

    payloads: list[dict[str, Any]] = []
    payload_by_repo: dict[str, dict[str, Any]] = {}
    seen_payload_urls: set[str] = set()
    for item in mirror_payloads:
        if not isinstance(item, dict) or not is_direct_asset_url(item.get("url")):
            continue
        if not all(isinstance(item.get(k), str) and item[k].strip()
                   for k in ("name", "filename", "url")):
            continue
        url = item["url"].strip()
        if url in seen_payload_urls:
            continue
        seen_payload_urls.add(url)
        payloads.append(dict(item))
        for field in ("source", "source_direct"):
            key = canonical_repo(item.get(field))
            if key:
                payload_by_repo.setdefault(key.lower(), item)

    # Merge explicitly curated direct ELF assets so manual additions survive scheduled rebuilds.
    curated_payload_path = OUT_DIR / "curated_payloads.json"
    try:
        curated_payload_data = json.loads(curated_payload_path.read_text(encoding="utf-8"))
        curated_payload_records = curated_payload_data.get("payloads", []) if isinstance(curated_payload_data, dict) else []
    except (OSError, json.JSONDecodeError):
        curated_payload_records = []
    for item in curated_payload_records:
        if not isinstance(item, dict) or not is_direct_asset_url(item.get("url")):
            continue
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("name", "filename", "url")):
            continue
        url = item["url"].strip()
        if url in seen_payload_urls:
            # A curated record may intentionally enrich an asset already discovered
            # from the mirror or a repository release. Keep live metrics/icon data,
            # but let the curated record control its display name and original
            # description, so multi-asset projects can label each payload accurately.
            existing = next((payload for payload in payloads if payload.get("url") == url), None)
            if existing:
                for field in (
                    "name", "filename", "description", "version", "last_update",
                    "category", "checksum", "id", "source", "source_direct",
                ):
                    value = item.get(field)
                    if isinstance(value, str) and value.strip():
                        existing[field] = value.strip()
            continue
        curated_item = dict(item)
        curated_item.setdefault("source_direct", url)
        if not isinstance(curated_item.get("source"), str) or not curated_item["source"].strip():
            curated_item["source"] = url.split("/releases/", 1)[0] + "/releases"
        payloads.append(curated_item)
        seen_payload_urls.add(url)
        for field in ("source", "source_direct"):
            key = canonical_repo(curated_item.get(field))
            if key:
                payload_by_repo.setdefault(key.lower(), curated_item)

    # Only poll GitHub Releases for curated projects and repositories that do not
    # already have a direct ELF in the upstream mirror. The mirror refreshes every
    # six hours, so rechecking every already-covered repository wastes API calls.
    curated_repo_keys = {
        key
        for obj in curated_records
        if isinstance(obj, dict)
        for key in [canonical_repo(obj.get("repository_url"))]
        if key
    }
    curated_repo_keys = {key.lower() for key in curated_repo_keys}

    discovered = 0
    refreshed = 0
    checked = 0
    for record in repositories:
        full_name = canonical_repo(record["repository_url"])
        if not full_name:
            continue
        repo_key = full_name.lower()
        match = payload_by_repo.get(repo_key)
        if match:
            record["payload_available"] = True
            candidate_icon = match.get("icon_key")
            if isinstance(candidate_icon, str) and candidate_icon in icons:
                record["icon_key"] = candidate_icon
            if not record.get("icon_key"):
                avatar_url = record.pop("_owner_avatar_url", "")
                if not avatar_url and full_name:
                    avatar_url = f"https://github.com/{full_name.split('/')[0]}.png?size=128"
                record["icon_key"] = add_avatar_icon(avatar_url, icons)
                if not record["icon_key"] and full_name:
                    record["icon_key"] = add_avatar_icon(f"https://github.com/{full_name.split('/')[0]}.png?size=128", icons)
            for src, dst in (
                ("version", "version"), ("last_update", "last_update"),
                ("filename", "payload_filename"),
                ("url", "payload_url"), ("checksum", "checksum"),
            ):
                if isinstance(match.get(src), str) and match[src].strip():
                    record[dst] = match[src]
            if record.get("icon_key") and match.get("icon_key") not in icons:
                match["icon_key"] = record["icon_key"]
        else:
            avatar_url = record.pop("_owner_avatar_url", "")
            if not avatar_url and full_name:
                avatar_url = f"https://github.com/{full_name.split('/')[0]}.png?size=128"
            record["icon_key"] = add_avatar_icon(avatar_url, icons)
            if not record["icon_key"] and full_name:
                record["icon_key"] = add_avatar_icon(f"https://github.com/{full_name.split('/')[0]}.png?size=128", icons)

        # Existing mirror payloads are already refreshed from the mirror every six
        # hours. Poll Releases only for curated records (to refresh pinned assets)
        # or repositories without a mirror payload (to discover new direct ELF assets).
        if match and repo_key not in curated_repo_keys:
            continue

        checked += 1
        release = get_latest_release(full_name)
        time.sleep(0.05)
        if not release:
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        version = str(release.get("tag_name") or release.get("name") or "")
        updated = str(release.get("published_at") or release.get("created_at") or "")
        if updated:
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                updated = updated[:10]
        # If a curated payload already exists, refresh it only when the upstream
        # release is newer and a direct ELF asset can be selected unambiguously.
        if match:
            old_date = str(match.get("last_update") or "")
            if updated and updated > old_date:
                elf_assets = [
                    asset for asset in assets
                    if isinstance(asset, dict)
                    and isinstance(asset.get("name"), str)
                    and is_direct_asset_url(asset.get("browser_download_url"))
                ]
                chosen = None
                if len(elf_assets) == 1:
                    chosen = elf_assets[0]
                elif elf_assets:
                    old_direct_name = str(match.get("source_direct") or "").split("?")[0].rsplit("/", 1)[-1]
                    chosen = next((a for a in elf_assets if a.get("name") == old_direct_name), None)
                if chosen:
                    old_url = match.get("url")
                    new_url = chosen["browser_download_url"]
                    if old_url in seen_payload_urls:
                        seen_payload_urls.remove(old_url)
                    match["url"] = new_url
                    match["filename"] = chosen["name"]
                    match["source_direct"] = new_url
                    if version:
                        match["version"] = version
                    if updated:
                        match["last_update"] = updated
                    digest = chosen.get("digest")
                    if isinstance(digest, str) and digest.startswith("sha256:"):
                        match["checksum"] = digest.removeprefix("sha256:")
                    else:
                        match.pop("checksum", None)
                    seen_payload_urls.add(new_url)
                    record["payload_filename"] = match["filename"]
                    record["payload_url"] = new_url
                    if version:
                        record["version"] = version
                    if updated:
                        record["last_update"] = updated
                    if match.get("checksum"):
                        record["checksum"] = match["checksum"]
                    refreshed += 1

            # Curated repositories may publish several ELF payloads in one release.
            # Keep the curated entry and add any additional direct ELF assets not already listed.
            description = str(record.get("description") or release.get("body") or "").strip()
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                asset_name = asset.get("name")
                download_url = asset.get("browser_download_url")
                if not isinstance(asset_name, str) or not is_direct_asset_url(download_url):
                    continue
                if download_url in seen_payload_urls:
                    continue
                digest = asset.get("digest")
                checksum = digest.removeprefix("sha256:") if isinstance(digest, str) and digest.startswith("sha256:") else ""
                extra = {
                    "name": record["name"],
                    "filename": asset_name,
                    "url": download_url,
                    "source": record["repository_url"].rstrip("/") + "/releases",
                    "source_direct": download_url,
                    "description": description or f"PS5 payload from {full_name}",
                    "last_update": updated,
                    "version": version,
                    "category": infer_category(record["name"], description, asset_name, record.get("category")),
                }
                if checksum:
                    extra["checksum"] = checksum
                if record.get("icon_key"):
                    extra["icon_key"] = record["icon_key"]
                payloads.append(extra)
                seen_payload_urls.add(download_url)
                discovered += 1
            continue

        description = str(record.get("description") or release.get("body") or "").strip()
        category = str(record.get("category") or "Utilities & Tools")
        owner = release.get("author") if isinstance(release.get("author"), dict) else {}
        avatar = owner.get("avatar_url", "") if isinstance(owner, dict) else ""
        icon_key = record.get("icon_key") or (add_avatar_icon(avatar, icons) if avatar else "")
        if icon_key:
            record["icon_key"] = icon_key

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            asset_name = asset.get("name")
            download_url = asset.get("browser_download_url")
            if not isinstance(asset_name, str) or not is_direct_asset_url(download_url):
                continue
            if download_url in seen_payload_urls:
                continue
            digest = asset.get("digest")
            checksum = digest.removeprefix("sha256:") if isinstance(digest, str) and digest.startswith("sha256:") else ""
            item = {
                "name": record["name"],
                "filename": asset_name,
                "url": download_url,
                "source": record["repository_url"].rstrip("/") + "/releases",
                "source_direct": download_url,
                "description": description or f"PS5 payload from {full_name}",
                "last_update": updated,
                "version": version,
                "category": infer_category(record["name"], description, asset_name, category),
            }
            if checksum:
                item["checksum"] = checksum
            if icon_key:
                item["icon_key"] = icon_key
            payloads.append(item)
            seen_payload_urls.add(download_url)
            payload_by_repo.setdefault(repo_key, item)
            record["payload_available"] = True
            record["payload_filename"] = asset_name
            record["payload_url"] = download_url
            if version:
                record["version"] = version
            if updated:
                record["last_update"] = updated
            if checksum:
                record["checksum"] = checksum
            if icon_key:
                record["icon_key"] = icon_key
            discovered += 1
        time.sleep(0.05)

    # Remove only the same direct asset URL (ignoring query/fragment tracking).
    # Do NOT collapse records by normalized filename or project/display-name similarity:
    # independent publishers can ship valid forks, ports, variants, or assets with the
    # same filename, including when their metadata points at a shared mirror.
    deduplicated_payloads: list[dict[str, Any]] = []
    seen_payload_urls_normalized: set[str] = set()
    for payload in payloads:
        filename = str(payload.get("filename") or "")
        if re.search(r"(?i)(?:^|[-_.])ps4(?:[-_.]|$)", filename):
            continue
        raw_url = str(payload.get("url") or "").strip()
        parsed_url = urllib.parse.urlsplit(raw_url)
        normalized_url = urllib.parse.urlunsplit((
            parsed_url.scheme.lower(),
            parsed_url.netloc.lower(),
            parsed_url.path.rstrip("/"),
            "",
            "",
        ))
        if normalized_url and normalized_url in seen_payload_urls_normalized:
            continue
        if normalized_url:
            seen_payload_urls_normalized.add(normalized_url)
        deduplicated_payloads.append(payload)
    removed_duplicates = len(payloads) - len(deduplicated_payloads)
    payloads = deduplicated_payloads

    # PLDMGR needs stable unique item IDs; names alone collide when a project
    # publishes multiple ELF assets, which can collapse entries in the UI.
    used_ids: set[str] = set()
    for payload in payloads:
        repo_name = canonical_repo(payload.get("source")) or canonical_repo(payload.get("source_direct")) or ""
        file_slug = payload_slug(str(payload.get("filename") or "").rsplit("/", 1)[-1].removesuffix(".elf"))
        digest = hashlib.sha256((repo_name.lower() + "|" + str(payload.get("filename") or "") + "|" + str(payload.get("url") or "")).encode("utf-8")).hexdigest()[:8]
        item_id = (payload_slug(payload.get("name")) + "-" + file_slug + "-" + digest)[:120]
        if item_id in used_ids:
            item_id = item_id[:110] + "-" + digest
        used_ids.add(item_id)
        payload["id"] = item_id

    # Disambiguate repeated display names: distinct repositories show publisher names;
    # multiple assets from the same repository show their asset stem.
    name_groups: dict[str, list[dict[str, Any]]] = {}
    for payload in payloads:
        base_name = re.sub(r"\s*[·•]\s*NEW\s*$", "", str(payload.get("name") or ""), flags=re.I)
        name_groups.setdefault(normalize_project_name(base_name), []).append(payload)
    for group in name_groups.values():
        if len(group) < 2:
            continue
        repo_names = [
            canonical_repo(p.get("source")) or canonical_repo(p.get("source_direct")) or ""
            for p in group
        ]
        unique_repos = set(repo_names)
        owner_counts: dict[str, int] = {}
        for repo in unique_repos:
            owner = repo.split("/")[0] if repo else ""
            owner_counts[owner.casefold()] = owner_counts.get(owner.casefold(), 0) + 1
        for payload, source_repo in zip(group, repo_names):
            if len(unique_repos) > 1 and source_repo:
                owner = source_repo.split("/")[0]
                suffix = owner if owner_counts.get(owner.casefold(), 0) == 1 else source_repo
            else:
                stem = str(payload.get("filename") or "").rsplit("/", 1)[-1].removesuffix(".elf")
                stem = re.sub(r"(?i)[_-]v?\d+(?:[._-]\d+)*.*$", "", stem).strip("-_ .")
                suffix = stem or (source_repo.split("/")[-1] if source_repo else "asset")
            payload["name"] = str(payload.get("name") or "Payload") + " — " + suffix

    # Keep every independently sourced asset visible in clients that require unique
    # display names. If publisher/filename labels still collide, append a stable URL hash
    # instead of deleting either entry.
    used_display_names: set[str] = set()
    for payload in payloads:
        display_name = str(payload.get("name") or "Payload")
        key = display_name.casefold()
        if key in used_display_names:
            digest = hashlib.sha256(str(payload.get("url") or "").encode("utf-8")).hexdigest()[:8]
            display_name = f"{display_name} [{digest}]"
            key = display_name.casefold()
            while key in used_display_names:
                digest = hashlib.sha256((str(payload.get("url") or "") + display_name).encode("utf-8")).hexdigest()[:10]
                display_name = f"{display_name} [{digest}]"
                key = display_name.casefold()
            payload["name"] = display_name
        used_display_names.add(key)

    # Mark genuinely new catalog entries for seven days. PLDMGR displays payload.name,
    # so this stays compatible with its current UI without requiring a client-side schema change.
    mark_recently_added_payloads(payloads, previous_payloads)

    # Ensure every entry has a useful category and a valid icon mapping.
    repository_by_name = {
        canonical_repo(record.get("repository_url")).lower(): record
        for record in repositories if canonical_repo(record.get("repository_url"))
    }
    for payload in payloads:
        current_category = str(payload.get("category") or "").strip()
        if not current_category or current_category.lower() in {"repositories", "uncategorized"}:
            payload["category"] = infer_category(
                payload.get("name"), payload.get("description"), payload.get("filename")
            )
        icon_key = payload.get("icon_key")
        if not isinstance(icon_key, str) or icon_key not in icons:
            full_name = canonical_repo(payload.get("source")) or canonical_repo(payload.get("source_direct"))
            related = repository_by_name.get(full_name.lower()) if full_name else None
            icon_key = related.get("icon_key") if related else None
            if not icon_key and full_name:
                owner = full_name.split("/")[0]
                icon_key = add_avatar_icon(f"https://github.com/{owner}.png?size=128", icons)
            if icon_key and icon_key in icons:
                payload["icon_key"] = icon_key
            else:
                print(f"ERROR: payload has no valid icon mapping: {payload.get('name')} ({payload.get('source')})", file=sys.stderr)
                return 8

    if not payloads:
        print("ERROR: no direct ELF assets found; refusing to publish empty PLDMGR feed.", file=sys.stderr)
        return 4

    # Ensure repositories on custom forges also have a valid icon entry.
    fallback_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#252a34"/>'
        '<path d="M18 20h28v6H18zm0 9h28v6H18zm0 9h18v6H18z" fill="#e6edf3"/>'
        '<circle cx="46" cy="44" r="7" fill="#58a6ff"/>'
        '</svg>'
    )
    fallback_key = hashlib.sha256(fallback_svg.encode("utf-8")).hexdigest()
    icons.setdefault(fallback_key, "data:image/svg+xml;base64," + base64.b64encode(fallback_svg.encode("utf-8")).decode("ascii"))
    for record in repositories:
        if not isinstance(record.get("icon_key"), str) or record["icon_key"] not in icons:
            record["icon_key"] = fallback_key

    missing_repository_icons = [r.get("repository_url") for r in repositories if not r.get("icon_key") or r["icon_key"] not in icons]
    if missing_repository_icons:
        print(f"ERROR: {len(missing_repository_icons)} repositories have no valid icon; refusing to publish partial icon coverage. Examples: {missing_repository_icons[:10]}", file=sys.stderr)
        return 6
    for record in repositories:
        record.pop("_owner_avatar_url", None)


    # Add optional community metrics without changing the existing PLDMGR fields.
    # GitHub stars measure popularity, not a user rating. Download counts are
    # attached only when GitHub exposes the count for the exact release asset.
    for record in repositories:
        full_name = canonical_repo(record.get("repository_url"))
        if full_name:
            community = get_repository_community_metadata(full_name)
            if community:
                for key, value in community.items():
                    if value is not None:
                        record[key] = value
        add_freshness_fields(record)

    for payload in payloads:
        source_repo = canonical_repo(payload.get("source")) or canonical_repo(payload.get("source_direct"))
        if source_repo:
            community = get_repository_community_metadata(source_repo)
            if community:
                for key, value in community.items():
                    if value is not None:
                        payload[key] = value
        count = get_download_count(payload.get("url"))
        if count is not None:
            payload["download_count"] = count
            payload["download_count_source"] = "github_release_asset"
        add_freshness_fields(payload)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    index_doc = {
        "name": "Repository Catalog",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": SOURCE_URL,
        "count": len(repositories),
        "payload_count": len(payloads),
        "icons_url": "https://theeteempire.github.io/repository-catalog/icons.json",
        "repositories": repositories,
    }
    pldmgr_doc = {
        "name": "Payload Catalog",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": MIRROR_URL,
        "icons_url": "https://theeteempire.github.io/repository-catalog/icons.json",
        "payloads": payloads,
    }
    (OUT_DIR / "repositories.json").write_text(
        json.dumps(index_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "payloads_v2.json").write_text(
        json.dumps(pldmgr_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    icon_json = json.dumps({"icons": icons}, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(icon_json.encode("utf-8")) >= 4 * 1024 * 1024:
        print("ERROR: optimized icon catalog still exceeds PLDMGR's 4 MiB limit.", file=sys.stderr)
        return 5
    (OUT_DIR / "icons.json").write_text(icon_json, encoding="utf-8")

    print(f"Repositories indexed: {len(repositories)}")
    print(f"Direct ELF payload entries retained from curated mirror: {len(payloads) - discovered}")
    print(f"Additional direct ELF release assets discovered: {discovered}")
    print(f"Duplicate/PS4-only entries removed: {removed_duplicates}")
    print(f"Existing curated payloads refreshed from newer releases: {refreshed}")
    print(f"Repositories checked through GitHub Releases API: {checked}")
    print(f"Icon records available: {len(icons)}")
    print(f"Optimized icon catalog size: {len(icon_json.encode('utf-8'))} bytes")
    print("Every payload URL points to a direct .elf asset, not a repository page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
