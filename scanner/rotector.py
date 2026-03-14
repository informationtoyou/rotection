"""
Rotector API helpers
"""

import threading
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.constants import VERIFICATION_SOURCES, WORKER_THREADS
from scanner.http import rotector_get, rotector_post


def get_tracked_users_for_group(group_id: int, log: Callable = print) -> list[dict]:
    users = []
    cursor = None
    page = 1
    while True:
        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        data = rotector_get(f"/v1/lookup/roblox/group/{group_id}/tracked-users", params)
        if not data or not data.get("success"):
            break
        page_users = data["data"].get("users", [])
        users.extend(page_users)
        total = data["data"].get("totalCount", "?")
        log(f"  Page {page}: got {len(page_users)} tracked users (total in group: {total})")
        if not data["data"].get("hasMore"):
            break
        cursor = data["data"].get("nextCursor")
        if not cursor:
            break
        page += 1
    return users


def batch_lookup_users(user_ids: list[int], log: Callable = print) -> dict:
    """Batch endpoint — threaded, looks up flag info for up to 100 users per request."""
    results = {}
    if not user_ids:
        return results
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    results_lock = threading.Lock()

    def _fetch_chunk(idx, chunk):
        log(f"  Batch lookup {idx + 1}/{len(chunks)} ({len(chunk)} users)...")
        data = rotector_post("/v1/lookup/roblox/user", {"ids": chunk})
        if data and data.get("success"):
            with results_lock:
                for uid_str, info in data["data"].items():
                    results[uid_str] = info

    with ThreadPoolExecutor(max_workers=min(WORKER_THREADS, len(chunks))) as executor:
        futures = [executor.submit(_fetch_chunk, i, chunk) for i, chunk in enumerate(chunks)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    return results


def get_discord_ids_for_user(roblox_id: int) -> dict:
    data = rotector_get(f"/v1/lookup/roblox/user/{roblox_id}/discord")
    if not data or not data.get("success"):
        return {"discord_ids": [], "alt_accounts": []}

    discord_ids = []
    for acc in data["data"].get("discordAccounts", []):
        did = acc.get("id")
        if did:
            sources = [VERIFICATION_SOURCES.get(s, f"Unknown({s})") for s in acc.get("sources", [])]
            discord_ids.append({
                "id": str(did),
                "sources": sources,
                "servers": acc.get("servers", []),
            })

    alts = []
    for alt in data["data"].get("altAccounts", []):
        alts.append({
            "robloxUserId": alt.get("robloxUserId"),
            "robloxUsername": alt.get("robloxUsername", "Unknown"),
        })

    return {"discord_ids": discord_ids, "alt_accounts": alts}
