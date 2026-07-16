# Production Release Blockers

Status: **Implementation complete in the repository; not approved for production**
Baseline date: 2026-07-16

The repository now contains the production completion model, services, API contracts, jobs, infrastructure, controls, tests, and runbooks. The following gates require external systems or real stakeholder operations and remain blocking:

1. Workflow, controlled-vocabulary, report-format, data-dictionary, and scoped-role signatures are absent.
2. GCP development, staging, and production projects have not been provisioned with authenticated Terraform 1.7+.
3. Cloud SQL HA failover, PITR, backup restoration, rollback, RPO, and RTO have not been exercised.
4. Live OIA Drive credentials/scopes and permission-drift validation have not been exercised.
5. Institutional SMTP credentials, sender approval, Cloud Tasks delivery, Scheduler OIDC, retry, and dead-letter monitoring have not been exercised in GCP.
6. The supplied samples are reconciled, but complete institutional source data has not been supplied, staged, or signed off.
7. One real ICC event and one real IGP program have not completed the staging pilot.
8. Formal WCAG 2.1 AA keyboard/screen-reader review, 200-user load test, penetration test, and container scan in CI have not produced approved evidence.
9. Role-based training, incident-owner assignment, seven-day hypercare, and four-party production acceptance are outstanding.
10. Internal accounts remain the initial provider. Institutional SSO is implemented as an adapter boundary but is not activated.

Legacy campus mutations are disabled when `APP_ENV=production`; production operations use the scoped ERP service/API layer. Legacy read views remain for continuity and should be removed after stakeholder acceptance of their replacement screens.

Deferred scope remains magazine generation, universal engagement scoring, dedicated journey timeline, native mobile applications, admissions, academic administration, official immigration casework, accounting ledger, and payment execution.
