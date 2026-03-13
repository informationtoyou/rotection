"""
Serves HTML templates for the web UI
"""

from flask import Blueprint, render_template, redirect, url_for, session

from app.routes.auth import login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
@login_required
def index():
    return render_template("index.html")
