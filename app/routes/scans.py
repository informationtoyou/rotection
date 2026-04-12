"""
Scans handler to list etc
"""

import json
import logging
import re
from flask import Blueprint, jsonify, request, Response

from scanner import get_previous_scans, get_scan_by_id, delete_scan_by_id
from app.routes.auth import login_required, get_current_user
from app.permissions import can_user_see_scan, filter_scans_for_user

logger = logging.getLogger(__name__)

scans_bp = Blueprint("scans", __name__)


@scans_bp.route("/api/scans")
@login_required
def list_scans():
    user = get_current_user()
    scans = get_previous_scans()
    return jsonify(filter_scans_for_user(scans, user))


@scans_bp.route("/api/scans/<scan_id>", methods=["GET", "DELETE"])
@login_required
def get_or_delete_scan(scan_id):
    user = get_current_user()

    if request.method == "DELETE":
        if not user["is_admin"]:
            logger.warning("403 delete scan %s by %s", scan_id, user.get("username"))
            return jsonify({"error": "Only admin can delete scans"}), 403
        if not delete_scan_by_id(scan_id):
            return jsonify({"error": "Scan not found"}), 404
        return jsonify({"ok": True})

    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    if not can_user_see_scan(user, scan):
        logger.warning("403 view scan %s by %s", scan_id, user.get("username"))
        return jsonify({"error": "You don't have permission to view this scan"}), 403

    return jsonify(scan)


@scans_bp.route("/api/scans/<scan_id>/discord-export")
@login_required
def discord_export(scan_id):
    user = get_current_user()
    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    if not can_user_see_scan(user, scan):
        logger.warning("403 discord-export scan %s by %s", scan_id, user.get("username"))
        return jsonify({"error": "You don't have permission to view this scan"}), 403

    # Get filter parameters from query string
    raw_conf = request.args.get("min_confidence", 0, type=float)
    min_confidence = max(0.0, min(1.0, raw_conf))
    exclude_seabanned = request.args.get("exclude_seabanned", "false").lower() == "true"
    exclude_false_positives = request.args.get("exclude_false_positives", "true").lower() == "true"

    users = scan.get("users", {})

    # Get user statuses for filtering
    from app.database import get_user_statuses_for_scan
    roblox_ids = [str(uid) for uid in users.keys()]
    statuses = get_user_statuses_for_scan(roblox_ids) if roblox_ids else {}

    discord_set = set()
    users_with_discord = []

    for uid, u in users.items():
        accs = u.get("discord_accounts", [])
        if not accs:
            continue

        confidence = u.get("confidence", 0)
        if confidence < min_confidence:
            continue

        user_status = statuses.get(str(uid), {}).get("status", "")

        if exclude_seabanned and user_status == "SEA Banned":
            continue

        if exclude_false_positives and user_status == "False Positive":
            continue

        users_with_discord.append({
            "roblox_id": u.get("id"),
            "roblox_name": u.get("name", "Unknown"),
            "flag_type": u.get("flagName", "Unknown"),
            "confidence": confidence,
            "status": user_status,
            "discord_accounts": accs,
        })

        for acc in accs:
            discord_id = acc.get("discord_id") or acc.get("id")
            if discord_id:
                discord_set.add(str(discord_id))

    export = {
        "scan_id": scan_id,
        "primary_group": scan.get("primary_group_name", "Unknown"),
        "timestamp": scan.get("timestamp"),
        "filters": {
            "min_confidence": min_confidence,
            "exclude_seabanned": exclude_seabanned,
            "exclude_false_positives": exclude_false_positives,
        },
        "discord_ids": sorted(list(discord_set)),
        "users_with_discord": users_with_discord,
    }

    # Sanitise scan_id before using it in a response header to prevent header injection
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(scan_id))
    return Response(
        json.dumps(export, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=rotection_discord_{safe_id}.json"},
    )
