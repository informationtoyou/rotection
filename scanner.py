"""
Scanner engine for Rotection v3.0
Handles all Roblox + Rotector API calls, caching, and background scanning.
Uses thread pools for parallel API work where possible.
"""

import requests
import time
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections import deque
from typing import Callable
from dotenv import load_dotenv

load_dotenv()
API_KEY_HEADER = os.getenv("API_KEY_HEADER")

# -- endpoints --
ROTECTOR_BASE = "https://roscoe.rotector.com"
ROBLOX_GROUPS_API = "https://groups.roblox.com"
ROBLOX_USERS_API = "https://users.roblox.com"
ROBLOX_THUMBNAILS_API = "https://thumbnails.roblox.com"

CACHE_FILE = "scan_cache.json"
FLAGGED_FILE = "flagged.txt"

# rotector allows 50 req / 10s - but i have an api key!
RATE_LIMIT = 500
RATE_WINDOW = 10

# how many threads to use for parallel API work
WORKER_THREADS = 50

MAX_RETRIES = 5

FLAG_TYPES = {
    0: {"name": "Unflagged", "actionable": False, "color": "#6b7280"},
    1: {"name": "Flagged", "actionable": True, "color": "#ef4444"},
    2: {"name": "Confirmed", "actionable": True, "color": "#dc2626"},
    3: {"name": "Queued", "actionable": False, "color": "#f59e0b"},
    5: {"name": "Mixed", "actionable": False, "color": "#f97316"},
    6: {"name": "Past Offender", "actionable": False, "color": "#8b5cf6"},
}

VERIFICATION_SOURCES = {0: "Bloxlink", 1: "RoVer", 2: "Discord Profile"}


# -- rate limiter (thread-safe) --
class RateLimiter:
    def __init__(self, max_requests: int = RATE_LIMIT, window: float = RATE_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self):
        while True:
            sleep_time = 0.0
            with self._lock:
                now = time.time()
                while self._timestamps and self._timestamps[0] < now - self.window:
                    self._timestamps.popleft()
                if len(self._timestamps) >= self.max_requests:
                    sleep_time = self._timestamps[0] + self.window - now + 0.05
                else:
                    self._timestamps.append(now)
                    return
            # sleep OUTSIDE the lock so other threads aren't blocked
            if sleep_time > 0:
                time.sleep(sleep_time)


rotector_limiter = RateLimiter(RATE_LIMIT, RATE_WINDOW)
roblox_limiter = RateLimiter(80, 10)

# -- persistent sessions for connection reuse (HTTP keep-alive) --
_rotector_session = requests.Session()
_rotector_session.headers.update({"X-Auth-Token": API_KEY_HEADER or ""})
_rotector_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=WORKER_THREADS, pool_maxsize=WORKER_THREADS, max_retries=0
))
_roblox_session = requests.Session()
_roblox_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=WORKER_THREADS, pool_maxsize=WORKER_THREADS, max_retries=0
))


# -- http helpers (loop-based retries, no recursion) --
def _rotector_get(path: str, params: dict | None = None) -> dict | None:
    url = f"{ROTECTOR_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        rotector_limiter.wait()
        try:
            resp = _rotector_session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


def _rotector_post(path: str, json_body: dict) -> dict | None:
    url = f"{ROTECTOR_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        rotector_limiter.wait()
        try:
            resp = _rotector_session.post(url, json=json_body, timeout=30)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


