import os
from unittest import mock

from app.config import shared_redis_uri


def test_integration_redis_url_wins_over_the_old_hand_set_values():
    env = {
        "BETA_REDIS_URL": "rediss://new-store.example:6379",
        "RATELIMIT_STORAGE_URI": "rediss://deleted-store.example:6379",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        assert shared_redis_uri("RATELIMIT_STORAGE_URI") == env["BETA_REDIS_URL"]
        assert shared_redis_uri("UPLOAD_SESSION_STORAGE_URI") == env["BETA_REDIS_URL"]


def test_hand_set_value_and_memory_default_still_apply_without_it():
    with mock.patch.dict(os.environ, {"RATELIMIT_STORAGE_URI": "redis://own:6379"}, clear=True):
        assert shared_redis_uri("RATELIMIT_STORAGE_URI") == "redis://own:6379"
        assert shared_redis_uri("UPLOAD_SESSION_STORAGE_URI") == "memory://"
