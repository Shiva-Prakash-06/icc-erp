# Production Deployment and Recovery Runbook

## Release prerequisites

- Product owner, OIA faculty owner, ICC head, and IGP head have signed the acceptance record.
- Staging reconciliation differences are zero or explicitly approved.
- No unresolved critical/high security finding or blocking accessibility defect.
- Backup restoration and rollback meet RPO 15 minutes and RTO four hours.

## Deployment sequence

1. Build and scan the immutable container image.
2. Apply reviewed Terraform from a pinned Terraform 1.7+ toolchain.
3. Create a Cloud SQL on-demand backup and record its identifier.
4. Run `flask db upgrade` as a Cloud Run Job against staging, then production.
5. Deploy the new Cloud Run revision without shifting traffic.
6. Run `/healthz`, schema, authentication, authorization, Drive-mock-disabled, and report smoke checks.
7. Shift a small traffic percentage; monitor error rate, latency, database connections, and audit writes.
8. Shift remaining traffic only after the technical owner approves the canary.

## Rollback

1. Stop traffic migration and route traffic to the prior Cloud Run revision.
2. If the migration is backward compatible, retain the upgraded schema.
3. If a reviewed downgrade is safe, run the matching Alembic downgrade job.
4. If data corruption occurred, isolate writes and restore Cloud SQL to a new instance at the approved point in time; never restore over the only production copy.
5. Reconcile post-restore records and obtain incident-owner approval before reopening writes.

## Backup drill evidence

Record backup/PITR identifier, start/end time, restored instance, last recovered audit event, measured RPO/RTO, reconciliation results, approver, and cleanup decision.
