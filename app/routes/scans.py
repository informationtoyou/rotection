"""
Scans blueprint
"""

import json
from flask import Blueprint, jsonify, request, Response
from scanner import get_previous_scans, get_scan_by_id, load_cache, save_cache

scans_bp = Blueprint("scans", __name__)


@scans_bp.route("/api/scans")
def list_scans():
    return jsonify(get_previous_scans())


@scans_bp.route("/api/scans/<scan_id>", methods=["GET", "DELETE"])
def get_or_delete_scan(scan_id):
    if request.method == "DELETE":
        cache = load_cache()
        before = len(cache.get("scans", []))
        cache["scans"] = [s for s in cache.get("scans", []) if s.get("id") != scan_id]
        if len(cache["scans"]) == before:
            return jsonify({"error": "Scan not found"}), 404
        save_cache(cache)
        return jsonify({"ok": True})

    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
    return jsonify(scan)


@scans_bp.route("/api/scans/<scan_id>/discord-export")
def discord_export(scan_id):
    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

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
