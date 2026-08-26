import os
import unittest

from limits.storage import storage_from_string

from app import create_app
from app.config import ProductionConfig


REQUIRED_ENV = {
    "SECRET_KEY": "prod-secret",
    "DATABASE_URL": "postgresql://user:pass@host/db",
    "RATELIMIT_STORAGE_URI": "redis://redis:6379/0",
    "MIGRATION_ONLY": "true",
}


class ProductionConfigValidationTestCase(unittest.TestCase):
    """Production startup must fail fast on missing infra config rather than
    silently degrading -- see PLAN.md "Additional release blockers" finding
    about the in-memory rate limiter."""

    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in list(REQUIRED_ENV) + ["APP_ENV"]}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _set_env(self, overrides):
        os.environ.update(REQUIRED_ENV)
        os.environ.update(overrides)

    def test_passes_with_complete_configuration(self):
        self._set_env({})
        ProductionConfig.validate()

    def test_serving_fails_when_ratelimit_storage_is_in_memory(self):
        self._set_env({"RATELIMIT_STORAGE_URI": "memory://", "MIGRATION_ONLY": "false"})
        with self.assertRaises(RuntimeError) as context:
            ProductionConfig.validate()
        self.assertIn("RATELIMIT_STORAGE_URI", str(context.exception))

    def test_serving_fails_when_ratelimit_storage_uri_unset(self):
        self._set_env({"MIGRATION_ONLY": "false"})
        os.environ.pop("RATELIMIT_STORAGE_URI", None)
        with self.assertRaises(RuntimeError) as context:
            ProductionConfig.validate()
        self.assertIn("RATELIMIT_STORAGE_URI", str(context.exception))

    def test_migration_job_does_not_require_rate_limiter(self):
        self._set_env({"MIGRATION_ONLY": "true"})
        os.environ.pop("RATELIMIT_STORAGE_URI", None)
        ProductionConfig.validate()

    def test_shared_redis_limiter_backend_is_installed(self):
        storage = storage_from_string("redis://:password@127.0.0.1:6379/0")
        self.assertEqual(storage.__class__.__name__, "RedisStorage")

    def test_postgresql_connections_are_forced_to_utc(self):
        class PostgreSQLTestConfig:
            TESTING = True
            SECRET_KEY = "test-only-key"
            SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://user:pass@127.0.0.1/example_test"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False

        app = create_app(PostgreSQLTestConfig)
        options = app.config["SQLALCHEMY_ENGINE_OPTIONS"]
        self.assertTrue(options["pool_pre_ping"])
        self.assertIn("timezone=UTC", options["connect_args"]["options"])

    def test_fails_when_secret_key_missing(self):
        self._set_env({})
        os.environ.pop("SECRET_KEY", None)
        with self.assertRaises(RuntimeError) as context:
            ProductionConfig.validate()
        self.assertIn("SECRET_KEY", str(context.exception))


if __name__ == "__main__":
    unittest.main()
