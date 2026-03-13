"""
Fetches and caches SEA Military affiliates (allies + enemies) from the Roblox API.
Excludes CFront Interactive.  Refreshes in the background so startup isn't blocked.
"""

import threading
import time
import logging

from scanner.roblox import get_allied_groups, get_enemy_groups

log = logging.getLogger(__name__)

SEA_MILITARY_GROUP_ID = 2648601
CFRONT_INTERACTIVE_ID = 10958729
CACHE_TTL = 3600  # 1 hour

_lock = threading.Lock()
_affiliates: list[dict] = []
_last_fetched: float = 0.0
_loading: bool = False


def _fetch() -> list[dict]:
    """Hit the Roblox API for allies + enemies of SEA Military."""
    try:
        allies = get_allied_groups(SEA_MILITARY_GROUP_ID)
        enemies = get_enemy_groups(SEA_MILITARY_GROUP_ID)
    except Exception as exc:
        log.warning("Failed to fetch affiliates from Roblox API: %s", exc)
        return []

    seen: set[int] = set()
    result: list[dict] = []

    # always include SEA Military itself
    result.append({"id": SEA_MILITARY_GROUP_ID, "name": "SEA Military", "memberCount": 0, "relationship": "self"})
    seen.add(SEA_MILITARY_GROUP_ID)

    for g in allies:
        gid = g["id"]
        if gid == CFRONT_INTERACTIVE_ID or gid in seen:
            continue
        seen.add(gid)
        result.append({
            "id": gid,
            "name": g.get("name", f"Group {gid}"),
            "memberCount": g.get("memberCount", 0),
            "relationship": "ally",
        })

    for g in enemies:
        gid = g["id"]
        if gid == CFRONT_INTERACTIVE_ID or gid in seen:
            continue
        seen.add(gid)
        result.append({
            "id": gid,
            "name": g.get("name", f"Group {gid}"),
            "memberCount": g.get("memberCount", 0),
            "relationship": "enemy",
        })

    result.sort(key=lambda x: x["name"].lower())
    return result


def _background_refresh():
    """Runs in a daemon thread to populate the cache without blocking startup."""
    global _affiliates, _last_fetched, _loading
    try:
        data = _fetch()
        if data:
            with _lock:
                _affiliates = data
                _last_fetched = time.time()
            log.info("Loaded %d SEA affiliates from Roblox API", len(data))
        else:
            log.warning("Roblox API returned no affiliates — cache unchanged")
    finally:
        with _lock:
            _loading = False


def get_sea_affiliates() -> list[dict]:
    """Return cached affiliates.  Triggers a background refresh if stale or empty."""
    global _loading
    with _lock:
        stale = (time.time() - _last_fetched) > CACHE_TTL
        need_refresh = (not _affiliates or stale) and not _loading

    if need_refresh:
        with _lock:
            _loading = True
        t = threading.Thread(target=_background_refresh, daemon=True)
        t.start()

    with _lock:
        return list(_affiliates)


def get_affiliate_ids() -> set[int]:
    """Return the set of valid affiliate group IDs."""
    return {a["id"] for a in get_sea_affiliates()}


def is_affiliates_loaded() -> bool:
    """True once the first fetch has completed successfully."""
    with _lock:
        return len(_affiliates) > 0


def is_affiliates_loading() -> bool:
    """True while a background fetch is in progress."""
    with _lock:
        return _loading


def init_affiliates():
    """Kick off the initial background fetch.  Call once at app startup."""
    global _loading
    with _lock:
        if _loading or _affiliates:
            return
        _loading = True
    t = threading.Thread(target=_background_refresh, daemon=True)
    t.start()
