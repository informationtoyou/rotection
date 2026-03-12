"""
Flask app creation and config
"""

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
    CORS(app)

    from app.routes import register_routes
    register_routes(app)

    return app
