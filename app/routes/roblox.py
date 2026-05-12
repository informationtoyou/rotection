"""
Roblox OAuth connection, verification, and group member removal endpoints.
"""

import json
import secrets
import time
from flask import Blueprint, jsonify, redirect, request, session, url_for

from app.crypto import encrypt_secret, decrypt_secret
from app.database import (
    upsert_roblox_oauth, get_roblox_oauth, delete_roblox_oauth,
    update_user_division_confirmed,
)
from app.routes.auth import login_required, get_current_user
from app.permissions import has_role
from app.utils import get_json_body, safe_audit
from app.roblox_client import remove_users_from_group
from app.roblox_oauth import build_authorize_url, exchange_code, fetch_userinfo, get_oauth_config, refresh_access_token
from scanner.roblox import check_user_in_group
from scanner.constants import ROBLOX_REMOVE_MAX

roblox_bp = Blueprint("roblox", __name__)


def _require_division_leader(user: dict, require_confirmed: bool = False):
    if not user or not has_role(user, "Division Leader"):
        return jsonify({"error": "Division Leader access required"}), 403
    if require_confirmed and not user.get("division_confirmed"):
        return jsonify({"error": "Division Leader confirmation required"}), 403
    if not user.get("division_group_id"):
        return jsonify({"error": "No division group configured"}), 400
    return None


@roblox_bp.route("/api/roblox/status")
@login_required
def roblox_status():
    user = get_current_user()
    conn = get_roblox_oauth(user["id"]) if user else None
    return jsonify({
        "connected": bool(conn),
        "roblox_user_id": conn.get("roblox_user_id") if conn else None,
        "roblox_username": conn.get("roblox_username") if conn else None,
        "last_verified_at": conn.get("last_verified_at") if conn else None,
        "last_in_group": conn.get("last_in_group") if conn else False,
        "division_group_id": user.get("division_group_id") if user else None,
        "division_name": user.get("division_name") if user else None,
        "division_confirmed": user.get("division_confirmed") if user else False,
        "oauth_configured": bool(get_oauth_config()),
        "remove_cap": ROBLOX_REMOVE_MAX,
    })


@roblox_bp.route("/api/roblox/oauth/start")
@login_required
def roblox_oauth_start():
    user = get_current_user()
    gate = _require_division_leader(user, require_confirmed=False)
    if gate:
        return gate

    if not get_oauth_config():
        return jsonify({"error": "Roblox OAuth not configured"}), 500

    state = secrets.token_urlsafe(24)
    session["roblox_oauth_state"] = state
    auth_url = build_authorize_url(state)
    return redirect(auth_url)


@roblox_bp.route("/api/roblox/oauth/callback")
@login_required
def roblox_oauth_callback():
    user = get_current_user()
    gate = _require_division_leader(user, require_confirmed=False)
    if gate:
        return gate

    if request.args.get("error"):
        return redirect(url_for("pages.dashboard", roblox="error"))

    state = request.args.get("state")
    code = request.args.get("code")
    expected_state = session.pop("roblox_oauth_state", None)
    if not state or not code or state != expected_state:
        return redirect(url_for("pages.dashboard", roblox="invalid_state"))

    token = exchange_code(code)
    if not token or not token.get("access_token"):
        return redirect(url_for("pages.dashboard", roblox="token_failed"))

    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    scope = token.get("scope")
    token_type = token.get("token_type")
    expires_at = token.get("expires_at")

    userinfo = fetch_userinfo(access_token)
    if not userinfo:
        return redirect(url_for("pages.dashboard", roblox="userinfo_failed"))

    roblox_user_id = userinfo.get("sub") or userinfo.get("user_id") or userinfo.get("id")
    roblox_username = userinfo.get("preferred_username") or userinfo.get("name") or userinfo.get("username")
    if not roblox_user_id:
        return redirect(url_for("pages.dashboard", roblox="userinfo_missing"))

    # Verify Roblox account is in the division group
    div_id = int(user["division_group_id"])
    try:
        membership = check_user_in_group(int(roblox_user_id), div_id)
        in_group = bool(membership.get("in_group"))
    except Exception:
        in_group = False

    try:
        access_enc = encrypt_secret(access_token)
        refresh_enc = encrypt_secret(refresh_token) if refresh_token else None
    except ValueError:
        return redirect(url_for("pages.dashboard", roblox="encrypt_failed"))

    upsert_roblox_oauth(
        user_id=user["id"],
        roblox_user_id=int(roblox_user_id),
        roblox_username=str(roblox_username or "Unknown"),
        access_token_enc=access_enc,
        refresh_token_enc=refresh_enc,
        scope=scope,
        token_type=token_type,
        expires_at=expires_at,
        last_in_group=in_group,
    )

    if in_group:
        update_user_division_confirmed(user["id"], True)
        safe_audit(user.get("id"), "division_auto_verified", obj=str(user.get("id")),
                   details=json.dumps({"roblox_user_id": roblox_user_id}))
        return redirect(url_for("pages.dashboard", roblox="verified"))

    return redirect(url_for("pages.dashboard", roblox="not_in_group"))


