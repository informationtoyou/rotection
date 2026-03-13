"""
The magic!
"""

import threading
import time
import traceback
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.constants import FLAG_TYPES, FLAGGED_FILE, WORKER_THREADS
from scanner.progress import scan_progress
from scanner.cache import load_cache, save_cache
from scanner.roblox import (
    get_group_info, get_allied_groups, get_enemy_groups, batch_get_user_info,
)
from scanner.rotector import (
    get_tracked_users_for_group, batch_lookup_users, get_discord_ids_for_user,
)

_scan_lock = threading.Lock()


def is_scanning() -> bool:
    return scan_progress.status == "scanning"


def run_scan(primary_group_id: int, include_allies: bool = True, include_enemies: bool = False):
    """Queue-compatible: starts scan in a background thread (used by CLI and legacy)."""
    with _scan_lock:
        if is_scanning():
            return False
        scan_progress.reset()
        scan_progress.status = "scanning"
        t = threading.Thread(
            target=_scan_worker, args=(primary_group_id, include_allies, include_enemies), daemon=True,
        )
        t.start()
        return True


def _scan_worker(primary_group_id: int, include_allies: bool, include_enemies: bool = False):
    """Core scan logic. Called by queue_worker or run_scan directly."""
    p = scan_progress
    if p.status != "scanning":
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

        allies = []
        enemies = []
        if include_allies or include_enemies:
            fetch_tasks = {}
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

        # cap threads to avoid CPU spikes on PythonAnywhere
        group_workers = min(WORKER_THREADS, len(groups_to_scan), 10)

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

        # ---- phase 2.5: fill in ALL missing usernames from Roblox ----
        missing_names = [int(uid) for uid, rec in all_user_records.items()
                         if not rec["name"] or rec["name"] == "Unknown" or rec["name"].strip() == ""]
        if missing_names:
            p.set_phase("Resolving usernames", f"Fetching names for {len(missing_names)} users from Roblox")
            p.log(f"Fetching usernames for {len(missing_names)} users missing name data...")
            name_data = batch_get_user_info(missing_names)
            filled = 0
            for uid_str, info in name_data.items():
                if uid_str in all_user_records:
                    rec = all_user_records[uid_str]
                    if not rec["name"] or rec["name"] == "Unknown" or rec["name"].strip() == "":
                        rec["name"] = info.get("name", "")
                        filled += 1
                    if not rec["displayName"]:
                        rec["displayName"] = info.get("displayName", "")
            p.log(f"  Filled in {filled} usernames from Roblox")

        # also fill display names for users that have a name but no displayName
        missing_display = [int(uid) for uid, rec in all_user_records.items()
                           if rec["name"] and not rec["displayName"]]
        if missing_display:
            p.log(f"Fetching display names for {len(missing_display)} users...")
            display_data = batch_get_user_info(missing_display)
            for uid_str, info in display_data.items():
                if uid_str in all_user_records and not all_user_records[uid_str]["displayName"]:
                    all_user_records[uid_str]["displayName"] = info.get("displayName", "")

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

        # ---- phase 4: discord ID resolution (threaded, capped for PythonAnywhere) ----
        p.set_phase("Resolving Discord accounts", "Looking up linked Discord IDs. This is the slowest part, please be patient")
        discord_workers = min(WORKER_THREADS, 20)  # cap to avoid CPU spikes
        p.log(f"Looking up Discord accounts ({discord_workers} threads)...")

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

        with ThreadPoolExecutor(max_workers=discord_workers) as executor:
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

        # ---- phase 5: final username sweep for any still missing ----
        still_missing = [int(uid) for uid, rec in all_user_records.items()
                         if not rec.get("name") or rec["name"] == "Unknown" or rec["name"].strip() == ""]
        if still_missing:
            p.log(f"Final username sweep for {len(still_missing)} remaining users...")
            final_data = batch_get_user_info(still_missing)
            for uid_str, info in final_data.items():
                if uid_str in all_user_records:
                    rec = all_user_records[uid_str]
                    if not rec.get("name") or rec["name"] == "Unknown":
                        rec["name"] = info.get("name", f"User_{uid_str}")
                    if not rec.get("displayName"):
                        rec["displayName"] = info.get("displayName", "")

        # ---- phase 6: save ----
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
        p.log(f"  Took {elapsed:.1f}s. Results in {FLAGGED_FILE} + scan_cache.json")

    except Exception as e:
        p.status = "error"
        p.set_phase("Error", str(e))
        p.log(f"SCAN ERROR: {e}")
        p.log(traceback.format_exc())
