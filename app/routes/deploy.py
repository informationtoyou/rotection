"""
Deployment blueprint
"""

import os
from flask import Blueprint, jsonify, request
from scanner import is_scanning
from app.deploy_state import get_deploy_state, set_deploy_pending, clear_deploy_pending
from app.database import is_queue_running

deploy_bp = Blueprint("deploy", __name__)

DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "")


def _is_scan_active():
    """Check if a scan is actually running (in-memory OR in database queue)."""
    # Check in-memory first (current process)
    if is_scanning():
        return True
    
    # Check database for any running queue entry (handles cross-process/reload cases)
    try:
        return is_queue_running()
    except Exception:
        # If DB check fails, default to safe assumption that nothing is running
        return False


@deploy_bp.route("/api/deploy/notify", methods=["POST"])
def deploy_notify():
    auth = request.headers.get("X-Deploy-Secret", "")
    if not DEPLOY_SECRET or auth != DEPLOY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    set_deploy_pending(message)
    return jsonify({"ok": True, "scanning": _is_scan_active()})


@deploy_bp.route("/api/deploy/clear", methods=["POST"])
def deploy_clear():
    auth = request.headers.get("X-Deploy-Secret", "")
    if not DEPLOY_SECRET or auth != DEPLOY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    clear_deploy_pending()
    return jsonify({"ok": True})


@deploy_bp.route("/api/deploy/status")
def deploy_status():
    state = get_deploy_state()
    return jsonify({
        "pending": state["pending"],
        "message": state["message"],
        "scanning": _is_scan_active(),
    })
