"""
Authentication handler
"""

import functools
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

from app.database import create_user, verify_user, get_user
from app.affiliates import get_sea_affiliates, get_affiliate_ids, is_affiliates_loaded, is_affiliates_loading
from app.utils import get_json_body, safe_audit

auth_bp = Blueprint("auth", __name__)

ROLE_OPTIONS = [
    "SEA Moderator",
    "Division Administrator",
    "Division Leader",
    "Moderator at a division",
    "Individual",
    "Other",
]


def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    """Decorator: require admin role."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "Authentication required"}), 401
        user = get_user(session["username"])
        if not user or not user["is_admin"]:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return wrapped


def get_current_user() -> dict | None:
    """Get the currently logged-in user from session."""
    if "username" not in session:
        return None
    return get_user(session["username"])


# ──────────────────────── Pages ────────────────────────

@auth_bp.route("/login")
def login_page():
    if "username" in session:
        return redirect(url_for("pages.index"))
    return render_template("login.html")


@auth_bp.route("/signup")
def signup_page():
    if "username" in session:
        return redirect(url_for("pages.index"))
    return render_template("signup.html", roles=ROLE_OPTIONS)


# ──────────────────────── API ────────────────────────

@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = get_json_body()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = verify_user(username, password)
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    session.permanent = True
    session["username"] = user["username"]
    session["is_admin"] = user["is_admin"]
    return jsonify({"ok": True, "user": _safe_user(user)})


@auth_bp.route("/api/auth/signup", methods=["POST"])
def api_signup():
    data = get_json_body()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    roles = data.get("roles") or []
    division_group_id = data.get("division_group_id")
    division_name = data.get("division_name")
    divisions_moderating = data.get("divisions_moderating") or []

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "Username must be 3-30 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not roles or not isinstance(roles, list):
        return jsonify({"error": "Select at least one role"}), 400

    # validate roles
    valid = set(ROLE_OPTIONS)
    for r in roles:
        if r not in valid:
            return jsonify({"error": f"Invalid role: {r}"}), 400

    # get the live affiliate IDs for validation
    affiliate_ids = get_affiliate_ids()

    # if Division Leader, require division info
    if "Division Leader" in roles:
        if not division_group_id or not division_name:
            return jsonify({"error": "Division Leaders must select their division"}), 400
        if affiliate_ids and int(division_group_id) not in affiliate_ids:
            return jsonify({"error": "Invalid division selected"}), 400

    # if Moderator at a division, require divisions
    if "Moderator at a division" in roles:
        if not divisions_moderating or not isinstance(divisions_moderating, list):
            return jsonify({"error": "Division Moderators must select their divisions"}), 400
        if affiliate_ids:
            for div in divisions_moderating:
                if int(div.get("id", 0)) not in affiliate_ids:
                    return jsonify({"error": f"Invalid division: {div.get('name', '?')}"}), 400

    # prevent creating 'admin' account via signup
    if username.lower() == "admin":
        return jsonify({"error": "That username is reserved"}), 400

    user = create_user(
        username=username,
        password=password,
        roles=roles,
        division_group_id=int(division_group_id) if division_group_id else None,
        division_name=division_name,
        divisions_moderating=divisions_moderating,
    )
    if not user:
        return jsonify({"error": "Username already taken"}), 409

    session.permanent = True
    session["username"] = user["username"]
    session["is_admin"] = user["is_admin"]

    safe_audit(user.get("id"), "user_signed_up", obj=str(user.get("id")))
    return jsonify({"ok": True, "user": _safe_user(user)})


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/api/auth/me")
def api_me():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401
    user = get_user(session["username"])
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 401
    return jsonify({"ok": True, "user": _safe_user(user)})


@auth_bp.route("/api/auth/affiliates")
def api_affiliates():
    affiliates = get_sea_affiliates()
    return jsonify({
        "affiliates": affiliates,
        "loaded": is_affiliates_loaded(),
        "loading": is_affiliates_loading(),
    })


def _safe_user(user: dict) -> dict:
    """Strip password from user dict for API responses."""
    return {
        "id": user["id"],
        "username": user["username"],
        "roles": user["roles"],
        "division_group_id": user["division_group_id"],
        "division_name": user["division_name"],
        "divisions_moderating": user["divisions_moderating"],
        "admin_confirmed": user["admin_confirmed"],
        "division_confirmed": user["division_confirmed"],
        "divisions_mod_confirmed": user["divisions_mod_confirmed"],
        "is_admin": user["is_admin"],
        "created_at": user["created_at"],
    }
