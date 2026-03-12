"""
JSON file cache setup
"""

import json
import os

from scanner.constants import CACHE_FILE


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"scans": [], "groups": {}}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, separators=(",", ":"), default=str)


def get_previous_scans() -> list[dict]:
    cache = load_cache()
    scans = cache.get("scans", [])
    summaries = []
    for s in reversed(scans):
        summaries.append({
            "id": s.get("id", ""),
            "timestamp": s.get("timestamp", ""),
            "primary_group": s.get("primary_group_name", "Unknown"),
            "primary_group_id": s.get("primary_group_id", 0),
            "include_allies": s.get("include_allies", False),
            "groups_scanned": len(s.get("groups", {})),
            "total_flagged": s.get("total_flagged", 0),
            "total_discord_ids": s.get("total_discord_ids", 0),
        })
    return summaries


def get_scan_by_id(scan_id: str) -> dict | None:
    cache = load_cache()
    for s in cache.get("scans", []):
        if s.get("id") == scan_id:
            return s
    return None
