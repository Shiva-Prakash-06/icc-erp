# UAT Remediation Release Audit

Audit date: 2026-08-11

Decision: **Software release candidate passes repository gates — institutional production approval remains required**

Claude's implementation was not accepted as delivered. This audit corrected authorization gaps, public-disclosure risks, migration provenance, production configuration, Terraform secret/networking controls, release contents, dependency exposure, browser state isolation, public performance, mobile navigation, database portability, and documentation drift. The resulting application satisfies the software thresholds in the validated remediation plan without requiring Docker. Institutional gates remain below.

## Result by area

| Area | Result | Evidence |
|---|---|---|
| ICC defects | Pass | Project Basics shows immutable campus/program/year/wing context; scoped campus screens exist; password setup and recovery use dedicated neutral screens; ambiguous fields use visible labels and controlled choices. |
| USC defects | Pass | One role-shaped navigation registry, visible demo warning, 200-response Mission Control, useful account/activity page, scoped operational approval, public-report return navigation, and one responsive project navigation are verified in browser acceptance. |
| IGP defect | Pass | Registration number remains optional in the model, forms, project enrollment, participant creation, and buddy workflow; server checks reject ineligible/cross-project pairings. |
| Authorization and privacy | Pass | Operational requests use a separate scoped permission and maker/checker rule. Generic people access is platform-admin-only; scoped search is minimal. Explicit publication approval and positive public allow-lists protect events, analytics, reports, and Drive references. |
| Migration and configuration | Pass | Fresh SQLite and PostgreSQL 16 upgrades and drift checks reach `27b173810b30`; populated reconciliation tests preserve identity and provenance. PostgreSQL connections are forced to UTC. Production requires PostgreSQL, shared Redis, secrets, and migration-only startup configuration. |
| UI/accessibility/performance | Pass | Cross-browser/mobile/keyboard/preferences tests and automated WCAG A/AA scans pass. Public charts have exact table equivalents. Lighthouse scores are 1.00 with CLS 0 and mobile LCP about 1.06 seconds. |
| Infrastructure and supply chain | Pass for native artifact | The 433 KB Docker-free artifact has a portable SHA-256, 301 allow-listed runtime files, a CycloneDX inventory, and no reported Python/npm vulnerability. A two-worker Gunicorn/PostgreSQL/Redis production rehearsal passes. Terraform remains available for an optional remotely built Cloud Run image. |

## Automated evidence

- Python on PostgreSQL 16: `163 passed`; service branch coverage `83%` against an `80%` gate.
- Critical workflow coverage: authorization `94%`; identity `100%`; job authentication `100%`; passwords `90%`; publication `94%`; operations `95%`.
- Playwright on independently reset PostgreSQL 16 databases: `163 passed` twice consecutively with retries disabled.
- UI: type check, production build, application/public/shared asset budgets, and npm audit pass.
- Lighthouse desktop/mobile: performance `100`, accessibility `100`, best practices `100`, CLS `0`, TBT `0`; mobile LCP approximately `1,057 ms`.
- Security: `pip check`, `pip-audit --local`, Bandit high-severity gate, npm high-severity audit, tracked-secret check, and build-context review pass.
- Infrastructure: Terraform 1.9.8 formatting, initialization, and validation pass.
- Migrations: fresh SQLite and PostgreSQL 16 upgrades plus `flask db check` pass at `27b173810b30`; populated legacy reconciliation and drift regressions pass.
- Native production: two Gunicorn workers, PostgreSQL readiness, Redis-backed shared limiter, login/public routes, HSTS, CSP, and clean graceful shutdown pass from the packaged artifact.

## Corrections made during this audit

- Enforced scoped generic-resource mutation and restricted-reference serialization checks.
- Converted Google OIDC verification failures into fail-closed 403 responses instead of 500 errors.
- Added role-assignment validation before deactivating the previous assignment.
- Added Redis/Direct VPC production infrastructure, per-secret IAM, digest validation, and dependency ordering.
- Replaced broad container copies with a runtime allow-list and hardened the build context.
- Moved to a patched Bookworm Python base, removed runtime setuptools, and pinned the vulnerable serialization dependency.
- Fixed retained authentication state between consecutive browser passes.
- Split and inlined the small public stylesheet, replaced the large public Chart.js dependency with a responsive native renderer, restored the mobile public header, eliminated CLS, and added accessible exact-value tables.
- Added negative publication coverage for cancelled projects and expanded critical authentication coverage to 100% for identity and job authentication.
- Forced PostgreSQL application sessions to UTC after native testing exposed naive/aware reset-expiry drift, and normalized monetary rendering across SQLite/PostgreSQL.
- Added a Docker-free, checksum-verifiable release builder/verifier and native PostgreSQL/Redis/Gunicorn deployment runbook.

## Blocking evidence before public production

Complete every blocking row and all four signatures in `PRODUCTION_ACCEPTANCE_RECORD.md`. Repository success cannot substitute for staging integrations, pilots, load/security/accessibility review, recovery, canary, rollback, or institutional approval. If Cloud Run is chosen instead of native deployment, the remotely built image must additionally receive its provider image scan and immutable digest evidence.
