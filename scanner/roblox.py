"""
Roblox API helpers
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.constants import (
    ROBLOX_GROUPS_API, ROBLOX_USERS_API, ROBLOX_THUMBNAILS_API, WORKER_THREADS,
    SEA_MILITARY_GROUP_ID, SEA_HRHC_PREFIXES,
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


def get_sea_hrhc_user_ids(log=print) -> set:
    """Fetch all user IDs that hold an HR/HC rank in SEA Military.
    Uses the roles endpoint: 1 call for roles list + 1 call per matching role."""
    hrhc_ids = set()
    roles_data = roblox_get(f"{ROBLOX_GROUPS_API}/v1/groups/{SEA_MILITARY_GROUP_ID}/roles")

    if not roles_data or "roles" not in roles_data:
        log("  ⚠ Could not fetch SEA Military roles (empty response)")
        return hrhc_ids

    matching_roles = []
    for role in roles_data["roles"]:
        role_name = role.get("name", "")
        if any(role_name.startswith(prefix) for prefix in SEA_HRHC_PREFIXES):
            matching_roles.append(role)

    if not matching_roles:
        log("  No HR/HC roles found in SEA Military role list")
        return hrhc_ids

    log(f"  Found {len(matching_roles)} HR/HC roles to check: {', '.join(r['name'] for r in matching_roles)}")

    for ri, role in enumerate(matching_roles):
        role_id = role["id"]
        role_name = role["name"]
        cursor = None
        pages = 0
        role_count = 0
        while True:
            params = {"limit": 100, "sortOrder": "Asc"}
            if cursor:
                params["cursor"] = cursor
            data = roblox_get(
                f"{ROBLOX_GROUPS_API}/v1/groups/{SEA_MILITARY_GROUP_ID}/roles/{role_id}/users",
                params,
            )
            if not data:
                break
            for u in data.get("data", []):
                hrhc_ids.add(u["userId"])
                role_count += 1
            cursor = data.get("nextPageCursor")
            pages += 1
            if not cursor or pages > 20:
                break
        log(f"    [{ri+1}/{len(matching_roles)}] {role_name}: {role_count} members ({pages} page(s))")

    return hrhc_ids


def get_user_group_roles(user_id: int) -> list[dict] | None:
    """Return the group-role list for a user, or None on error."""
    data = roblox_get(f"{ROBLOX_GROUPS_API}/v2/users/{user_id}/groups/roles")
    if not data or "data" not in data:
        return None
    return data.get("data", [])


def check_user_in_group(user_id: int, group_id: int) -> dict:
    """Check if user is in the given group and return role info if present."""
    roles = get_user_group_roles(user_id)
    if not roles:
        return {"in_group": False, "role": None, "role_id": None, "rank": None}
    for entry in roles:
        group = entry.get("group") or {}
        if group.get("id") == group_id:
            role = entry.get("role") or {}
            return {
                "in_group": True,
                "role": role.get("name"),
                "role_id": role.get("id"),
                "rank": role.get("rank"),
            }
    return {"in_group": False, "role": None, "role_id": None, "rank": None}


def batch_check_group_membership(user_records: dict, log=print, max_workers: int = 10, progress=None) -> dict:
    """
    Check group membership for each user record (uses record's group_id).
    Returns dict keyed by uid_str -> membership info.
    """
    results = {}
    if not user_records:
        return results

    users = list(user_records.values())
    total = len(users)
    checked = 0
    results_lock = threading.Lock()

    def _check(u):
        uid = int(u["id"])
        gid = int(u.get("group_id") or 0)
        if gid <= 0:
            return str(uid), {"in_group": False, "role": None, "role_id": None, "rank": None}
        info = check_user_in_group(uid, gid)
        return str(uid), info

    with ThreadPoolExecutor(max_workers=min(max_workers, len(users))) as executor:
        futures = {executor.submit(_check, u): u for u in users}
        for f in as_completed(futures):
            try:
                uid_str, info = f.result()
                with results_lock:
                    results[uid_str] = info
                    checked += 1
                    if progress:
                        progress.users_checked = checked
                if checked % 50 == 0:
                    log(f"  Membership checked: {checked}/{total}")
            except Exception:
                pass

    return results
