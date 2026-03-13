"""
Route registration
"""

from app.routes.pages import pages_bp
from app.routes.scan import scan_bp
from app.routes.scans import scans_bp
from app.routes.deploy import deploy_bp
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp


def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(scans_bp)
    app.register_blueprint(deploy_bp)
    app.register_blueprint(admin_bp)
