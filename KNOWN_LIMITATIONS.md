# Production Release Blockers

Status: **Software release candidate; not approved for production**
Audit date: 2026-08-11

The repository now contains the production completion model, services, API contracts, jobs, infrastructure, controls, tests, and runbooks. The following gates require external systems or real stakeholder operations and remain blocking:

1. Workflow, controlled-vocabulary, report-format, data-dictionary, and scoped-role signatures are absent.
2. GCP development, staging, and production projects have not been provisioned with authenticated Terraform 1.7+.
3. Cloud SQL HA failover, PITR, backup restoration, rollback, RPO, and RTO have not been exercised.
4. Live OIA Drive credentials/scopes and permission-drift validation have not been exercised.
5. Institutional SMTP credentials, sender approval, Cloud Tasks delivery, Scheduler OIDC, retry, and dead-letter monitoring have not been exercised in GCP.
6. The supplied samples are reconciled, but complete institutional source data has not been supplied, staged, or signed off.
7. One real ICC event and one real IGP program have not completed the staging pilot.
8. Automated WCAG and keyboard/preference checks pass, and the native artifact has an SBOM and clean dependency audits, but a formal screen-reader review, 200-user load test, penetration test, and independent approval have not produced signed evidence.
9. Role-based training, incident-owner assignment, seven-day hypercare, and four-party production acceptance are outstanding.
10. Internal accounts remain the initial provider. Institutional SSO is implemented as an adapter boundary but is not activated.

Legacy campus mutations are disabled when `APP_ENV=production`; production operations use the scoped ERP service/API layer. Legacy read views remain for continuity and should be removed after stakeholder acceptance of their replacement screens.

The native artifact, PostgreSQL 16 rehearsal, Redis-backed production configuration, and Gunicorn smoke tests pass without Docker. If the optional Cloud Run deployment path is selected, remote image build/scan/digest evidence remains required for that target.

Deferred scope remains magazine generation, universal engagement scoring, dedicated journey timeline, native mobile applications, admissions, academic administration, official immigration casework, accounting ledger, and payment execution.

## Automation/simplification additions (2026-08-12)

The itinerary, buddy-allocation, reimbursement, ICC event-folder/attendance,
document-upload, and complete-PDF-report-assembly features described in
`PLAN.md` are implemented and unit/integration tested against sanitized
fixtures (`tests/fixtures/`, copied from `references/`). Still outstanding
before production use:

- Live Google Drive upload/download/export (item 4 above) — these features
  are fully exercised only in `DRIVE_VALIDATION_MODE=mock`; a live-mode
  pilot with real service-account credentials has not been run.
- DOCX/PPTX-to-PDF report assembly re-renders content with `reportlab`
  (paragraphs, tables, images, author metadata) rather than a pixel-faithful
  Office-to-PDF conversion; a stakeholder should confirm this is acceptable
  fidelity before relying on it for an official report.
- `AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD` must be set via a real secret
  manager in production and rotated per institutional policy; it is not a
  substitute for eventual SSO-based buddy onboarding.
- The Playwright/Lighthouse UI/E2E suite (`npm run test:e2e:twice`,
  `npm run test:lighthouse`) has not been run against these changes in this
  environment; only the Python test suite and Jinja template compilation
  were verified here.

## Checklist evidence links, dashboard merge, and UI/UX simplification (2026-08-22)

Mission Control, the ERP hub, and Oversight are merged into one role-adaptive
home page at `/`; checklist requirements can now link repository documents
as evidence; and the project workspace's single "operations" tab is split
into `delivery`/`contributions`/`finance` (with `operations` kept as a
redirect alias). See
`in-the-operation-checklists-crystalline-dongarra.md` for the full plan.

Three pre-existing defects found and fixed in the process:
- Collapsed disclosure content was permanently unreachable with JavaScript
  disabled (`.aurora-collapse:not(.is-open)` had no JS-presence scoping).
- The old single-`operations`-tab action-queue deep links pointed at
  content hidden inside that same collapsed disclosure, so seven of the ten
  Oversight action-queue kinds could not resolve to visible content.
- `add_task`, `update_task`, and `update_checklist_item` redirected to the
  bare project URL with no `tab`, throwing the user back to Overview after
  every save.

Still outstanding:
- `e2e/*.spec.ts` and the visual snapshots (`oversight-desktop.png`,
  `oversight-mobile.png`) still reference the pre-merge pages/tab names and
  have not been updated or re-run in this environment — Playwright was not
  available to run interactively here. Before relying on this slice for
  production, update the e2e route/tab-name references documented in the
  plan file and run `npm run test:e2e:twice` plus a visual-snapshot
  regeneration (`--update-snapshots`).
- One pre-existing, unrelated Python test failure
  (`test_all_standard_operational_imports_commit_and_reconcile`, an
  IntegrityError from a duplicated `MAIN` session code) was confirmed
  present before this slice's changes and is out of this slice's scope.
