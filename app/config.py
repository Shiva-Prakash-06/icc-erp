"""Environment-driven application configuration.

Production deliberately has no implicit accounts, passwords, signing keys, or
database. Development defaults are isolated from the legacy v2 database.
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _database_url(default_name: str) -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        # SQLAlchemy no longer accepts Heroku's historic postgres:// prefix.
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(INSTANCE_DIR / default_name).resolve()}"


class BaseConfig:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
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
    BREACHED_PASSWORD_CHECK_MODE = os.getenv("BREACHED_PASSWORD_CHECK_MODE", "disabled")
    OPERATIONAL_RETENTION_DAYS = int(os.getenv("OPERATIONAL_RETENTION_DAYS", "2555"))
    AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
    REJECTED_APPLICATION_RETENTION_DAYS = int(os.getenv("REJECTED_APPLICATION_RETENTION_DAYS", "365"))
    OFFLINE_SNAPSHOT_TTL_SECONDS = int(os.getenv("OFFLINE_SNAPSHOT_TTL_SECONDS", "28800"))
    DEMONSTRATOR = os.getenv("DEMONSTRATOR", "true").lower() == "true"
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"


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
    DEMONSTRATOR = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not os.getenv("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if not os.getenv("DATABASE_URL"):
            missing.append("DATABASE_URL")
        if os.getenv("MIGRATION_ONLY", "false").lower() != "true":
            if os.getenv("DRIVE_VALIDATION_MODE", "live") != "live":
                missing.append("DRIVE_VALIDATION_MODE=live")
            if not (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")):
                missing.append("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")
            if not os.getenv("INTERNAL_JOB_AUDIENCE"):
                missing.append("INTERNAL_JOB_AUDIENCE")
            if not os.getenv("SCHEDULER_SERVICE_ACCOUNT"):
                missing.append("SCHEDULER_SERVICE_ACCOUNT")
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
