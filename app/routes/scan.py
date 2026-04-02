"""
queue-based scan management and progress tracker
"""

from flask import Blueprint, jsonify, request, session
import json

from scanner import scan_progress, is_scanning, FLAG_TYPES
from app.database import (
    enqueue_scan, get_queue, get_queue_position, get_queue_entry,
    set_user_status, get_user_statuses_for_scan, VALID_STATUSES, PUBLIC_STATUSES, log_audit,
    mark_queue_failed,
)
from app.routes.auth import login_required, get_current_user, admin_required

scan_bp = Blueprint("scan", __name__)

# SEA Military group ID — scans of this (with allies) are visible to everyone
SEA_GROUP_ID = 2648601


@scan_bp.route("/api/scan", methods=["POST"])
@login_required
def start_scan():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    raw_group_id = data.get("group_id", "2648601")

    try:
        group_id = int(raw_group_id)
        if group_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": f"Invalid group ID: '{raw_group_id}'. Must be a positive number."}), 400

    include_allies = bool(data.get("include_allies", True))
    include_enemies = bool(data.get("include_enemies", False))

    # permission check: Division Leaders/Mods can only scan their own division
    if not user["is_admin"] and not _has_role(user, "SEA Moderator") and not _has_role(user, "Individual"):
        allowed_ids = _get_user_division_ids(user)
        if group_id not in allowed_ids and group_id != SEA_GROUP_ID:
            return jsonify({"error": "You can only scan your own division or all of SEA"}), 403

    queue_id = enqueue_scan(group_id, include_allies, include_enemies, user["username"])

    # kick the queue worker
    from app.queue_worker import maybe_start_worker
    maybe_start_worker()

    # audit: someone queued a scan
    try:
        from app.database import get_user_by_id, log_audit, get_user
        actor_id = user.get("id") if user else None
        log_audit(actor_id, "scan_queued", obj=str(queue_id), details=json.dumps({"group_id": group_id, "include_allies": include_allies, "include_enemies": include_enemies}))
    except Exception:
        pass

    position = get_queue_position(queue_id)
    return jsonify({
        "ok": True,
        "message": "Scan queued",
        "queue_id": queue_id,
        "position": position,
        "group_id": group_id,
    })


@scan_bp.route("/api/progress")
@login_required
def api_progress():
    user = get_current_user()
    cursor = request.args.get("cursor", 0, type=int)
    data = scan_progress.to_dict(log_cursor=cursor)
    # tell the frontend whether the current user can cancel this scan
    if user:
        data["owned_by_current_user"] = (
            user["is_admin"] or scan_progress.requested_by == user["username"]
        )
    else:
        data["owned_by_current_user"] = False
    return jsonify(data)


@scan_bp.route("/api/scan/cancel", methods=["POST"])
@login_required
def cancel_scan():
    user = get_current_user()
    if not is_scanning():
        return jsonify({"error": "No scan running"}), 400
    # only admin or the user who started the scan can cancel
    if not user["is_admin"]:
        if scan_progress.requested_by != user["username"]:
            return jsonify({"error": "Only the person who started this scan (or an admin) can cancel it"}), 403
    scan_progress.cancel()
    return jsonify({"ok": True, "message": "Cancellation requested"})


@scan_bp.route("/api/admin/queue/<int:queue_id>/delete", methods=["POST"])
@admin_required
def admin_delete_queue_scan(queue_id):
    """Admin endpoint to delete a queued or running scan (even if stuck)."""
    entry = get_queue_entry(queue_id)
    if not entry:
        return jsonify({"error": "Queue entry not found"}), 404
    
    user = get_current_user()
    
    if entry["status"] == "running":
        # Try to cancel if actually running, but force-delete regardless
        # This handles the PythonAnywhere reload edge case where status is "running" but is_scanning() is False
        if is_scanning():
            scan_progress.cancel()
        
        # Always mark as failed - this removes the stuck entry from the queue
        mark_queue_failed(queue_id)
        try:
            actor_id = user.get("id") if user else None
            log_audit(actor_id, "scan_deleted", obj=str(queue_id), details=json.dumps({
                "reason": "admin_delete_running", 
                "group_id": entry["group_id"],
                "was_actually_running": is_scanning()
            }))
        except Exception:
            pass
        return jsonify({"ok": True, "message": "Running scan removed"})
    
    elif entry["status"] == "queued":
        # Mark queued scan as failed (effectively removing it from queue)
        mark_queue_failed(queue_id)
        try:
            actor_id = user.get("id") if user else None
            log_audit(actor_id, "scan_deleted", obj=str(queue_id), details=json.dumps({
                "reason": "admin_delete_queued", 
                "group_id": entry["group_id"]
            }))
        except Exception:
            pass
        return jsonify({"ok": True, "message": "Queued scan removed"})
    
    else:
        return jsonify({"error": f"Cannot delete scan with status: {entry['status']}"}), 400


