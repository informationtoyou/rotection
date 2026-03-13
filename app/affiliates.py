"""
Fetches and caches SEA Military affiliates (allies + enemies) from the Roblox API.
Excludes CFront Interactive.  Refreshes in the background so startup isn't blocked.
Persists to disk so restarts don't require a fresh fetch.
"""

import json
import os
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.roblox import get_allied_groups, get_enemy_groups

log = logging.getLogger(__name__)

SEA_MILITARY_GROUP_ID = 2648601
CFRONT_INTERACTIVE_ID = 10958729
CACHE_TTL = 3600  # 1 hour
DISK_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "affiliates_cache.json")

_lock = threading.Lock()
_affiliates: list[dict] = []
_last_fetched: float = 0.0
_loading: bool = False


# ──────────────────── Disk cache ────────────────────

def _load_disk_cache() -> tuple[list[dict], float]:
    """Load affiliates from disk cache. Returns (affiliates, timestamp)."""
    try:
        if os.path.exists(DISK_CACHE_PATH):
            with open(DISK_CACHE_PATH, "r") as f:
                data = json.load(f)
            return data.get("affiliates", []), data.get("fetched_at", 0.0)
    except (json.JSONDecodeError, IOError, KeyError) as exc:
        log.warning("Failed to read affiliates disk cache: %s", exc)
    return [], 0.0


def _save_disk_cache(affiliates: list[dict], fetched_at: float):
    """Persist affiliates to disk."""
    try:
        with open(DISK_CACHE_PATH, "w") as f:
            json.dump({"affiliates": affiliates, "fetched_at": fetched_at}, f, separators=(",", ":"))
    except IOError as exc:
        log.warning("Failed to write affiliates disk cache: %s", exc)


# ──────────────────── Fetch ────────────────────

def _fetch() -> list[dict]:
    """Hit the Roblox API for allies + enemies of SEA Military in parallel."""
    allies = []
    enemies = []

    def _get_allies():
        nonlocal allies
        try:
            allies = get_allied_groups(SEA_MILITARY_GROUP_ID)
        except Exception as exc:
            log.warning("Failed to fetch allies: %s", exc)

    def _get_enemies():
        nonlocal enemies
        try:
            enemies = get_enemy_groups(SEA_MILITARY_GROUP_ID)
        except Exception as exc:
            log.warning("Failed to fetch enemies: %s", exc)

    # fetch allies and enemies in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_get_allies), executor.submit(_get_enemies)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    if not allies and not enemies:
        log.warning("Both ally and enemy fetches returned empty")
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
            now = time.time()
            with _lock:
                _affiliates = data
                _last_fetched = now
            _save_disk_cache(data, now)
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
    """Kick off the initial background fetch.  Call once at app startup.
    Loads disk cache first for instant availability."""
    global _affiliates, _last_fetched, _loading

    # load disk cache first — instant availability
    cached, cached_at = _load_disk_cache()
    if cached:
        with _lock:
            _affiliates = cached
            _last_fetched = cached_at
        log.info("Restored %d affiliates from disk cache (age: %ds)",
                 len(cached), int(time.time() - cached_at))

    # if disk cache is stale or empty, refresh in background
    with _lock:
        stale = (time.time() - _last_fetched) > CACHE_TTL
        if (not _affiliates or stale) and not _loading:
            _loading = True
            t = threading.Thread(target=_background_refresh, daemon=True)
            t.start()
