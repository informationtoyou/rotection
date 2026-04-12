"""
Shared permission helpers for route handlers.

Centralises all user-visibility and role-check logic so that scan.py and
scans.py (and any future routes) stay in sync automatically.
"""

from scanner.constants import SEA_MILITARY_GROUP_ID


def has_role(user: dict, role: str) -> bool:
    """Return True if the user holds the named role."""
    return role in user.get("roles", [])


def get_user_division_ids(user: dict) -> set:
    """Return the set of group IDs the user is associated with (as leader or moderator)."""
    ids = set()
    if user.get("division_group_id") and user.get("division_confirmed"):
        ids.add(user["division_group_id"])
    for div in user.get("divisions_mod_confirmed", []):
        if isinstance(div, dict) and div.get("id"):
            ids.add(div["id"])
    return ids


def can_user_see_scan(user: dict, scan: dict) -> bool:
    """Return True if the user is allowed to view the given scan."""
    if user["is_admin"]:
        return True

    primary_gid = scan.get("primary_group_id")

    # "All of SEA" scans (SEA Military + allies) are visible to everyone
    if primary_gid == SEA_MILITARY_GROUP_ID and scan.get("include_allies"):
        return True

    if scan.get("requested_by") == user["username"]:
        return True

    if "SEA Moderator" in user.get("roles", []):
        return True

    if "Division Administrator" in user.get("roles", []) and user.get("admin_confirmed"):
        return True

    user_div_ids = get_user_division_ids(user)
    if primary_gid and primary_gid in user_div_ids:
        return True

    # also check if any group within the scan is one the user is associated with
    scan_group_ids = set()
    for gid_str in scan.get("groups", {}).keys():
        try:
            scan_group_ids.add(int(gid_str))
        except (ValueError, TypeError):
            pass
    if primary_gid:
        scan_group_ids.add(primary_gid)
    if user_div_ids & scan_group_ids:
        return True

    return False


def filter_scans_for_user(scans: list[dict], user: dict) -> list[dict]:
    """Filter a list of scan summaries down to those the user is permitted to see."""
    if user["is_admin"]:
        return scans
    if "SEA Moderator" in user.get("roles", []):
        return scans
    if "Division Administrator" in user.get("roles", []) and user.get("admin_confirmed"):
        return scans

    visible = []
    user_div_ids = get_user_division_ids(user)

    for s in scans:
        primary_gid = s.get("primary_group_id")
        if primary_gid == SEA_MILITARY_GROUP_ID and s.get("include_allies"):
            visible.append(s)
            continue
        if s.get("requested_by") == user["username"]:
            visible.append(s)
            continue
        if primary_gid and primary_gid in user_div_ids:
            visible.append(s)
            continue

    return visible
