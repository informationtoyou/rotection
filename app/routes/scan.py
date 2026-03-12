"""
Scan blueprint
"""

from flask import Blueprint, jsonify, request
from scanner import run_scan, scan_progress, is_scanning, FLAG_TYPES

scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/api/scan", methods=["POST"])
def start_scan():
    if is_scanning():
        return jsonify({"error": "Someone else is already running a scan. Allow for that scan to finish"}), 409

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
    run_scan(group_id, include_allies, include_enemies)
    return jsonify({"ok": True, "message": "Scan started", "group_id": group_id})


@scan_bp.route("/api/progress")
def api_progress():
    cursor = request.args.get("cursor", 0, type=int)
    return jsonify(scan_progress.to_dict(log_cursor=cursor))


@scan_bp.route("/api/scan/cancel", methods=["POST"])
def cancel_scan():
    if not is_scanning():
        return jsonify({"error": "No scan running"}), 400
    scan_progress.cancel()
    return jsonify({"ok": True, "message": "Cancellation requested"})


@scan_bp.route("/api/flag-types")
def flag_types():
    return jsonify(FLAG_TYPES)
