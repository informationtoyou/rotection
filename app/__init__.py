"""
Flask app creation and config
"""

import os
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# absolute path to project root (works under any WSGI cwd)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


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

    CORS(app)

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
