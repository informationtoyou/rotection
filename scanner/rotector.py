"""
Rotector API helpers
"""

import json
import os
import sqlite3
import threading
import time
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.constants import (
    DISCORD_LOOKUP_CACHE_TTL_SECONDS, PROJECT_ROOT, VERIFICATION_SOURCES, WORKER_THREADS
)
from scanner.http import rotector_get, rotector_post

DISCORD_LOOKUP_CACHE_DB = os.path.join(PROJECT_ROOT, "discord_lookup_cache.db")
_cache_local = threading.local()
_cache_init_lock = threading.Lock()
_cache_ready = False


def _get_cache_conn() -> sqlite3.Connection:
    conn = getattr(_cache_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DISCORD_LOOKUP_CACHE_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _cache_local.conn = conn
    _init_discord_cache(conn)
    return conn


def _init_discord_cache(conn: sqlite3.Connection) -> None:
    global _cache_ready
    if _cache_ready:
        return
    with _cache_init_lock:
        if _cache_ready:
            return
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_lookup_cache (
                roblox_id TEXT PRIMARY KEY,
                fetched_at INTEGER NOT NULL,
                data TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discord_lookup_fetched_at ON discord_lookup_cache(fetched_at)")
        if DISCORD_LOOKUP_CACHE_TTL_SECONDS > 0:
            conn.execute(
                "DELETE FROM discord_lookup_cache WHERE fetched_at < ?",
                (int(time.time()) - DISCORD_LOOKUP_CACHE_TTL_SECONDS,),
            )
        conn.commit()
        _cache_ready = True


def _load_cached_discord_results(roblox_ids: list[str]) -> dict[str, dict]:
    if not roblox_ids or DISCORD_LOOKUP_CACHE_TTL_SECONDS <= 0:
        return {}
    cutoff = int(time.time()) - DISCORD_LOOKUP_CACHE_TTL_SECONDS
    cached = {}
    conn = _get_cache_conn()
    for start in range(0, len(roblox_ids), 900):
        chunk = roblox_ids[start:start + 900]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""SELECT roblox_id, data
                FROM discord_lookup_cache
                WHERE fetched_at >= ? AND roblox_id IN ({placeholders})""",
            [cutoff, *chunk],
        ).fetchall()
        for row in rows:
            try:
                cached[row["roblox_id"]] = json.loads(row["data"])
            except (TypeError, json.JSONDecodeError):
                pass
    return cached


def _store_cached_discord_result(roblox_id: str, result: dict) -> None:
    if DISCORD_LOOKUP_CACHE_TTL_SECONDS <= 0:
        return
    fetched_at = int(time.time())
    conn = _get_cache_conn()
    conn.execute(
        """INSERT OR REPLACE INTO discord_lookup_cache (roblox_id, fetched_at, data)
           VALUES (?, ?, ?)""",
        (roblox_id, fetched_at, json.dumps(result, separators=(",", ":"), default=str)),
    )
    conn.execute(
        "DELETE FROM discord_lookup_cache WHERE fetched_at < ?",
        (fetched_at - DISCORD_LOOKUP_CACHE_TTL_SECONDS,),
    )
    conn.commit()


def _store_cached_discord_results(results_by_id: dict[str, dict]) -> None:
    if DISCORD_LOOKUP_CACHE_TTL_SECONDS <= 0 or not results_by_id:
        return
    fetched_at = int(time.time())
    rows = [
        (uid, fetched_at, json.dumps(result, separators=(",", ":"), default=str))
        for uid, result in results_by_id.items()
    ]
    conn = _get_cache_conn()
    conn.executemany(
        """INSERT OR REPLACE INTO discord_lookup_cache (roblox_id, fetched_at, data)
           VALUES (?, ?, ?)""",
        rows,
    )
    conn.execute(
        "DELETE FROM discord_lookup_cache WHERE fetched_at < ?",
        (fetched_at - DISCORD_LOOKUP_CACHE_TTL_SECONDS,),
    )
    conn.commit()


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


def batch_lookup_users(user_ids: list[int], log: Callable = print,
                       progress_callback: Callable[[int], None] | None = None) -> dict:
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
        return len(chunk)

    with ThreadPoolExecutor(max_workers=min(WORKER_THREADS, len(chunks))) as executor:
        futures = {
            executor.submit(_fetch_chunk, i, chunk): len(chunk)
            for i, chunk in enumerate(chunks)
        }
        for f in as_completed(futures):
            completed = futures[f]
            try:
                completed = f.result()
            except Exception:
                pass
            if progress_callback:
                progress_callback(completed)

    return results


def _fetch_discord_ids_for_user(roblox_id: int) -> dict | None:
    data = rotector_get(f"/v1/lookup/roblox/user/{roblox_id}/discord")
    if data is None:
        return None
    if not data.get("success"):
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


def get_discord_ids_for_user(roblox_id: int, use_cache: bool = True) -> dict:
    uid = str(roblox_id)
    if use_cache:
        cached = _load_cached_discord_results([uid])
        if uid in cached:
            return cached[uid]

    result = _fetch_discord_ids_for_user(roblox_id)
    if result is None:
        return {"discord_ids": [], "alt_accounts": []}
    if use_cache:
        _store_cached_discord_result(uid, result)
    return result


def batch_get_discord_ids_for_users(
    roblox_ids: list[int],
    log: Callable = print,
    max_workers: int = WORKER_THREADS,
    progress_callback: Callable[[int], None] | None = None,
) -> dict[str, dict]:
    """Resolve Discord links for many Roblox IDs with a 24h-bounded local cache."""
    unique_ids = list(dict.fromkeys(str(uid) for uid in roblox_ids if uid))
    if not unique_ids:
        return {}

    results = _load_cached_discord_results(unique_ids)
    cached_count = len(results)
    if cached_count:
        log(f"  Discord cache hit: {cached_count}/{len(unique_ids)} users")
        if progress_callback:
            progress_callback(cached_count)

    missing_ids = [uid for uid in unique_ids if uid not in results]
    if not missing_ids:
        return results

    results_lock = threading.Lock()

    def _fetch(uid: str):
        result = _fetch_discord_ids_for_user(int(uid))
        if result is None:
            result = {"discord_ids": [], "alt_accounts": []}
        return uid, result

    fetched_results = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(missing_ids))) as executor:
        futures = {executor.submit(_fetch, uid): uid for uid in missing_ids}
        completed = 0
        for future in as_completed(futures):
            uid = futures[future]
            try:
                uid, result = future.result()
            except Exception as exc:
                log(f"  Warning: Discord lookup failed for Roblox {uid}: {exc}")
                result = {"discord_ids": [], "alt_accounts": []}
            with results_lock:
                results[uid] = result
                fetched_results[uid] = result
                completed += 1
            if progress_callback:
                progress_callback(1)
            if completed % 250 == 0:
                log(f"  Discord lookups fetched: {completed}/{len(missing_ids)} uncached users")

    _store_cached_discord_results(fetched_results)
    return results