@scan_bp.route("/api/queue")
@login_required
def api_queue():
    user = get_current_user()
    queue = get_queue()
    # non-admin users only see their own queue entries + the position info
    if not user["is_admin"]:
        visible = []
        for entry in queue:
            if entry["requested_by"] == user["username"]:
                visible.append(entry)
            else:
                # show position only, not who requested it
                visible.append({
                    "id": entry["id"],
                    "group_id": entry["group_id"],
                    "status": entry["status"],
                    "position": entry["position"],
                    "requested_by": "Another user",
                    "created_at": entry["created_at"],
                    "include_allies": entry["include_allies"],
                    "include_enemies": entry["include_enemies"],
                    "scan_id": None,
                    "started_at": entry["started_at"],
                    "finished_at": entry["finished_at"],
                })
        queue = visible
    return jsonify(queue)


@scan_bp.route("/api/queue/<int:queue_id>")
@login_required
def api_queue_entry(queue_id):
    entry = get_queue_entry(queue_id)
    if not entry:
        return jsonify({"error": "Queue entry not found"}), 404
    return jsonify(entry)


@scan_bp.route("/api/flag-types")
@login_required
def flag_types():
    return jsonify(FLAG_TYPES)


@scan_bp.route("/api/user-status", methods=["POST"])
@login_required
def api_set_user_status():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    roblox_id = str(data.get("roblox_id", ""))
    status = data.get("status", "")
    discord_ids = data.get("discord_ids", None)

    if not roblox_id or not status:
        return jsonify({"error": "roblox_id and status are required"}), 400

    if status not in VALID_STATUSES:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"}), 400

    # permission check for status changes — admin, confirmed DA, or SEA Moderator
    is_div_admin = _has_role(user, "Division Administrator") and user["admin_confirmed"]
    is_sea_mod = _has_role(user, "SEA Moderator")
    if not user["is_admin"] and not is_div_admin and not is_sea_mod:
        return jsonify({"error": "Only admins, confirmed Division Administrators, and SEA Moderators can set user statuses"}), 403

    # only admin and confirmed div admins can set internal statuses
    if status in ("Suspicious", "Under Investigation") and not user["is_admin"] and not is_div_admin and not is_sea_mod:
        return jsonify({"error": "Only Division Administrators and SEA Moderators can set this status"}), 403

    ok = set_user_status(roblox_id, status, user["username"], discord_ids)
    if not ok:
        return jsonify({"error": "Failed to set status"}), 500

    # audit log
    try:
        actor_id = user.get("id") if user else None
        details = json.dumps({"status": status, "discord_ids": discord_ids if discord_ids else []})
        log_audit(actor_id, "status_set", obj=roblox_id, details=details)
    except Exception:
        pass

    return jsonify({"ok": True})


@scan_bp.route("/api/user-statuses/<scan_id>")
@login_required
def api_get_user_statuses(scan_id):
    user = get_current_user()

    # load the scan to get roblox IDs in it
    from scanner.cache import get_scan_by_id
    scan_data = get_scan_by_id(scan_id)
    if not scan_data:
        return jsonify({})

    roblox_ids = [str(uid) for uid in (scan_data.get("users") or {}).keys()]
    statuses = get_user_statuses_for_scan(roblox_ids)

    # non-admin, non-div-admin, non-SEA-mod users only see public statuses
    is_div_admin = _has_role(user, "Division Administrator") and user["admin_confirmed"]
    is_sea_mod = _has_role(user, "SEA Moderator")
    if not user["is_admin"] and not is_div_admin and not is_sea_mod:
        statuses = {k: v for k, v in statuses.items() if v["status"] in PUBLIC_STATUSES}

    return jsonify(statuses)


def _has_role(user: dict, role: str) -> bool:
    return role in user.get("roles", [])


def _get_user_division_ids(user: dict) -> set:
    """Get all group IDs a user is associated with (as leader or moderator)."""
    ids = set()
    if user.get("division_group_id") and user.get("division_confirmed"):
        ids.add(user["division_group_id"])
    for div in user.get("divisions_mod_confirmed", []):
        if isinstance(div, dict) and div.get("id"):
            ids.add(div["id"])
    return ids
