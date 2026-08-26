"""Environment-driven application configuration.

Production deliberately has no implicit accounts, passwords, signing keys, or
database. Development defaults are isolated from the legacy v2 database.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _persisted_dev_secret_key() -> str:
    """Return a SECRET_KEY that stays stable across process restarts/workers
    when no SECRET_KEY env var is set (dev/staging only -- production always
    requires an explicit env var via ProductionConfig.validate()). Without
    this, every gunicorn worker would mint its own random key at import time,
    breaking session/CSRF validation whenever a request is served by a
    different worker than the one that issued it."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    key_path = INSTANCE_DIR / "dev_secret_key"
    try:
        existing = key_path.read_text().strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    generated = secrets.token_urlsafe(32)
    key_path.write_text(generated)
    return generated


def _database_url(default_name: str) -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        # Supabase's direct database endpoint is IPv6-only. Vercel Functions
        # currently need the IPv4-compatible session pooler. Preserve the
        # password embedded in DATABASE_URL and replace only its username,
        # host, and port when a pooler host is configured.
        pooler_host = os.getenv("SUPABASE_POOLER_HOST", "").strip()
        direct_match = re.match(
            r"^(?P<scheme>postgres(?:ql)?(?:\+psycopg)?://)"
            r"(?P<username>[^:@/]+):(?P<password>[^@]+)@"
            r"db\.(?P<project_ref>[a-z0-9]+)\.supabase\.co(?::\d+)?"
            r"(?P<suffix>/.*)$",
            value,
            flags=re.IGNORECASE,
        )
        if pooler_host and direct_match:
            value = (
                "postgresql+psycopg://"
                f"postgres.{direct_match.group('project_ref')}:"
                f"{direct_match.group('password')}@{pooler_host}:5432"
                f"{direct_match.group('suffix')}"
            )
        # Use the installed Psycopg 3 driver explicitly. SQLAlchemy otherwise
        # maps a plain postgresql:// URL to the legacy psycopg2 package, which
        # is intentionally not part of the runtime dependency set.
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://"):]
        return value
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(INSTANCE_DIR / default_name).resolve()}"