@roblox_bp.route("/api/roblox/oauth/disconnect", methods=["POST"])
@login_required
def roblox_oauth_disconnect():
    user = get_current_user()
    gate = _require_division_leader(user, require_confirmed=False)
    if gate:
        return gate

    delete_roblox_oauth(user["id"])
    safe_audit(user.get("id"), "roblox_oauth_disconnected", obj=str(user.get("id")))
    return jsonify({"ok": True})


@roblox_bp.route("/api/roblox/remove", methods=["POST"])
@login_required
def roblox_remove():
    user = get_current_user()
    gate = _require_division_leader(user, require_confirmed=True)
    if gate:
        return gate

    data = get_json_body()
    roblox_ids = data.get("roblox_ids") or []
    if not isinstance(roblox_ids, list):
        return jsonify({"error": "roblox_ids must be a list"}), 400

    # Normalize IDs
    cleaned = []
    for rid in roblox_ids:
        try:
            uid = int(str(rid).strip())
            if uid > 0:
                cleaned.append(uid)
        except (TypeError, ValueError):
            continue
    cleaned = list(dict.fromkeys(cleaned))  # de-dupe, keep order

    if not cleaned:
        return jsonify({"error": "No valid roblox_ids provided"}), 400
    if len(cleaned) > ROBLOX_REMOVE_MAX:
        return jsonify({"error": f"Too many users. Max allowed: {ROBLOX_REMOVE_MAX}"}), 400
    if not get_oauth_config():
        return jsonify({"error": "Roblox OAuth not configured"}), 500

    conn = get_roblox_oauth(user["id"], include_secret=True)
    if not conn or not conn.get("access_token_enc"):
        return jsonify({"error": "Roblox account not connected"}), 400

    try:
        access_token = decrypt_secret(conn["access_token_enc"])
    except ValueError:
        return jsonify({"error": "Failed to decrypt Roblox connection. Reconnect your account."}), 400

    # Refresh token if expired
    expires_at = conn.get("expires_at")
    if expires_at and isinstance(expires_at, int) and expires_at <= int(time.time()):
        refresh_enc = conn.get("refresh_token_enc")
        if not refresh_enc:
            return jsonify({"error": "Roblox token expired. Reconnect your account."}), 401
        try:
            refresh_token = decrypt_secret(refresh_enc)
        except ValueError:
            return jsonify({"error": "Roblox token expired. Reconnect your account."}), 401
        refreshed = refresh_access_token(refresh_token)
        if not refreshed or not refreshed.get("access_token"):
            return jsonify({"error": "Roblox token refresh failed. Reconnect your account."}), 401
        access_token = refreshed.get("access_token")
        try:
            access_enc = encrypt_secret(access_token)
            refresh_enc_new = encrypt_secret(refreshed.get("refresh_token")) if refreshed.get("refresh_token") else refresh_enc
        except ValueError:
            return jsonify({"error": "Failed to update Roblox token. Reconnect your account."}), 500
        upsert_roblox_oauth(
            user_id=user["id"],
            roblox_user_id=conn["roblox_user_id"],
            roblox_username=conn["roblox_username"],
            access_token_enc=access_enc,
            refresh_token_enc=refresh_enc_new,
            scope=refreshed.get("scope") or conn.get("scope"),
            token_type=refreshed.get("token_type") or conn.get("token_type"),
            expires_at=refreshed.get("expires_at") or conn.get("expires_at"),
            last_in_group=conn.get("last_in_group", False),
        )

    group_id = int(user["division_group_id"])

    # Skip users no longer in the group
    to_remove = []
    skipped = []
    for uid in cleaned:
        membership = check_user_in_group(uid, group_id)
        if membership.get("in_group"):
            to_remove.append(uid)
        else:
            skipped.append({"id": uid, "reason": "not_in_group"})

    result = remove_users_from_group(access_token, group_id, to_remove)

    safe_audit(user.get("id"), "roblox_remove",
               obj=str(user.get("id")),
               details=json.dumps({
                   "group_id": group_id,
                   "requested": len(cleaned),
                   "removed": len(result.get("removed", [])),
                   "failed": len(result.get("failed", {})),
                   "skipped": len(skipped),
               }))

    return jsonify({
        "ok": True,
        "group_id": group_id,
        "requested": len(cleaned),
        "removed": result.get("removed", []),
        "failed": result.get("failed", {}),
        "skipped": skipped,
    })
