import os

os.environ["TESTING"] = "true"

from app import create_app
from app.config import TestingConfig
from app.database import db


class UnreachableLimiterStore(TestingConfig):
    RATELIMIT_ENABLED = True
    # `.invalid` never resolves, so this fails the way a deleted Redis does.
    RATELIMIT_STORAGE_URI = "redis://limiter-store.invalid:6379"


def test_pages_still_load_when_the_limiter_store_is_unreachable():
    """The hosted Redis was deleted once and every page, /healthz included,
    returned 500. Losing the limiter store must not take the site down."""
    app = create_app(UnreachableLimiterStore)
    with app.app_context():
        db.create_all()
        client = app.test_client()
        for path in ("/healthz", "/readyz", "/login"):
            assert client.get(path).status_code == 200, path
        db.session.remove()
        db.drop_all()
