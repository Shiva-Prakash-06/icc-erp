from flask import current_app, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate(compare_type=True)
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def rate_limit_key() -> str:
    """Bill a signed-in request to the account, and only anonymous traffic
    to the IP.

    Audit finding P0-01: the default limit was one ``300 per hour`` bucket
    keyed by ``get_remote_address`` and **shared across every endpoint**
    (Flask-Limiter's default limits are not per-route). Every campus user
    is behind one NAT, so the whole institution shared five requests a
    minute, and the first route anyone loaded after the budget ran out --
    in practice ``/``, the destination of every sign-in redirect -- served
    a raw 429 while the window drained.

    ``session`` is read directly rather than via ``g.user`` because the
    limiter runs before the request-context loader that populates it, and
    it costs no database query.
    """
    user_id = session.get("user_id")
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address()}"


def _default_limits() -> str:
    # A working ERP session is far denser than five requests a minute: a
    # setup step is six page loads, and a roll call posts once per save.
    # The abuse surface (sign-in, password recovery, registration, the
    # write API) keeps its own much tighter explicit limits, which this
    # does not touch.
    return current_app.config.get("RATELIMIT_DEFAULT", "1200 per hour;120 per minute")


limiter = Limiter(key_func=rate_limit_key, default_limits=[_default_limits])


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite does not enforce FK constraints by default, so every
    ondelete=CASCADE/SET NULL declaration in the models is silently inert in
    dev/test unless this is turned on per-connection. No-op on Postgres."""
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
