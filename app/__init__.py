"""ICC/OIA ERP application factory."""

from __future__ import annotations

import json
import hmac
import logging
import os
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, redirect, request, session, url_for
from markupsafe import Markup
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import select_config
from app.database import csrf, db, limiter, login_manager, migrate


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or select_config())
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if database_uri.startswith(("postgresql://", "postgresql+")):
        # PostgreSQL interprets a naive timestamp in the connection's session
        # timezone before storing it as timestamptz. Force every application
        # connection to UTC so legacy naive values and current aware values have
        # identical semantics on developer machines, CI, Cloud SQL, and native
        # deployments. SQLite has no equivalent connection option.
        engine_options = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
        connect_args = dict(engine_options.get("connect_args") or {})
        existing_options = connect_args.get("options", "")
        connect_args["options"] = f"{existing_options} -c timezone=UTC".strip()
        engine_options["connect_args"] = connect_args
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options
    if app.config.get("TESTING"):
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
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
    from app.blueprints.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    # New modular ERP interfaces are isolated behind their own blueprints.
    from app.blueprints.erp import erp_bp
    from app.blueprints.api_v1 import api_v1_bp
    from app.blueprints.internal_jobs import internal_jobs_bp
    from app.blueprints.public import public_bp

    app.register_blueprint(erp_bp)
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    app.register_blueprint(internal_jobs_bp)
    app.register_blueprint(public_bp)

    from app.cli import register_cli
    register_cli(app)

    @app.context_processor
    def ui_assets():
        """Resolve content-hashed Vite entries without requiring Node at runtime."""
        manifest_path = Path(app.static_folder) / "ui" / "manifest.json"

        def ui_asset(entry: str):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                filename = manifest.get(entry, {}).get("file")
                return url_for("static", filename=f"ui/{filename}") if filename else None
            except (OSError, ValueError, TypeError):
                return None

        def ui_styles(entry: str):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return [url_for("static", filename=f"ui/{filename}") for filename in manifest.get(entry, {}).get("css", [])]
            except (OSError, ValueError, TypeError):
                return []

        def ui_inline_styles(entry: str):
            """Inline the small, separately purged public stylesheet.

            The content comes only from the trusted, build-generated manifest
            and asset directory; no request or database value is interpolated
            into it. Inlining removes the public landing page's only
            render-blocking request and gives the mobile LCP gate useful
            headroom instead of relying on measurement variance.
            """
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                styles = []
                asset_root = (Path(app.static_folder) / "ui").resolve()
                for filename in manifest.get(entry, {}).get("css", []):
                    stylesheet_path = (asset_root / filename).resolve()
                    if asset_root not in stylesheet_path.parents:
                        raise ValueError("UI stylesheet resolved outside the asset directory")
                    styles.append(Markup(stylesheet_path.read_text(encoding="utf-8")))
                return styles
            except (OSError, ValueError, TypeError):
                return []

        return {
            "ui_asset": ui_asset,
            "ui_styles": ui_styles,
            "ui_inline_styles": ui_inline_styles,
        }

    @app.context_processor
    def authorization_helpers():
        """Expose has_permission to Jinja so navigation/page conditionals can
        gate on real scoped permissions instead of matching legacy role
        strings (base.html's nav previously did `g.user.role in [...]`)."""
        from app.services.authorization import has_any_permission, has_permission

        from app.services.vocabulary import vocabulary_display

        return {
            "has_permission": has_permission,
            "has_any_permission": has_any_permission,
            "vocabulary_display": vocabulary_display,
        }

    @app.context_processor
    def current_academic_year_label():
        from app.models.project import AcademicYear

        year = AcademicYear.query.filter_by(is_current=True).first()
        return {"current_academic_year_label": year.name if year else "—"}

    @app.context_processor
    def primary_navigation():
        """Single server-side registry rendered by the sidebar, mobile
        drawer, and command palette -- see PLAN.md "USC sidebar" finding."""
        user = getattr(g, "user", None)
        if not user:
            return {"primary_nav": []}
        from app.services.navigation import build_nav

        return {"primary_nav": build_nav(user, request.endpoint, request.blueprint)}

    @app.context_processor
    def shell_notifications():
        """Expose only the signed-in user's latest in-app notices to the shell."""
        user = getattr(g, "user", None)
        if not user:
            return {"shell_notifications": [], "shell_unread_count": 0}
        from app.models.production import Notification

        items = (
            Notification.query.filter_by(user_id=user.id)
            .order_by(Notification.created_at.desc())
            .limit(4)
            .all()
        )
        unread = Notification.query.filter_by(user_id=user.id, read_at=None).count()
        return {"shell_notifications": items, "shell_unread_count": unread}

    @app.before_request
    def load_request_context():
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None

        if request.path.startswith(("/static/", "/healthz", "/readyz", "/api/v1/public/", "/internal/jobs/", "/public/")):
            return None

        public = {"auth.login", "auth.register", "auth.logout", "auth.forgot_password", "auth.forgot_password_sent", "auth.recover_password"}
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
            "script-src 'self'; img-src 'self' data:; "
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

    @app.post("/internal/seed-acceptance")
    @csrf.exempt
    def seed_acceptance_internal():
        """One-time, token-gated acceptance fixture provisioning hook."""
        expected = os.getenv("ACCEPTANCE_SEED_TOKEN")
        supplied = request.headers.get("X-Acceptance-Seed-Token", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            return {"error": "Not found"}, 404
        if os.getenv("ACCEPTANCE_SEED") != "1":
            return {"error": "Acceptance seeding is disabled"}, 403
        command = app.cli.commands.get("seed-acceptance")
        if command is None:
            return {"error": "Seed command unavailable"}, 500
        command.callback()
        return {"status": "Acceptance fixtures ready"}

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
