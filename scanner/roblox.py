"""
Roblox API helpers
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.constants import (
    ROBLOX_GROUPS_API, ROBLOX_USERS_API, ROBLOX_THUMBNAILS_API, WORKER_THREADS,
)
from scanner.http import roblox_get, roblox_post


def get_group_info(group_id: int) -> dict | None:
    return roblox_get(f"{ROBLOX_GROUPS_API}/v1/groups/{group_id}")


def get_allied_groups(group_id: int) -> list[dict]:
    return _get_related_groups(group_id, "allies")


def get_enemy_groups(group_id: int) -> list[dict]:
    return _get_related_groups(group_id, "enemies")


def _get_related_groups(group_id: int, relationship: str) -> list[dict]:
    groups = []
    cursor = None
    while True:
        params = {"limit": 100, "sortOrder": "Asc",
                  "model.startRowIndex": 0, "model.maxRows": 100}
        if cursor:
            params["cursor"] = cursor
        data = roblox_get(
            f"{ROBLOX_GROUPS_API}/v1/groups/{group_id}/relationships/{relationship}",
            params,
        )
        if not data:
            break
        for g in data.get("relatedGroups", []):
            groups.append({
                "id": g["id"],
                "name": g.get("name", f"Group {g['id']}"),
                "memberCount": g.get("memberCount", 0),
            })
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    return groups


def get_user_info(user_id: int) -> dict | None:
    data = roblox_get(f"{ROBLOX_USERS_API}/v1/users/{user_id}")
    if data:
        return {
            "name": data.get("name", "Unknown"),
            "displayName": data.get("displayName", ""),
        }
    return None


def batch_get_user_info(user_ids: list[int]) -> dict:
    results = {}
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    results_lock = threading.Lock()

    def _fetch_chunk(chunk):
        data = roblox_post(
            f"{ROBLOX_USERS_API}/v1/users",
            {"userIds": chunk, "excludeBannedUsers": False},
        )
        if data:
            with results_lock:
                for u in data.get("data", []):
                    results[str(u["id"])] = {
                        "name": u.get("name", "Unknown"),
                        "displayName": u.get("displayName", ""),
                    }

    with ThreadPoolExecutor(max_workers=min(WORKER_THREADS, len(chunks) or 1)) as executor:
        futures = [executor.submit(_fetch_chunk, chunk) for chunk in chunks]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    return results


def get_user_thumbnail(user_id: int) -> str | None:
    data = roblox_get(
        f"{ROBLOX_THUMBNAILS_API}/v1/users/avatar-headshot",
        params={"userIds": user_id, "size": "48x48", "format": "Png"},
    )
    if data and data.get("data"):
        return data["data"][0].get("imageUrl")
    return None
