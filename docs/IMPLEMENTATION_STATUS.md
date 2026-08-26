# Implementation Status

Baseline: v2 commit `111f1ae`

Audit date: 2026-08-11

Status: **Software release candidate; public-production acceptance pending**

Always obtain the migration head from the release commit with `flask --app run:app db heads`. The head observed for this audit is `27b173810b30`; the runbook deliberately does not hard-code it as a future release target.

The validated ICC, USC, IGP, privacy, authorization, and UX defects are implemented. The repository meets the plan's configured service coverage threshold and its 90% critical-workflow threshold. Public traffic is still prohibited until the production acceptance record contains the required staging, security, recovery, pilot, and stakeholder evidence.

## Implemented in the repository

- Scoped campus/program/year/wing context, read-only campus hierarchy screens, and a single responsive project navigation.
- Neutral first-time password setup, dedicated reset success and forgot-password confirmation screens, session rotation, lockout, and anti-enumeration behavior.
- Controlled vocabularies and visibly labelled, accessible inputs for the previously ambiguous operational forms.
- Role-aware Mission Control, one navigation registry, demo-data warnings, My Account & Activity, and reliable public-to-ERP return navigation.
- Nullable IGP registration numbers, person-public-ID enrollment, scoped participant search/creation, and server-enforced buddy eligibility.
- A distinct scoped `approve_operational_requests` permission, shared HTML/API state machine, recorded maker/submitter provenance, and maker/checker separation.
- Explicit `Private → Pending → Published → Withdrawn` publication governance. Public events, documents, reports, and analytics use positive allow-lists and exclude cancelled, unpublished, unapproved, Internal, Restricted, or missing content.
- Accessible public analytics whose canvases and exact data tables are generated from the same aggregate-only payload.
- Production Redis enforcement, OIDC-protected job endpoints, native Gunicorn deployment, optional immutable-image Terraform, per-secret IAM, Cloud SQL/Redis networking, and fail-closed production configuration.
- A checksum-verifiable native runtime allow-list excludes credentials, secrets, databases, backups, tests, Terraform, frontend source, and dependency trees. Docker remains optional for remote Cloud Run packaging and is not needed locally.

## Verified repository evidence

- Python: `163 passed` on PostgreSQL 16; service-layer branch coverage `83%` (required `80%`). Critical services: authorization `94%`, identity `100%`, job authentication `100%`, passwords `90%`, publication `94%`, and operations `95%`.
- Browser acceptance: `163 passed` twice consecutively on independently reset PostgreSQL 16 acceptance databases with retries disabled, covering Chromium, Firefox, WebKit, mobile viewports, JavaScript-disabled, reduced motion, forced colors, zoom, visual, accessibility, role, scope, and disclosure checks.
- Lighthouse: desktop and mobile performance, accessibility, and best-practices scores all `1.00`; CLS `0`; mobile LCP approximately `1.06 s`; TBT `0 ms`.
- UI: TypeScript, production build, and asset budgets pass. Application CSS is `46,026 B`, public CSS `15,468 B`, and shared JavaScript `6,719 B`.
- Fresh SQLite and PostgreSQL 16 Alembic upgrades and drift checks pass at `27b173810b30`; populated legacy reconciliation tests pass. PostgreSQL testing exposed and corrected UTC timestamp and numeric-display portability defects.
- Python and npm dependency audits report no known vulnerabilities; `pip check`, Bandit high-severity gate, Terraform formatting/validation, tracked-secret checks, and repository whitespace checks pass.
- The Docker-free artifact is `433 KB`, contains 301 verified runtime files, has a portable SHA-256, and has a CycloneDX inventory of 102 installed components with zero reported vulnerabilities. A two-worker Gunicorn production rehearsal passed health, PostgreSQL readiness, public/login, security-header, and Redis-backed rate-limit checks.

## Remaining release evidence

The following evidence cannot be inferred from application tests and must remain blocking:

- Authenticated target-environment provisioning and either the native artifact SHA-256 or, for the optional Cloud Run path, an immutable remotely built image digest.
- Signed workflow, vocabulary, data dictionary, report format, and role/scope decisions.
- Live Drive, SMTP, Cloud Tasks, Scheduler, OIDC, retry, and dead-letter validation with approved service identities.
- Real source-data reconciliation, one ICC pilot, one IGP pilot, role-based training, screen-reader review, penetration test, 200-user load test, backup/PITR restore, canary/rollback rehearsal, and seven-day hypercare ownership.
- Product owner, OIA faculty owner, ICC head, and IGP head approval.

Synthetic or local evidence must not be used to mark any external gate complete.
