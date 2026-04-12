"""
Rotection CLI
Are you cool (or not) and like using CLIs? Execute this file in a terminal and watch the results return! This will update requirements.txt with Discord IDs of all Discord IDs provided by Rotector.
The results are recorded to the scan_cache.db, so you can technically view this in the web.
If you are not a developer, or someone who does not know how to use CLIs, I'd recommend using the web-based app.py.
Instructions for which will be found once you run it.
"""

import sys
import time
from scanner import (
    run_scan, scan_progress, is_scanning,
    get_previous_scans, get_scan_by_id,
)
from scanner.constants import SEA_MILITARY_GROUP_ID

GROUP_ID = SEA_MILITARY_GROUP_ID  # default group; override with --group=ID


def main():
    print("=" * 55)
    print("  ROTECTION - CLI Scanner")
    print(f"  Group ID: {GROUP_ID}")
    print("  Web UI: python app.py")
    print("=" * 55)

    include_allies = "--no-allies" not in sys.argv
    include_enemies = "--enemies" in sys.argv

    # --history: list previous scans
    if "--history" in sys.argv:
        scans = get_previous_scans()
        if not scans:
            print("\nNo previous scans found.")
            return
        print(f"\n{'ID':<20} {'Group':<25} {'Flagged':>8} {'Discord IDs':>12} {'Time'}")
        print("-" * 85)
        for s in scans:
            print(f"{s['id']:<20} {s['primary_group']:<25} {s['total_flagged']:>8} {s['total_discord_ids']:>12} {s['timestamp']}")
        return

    # --load=SCAN_ID: print a saved scan
    for arg in sys.argv:
        if arg.startswith("--load="):
            scan_id = arg.split("=", 1)[1]
            scan = get_scan_by_id(scan_id)
            if not scan:
                print(f"\nScan '{scan_id}' not found. Use --history to list scans.")
                return
            print(f"\nLoaded scan: {scan_id}")
            print(f"  Group: {scan.get('primary_group_name', '?')}")
            print(f"  Flagged: {scan.get('total_flagged', 0)}")
            print(f"  Discord IDs: {scan.get('total_discord_ids', 0)}")
            print(f"  IDs: {' '.join(scan.get('discord_ids', []))}")
            return

    # override grp id
    group_id = GROUP_ID
    for arg in sys.argv:
        if arg.startswith("--group="):
            raw = arg.split("=", 1)[1]
            try:
                group_id = int(raw)
                if group_id <= 0:
                    raise ValueError
            except ValueError:
                print(f"Error: '{raw}' is not a valid group ID (must be a positive number).")
                return

    print(f"\nStarting scan (allies={'yes' if include_allies else 'no'}, enemies={'yes' if include_enemies else 'no'})...\n")
    run_scan(group_id, include_allies, include_enemies)

    # stream progress to terminal
    last_log_count = 0
    while is_scanning():
        state = scan_progress.to_dict(log_cursor=last_log_count)
        for line in state["logs"]:
            print(line)
        last_log_count = state["log_count"]
        time.sleep(1)

    # flush remaining logs
    state = scan_progress.to_dict(log_cursor=last_log_count)
    for line in state["logs"]:
        print(line)

    if state["status"] == "done":
        print(f"\n{'=' * 55}")
        print(f"  SCAN COMPLETE")
        print(f"  Flagged users: {state['flagged_found']}")
        print(f"  Discord IDs:   {state['discord_ids_found']}")
        print(f"  Scan ID:       {state['scan_id']}")
        print(f"  Saved to flagged.txt + scan_cache.db")
        print(f"{'=' * 55}")
    else:
        print(f"\n  Scan ended with status: {state['status']}")


if __name__ == "__main__":
    main()