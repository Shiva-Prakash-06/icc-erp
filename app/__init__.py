"""ICC/OIA ERP application factory."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_wtf.csrf import CSRFError
from markupsafe import Markup
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import select_config
from app.database import csrf, db, limiter, login_manager, migrate


# The app shell files an installable PWA fetches before any session exists.
_UNAUTHENTICATED_PATHS = {"/sw.js", "/manifest.webmanifest", "/favicon.ico", "/offline"}


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

    # Every template renders datetimes campus-local through these filters;
    # storage stays UTC. See app/services/timeutil.py and audit finding B09.
    from app.services.timeutil import register_filters
    register_filters(app)

    # Money, counts and the status vocabulary are shared the same way, so a
    # convention lives in one module instead of in forty template
    # expressions. Audit findings P0-04, P1-07, P1-08.
    from app.services.formatting import register_filters as register_format_filters
    from app.services.glossary import register_globals as register_glossary
    from app.services.status import register_globals as register_status

    register_format_filters(app)
    register_status(app)
    register_glossary(app)

    # The four reserved states are read by the directory, both dashboards
    # and every work row. Exposing the mapping rather than pre-computing it
    # per view is what keeps a card and the counter above it in agreement.
    from app.services.hierarchy import STATE_LABELS, event_state

    app.jinja_env.globals["event_state"] = event_state
    app.jinja_env.globals["STATE_LABELS"] = STATE_LABELS

    # Server duration and query counts for the beta latency work (audit B13).
    # Off unless REQUEST_TIMING_ENABLED is set.
    from app.services.instrumentation import register_request_timing
    register_request_timing(app, db)

    # Role assignments are memoised per request; this resets that cache at
    # each request boundary. See app/services/authorization.py.
    from app.services.authorization import register_assignment_cache
    register_assignment_cache(app)

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
        from app.services.roles import role_context

        return {
            "primary_nav": build_nav(user, request.endpoint, request.blueprint),
            # Audit P1-10: the shell states which role and scope the screen
            # is being read through, so identical-looking directories stop
            # being unexplained.
            "role_context": role_context(user),
        }

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

    @app.context_processor
    def onboarding_shell():
        """First-run state for every authenticated page.

        Deliberately cheap: copy and flags only, no project queries. The one
        piece of onboarding data that needs a query -- the project the tour's
        "blockers" step navigates to -- is resolved in ``build_home`` where
        the project list is already in hand.
        """
        user = getattr(g, "user", None)
        if not user or getattr(user, "status", None) != "Approved":
            return {"onboarding": None}
        from app.services.roles import ONBOARDING_WELCOME, onboarding_audience, onboarding_tour_steps

        audience = onboarding_audience(user)
        # Two getting-started tasks leave no row behind, so the page that
        # satisfies them reports itself once when it loads.
        page_signal = {"erp.project_detail": "project_opened", "erp.audit": "audit_viewed"}.get(request.endpoint)
        return {
            "onboarding": {
                "audience": audience,
                "page_signal": page_signal,
                "welcome": ONBOARDING_WELCOME[audience],
                "steps": onboarding_tour_steps(audience),
                "seen": bool(user.onboarding_seen),
                "step": user.onboarding_step or 0,
            }
        }

    @app.before_request
    def load_request_context():
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        # Static assets and liveness checks need no account lookup. Browsers
        # fetch many assets concurrently; querying here exhausted the hosted
        # database pool and made even the login page fail to load.
        g.user = None
        if request.path.startswith(("/static/", "/healthz")) or request.path in _UNAUTHENTICATED_PATHS:
            return None
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None

        if request.path.startswith(("/static/", "/healthz", "/readyz", "/api/v1/public/", "/internal/jobs/", "/public/")) or request.path in _UNAUTHENTICATED_PATHS:
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
        # Every request, static assets included, is served by the Python
        # function on serverless -- there is no CDN layer in front of it -- so
        # these headers are what stop a phone re-downloading the CSS, fonts and
        # JS on every page load.
        if request.path.startswith("/static/ui/assets/"):
            # Vite output is content-hashed: a change produces a new filename.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        if request.path in {"/sw.js", "/manifest.webmanifest"}:
            # The worker and manifest must be revalidated or an update never
            # reaches an installed app.
            response.headers["Cache-Control"] = "no-cache"
        if request.path.startswith(("/api/v1/documents", "/api/v1/people", "/api/v1/audit-events", "/api/v1/offline-snapshot")):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Served from the root, not /static/, on purpose. A worker's scope defaults
    # to the directory it is served from, so /static/sw.js could only ever
    # control /static/* -- it never saw a single app navigation. Serving it here
    # gives it scope "/" with no Service-Worker-Allowed header needed. The
    # manifest is served alongside it so scope and start_url resolve against the
    # origin root too.
    @app.get("/sw.js")
    def service_worker():
        response = send_from_directory(app.static_folder, "sw.js")
        response.headers["Content-Type"] = "text/javascript; charset=utf-8"
        return response

    @app.get("/manifest.webmanifest")
    def web_manifest():
        response = send_from_directory(app.static_folder, "manifest.webmanifest")
        response.headers["Content-Type"] = "application/manifest+json"
        return response

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(Path(app.static_folder) / "brand", "favicon.ico")

    @app.get("/offline")
    def offline():
        return render_template("offline.html"), 200

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
        return _error_page(
            403,
            "You do not have access to this",
            "Your account does not carry the permission this screen needs. "
            "Access follows your role and campus assignment, not the link you followed.",
            guidance="If you should have access, ask an administrator to review your role assignment.",
        )

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/v1/"):
            return _problem(404, "Resource not found")
        return _error_page(
            404,
            "That page does not exist",
            "The address is wrong, or the record it pointed at has been removed or renamed.",
            guidance="Check the link, or use search to find the record by title or code.",
        )

    @app.errorhandler(PermissionError)
    def internal_permission_denied(error):
        return _problem(403, str(error))

    @app.errorhandler(CSRFError)
    def csrf_expired(error):
        # WTF_CSRF_TIME_LIMIT (2h) is shorter than PERMANENT_SESSION_LIFETIME
        # (8h), so a form left open past two hours fails here. Without this
        # handler that surfaced as a raw Werkzeug page.
        if request.path.startswith("/api/v1/"):
            return _problem(400, "CSRF token missing or expired")
        return _error_page(
            400,
            "This form expired before it was submitted",
            "For security, a form can only be submitted for two hours after the page is opened. "
            "Nothing was saved.",
            guidance="Open the record again and re-enter the change. Copy anything you typed first if the page is still open in another tab.",
        )

    @app.errorhandler(429)
    def rate_limited(error):
        if request.path.startswith("/api/v1/"):
            return _problem(429, "Too many requests")
        retry_seconds = getattr(error, "retry_after", None) or _retry_after_seconds(error)
        response = _error_page(
            429,
            "Too many requests from this account",
            "The platform limits how fast one account can load pages, to keep the service "
            "available for everybody. Nothing you submitted was lost or changed.",
            guidance="If this keeps happening during ordinary use, report it -- the limit is "
                     "meant to sit well above normal work.",
            retry_after=_humanise_seconds(retry_seconds),
        )
        if retry_seconds:
            response.headers["Retry-After"] = str(int(retry_seconds))
        return response

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def internal_error(error):
        # Roll back first: without this a failed request leaves the session
        # dirty for whatever reuses this worker or warm serverless instance.
        try:
            db.session.rollback()
        except Exception:
            app.logger.exception("Rollback after unhandled error failed")
        # Let Werkzeug's own HTTP exceptions (404, 403, ...) keep their status
        # and their dedicated handlers above.
        from werkzeug.exceptions import HTTPException

        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled application error")
        if request.path.startswith("/api/v1/"):
            return _problem(500, "Internal server error")
        return _error_page(
            500,
            "Something went wrong at our end",
            "The request could not be completed. The failure has been logged with the "
            "reference below; no partial change was saved.",
            guidance="Try again in a moment. If it keeps failing, report it with the request reference.",
        )

    return app


def _retry_after_seconds(error):
    """Seconds Flask-Limiter is willing to disclose, if any.

    The exception carries the window description rather than a number, so
    the value is only used when the limiter attached a real one; a guess
    printed as a deadline would be worse than no deadline.
    """
    description = getattr(error, "description", "") or ""
    for window, seconds in (("second", 1), ("minute", 60), ("hour", 3600), ("day", 86400)):
        if window in str(description):
            return seconds
    return None


def _humanise_seconds(seconds) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds < 3600:
        minutes = max(1, round(seconds / 60))
        return f"{minutes} minute" + ("s" if minutes != 1 else "")
    hours = max(1, round(seconds / 3600))
    return f"{hours} hour" + ("s" if hours != 1 else "")


def _error_page(status: int, heading: str, explanation: str, *, guidance: str = "", retry_after: str = ""):
    """Render an error inside the application shell.

    Falls back to plain text only if the template itself cannot render --
    an error page that raises is how a 500 becomes an infinite loop.
    """
    # `g.user` is populated by `load_request_context`, which is registered
    # *after* Flask-Limiter's own before_request hook. A rate-limited signed
    # in reader therefore reaches this function with `g.user` unset and used
    # to be handed the anonymous auth shell -- losing the identity and
    # navigation that audit finding P0-01 specifically asks the error page
    # to keep. The session is re-read here, on the error path only.
    from app.models.user import User

    user = getattr(g, "user", None)
    if user is None and session.get("user_id"):
        try:
            user = db.session.get(User, session["user_id"])
            g.user = user
        except Exception:  # pragma: no cover - a failing lookup must not mask the error
            user = None
    safe_url, safe_label = ("/", "Go to campuses") if user else ("/login", "Go to sign in")
    try:
        body = render_template(
            "error.html",
            status=status,
            heading=heading,
            explanation=explanation,
            guidance=guidance,
            retry_after=retry_after,
            safe_url=safe_url,
            safe_label=safe_label,
            request_id=getattr(g, "request_id", None),
            hide_sidebar=False,
        )
    except Exception:  # pragma: no cover - defensive
        return make_response((f"{heading}. {explanation}", status))
    return make_response((body, status))


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
