#!/usr/bin/env python3
"""Generate a repository index and a direct-download PLDMGR payload catalog.

Only genuine release assets (ELF files) are emitted as installable payloads.
Repository pages remain in repositories.json and are never disguised as binaries.
"""
from __future__ import annotations

import base64
import hashlib
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
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.match(r"^https://github\.com/[^/\s]+/[^/\s?#]+/?$", value, re.I):
        return None
    return value.rstrip("/")


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

    # Normalize display-only metadata; never invent a checksum or binary URL.
    return {
        "name": name,
        "description": description,
        "repository_url": url,
        "category": category,
        "author": author or "",
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


def add_avatar_icon(owner_avatar_url: str, icons: dict[str, str]) -> str:
    if not owner_avatar_url.startswith("https://"):
        return ""
    try:
        raw = request_bytes(owner_avatar_url, accept="image/*", timeout=20)
        if not raw:
            return ""
        key = hashlib.sha256(raw).hexdigest()
        mime = mimetypes.guess_type(owner_avatar_url.split("?")[0])[0] or "image/png"
        icons.setdefault(key, f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}")
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
    checked = 0
    for record in repositories:
        full_name = canonical_repo(record["repository_url"])
        if not full_name:
            continue
        repo_key = full_name.lower()
        if repo_key in payload_by_repo:
            match = payload_by_repo[repo_key]
            record["payload_available"] = True
            for src, dst in (
                ("version", "version"), ("last_update", "last_update"),
                ("icon_key", "icon_key"), ("filename", "payload_filename"),
                ("url", "payload_url"), ("checksum", "checksum"),
            ):
                if isinstance(match.get(src), str) and match[src].strip():
                    record[dst] = match[src]
            continue

        checked += 1
        release = get_latest_release(full_name)
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
        description = str(record.get("description") or release.get("body") or "").strip()
        category = str(record.get("category") or "Utilities & Tools")
        owner = release.get("author") if isinstance(release.get("author"), dict) else {}
        avatar = owner.get("avatar_url", "") if isinstance(owner, dict) else ""
        icon_key = add_avatar_icon(avatar, icons) if avatar else ""

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

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    index_doc = {
        "name": "PS5 Repository Catalog",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": SOURCE_URL,
        "count": len(repositories),
        "payload_count": len(payloads),
        "icons_url": "icons.json",
        "repositories": repositories,
    }
    pldmgr_doc = {
        "name": "PS5 Payloads",
        "schema_version": 2,
        "generated_at": generated_at,
        "source": MIRROR_URL,
        "icons_url": "icons.json",
        "payloads": payloads,
    }
    (OUT_DIR / "repositories.json").write_text(
        json.dumps(index_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "payloads_v2.json").write_text(
        json.dumps(pldmgr_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "icons.json").write_text(
        json.dumps({"icons": icons}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8"
    )

    print(f"Repositories indexed: {len(repositories)}")
    print(f"Direct ELF payload entries retained from curated mirror: {len(payloads) - discovered}")
    print(f"Additional direct ELF release assets discovered: {discovered}")
    print(f"Repositories checked through GitHub Releases API: {checked}")
    print(f"Icon records available: {len(icons)}")
    print("Every payload URL points to a direct .elf asset, not a repository page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
