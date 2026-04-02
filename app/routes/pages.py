"""
Serves HTML templates for the web UI
"""

from flask import Blueprint, render_template, redirect, url_for, session

from app.routes.auth import login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    """Home route - show landing if not logged in, dashboard if logged in."""
    if "username" in session:
        return render_template("index.html")
    return render_template("landing.html")


@pages_bp.route("/landing")
def landing():
    """Public landing/hero page."""
    return render_template("landing.html")


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    """Protected dashboard route."""
    return render_template("index.html")
