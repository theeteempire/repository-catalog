#!/usr/bin/env python3
"""Add concise, plain-text metadata summaries and a rolling catalog changelog."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEED_PATH = Path("payloads_v2.json")
CHANGELOG_PATH = Path("changelog.json")
UNKNOWN = "Unknown"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def prior_feed() -> dict[str, Any]:
    try:
        raw = subprocess.run(
            ["git", "show", "HEAD:payloads_v2.json"],
            check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def compact_count(value: Any) -> str:
    """Format large counts compactly for the PLDMGR description line."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return UNKNOWN
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 10_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:,}"


def summary(payload: dict[str, Any]) -> str:
    original = payload.get("original_description")
    if not isinstance(original, str) or not original.strip():
        original = payload.get("description")
    original = original.strip() if isinstance(original, str) else ""
    if not original:
        original = "PS5 payload"

    stars = payload.get("github_stars")
    downloads = payload.get("download_count")
    last_update = payload.get("last_update")

    stars_label = str(stars) if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0 else UNKNOWN
    metadata = [f"⭐ {stars_label}", f"📥 {compact_count(downloads)}"]

    # Only show a real, parseable update date supplied by the catalog source.
    if isinstance(last_update, str) and last_update.strip():
        try:
            update_date = datetime.strptime(last_update.strip(), "%Y-%m-%d").date()
            metadata.append(f"🕒 {update_date.isoformat()}")
        except ValueError:
            pass

    # Put compact gaming metadata first; omit firmware because it is often unknown.
    return " · ".join(metadata) + " | " + original


def main() -> None:
    feed = read_json(FEED_PATH)
    payloads = feed.get("payloads")
    if not isinstance(payloads, list):
        raise SystemExit("payloads_v2.json has no payloads array")

    previous = prior_feed()
    previous_items = previous.get("payloads", []) if isinstance(previous.get("payloads"), list) else []
    previous_by_id = {
        str(item.get("id")): item for item in previous_items
        if isinstance(item, dict) and item.get("id")
    }
    current_ids: set[str] = set()
    now = datetime.now(timezone.utc)
    added, updated, removed = [], [], []

    for item in payloads:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("url") or item.get("name") or "")
        current_ids.add(item_id)
        if "original_description" not in item:
            desc = item.get("description")
            item["original_description"] = desc if isinstance(desc, str) else ""
        old = previous_by_id.get(item_id)
        if old is None:
            added.append({"id": item_id, "name": item.get("name", ""), "url": item.get("url", "")})
        elif any(old.get(k) != item.get(k) for k in ("version", "last_update", "url", "checksum")):
            updated.append({"id": item_id, "name": item.get("name", ""), "version": item.get("version", "")})
        item["description"] = summary(item)

    for item_id, item in previous_by_id.items():
        if item_id not in current_ids:
            removed.append({"id": item_id, "name": item.get("name", ""), "url": item.get("url", "")})

    FEED_PATH.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changelog = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "summary": {"added": len(added), "updated": len(updated), "removed": len(removed)},
        "changes": {"added": added, "updated": updated, "removed": removed},
    }
    CHANGELOG_PATH.write_text(json.dumps(changelog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added summaries to {len(payloads)} payloads; changelog: +{len(added)} ~{len(updated)} -{len(removed)}")


if __name__ == "__main__":
    main()
