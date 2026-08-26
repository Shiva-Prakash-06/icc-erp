# ICC/OIA ERP

This repository upgrades `icc-platform-2` into the modular Flask demonstrator defined by the authoritative [production PRD](../ICC_ERP_Production_PRD_and_Implementation_Plan.md).

> **Status:** Production release candidate; institutional production approval is pending. The repository quality gates are documented in `docs/FINAL_IMPLEMENTATION_AUDIT.md`. Do not use live operational or sensitive IGP data until the staging, pilot, recovery, security-review, and four-approver gates in `docs/PRODUCTION_ACCEPTANCE_RECORD.md` are signed.

## What is implemented

- Environment-driven Flask application factory; no account or password is created at startup.
- SQLAlchemy 2.x-compatible modular domain model and Alembic migrations.
- PostgreSQL configuration, local SQLite test/demo isolation, a Docker-free native release artifact, and optional Cloud Build/Terraform scaffolding for Cloud Run and Cloud SQL.
- Separate people and accounts; organization units, wings, scoped/effective role assignments, projects, components, sessions, teams, tasks, checklists, documents, budgets, feedback, imports, audits, and report snapshots.
- Lifecycle rules with optimistic concurrency and closure blockers.
- Staged, checksum-idempotent imports for the supplied event summary, Coffee Meet & Greet folder, and Summer School checklist.
- `/api/v1` JSON resources with cursor pagination, RFC 7807 errors, project scoping, workflow decisions, Drive-link validation, report exports, and moderated public token feedback.
- Production completion domains for governance, recruitment, cohorts, risks, immutable decision histories, aggregate attendance, notifications, report jobs, and sensitive-access audit.
- OIDC-protected Scheduler/Tasks endpoints, live Drive metadata mode, SMTP delivery attempts, account recovery, and encrypted read-only offline snapshots.
- Local UI assets and accessible public analytics; CSRF, request limits, login throttling/lockout, security headers, and a safe static-only service worker.

## Local setup

The easiest local start is one command. It creates `.venv` and `.env` when
needed, installs Python dependencies, applies migrations, loads reference
data, and starts the development server at <http://127.0.0.1:5000>:

```bash
./scripts/start.sh
```

Create the first administrator explicitly; values are supplied through the environment and are never committed:

```bash
BOOTSTRAP_ADMIN_USERNAME='your.name' \
BOOTSTRAP_ADMIN_EMAIL='your.email@example.org' \
BOOTSTRAP_ADMIN_PASSWORD='a-long-one-time-password' \
.venv/bin/flask --app run:app bootstrap-admin
```

To use Docker Compose instead, copy `.env.example` to `.env` and run:

```bash
docker compose up --build
```

Docker is not required. For a checksum-verifiable native production artifact and PostgreSQL/Redis/Gunicorn deployment, follow [Native Deployment Without Docker](docs/NATIVE_DEPLOYMENT.md).

## Supplied-data demonstrator

Use a separate database. Never point this command at production:

```bash
export APP_ENV=development
export DEMONSTRATOR=true
export DATABASE_URL='sqlite:////absolute/path/to/instance/erp_demonstrator.db'
.venv/bin/flask --app run:app db upgrade
.venv/bin/flask --app run:app demo-import-supplied
```

The import sequence is intentionally fixed: events summary → Coffee Meet folder → Summer School checklist. Every source row retains file, sheet, row, checksum, normalized data, validation messages, and target public identifier.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/pip check
.venv/bin/coverage run --branch --source=app/services -m pytest -q
.venv/bin/coverage report --fail-under=80
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
npm run typecheck
npm run build:ui
npm run check:assets
npm run test:e2e:twice
npm run test:lighthouse
bash scripts/build-native-release.sh dist/icc-erp-native.tar.gz
bash scripts/verify-native-release.sh dist/icc-erp-native.tar.gz
```

The production Terraform configuration requires Terraform 1.7 or newer.

## Production invariants

- Production requires `APP_ENV=production`, `SECRET_KEY`, and `DATABASE_URL`; startup fails closed when either secret is missing.
- Production begins with a fresh migrated PostgreSQL database.
- Sensitive passport, visa, and C-Form files remain in restricted Google Drive. This app stores requirement status, verification metadata, classification, and a restricted reference only.
- Drive validation never broadens sharing.
- Synthetic/example data and demonstrator accounts are not part of normal startup or migration.
- Completing a project requires modeled closure requirements or faculty-audited waivers.

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) before any pilot or deployment.
