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
USER_AGENT = "PS5-Repository-Catalog/2.0"
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
    """Extract the canonical repository URL from GitHub repo, tree, or release links."""
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



def request_bytes(url: str, *, accept: str = "application/json", timeout: int = 45) -> bytes:
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


def get_latest_release(full_name: str) -> dict[str, Any] | None:
    url = f"{API_ROOT}/repos/{full_name}/releases/latest"
    try:
        data = download_json(url)
        return data if isinstance(data, dict) else None
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
    if not owner_avatar_url.startswith("https://"):
        return ""
    try:
        raw = request_bytes(owner_avatar_url, accept="image/*", timeout=20)
        if not raw:
            return ""
        key = hashlib.sha256(raw).hexdigest()
        mime = mimetypes.guess_type(owner_avatar_url.split("?")[0])[0] or "image/png"
        normalized = normalize_icon_data(f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}")
        if not normalized:
            return ""
        icons.setdefault(key, normalized)
        return key
    except Exception as exc:
        print(f"NOTICE: could not fetch repository avatar: {exc}", file=sys.stderr)
        return ""


def main() -> int:
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
                record["icon_key"] = add_avatar_icon(avatar_url, icons) if avatar_url else ""
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
            record["icon_key"] = add_avatar_icon(avatar_url, icons) if avatar_url else ""

        # Poll release metadata for existing curated entries too, so the mirror feed
        # is not the sole source of truth for new versions.
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
                "category": category if category != "Repositories" else "Utilities & Tools",
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

    if not payloads:
        print("ERROR: no direct ELF assets found; refusing to publish empty PLDMGR feed.", file=sys.stderr)
        return 4

    missing_repository_icons = [r.get("repository_url") for r in repositories if not r.get("icon_key") or r["icon_key"] not in icons]
    if missing_repository_icons:
        print(f"ERROR: {len(missing_repository_icons)} repositories have no valid icon; refusing to publish partial icon coverage. Examples: {missing_repository_icons[:10]}", file=sys.stderr)
        return 6
    for record in repositories:
        record.pop("_owner_avatar_url", None)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    index_doc = {
        "name": "PS5 Repository Catalog",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": SOURCE_URL,
        "count": len(repositories),
        "payload_count": len(payloads),
        "icons_url": "https://theeteempire.github.io/ps5-repository-catalog/icons.json",
        "repositories": repositories,
    }
    pldmgr_doc = {
        "name": "PS5 Payloads",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": MIRROR_URL,
        "icons_url": "https://theeteempire.github.io/ps5-repository-catalog/icons.json",
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
    print(f"Existing curated payloads refreshed from newer releases: {refreshed}")
    print(f"Repositories checked through GitHub Releases API: {checked}")
    print(f"Icon records available: {len(icons)}")
    print(f"Optimized icon catalog size: {len(icon_json.encode('utf-8'))} bytes")
    print("Every payload URL points to a direct .elf asset, not a repository page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
