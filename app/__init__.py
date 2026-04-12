"""
Flask app creation and config
"""

import logging
import os
from datetime import timedelta
from flask import Flask
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
    app.secret_key = os.getenv("SECRET_KEY", "rotection-dev-key-change-me")
    app.permanent_session_lifetime = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # CORS — restrict to declared origins when ALLOWED_ORIGINS is set
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
    if allowed_origins_env:
        allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        CORS(app, origins=allowed_origins)
    else:
        logger.warning("ALLOWED_ORIGINS not set; allowing all CORS origins")
        CORS(app)

    # warn on missing secrets so misconfigured deployments are obvious in logs
    if not os.getenv("API_KEY_HEADER"):
        logger.warning("API_KEY_HEADER not set; Rotector API calls will fail")
    if not os.getenv("DEPLOY_SECRET"):
        logger.warning("DEPLOY_SECRET not set; deploy endpoints are unprotected")

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
