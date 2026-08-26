# Native Deployment Without Docker

The application does not require Docker at build time or runtime. The supported native production stack is Python 3.12, PostgreSQL 16, Redis 7 or 8, Gunicorn, and a TLS reverse proxy or managed ingress. Node.js is required only on the build machine to compile the checked-in frontend assets.

## Build and verify the release

From a reviewed release commit:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
npm ci
bash scripts/build-native-release.sh dist/icc-erp-native.tar.gz
bash scripts/verify-native-release.sh dist/icc-erp-native.tar.gz
.venv/bin/pip-audit --local --format cyclonedx-json --output dist/icc-erp-native-sbom.cdx.json
```

The build emits a compressed runtime allow-list and a portable SHA-256 file. It contains only `app/`, `migrations/`, `run.py`, `requirements.txt`, and `MANIFEST.sha256`; it excludes instances, databases, credentials, secrets, backups, tests, Node dependencies, frontend source, Terraform, and repository metadata.

## Install a release

Extract the verified archive into a versioned, non-writable application directory and create a dedicated virtual environment:

```bash
mkdir -p /opt/icc-erp/releases/RELEASE_ID
tar -xzf icc-erp-native.tar.gz -C /opt/icc-erp/releases/RELEASE_ID
python3.12 -m venv /opt/icc-erp/venv-RELEASE_ID
/opt/icc-erp/venv-RELEASE_ID/bin/pip install --requirement /opt/icc-erp/releases/RELEASE_ID/requirements.txt
/opt/icc-erp/venv-RELEASE_ID/bin/pip check
/opt/icc-erp/venv-RELEASE_ID/bin/python -m compileall -q /opt/icc-erp/releases/RELEASE_ID/app
```

Run the process under a dedicated unprivileged service account. Give that account read access to the release and approved secret references, but not to source-data exports, backups, or administrator home directories.

## Required production configuration

Supply secrets through the operating system's secret manager or a mode-0600 service environment file. Never add them to the archive or source tree.

Required serving settings include:

- `APP_ENV=production`
- a long random `SECRET_KEY`
- a PostgreSQL `DATABASE_URL`
- a shared Redis `RATELIMIT_STORAGE_URI`
- live Drive service-account configuration
- Scheduler/Tasks OIDC audience and service identities
- GCP job/task settings when those integrations are enabled
- `BREACHED_PASSWORD_CHECK_MODE=live`
- approved SMTP settings when `NOTIFICATION_EMAIL_MODE=smtp`

Production validation fails closed if mandatory serving configuration is absent or the limiter uses process-local memory.

## Migrate and serve

Run migrations as a separate one-shot process before starting the new release:

```bash
APP_ENV=production MIGRATION_ONLY=true \
  /opt/icc-erp/venv-RELEASE_ID/bin/flask --app run:app db upgrade
APP_ENV=production MIGRATION_ONLY=true \
  /opt/icc-erp/venv-RELEASE_ID/bin/flask --app run:app db check
```

Start Gunicorn behind HTTPS ingress or a reverse proxy that supplies trusted forwarded scheme and host headers:

```bash
cd /opt/icc-erp/releases/RELEASE_ID
/opt/icc-erp/venv-RELEASE_ID/bin/gunicorn \
  --bind 127.0.0.1:8080 \
  --workers 2 --threads 4 --timeout 60 \
  --access-logfile - --error-logfile - run:app
```

Use systemd, launchd, supervisord, or an equivalent service manager for restart policy, resource limits, environment injection, log capture, and graceful shutdown. Do not expose Gunicorn directly to the public internet.

## Acceptance and rollback

Confirm `/healthz` and `/readyz`, authentication, publication privacy, Redis-backed rate-limit keys, audit writes, SMTP/Drive integrations, and scheduled jobs before routing traffic. Keep the prior release directory and virtual environment intact during canary. Roll back traffic and the process symlink to the prior release if a runbook threshold is crossed; do not downgrade the database unless that exact downgrade was rehearsed and approved.

The institutional pilot, recovery, security, accessibility, load, and four-signature gates in `PRODUCTION_ACCEPTANCE_RECORD.md` still apply to native deployments.
