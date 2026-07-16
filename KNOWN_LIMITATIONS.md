# Demonstrator Known Limitations

Status: **Demonstrator—Not Production**  
Baseline date: 2026-07-16

The implementation establishes the production architecture and critical workflow rules, but it has not passed the PRD's fourteen-week production program or release gates.

## Blocking before production

1. Stakeholders have not signed the workflow, data dictionary, or scoped authorization matrix.
2. The service has not been deployed to separate GCP development/staging/production projects. Terraform is formatted, but the local machine has Terraform 0.14.9; validation requires Terraform 1.7+ and authenticated provider initialization.
3. Cloud SQL regional failover, point-in-time recovery, backup restoration, and rollback have not been exercised.
4. Google Drive validation runs in mock mode. Live metadata/permission checks and named sensitive-reference authorization require approved service credentials and Drive scopes.
5. Email notifications, Cloud Tasks workers, Scheduler OIDC verification, reminder preferences, and escalation delivery are modeled/planned but not wired end-to-end.
6. Institutional Google/CHRIST identity is an adapter interface only. Internal platform accounts remain the demonstrator provider.
7. Legacy v2 screens remain available for continuity and still contain coarse role-era workflows. New ERP routes use scoped authorization; every legacy mutation must be migrated to the shared service layer before production.
8. New public UUIDs are stable API identifiers, while legacy-compatible integer keys remain physical database primary keys. A production decision is required before any UUID primary-key promotion.
9. API coverage is read-heavy. Core project update/transition, import, Drive validation, and public feedback mutations exist; full mutation contracts, idempotency, and concurrency behavior are not complete for every resource.
10. PWA support safely caches only local static shell assets. Offline read-only schedule/task snapshots are intentionally deferred until encryption, revocation, and sensitive-data exclusions are verified.
11. Accessibility, keyboard, and responsive browser spot-checks passed for demonstrator journeys, but formal WCAG 2.1 AA testing with screen readers has not occurred.
12. Load testing at 200 concurrent users, dependency/DAST scanning, secret scanning, breached-password API integration, and penetration testing remain release gates.
13. Report snapshots are reproducible JSON previews. Stakeholder-ready PDF/XLSX/DOCX templates, approval signatures, publication controls, and renderer reconciliation need production work.
14. The Coffee Meet narrative was imported as a **Draft** from the supplied event report. It must not be represented as institutionally approved until an authorized faculty reviewer approves the snapshot.
15. The supplied Coffee Meet guest-list sheet is empty and its attendance column is unmarked. The imported reach and audience breakdown therefore come from the narrative event report, not a reconciled participant attendance roster.
16. Summer School requirements are complete as a 50-item operational template, but owners, deadlines, evidence, approvals, and waivers must be completed by the actual program team.

## Explicitly deferred product scope

- Magazine generation, universal engagement scoring, and a dedicated journey timeline.
- Native mobile apps.
- Admissions, academic administration, official immigration casework, accounting ledger, and payment execution.
