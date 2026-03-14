"""
Scans handler to list etc
"""

import json
from flask import Blueprint, jsonify, request, Response

from scanner import get_previous_scans, get_scan_by_id, delete_scan_by_id
from app.routes.auth import login_required, get_current_user

scans_bp = Blueprint("scans", __name__)

SEA_GROUP_ID = 2648601


@scans_bp.route("/api/scans")
@login_required
def list_scans():
    user = get_current_user()
    scans = get_previous_scans()
    return jsonify(_filter_scans_for_user(scans, user))


@scans_bp.route("/api/scans/<scan_id>", methods=["GET", "DELETE"])
@login_required
def get_or_delete_scan(scan_id):
    user = get_current_user()

    if request.method == "DELETE":
        if not user["is_admin"]:
            return jsonify({"error": "Only admin can delete scans"}), 403
        if not delete_scan_by_id(scan_id):
            return jsonify({"error": "Scan not found"}), 404
        return jsonify({"ok": True})

    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    # visibility check
    if not _can_user_see_scan(user, scan):
        return jsonify({"error": "You don't have permission to view this scan"}), 403

    return jsonify(scan)


@scans_bp.route("/api/scans/<scan_id>/discord-export")
@login_required
def discord_export(scan_id):
    user = get_current_user()
    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    if not _can_user_see_scan(user, scan):
        return jsonify({"error": "You don't have permission to view this scan"}), 403

    users = scan.get("users", {})
    export = {
        "scan_id": scan_id,
        "primary_group": scan.get("primary_group_name", "Unknown"),
        "timestamp": scan.get("timestamp"),
        "discord_ids": scan.get("discord_ids", []),
        "users_with_discord": [],
    }
    for uid, u in users.items():
        accs = u.get("discord_accounts", [])
        if accs:
            export["users_with_discord"].append({
                "roblox_id": u.get("id"),
                "roblox_name": u.get("name", "Unknown"),
                "flag_type": u.get("flagName", "Unknown"),
                "confidence": u.get("confidence", 0),
                "discord_accounts": accs,
            })

    return Response(
        json.dumps(export, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=rotection_discord_{scan_id}.json"},
    )


def _can_user_see_scan(user: dict, scan: dict) -> bool:
    """Check if a user is allowed to see a specific scan."""
    # admin sees everything
    if user["is_admin"]:
        return True

    primary_gid = scan.get("primary_group_id")

    # "All of SEA" scans (SEA Military with allies) are visible to everyone
    if primary_gid == SEA_GROUP_ID and scan.get("include_allies"):
        return True

    # check if scan was requested by this user (from scan_queue via scan metadata)
    if scan.get("requested_by") == user["username"]:
        return True

    # SEA Moderators see all scans
    if "SEA Moderator" in user.get("roles", []):
        return True

    # Division Administrators (confirmed) see all scans
    if "Division Administrator" in user.get("roles", []) and user.get("admin_confirmed"):
        return True

    # Division Leaders see scans of their own division
    user_div_ids = _get_user_division_ids(user)
    if primary_gid and primary_gid in user_div_ids:
        return True

    # check if scan covers any group the user is associated with
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

    # Individuals see their own scans (handled by requested_by above)
    return False


def _filter_scans_for_user(scans: list[dict], user: dict) -> list[dict]:
    """Filter scan summaries based on user permissions."""
    if user["is_admin"]:
        return scans
    if "SEA Moderator" in user.get("roles", []):
        return scans
    if "Division Administrator" in user.get("roles", []) and user.get("admin_confirmed"):
        return scans

    visible = []
    user_div_ids = _get_user_division_ids(user)

    for s in scans:
        primary_gid = s.get("primary_group_id")
        # "All of SEA" scans visible to everyone
        if primary_gid == SEA_GROUP_ID and s.get("include_allies"):
            visible.append(s)
            continue
        # user's own scans
        if s.get("requested_by") == user["username"]:
            visible.append(s)
            continue
        # user's own division scans
        if primary_gid and primary_gid in user_div_ids:
            visible.append(s)
            continue

    return visible


def _get_user_division_ids(user: dict) -> set:
    """Get all group IDs a user is associated with."""
    ids = set()
    if user.get("division_group_id") and user.get("division_confirmed"):
        ids.add(user["division_group_id"])
    # Division Moderator confirmed divisions
    for div in user.get("divisions_mod_confirmed", []):
        if isinstance(div, dict) and div.get("id"):
            ids.add(div["id"])
    return ids
