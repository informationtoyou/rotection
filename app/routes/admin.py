"""
Admin handler
"""

import json
import logging
from flask import Blueprint, jsonify, request

from app.database import (
    get_all_users, get_user_by_id, update_user_roles,
    update_user_admin_confirmed, update_user_division_confirmed,
    update_user_divisions_mod_confirmed, delete_user,
    get_audit,
)
from app.routes.auth import admin_required, _safe_user, get_current_user
from app.utils import get_json_body, safe_audit

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/users")
@admin_required
def list_users():
    users = get_all_users()
    return jsonify([_safe_user(u) for u in users])


@admin_bp.route("/api/admin/audit")
@admin_required
def admin_audit():
    try:
        limit_param = request.args.get("limit", "200")
        try:
            limit = int(limit_param)
        except (ValueError, TypeError):
            limit = 200

        since = request.args.get("since_ts")
        since_ts = None
        if since:
            try:
                since_ts = int(since)
            except (ValueError, TypeError):
                since_ts = None

        rows = get_audit(limit=limit, since_ts=since_ts)

        # Batch-load all referenced actor users in a single query to avoid N+1
        actor_ids = {r.get("actor_id") for r in rows if r.get("actor_id") is not None}
        actors = {}
        if actor_ids:
            for aid in actor_ids:
                try:
                    u = get_user_by_id(aid)
                    actors[aid] = u["username"] if u else None
                except Exception:
                    actors[aid] = None

        for r in rows:
            r["actor_username"] = actors.get(r.get("actor_id")) if r.get("actor_id") else None

        return jsonify(rows)
    except Exception as e:
        logger.exception("Failed to load audit log")
        return jsonify({"error": "Failed to load audit: " + str(e)}), 500


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PATCH"])
@admin_required
def update_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = get_json_body()
    actor = get_current_user()
    actor_id = actor["id"] if actor else None

    if "roles" in data:
        old_roles = user.get("roles")
        update_user_roles(user_id, data["roles"])
        safe_audit(actor_id, "roles_changed", obj=str(user_id),
                   details=json.dumps({"from": old_roles, "to": data["roles"]}))

    if "admin_confirmed" in data:
        update_user_admin_confirmed(user_id, bool(data["admin_confirmed"]))
        event = "approved_admin" if data["admin_confirmed"] else "revoked_admin"
        safe_audit(actor_id, event, obj=str(user_id))

    if "division_confirmed" in data:
        update_user_division_confirmed(user_id, bool(data["division_confirmed"]))
        event = "approved_division" if data["division_confirmed"] else "revoked_division"
        safe_audit(actor_id, event, obj=str(user_id))

    if "divisions_mod_confirmed" in data:
        update_user_divisions_mod_confirmed(user_id, data["divisions_mod_confirmed"])
        safe_audit(actor_id, "approved_mods", obj=str(user_id),
                   details=json.dumps(data["divisions_mod_confirmed"]))

    updated = get_user_by_id(user_id)
    return jsonify({"ok": True, "user": _safe_user(updated)})


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def remove_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user["is_admin"]:
        return jsonify({"error": "Cannot delete admin account"}), 403
    delete_user(user_id)
    actor = get_current_user()
    actor_id = actor["id"] if actor else None
    safe_audit(actor_id, "user_deleted", obj=str(user_id))
    return jsonify({"ok": True})
