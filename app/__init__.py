"""
Flask app creation and config
"""

import logging
import os
from datetime import timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# absolute path to project root (works under any WSGI cwd)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(_PROJECT_ROOT, "templates"),
        static_folder=os.path.join(_PROJECT_ROOT, "static"),
    )

    # session config
    env_secret = os.getenv("SECRET_KEY")
    if env_secret:
        app.secret_key = env_secret
    else:
        # Secure fallback so we never ship with a static secret in production.
        # This will invalidate sessions on restart, but it's safer than a hardcoded key.
        app.secret_key = os.urandom(32)
        logger.warning("SECRET_KEY not set; using a random per-boot secret (sessions will reset on restart)")
    app.permanent_session_lifetime = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    secure_cookie_env = os.getenv("SESSION_COOKIE_SECURE")
    if secure_cookie_env is not None:
        app.config["SESSION_COOKIE_SECURE"] = secure_cookie_env.lower() in ("1", "true", "yes")
    else:
        app.config["SESSION_COOKIE_SECURE"] = not app.debug

    # CORS — only enable when explicitly configured
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
    if allowed_origins_env:
        allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        CORS(app, origins=allowed_origins)
    else:
        logger.warning("ALLOWED_ORIGINS not set; CORS disabled (same-origin only)")

    # warn on missing secrets so misconfigured deployments are obvious in logs
    if not os.getenv("API_KEY_HEADER"):
        logger.warning("API_KEY_HEADER not set; Rotector API calls will fail")
    if not os.getenv("DEPLOY_SECRET"):
        logger.warning("DEPLOY_SECRET not set; deploy endpoints are unprotected")

    # rate limiter
    from app.extensions import limiter
    limiter.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    # security headers on every response
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    # init database + admin account
    from app.database import init_db, ensure_admin
    init_db()
    ensure_admin()

    # kick off background fetch of SEA affiliates from Roblox API
    from app.affiliates import init_affiliates
    init_affiliates()

    from app.routes import register_routes
    register_routes(app)

    return app
