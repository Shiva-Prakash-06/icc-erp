# ICC/OIA ERP

This repository upgrades `icc-platform-2` into the modular Flask demonstrator defined by the authoritative [production PRD](../ICC_ERP_Production_PRD_and_Implementation_Plan.md).

> **Status:** Demonstrator—Not Production. Do not use it for live operational or sensitive IGP data until the PRD's security, migration, pilot, recovery, and four-approver release gates have passed.

## What is implemented

- Environment-driven Flask application factory; no account or password is created at startup.
- SQLAlchemy 2.x-compatible modular domain model and Alembic migrations.
- PostgreSQL configuration, local SQLite test/demo isolation, Docker, Cloud Build, and Terraform scaffolding for Cloud Run and Cloud SQL.
- Separate people and accounts; organization units, wings, scoped/effective role assignments, projects, components, sessions, teams, tasks, checklists, documents, budgets, feedback, imports, audits, and report snapshots.
- Lifecycle rules with optimistic concurrency and closure blockers.
- Staged, checksum-idempotent imports for the supplied event summary, Coffee Meet & Greet folder, and Summer School checklist.
- `/api/v1` JSON resources with cursor pagination, RFC 7807 errors, project scoping, Drive-link validation, and public token feedback.
- Local Bootstrap, icons, and Chart.js assets; CSRF, request limits, login throttling/lockout, security headers, and a safe static-only service worker.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/flask --app run:app db upgrade
.venv/bin/flask --app run:app bootstrap-reference-data
```

Create the first administrator explicitly; values are supplied through the environment and are never committed:

```bash
BOOTSTRAP_ADMIN_USERNAME='your.name' \
BOOTSTRAP_ADMIN_EMAIL='your.email@example.org' \
BOOTSTRAP_ADMIN_PASSWORD='a-long-one-time-password' \
.venv/bin/flask --app run:app bootstrap-admin
```

Start the app:

```bash
.venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 --threads 4 run:app
```

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
.venv/bin/python -m unittest discover -s tests -p '*test.py' -v
.venv/bin/pip check
terraform fmt -check -recursive
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
