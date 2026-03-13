"""
Admin handler
"""

from flask import Blueprint, jsonify, request

from app.database import (
    get_all_users, get_user_by_id, update_user_roles,
    update_user_admin_confirmed, update_user_division_confirmed,
    update_user_divisions_mod_confirmed, delete_user,
)
from app.routes.auth import admin_required, _safe_user

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/users")
@admin_required
def list_users():
    users = get_all_users()
    return jsonify([_safe_user(u) for u in users])


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PATCH"])
@admin_required
def update_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(force=True, silent=True) or {}

    if "roles" in data:
        update_user_roles(user_id, data["roles"])

    if "admin_confirmed" in data:
        update_user_admin_confirmed(user_id, bool(data["admin_confirmed"]))

    if "division_confirmed" in data:
        update_user_division_confirmed(user_id, bool(data["division_confirmed"]))

    if "divisions_mod_confirmed" in data:
        update_user_divisions_mod_confirmed(user_id, data["divisions_mod_confirmed"])

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
    return jsonify({"ok": True})
