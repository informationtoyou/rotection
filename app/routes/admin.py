"""
Admin handler
"""

from flask import Blueprint, jsonify, request
import json

from app.database import (
    get_all_users, get_user_by_id, update_user_roles,
    update_user_admin_confirmed, update_user_division_confirmed,
    update_user_divisions_mod_confirmed, delete_user,
    log_audit, get_audit,
)
from app.routes.auth import admin_required, _safe_user, get_current_user

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/users")
@admin_required
def list_users():
    users = get_all_users()
    return jsonify([_safe_user(u) for u in users])


@admin_bp.route("/api/admin/audit")
@admin_required
def admin_audit():
    # params: limit, since_ts
    try:
        limit = int(request.args.get("limit", 200))
        since = request.args.get("since_ts")
        since_ts = int(since) if (since and since.isdigit()) else None
        rows = get_audit(limit=limit, since_ts=since_ts)
        # resolve actor usernames cheaply
        actor_ids = {r.get("actor_id") for r in rows if r.get("actor_id") is not None}
        actors = {}
        for aid in actor_ids:
            try:
                u = get_user_by_id(aid)
                actors[aid] = (u["username"] if u else None)
            except Exception:
                actors[aid] = None
        for r in rows:
            r["actor_username"] = actors.get(r.get("actor_id")) if r.get("actor_id") else None
        return jsonify(rows)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to load audit: " + str(e)}), 500


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PATCH"])
@admin_required
def update_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    actor = get_current_user()
    actor_id = actor["id"] if actor else None

    # record changes
    if "roles" in data:
        old_roles = user.get("roles")
        update_user_roles(user_id, data["roles"])
        log_audit(actor_id, "roles_changed", obj=str(user_id), details=json.dumps({"from": old_roles, "to": data["roles"]}))

    if "admin_confirmed" in data:
        update_user_admin_confirmed(user_id, bool(data["admin_confirmed"]))
        if data["admin_confirmed"]:
            log_audit(actor_id, "approved_admin", obj=str(user_id))
        else:
            log_audit(actor_id, "revoked_admin", obj=str(user_id))

    if "division_confirmed" in data:
        update_user_division_confirmed(user_id, bool(data["division_confirmed"]))
        if data["division_confirmed"]:
            log_audit(actor_id, "approved_division", obj=str(user_id))
        else:
            log_audit(actor_id, "revoked_division", obj=str(user_id))

    if "divisions_mod_confirmed" in data:
        update_user_divisions_mod_confirmed(user_id, data["divisions_mod_confirmed"])
        log_audit(actor_id, "approved_mods", obj=str(user_id), details=json.dumps(data["divisions_mod_confirmed"]))

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
    log_audit(actor_id, "user_deleted", obj=str(user_id))
    return jsonify({"ok": True})
