# Incident, Recovery, and Hypercare Procedure

## Incident response

1. Identify severity, incident owner, affected environment, scope, and request IDs.
2. For suspected privacy exposure, revoke application/Drive access and preserve audit evidence before investigation.
3. For corruption, stop or isolate writes; never restore over the only production database.
4. Route traffic to the last healthy Cloud Run revision when application rollback is sufficient.
5. Restore Cloud SQL to a new instance at the approved point in time when data recovery is required.
6. Reconcile projects, people, approvals, audit events, imports, notification jobs, and latest timestamps.
7. Obtain incident-owner and OIA approval before reopening writes.
8. Record cause, impact, timeline, corrective action, and follow-up owner without copying restricted content into the incident record.

## Recovery drill evidence

Record backup/PITR identifier, start/end time, recovered instance, last recovered audit event, measured RPO/RTO, reconciliation result, rollback result, approver, and cleanup decision.

## Seven-day hypercare

- Daily availability, latency, 5xx, database, task, email, Drive validation, audit-write, and backup review.
- Named incident owner and daily product/OIA checkpoint.
- Only critical defects and data corrections; no scope expansion.
- Daily unresolved issue and notification dead-letter report.
- Final hypercare closure signed by product owner and OIA faculty owner.
