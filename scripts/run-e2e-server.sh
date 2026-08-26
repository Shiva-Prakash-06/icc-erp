#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
database_path="$repo_root/instance/e2e-acceptance.db"
if [[ -n "${E2E_DATABASE_URL:-}" ]]; then
  export DATABASE_URL="$E2E_DATABASE_URL"
  if [[ "${ACCEPTANCE_RESET_POSTGRES:-0}" == "1" ]]; then
    .venv/bin/python - <<'PY'
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1"} or not (url.database or "").endswith("_test"):
    raise SystemExit("Refusing to reset a PostgreSQL database that is not an explicit local *_test target")
engine = create_engine(url)
with engine.begin() as connection:
    connection.execute(text("DROP SCHEMA public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))
PY
  fi
else
  rm -f "$database_path"
  export DATABASE_URL="sqlite:///$database_path"
fi
export FLASK_APP=run.py
export APP_ENV=testing
export TESTING=true
export DEMONSTRATOR=true
export ACCEPTANCE_SEED=1
export SECRET_KEY="acceptance-test-secret-key-only"
export PASSWORD_RESET_MIN_RESPONSE_MS=20

cd "$repo_root"
.venv/bin/flask db upgrade
.venv/bin/flask seed-acceptance
exec .venv/bin/flask run --host 127.0.0.1 --port 5010 --no-debugger --no-reload
