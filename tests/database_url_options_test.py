import os

os.environ["TESTING"] = "true"

from app import create_app
from app.config import TestingConfig


class PostgresWithUrlOptions(TestingConfig):
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://u:p@db.example/app?options=-c%20role%3Dpostgres"


def test_options_in_the_database_url_are_kept_alongside_utc():
    """The UTC connect option used to replace the URL's own options."""
    app = create_app(PostgresWithUrlOptions)
    options = app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["options"]
    assert options == "-c role=postgres -c timezone=UTC"
