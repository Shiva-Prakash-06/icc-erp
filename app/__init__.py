"""ICC/OIA ERP application factory."""

from __future__ import annotations

import uuid

from flask import Flask, g, jsonify, redirect, request, session, url_for
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import select_config
from app.database import csrf, db, limiter, login_manager, migrate


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or select_config())
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Importing models registers all tables with SQLAlchemy/Alembic. Schema
    # creation is intentionally not performed during normal application startup.
    from app import models as _models  # noqa: F401
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id)) if user_id else None

    from app.blueprints.auth import auth_bp
    from app.blueprints.campus import campus_bp
    from app.blueprints.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(campus_bp)

    # New modular ERP interfaces are isolated behind their own blueprints.
    from app.blueprints.erp import erp_bp
    from app.blueprints.api_v1 import api_v1_bp
    from app.blueprints.internal_jobs import internal_jobs_bp

    app.register_blueprint(erp_bp)
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    app.register_blueprint(internal_jobs_bp)

    from app.cli import register_cli
    register_cli(app)

    @app.before_request
    def load_request_context():
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None

        if request.path.startswith(("/static/", "/healthz", "/readyz", "/api/v1/public/", "/internal/jobs/")):
            return None

        public = {"auth.login", "auth.register", "auth.logout", "auth.forgot_password", "auth.recover_password"}
        if not g.user and request.endpoint not in public:
            if request.path.startswith("/api/v1/"):
                return _problem(401, "Authentication required")
            return redirect(url_for("auth.login"))

        if not g.user:
            return None
        if g.user.is_archived or session.get("session_version", g.user.session_version) != g.user.session_version:
            session.clear()
            if request.path.startswith("/api/v1/"):
                return _problem(401, "Session expired")
            return redirect(url_for("auth.login"))
        if g.user.needs_password_reset and request.endpoint not in {
            "auth.reset_password",
            "auth.logout",
        }:
            return redirect(url_for("auth.reset_password"))
        if g.user.status == "Pending" and request.endpoint not in {
            "auth.pending_approval",
            "auth.logout",
        }:
            return redirect(url_for("auth.pending_approval"))
        if g.user.status == "Approved" and request.endpoint == "auth.pending_approval":
            return redirect(url_for("dashboard.index"))
        if app.config.get("APP_ENV") == "production" and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.blueprint == "campus" or request.endpoint == "dashboard.generate_report":
                if request.path.startswith("/api/"):
                    return _problem(410, "Legacy mutation retired")
                return ("This legacy workflow is read-only in production. Use ERP Operations or /api/v1.", 410)
        return None

    @app.after_request
    def secure_response(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith(("/erp/restricted", "/api/v1/documents", "/api/v1/people", "/api/v1/audit-events", "/api/v1/offline-snapshot")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "icc-oia-erp"}

    @app.get("/readyz")
    def readyz():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            app.logger.exception("Readiness database check failed")
            return {"status": "not-ready", "service": "icc-oia-erp"}, 503
        return {"status": "ready", "service": "icc-oia-erp"}

    @app.errorhandler(403)
    def forbidden(error):
        if request.path.startswith("/api/v1/"):
            return _problem(403, "Access denied")
        return ("Access denied", 403)

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/v1/"):
            return _problem(404, "Resource not found")
        return ("Not found", 404)

    @app.errorhandler(PermissionError)
    def internal_permission_denied(error):
        return _problem(403, str(error))

    return app


def _problem(status: int, detail: str):
    response = jsonify(
        {
            "type": "about:blank",
            "title": detail,
            "status": status,
            "detail": detail,
            "instance": request.path,
            "request_id": getattr(g, "request_id", None),
        }
    )
    response.status_code = status
    response.content_type = "application/problem+json"
    return response
