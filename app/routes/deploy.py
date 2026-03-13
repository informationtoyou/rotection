"""
Deployment blueprint
"""

import os
from flask import Blueprint, jsonify, request
from scanner import is_scanning
from app.deploy_state import get_deploy_state, set_deploy_pending

deploy_bp = Blueprint("deploy", __name__)

DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "rotection-deploy-key")


@deploy_bp.route("/api/deploy/notify", methods=["POST"])
def deploy_notify():
    if DEPLOY_SECRET:
        auth = request.headers.get("X-Deploy-Secret", "")
        if auth != DEPLOY_SECRET:
            return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    set_deploy_pending(message)
    return jsonify({"ok": True, "scanning": is_scanning()})


@deploy_bp.route("/api/deploy/status")
def deploy_status():
    state = get_deploy_state()
    return jsonify({
        "pending": state["pending"],
        "message": state["message"],
        "scanning": is_scanning(),
    })
