"""
Flask app creation and config
"""

import os
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
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