def _roblox_get(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(MAX_RETRIES):
        roblox_limiter.wait()
        try:
            resp = _roblox_session.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


def _roblox_post(url: str, json_body: dict) -> dict | None:
    """POST helper for Roblox APIs with rate limiting, 429 handling, and retries."""
    for attempt in range(MAX_RETRIES):
        roblox_limiter.wait()
        try:
            resp = _roblox_session.post(url, json=json_body, timeout=20)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


# -- roblox user info fallback --
def get_user_info_from_roblox(user_id: int) -> dict | None:
    data = _roblox_get(f"{ROBLOX_USERS_API}/v1/users/{user_id}")
    if data:
        return {
            "name": data.get("name", "Unknown"),
            "displayName": data.get("displayName", ""),
        }
    return None


def batch_get_user_info_from_roblox(user_ids: list[int]) -> dict:
    results = {}
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    results_lock = threading.Lock()

    def _fetch_chunk(chunk):
        data = _roblox_post(
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
    data = _roblox_get(
        f"{ROBLOX_THUMBNAILS_API}/v1/users/avatar-headshot",
        params={"userIds": user_id, "size": "48x48", "format": "Png"},
    )
    if data and data.get("data"):
        return data["data"][0].get("imageUrl")
    return None


# -- cache --
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


# -- roblox group helpers --
def get_group_info(group_id: int) -> dict | None:
    return _roblox_get(f"{ROBLOX_GROUPS_API}/v1/groups/{group_id}")


def get_allied_groups(group_id: int) -> list[dict]:
    allies = []
    cursor = None
    while True:
        params = {"limit": 100, "sortOrder": "Asc", "model.startRowIndex": 0, "model.maxRows": 100}
        if cursor:
            params["cursor"] = cursor
        data = _roblox_get(
            f"{ROBLOX_GROUPS_API}/v1/groups/{group_id}/relationships/allies",
            params,
        )
        if not data:
            break
        for g in data.get("relatedGroups", []):
            allies.append({
                "id": g["id"],
                "name": g.get("name", f"Group {g['id']}"),
                "memberCount": g.get("memberCount", 0),
            })
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    return allies


def get_enemy_groups(group_id: int) -> list[dict]:
    enemies = []
    cursor = None
    while True:
        params = {"limit": 100, "sortOrder": "Asc", "model.startRowIndex": 0, "model.maxRows": 100}
        if cursor:
            params["cursor"] = cursor
        data = _roblox_get(
            f"{ROBLOX_GROUPS_API}/v1/groups/{group_id}/relationships/enemies",
            params,
        )
        if not data:
            break
        for g in data.get("relatedGroups", []):
            enemies.append({
                "id": g["id"],
                "name": g.get("name", f"Group {g['id']}"),
                "memberCount": g.get("memberCount", 0),
            })
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    return enemies


# -- rotector helpers --
def get_tracked_users_for_group(group_id: int, log: Callable = print) -> list[dict]:
    users = []
    cursor = None
    page = 1
    while True:
        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        data = _rotector_get(f"/v1/lookup/roblox/group/{group_id}/tracked-users", params)
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
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    results_lock = threading.Lock()

    def _fetch_chunk(idx, chunk):
        log(f"  Batch lookup {idx + 1}/{len(chunks)} ({len(chunk)} users)...")
        data = _rotector_post("/v1/lookup/roblox/user", {"ids": chunk})
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
    data = _rotector_get(f"/v1/lookup/roblox/user/{roblox_id}/discord")
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


# -- progress tracker (thread-safe, read by the web UI) --
class ScanProgress:
    def __init__(self):
        self.lock = threading.Lock()
        self._cancel = threading.Event()
        self.status = "idle"
        self.phase = ""
        self.phase_description = ""
        self.logs: list[str] = []
        self.progress = 0.0
        self.current_group = ""
        self.groups_done = 0
        self.groups_total = 0
        self.users_checked = 0
        self.users_total = 0
        self.flagged_found = 0
        self.discord_ids_found = 0
        self.scan_id: str | None = None
        self.eta_seconds: float | None = None
        self.start_time: float | None = None

    def reset(self):
        """Safely reset all fields without replacing the lock."""
        with self.lock:
            self._cancel.clear()
            self.status = "idle"
            self.phase = ""
            self.phase_description = ""
            self.logs = []
            self.progress = 0.0
            self.current_group = ""
            self.groups_done = 0
            self.groups_total = 0
            self.users_checked = 0
            self.users_total = 0
            self.flagged_found = 0
            self.discord_ids_found = 0
            self.scan_id = None
            self.eta_seconds = None
            self.start_time = None

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def log(self, msg: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{ts}] {msg}")

    def set_phase(self, phase: str, description: str = ""):
        with self.lock:
            self.phase = phase
            self.phase_description = description

    def update_eta(self):
        with self.lock:
            if not self.start_time or self.progress <= 0:
                self.eta_seconds = None
                return
            elapsed = time.time() - self.start_time
            if self.progress >= 100:
                self.eta_seconds = 0
                return
            rate = elapsed / self.progress
            remaining = (100 - self.progress) * rate
            self.eta_seconds = remaining

    def to_dict(self, log_cursor: int = 0) -> dict:
        """Return state dict. log_cursor = index to slice logs from (only new logs)."""
        with self.lock:
            all_logs = self.logs
            new_logs = all_logs[log_cursor:] if log_cursor < len(all_logs) else []
            return {
                "status": self.status,
                "phase": self.phase,
                "phase_description": self.phase_description,
                "log_count": len(all_logs),
                "logs": new_logs,
                "progress": round(self.progress, 1),
                "current_group": self.current_group,
                "groups_done": self.groups_done,
                "groups_total": self.groups_total,
                "users_checked": self.users_checked,
                "users_total": self.users_total,
                "flagged_found": self.flagged_found,
                "discord_ids_found": self.discord_ids_found,
                "scan_id": self.scan_id,
                "eta_seconds": round(self.eta_seconds, 0) if self.eta_seconds is not None else None,
            }


# global state
scan_progress = ScanProgress()
_scan_thread: threading.Thread | None = None
_scan_lock = threading.Lock()


def is_scanning() -> bool:
    return scan_progress.status == "scanning"


def run_scan(primary_group_id: int, include_allies: bool = True, include_enemies: bool = False):
    global _scan_thread
    with _scan_lock:
        if is_scanning():
            return False
        scan_progress.reset()
        scan_progress.status = "scanning"
        _scan_thread = threading.Thread(
            target=_scan_worker, args=(primary_group_id, include_allies, include_enemies), daemon=True
        )
        _scan_thread.start()
        return True


def _scan_worker(primary_group_id: int, include_allies: bool, include_enemies: bool = False):
    p = scan_progress
    p.reset()
    p.status = "scanning"
    p.start_time = time.time()
    scan_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p.scan_id = scan_id

    try:
        # ---- phase 1: group discovery ----
        p.set_phase("Discovering groups", "Looking up the primary group and finding allies/enemies on Roblox")
        p.log(f"Target group: {primary_group_id}")

        primary_info = get_group_info(primary_group_id)
        primary_name = primary_info["name"] if primary_info else f"Group {primary_group_id}"
        p.log(f"  Name: {primary_name}")

        groups_to_scan = [{"id": primary_group_id, "name": primary_name, "is_primary": True}]
        seen_ids = {primary_group_id}

        # fetch allies and enemies in parallel if both are requested
        allies = []
        enemies = []
        fetch_tasks = {}
        if include_allies or include_enemies:
            with ThreadPoolExecutor(max_workers=2) as executor:
                if include_allies:
                    p.log("Fetching allied groups...")
                    fetch_tasks["allies"] = executor.submit(get_allied_groups, primary_group_id)
                if include_enemies:
                    p.log("Fetching enemy groups...")
                    fetch_tasks["enemies"] = executor.submit(get_enemy_groups, primary_group_id)

                if "allies" in fetch_tasks:
                    try:
                        allies = fetch_tasks["allies"].result()
                    except Exception:
                        allies = []
                if "enemies" in fetch_tasks:
                    try:
                        enemies = fetch_tasks["enemies"].result()
                    except Exception:
                        enemies = []

        if include_allies:
            p.log(f"  Found {len(allies)} allies")
            for a in allies:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    groups_to_scan.append({"id": a["id"], "name": a["name"], "is_primary": False})
                    p.log(f"    + {a['name']} ({a['memberCount']} members)")

        if include_enemies:
            p.log(f"  Found {len(enemies)} enemies")
            for e in enemies:
                if e["id"] not in seen_ids:
                    seen_ids.add(e["id"])
                    groups_to_scan.append({"id": e["id"], "name": e["name"], "is_primary": False})
                    p.log(f"    ⚔ {e['name']} ({e['memberCount']} members)")

        p.groups_total = len(groups_to_scan)
        p.progress = 5.0
        p.update_eta()

        # ---- phase 2: pull tracked users from each group (threaded) ----
        p.set_phase("Scanning groups", "Pulling tracked users from Rotector for each group (parallel)")
        all_user_records = {}
        group_results = {}
        group_scan_lock = threading.Lock()
        groups_done_counter = [0]

        def _scan_group(gi, group):
            gid = group["id"]
            gname = group["name"]
            p.log(f"[{gi + 1}/{len(groups_to_scan)}] Scanning {gname} (ID: {gid})")

            tracked = get_tracked_users_for_group(gid, log=p.log)
            p.log(f"  Tracked users in {gname}: {len(tracked)}")

            local_records = {}
            for u in tracked:
                uid = u["id"]
                uid_str = str(uid)
                local_records[uid_str] = {
                    "id": uid,
                    "name": u.get("name") or "",
                    "displayName": u.get("displayName") or "",
                    "thumbnailUrl": u.get("thumbnailUrl"),
                    "isActive": u.get("isActive", False),
                    "group_id": gid,
                    "group_name": gname,
                }

            local_group_result = {
                "name": gname,
                "is_primary": group["is_primary"],
                "tracked_count": len(tracked),
                "users": [str(u["id"]) for u in tracked],
            }

            with group_scan_lock:
                for uid_str, record in local_records.items():
                    if uid_str not in all_user_records:
                        all_user_records[uid_str] = record
                    else:
                        existing = all_user_records[uid_str]
                        if "all_groups" not in existing:
                            existing["all_groups"] = [{"id": existing["group_id"], "name": existing["group_name"]}]
                        existing["all_groups"].append({"id": gid, "name": gname})

                group_results[str(gid)] = local_group_result
                groups_done_counter[0] += 1
                done = groups_done_counter[0]

            p.current_group = gname
            p.groups_done = done
            p.progress = 5 + done / len(groups_to_scan) * 25
            p.flagged_found = len(all_user_records)
            p.update_eta()

        # use fewer workers for group scanning to avoid overwhelming the rotector API
        group_workers = min(WORKER_THREADS, len(groups_to_scan))
        with ThreadPoolExecutor(max_workers=group_workers) as executor:
            futures = [executor.submit(_scan_group, gi, group) for gi, group in enumerate(groups_to_scan)]
            for f in as_completed(futures):
                if p.cancelled:
                    p.log("Scan cancelled")
                    p.status = "cancelled"
                    return
                try:
                    f.result()
                except Exception as exc:
                    p.log(f"  Warning: group scan error: {exc}")

        p.users_total = len(all_user_records)
        p.log(f"Total unique tracked users: {len(all_user_records)}")

        # ---- phase 2.5: fill in missing usernames from roblox ----
        missing_names = [int(uid) for uid, rec in all_user_records.items() if not rec["name"] or rec["name"] == "Unknown"]
        if missing_names:
            p.set_phase("Resolving usernames", f"Fetching names for {len(missing_names)} users from Roblox")
            p.log(f"Fetching usernames for {len(missing_names)} users missing name data...")
            name_data = batch_get_user_info_from_roblox(missing_names)
            filled = 0
            for uid_str, info in name_data.items():
                if uid_str in all_user_records:
                    if not all_user_records[uid_str]["name"] or all_user_records[uid_str]["name"] == "Unknown":
                        all_user_records[uid_str]["name"] = info["name"]
                        filled += 1
                    if not all_user_records[uid_str]["displayName"]:
                        all_user_records[uid_str]["displayName"] = info["displayName"]
            p.log(f"  Filled in {filled} usernames from Roblox")

        # ---- phase 3: batch flag detail lookup (threaded) ----
        p.set_phase("Fetching flag details", "Looking up flag type, confidence, and reasons from Rotector")
        p.log("Batch-fetching flag details from Rotector...")

        all_ids = [int(uid) for uid in all_user_records.keys()]
        flag_details = batch_lookup_users(all_ids, log=p.log)

        for uid_str, details in flag_details.items():
            if uid_str in all_user_records:
                ft = details.get("flagType", 0)
                if isinstance(ft, str):
                    ft = int(ft)
                rec = all_user_records[uid_str]
                rec["flagType"] = ft
                rec["flagName"] = FLAG_TYPES.get(ft, {}).get("name", "Unknown")
                rec["flagColor"] = FLAG_TYPES.get(ft, {}).get("color", "#6b7280")
                rec["actionable"] = FLAG_TYPES.get(ft, {}).get("actionable", False)
                rec["confidence"] = details.get("confidence", 0)
                reasons = details.get("reasons", {})
                reason_list = []
                for reason_type, reason_data in reasons.items():
                    reason_list.append({
                        "type": reason_type,
                        "message": reason_data.get("message", ""),
                        "confidence": reason_data.get("confidence", 0),
                        "evidence": reason_data.get("evidence", []),
                    })
                rec["reasons"] = reason_list
                rec["lastUpdated"] = details.get("lastUpdated")

        p.progress = 55.0
        p.update_eta()

        # ---- phase 4: discord ID resolution (threaded) ----
        p.set_phase("Resolving Discord accounts", "Looking up linked Discord IDs. This is the slowest part, please be patient")
        p.log(f"Looking up Discord accounts ({WORKER_THREADS} threads)...")

        all_discord_ids = set()
        user_list = list(all_user_records.values())
        discord_lock = threading.Lock()
        checked_counter = [0]

        def _lookup_discord(user):
            uid = user["id"]
            discord_data = get_discord_ids_for_user(uid)
            dids = discord_data["discord_ids"]
            alts = discord_data["alt_accounts"]
            user["discord_accounts"] = dids
            user["alt_accounts"] = alts
            with discord_lock:
                for d in dids:
                    all_discord_ids.add(d["id"])
                checked_counter[0] += 1
                count = checked_counter[0]
            return uid, len(dids), count

        with ThreadPoolExecutor(max_workers=WORKER_THREADS) as executor:
            futures = {executor.submit(_lookup_discord, u): u for u in user_list}
            for future in as_completed(futures):
                if p.cancelled:
                    p.log("Scan cancelled")
                    p.status = "cancelled"
                    return

                try:
                    uid, n_dids, count = future.result()
                    p.users_checked = count
                    p.discord_ids_found = len(all_discord_ids)
                    p.progress = 55 + (count / max(len(user_list), 1)) * 40
                    p.update_eta()
                    if n_dids > 0:
                        u = futures[future]
                        p.log(f"  [{count}/{len(user_list)}] {u['name']}: {n_dids} Discord ID(s)")
                    elif count % 50 == 0:
                        p.log(f"  ... {count}/{len(user_list)} users checked")
                except Exception:
                    pass

        # ---- phase 5: save ----
        p.set_phase("Saving results", "Writing flagged.txt and updating scan_cache.json")
        p.progress = 97.0

        unique_discord_ids = sorted(all_discord_ids)
        with open(FLAGGED_FILE, "w") as f:
            f.write(" ".join(unique_discord_ids))

        scan_result = {
            "id": scan_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "primary_group_id": primary_group_id,
            "primary_group_name": primary_name,
            "include_allies": include_allies,
            "include_enemies": include_enemies,
            "groups": group_results,
            "users": all_user_records,
            "discord_ids": unique_discord_ids,
            "total_flagged": len(all_user_records),
            "total_discord_ids": len(unique_discord_ids),
        }

        cache = load_cache()
        dup_idx = None
        for i, s in enumerate(cache.get("scans", [])):
            if (s.get("primary_group_id") == primary_group_id
                    and s.get("include_allies") == include_allies
                    and s.get("include_enemies", False) == include_enemies):
                dup_idx = i
                break
        if dup_idx is not None:
            p.log(f"  Replacing previous scan for this group (was: {cache['scans'][dup_idx].get('id')})")
            cache["scans"][dup_idx] = scan_result
        else:
            cache["scans"].append(scan_result)

        if len(cache["scans"]) > 20:
            cache["scans"] = cache["scans"][-20:]
        save_cache(cache)

        elapsed = time.time() - p.start_time if p.start_time else 0
        p.progress = 100.0
        p.status = "done"
        p.eta_seconds = 0
        p.set_phase("Complete", "All done, view Results!")
        p.log(f"Done! {len(all_user_records)} flagged users, {len(unique_discord_ids)} Discord IDs")
        p.log(f"  Took {elapsed:.1f}s. Results in {FLAGGED_FILE} + {CACHE_FILE}")

    except Exception as e:
        p.status = "error"
        p.set_phase("Error", str(e))
        p.log(f"SCAN ERROR: {e}")
        import traceback
        p.log(traceback.format_exc())
