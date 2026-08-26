# Production Acceptance Record

Release identifier:

Release artifact SHA-256 or container digest:

Migration revision: _(fill in from `flask --app run:app db heads` against the released commit -- do not carry forward a value from a prior release record)_
Release date:

| Gate | Required evidence | Result/reference | Blocking |
|---|---|---|---:|
| Workflow/data contract | Signed workflow, vocabulary, data dictionary, and role matrix |  | Yes |
| Authorization | Complete automated decision coverage and stakeholder review |  | Yes |
| Migration | Two idempotent staging runs and signed reconciliation |  | Yes |
| ICC pilot | Approved closure report |  | Yes |
| IGP pilot | Approved program/checklist report |  | Yes |
| Drive/privacy | Live validation, drift check, sensitive-access audit |  | Yes |
| Notifications/jobs | Cloud Tasks, Scheduler, SMTP, retry and dead-letter evidence |  | Yes |
| Security | No unresolved critical/high findings |  | Yes |
| Accessibility | No blocking WCAG 2.1 AA defects |  | Yes |
| Performance | p95 below 500 ms at 200 concurrent users |  | Yes |
| Recovery | PITR/backup restore meets RPO 15 min and RTO 4 hr |  | Yes |
| Deployment | Canary promotion and rollback rehearsed |  | Yes |
| Data hygiene | No demonstrator data/default credentials in production |  | Yes |

## Required approvals

| Authority | Name | Decision | Date | Signature/reference |
|---|---|---|---|---|
| Product owner |  |  |  |  |
| OIA faculty owner |  |  |  |  |
| ICC head |  |  |  |  |
| IGP head |  |  |  |  |

Production is not approved unless every blocking gate passes and all four authorities approve.