class BaseConfig:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY") or _persisted_dev_secret_key()
    SQLALCHEMY_DATABASE_URI = _database_url("erp_development.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    WTF_CSRF_TIME_LIMIT = 7200
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    DRIVE_VALIDATION_MODE = os.getenv("DRIVE_VALIDATION_MODE", "mock")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    INTERNAL_JOB_AUDIENCE = os.getenv("INTERNAL_JOB_AUDIENCE")
    SCHEDULER_SERVICE_ACCOUNT = os.getenv("SCHEDULER_SERVICE_ACCOUNT")
    TASKS_SERVICE_ACCOUNT = os.getenv("TASKS_SERVICE_ACCOUNT")
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    GCP_REGION = os.getenv("GCP_REGION", "asia-south1")
    CLOUD_TASKS_QUEUE = os.getenv("CLOUD_TASKS_QUEUE")
    INTERNAL_JOB_BASE_URL = os.getenv("INTERNAL_JOB_BASE_URL")
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_ADDRESS = os.getenv("SMTP_FROM_ADDRESS")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    NOTIFICATION_EMAIL_MODE = os.getenv("NOTIFICATION_EMAIL_MODE", "disabled")
    PASSWORD_RESET_MIN_RESPONSE_MS = int(os.getenv("PASSWORD_RESET_MIN_RESPONSE_MS", "150"))
    BREACHED_PASSWORD_CHECK_MODE = os.getenv("BREACHED_PASSWORD_CHECK_MODE", "disabled")
    OPERATIONAL_RETENTION_DAYS = int(os.getenv("OPERATIONAL_RETENTION_DAYS", "2555"))
    AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
    REJECTED_APPLICATION_RETENTION_DAYS = int(os.getenv("REJECTED_APPLICATION_RETENTION_DAYS", "365"))
    OFFLINE_SNAPSHOT_TTL_SECONDS = int(os.getenv("OFFLINE_SNAPSHOT_TTL_SECONDS", "28800"))
    DEMONSTRATOR = os.getenv("DEMONSTRATOR", "true").lower() == "true"
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"
    # Explicit opt-in for hosted acceptance testing before external providers
    # (Google Drive, GCP jobs, SMTP, breach checks) are connected.
    DISABLE_EXTERNAL_INTEGRATIONS = os.getenv("DISABLE_EXTERNAL_INTEGRATIONS", "false").lower() == "true"
    GOOGLE_DRIVE_REPOSITORY_ROOT_ID = os.getenv("GOOGLE_DRIVE_REPOSITORY_ROOT_ID")
    SUPABASE_POOLER_HOST = os.getenv("SUPABASE_POOLER_HOST")
    AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD = os.getenv("AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD")
    UPLOAD_SESSION_STORAGE_URI = os.getenv("UPLOAD_SESSION_STORAGE_URI", "memory://")
    UPLOAD_CHUNK_SIZE_BYTES = int(os.getenv("UPLOAD_CHUNK_SIZE_BYTES", str(8 * 1024 * 1024)))
    UPLOAD_MAX_TOTAL_BYTES = int(os.getenv("UPLOAD_MAX_TOTAL_BYTES", str(100 * 1024 * 1024)))


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-only-key"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    APP_ENV = "production"
    DEMONSTRATOR = os.getenv("DEMONSTRATOR", "false").lower() == "true"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def validate(cls) -> None:
        missing = []
        migration_only = os.getenv("MIGRATION_ONLY", "false").lower() == "true"
        if not os.getenv("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if not os.getenv("DATABASE_URL"):
            missing.append("DATABASE_URL")
        # An in-memory limiter only rate-limits within a single process, so
        # it silently stops enforcing anything once Cloud Run scales past one
        # instance. Production must use a shared store (managed Redis).
        # See PLAN.md "Additional release blockers" finding.
        if not migration_only and os.getenv("RATELIMIT_STORAGE_URI", "memory://").startswith("memory://"):
            missing.append("RATELIMIT_STORAGE_URI (must not be memory:// in production)")
        if not migration_only and not os.getenv("DISABLE_EXTERNAL_INTEGRATIONS", "false").lower() == "true":
            if os.getenv("DRIVE_VALIDATION_MODE", "live") != "live":
                missing.append("DRIVE_VALIDATION_MODE=live")
            if not (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")):
                missing.append("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")
            if not os.getenv("INTERNAL_JOB_AUDIENCE"):
                missing.append("INTERNAL_JOB_AUDIENCE")
            if not os.getenv("SCHEDULER_SERVICE_ACCOUNT"):
                missing.append("SCHEDULER_SERVICE_ACCOUNT")
            if not os.getenv("AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD"):
                missing.append("AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD")
            for name in ("TASKS_SERVICE_ACCOUNT", "GCP_PROJECT_ID", "CLOUD_TASKS_QUEUE", "INTERNAL_JOB_BASE_URL"):
                if not os.getenv(name):
                    missing.append(name)
            if os.getenv("BREACHED_PASSWORD_CHECK_MODE", "live") != "live":
                missing.append("BREACHED_PASSWORD_CHECK_MODE=live")
            if os.getenv("NOTIFICATION_EMAIL_MODE", "smtp") == "smtp":
                for name in ("SMTP_HOST", "SMTP_FROM_ADDRESS", "SMTP_PASSWORD"):
                    if not os.getenv(name):
                        missing.append(name)
        if missing:
            raise RuntimeError(
                "Production configuration is incomplete: " + ", ".join(missing)
            )


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def select_config():
    if os.getenv("TESTING", "false").lower() == "true":
        return TestingConfig
    name = os.getenv("APP_ENV", "development").lower()
    config = CONFIGS.get(name, DevelopmentConfig)
    if config is ProductionConfig:
        config.validate()
    return config
