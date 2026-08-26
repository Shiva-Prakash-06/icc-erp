#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
venv_dir="${VENV_DIR:-$repo_root/.venv}"
host="${HOST:-127.0.0.1}"
port="${PORT:-5000}"

if [[ "${APP_ENV:-development}" == "production" ]]; then
  echo "scripts/start.sh is for local development only. Use docs/NATIVE_DEPLOYMENT.md for production." >&2
  exit 1
fi

if [[ ! -x "$venv_dir/bin/python" ]]; then
  command -v python3 >/dev/null 2>&1 || {
    echo "python3 is required to start ICC ERP." >&2
    exit 1
  }
  echo "Creating local Python environment in $venv_dir"
  python3 -m venv "$venv_dir"
fi

python_bin="$venv_dir/bin/python"
flask_bin="$venv_dir/bin/flask"

if ! "$python_bin" -c 'import flask, flask_migrate, gunicorn' >/dev/null 2>&1; then
  echo "Installing Python dependencies"
  "$python_bin" -m pip install -r "$repo_root/requirements.txt"
fi

if [[ ! -f "$repo_root/.env" ]]; then
  cp "$repo_root/.env.example" "$repo_root/.env"
  echo "Created .env from .env.example"
fi

cd "$repo_root"
export FLASK_APP="${FLASK_APP:-run:app}"
export APP_ENV="${APP_ENV:-development}"

echo "Preparing local database"
"$flask_bin" db upgrade
"$flask_bin" bootstrap-reference-data

echo "ICC ERP is running at http://${host}:${port}"
exec "$flask_bin" run --host "$host" --port "$port" --debug
