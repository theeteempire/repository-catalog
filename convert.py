#!/usr/bin/env python3
"""Convert the Nexgen PS5 repository database to a PLDMGR-shaped catalog.

Important:
- This preserves every repository entry that has a real repository URL.
- Repositories without a direct payload binary are display-only entries:
  `url` points to the repository page, so attempting to download it as a payload
  will not work. The companion repositories.json is the accurate full index.
- No checksums, release assets, or download URLs are fabricated.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_URL = (
    "https://raw.githubusercontent.com/nexgen999/PS5-Repository-List/"
    "main/json/repos-database.json"
)
OUT_DIR = Path(".")
USER_AGENT = "PS5-Repository-List-PLDMGR-Converter/1.0"

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


def main() -> int:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read()
    except Exception as exc:
        print(f"ERROR: could not download source database: {exc}", file=sys.stderr)
        return 1

    try:
        source_data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: source did not contain valid JSON: {exc}", file=sys.stderr)
        return 1

    # Deduplicate by canonical repository URL while preserving source order.
    repositories = []
    seen = set()
    for obj in walk_objects(source_data):
        record = repository_record(obj)
        if not record:
            continue
        key = record["repository_url"].lower()
        if key in seen:
            continue
        seen.add(key)
        repositories.append(record)

    if not repositories:
        print(
            "ERROR: no repository records with explicit GitHub URLs were found. "
            "The source schema may have changed; inspect the source before publishing.",
            file=sys.stderr,
        )
        return 2

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Accurate all-repositories index. This is the correct file for browsing
    # repositories, including those that do not publish a direct payload binary.
    index_doc = {
        "name": "PS5 Repository List — all repositories",
        "source": SOURCE_URL,
        "generated_at": generated_at,
        "count": len(repositories),
        "repositories": repositories,
    }
    (OUT_DIR / "repositories.json").write_text(
        json.dumps(index_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # PLDMGR requires a payload `name`, `filename`, and HTTP(S) `url`.
    # For repos with no known binary, the repo page is used as URL only to make
    # the entry visible; filename is the repository name (not a real binary).
    # These entries are display-only; download/install cannot work until a
    # genuine direct binary URL and exact filename are supplied.
    payloads = []
    for record in repositories:
        name = record["name"]
        entry = {
            "id": re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or "repository",
            "name": name,
            "filename": name,
            "url": record["repository_url"],
            "source": record["repository_url"],
            "description": record["description"],
            "category": record["category"],
        }
        if record["author"]:
            entry["author"] = record["author"]
        payloads.append(entry)

    pldmgr_doc = {
        "name": "PS5 Repository List (repository links; not all are downloadable payloads)",
        "payloads": payloads,
    }
    (OUT_DIR / "payloads_v2.json").write_text(
        json.dumps(pldmgr_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated repositories.json with {len(repositories)} repositories.")
    print(f"Generated payloads_v2.json with {len(payloads)} PLDMGR-shaped entries.")
    print("Note: entries without a real binary URL are display-only and cannot be downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
