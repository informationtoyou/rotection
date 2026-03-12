"""
Rotection web server — serves the dashboard and scan API.
Run directly with `python app.py` for development, or use gunicorn for production.
"""

from flask import Flask, jsonify, request, render_template, Response
from flask_cors import CORS
import json
import time
import threading
from scanner import (
    run_scan, scan_progress, is_scanning,
    get_previous_scans, get_scan_by_id, FLAG_TYPES,
    load_cache, save_cache,
)
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "")

# -- deploy state (thread-safe) --
_deploy_lock = threading.Lock()
_deploy_state = {
    "pending": False,
    "message": "",
    "notified_at": None,
}


def get_deploy_state() -> dict:
    with _deploy_lock:
        return dict(_deploy_state)


def set_deploy_pending(message: str = ""):
    with _deploy_lock:
        _deploy_state["pending"] = True
        _deploy_state["message"] = message or "A new update is being deployed. The site will refresh shortly."
        _deploy_state["notified_at"] = time.time()


def clear_deploy_pending():
    with _deploy_lock:
        _deploy_state["pending"] = False
        _deploy_state["message"] = ""
        _deploy_state["notified_at"] = None


# -- pages --
@app.route("/")
def index():
    return render_template("index.html")


# -- api: start a scan --
@app.route("/api/scan", methods=["POST"])
def start_scan():
    if is_scanning():
        return jsonify({"error": "Someone else is already running a scan. Allow for that scan to finish"}), 409

    data = request.get_json(force=True, silent=True) or {}
    raw_group_id = data.get("group_id", "2648601")

    # validate group id — must be a positive integer
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


# -- api: poll scan progress --
@app.route("/api/progress")
def api_progress():
    cursor = request.args.get("cursor", 0, type=int)
    return jsonify(scan_progress.to_dict(log_cursor=cursor))


# -- api: previous scans --
@app.route("/api/scans")
def list_scans():
    return jsonify(get_previous_scans())


# -- api: full scan result by id / delete --
@app.route("/api/scans/<scan_id>", methods=["GET", "DELETE"])
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


# -- api: cancel a running scan --
@app.route("/api/scan/cancel", methods=["POST"])
def cancel_scan():
    if not is_scanning():
        return jsonify({"error": "No scan running"}), 400
    scan_progress.cancel()
    return jsonify({"ok": True, "message": "Cancellation requested"})


# -- api: flag type reference --
@app.route("/api/flag-types")
def flag_types():
    return jsonify(FLAG_TYPES)


# -- api: export discord ids as json download --
@app.route("/api/scans/<scan_id>/discord-export")
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


# -- api: deploy notification (called by GitHub Actions before reload) --
@app.route("/api/deploy/notify", methods=["POST"])
def deploy_notify():
    # authenticate with a shared secret
    auth = request.headers.get("X-Deploy-Secret", "")
    if not DEPLOY_SECRET or auth != DEPLOY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    set_deploy_pending(message)
    return jsonify({"ok": True, "scanning": is_scanning()})


# -- api: deploy status (polled by frontend) --
@app.route("/api/deploy/status")
def deploy_status():
    state = get_deploy_state()
    return jsonify({
        "pending": state["pending"],
        "message": state["message"],
        "scanning": is_scanning(),
    })


if __name__ == "__main__":
    print("=" * 55)
    print("  ROTECTION - WEB DASHBOARD RUNNING LOCALLY")
    print("  Open http://localhost:5050 in your browser")
    print("  An API Key is NOT required to use this, although you can use one.")
    print("=" * 55)
    app.run(debug=False, port=5050, threaded=True)
