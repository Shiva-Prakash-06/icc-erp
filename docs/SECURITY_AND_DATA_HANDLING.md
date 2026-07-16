# Security and Data Handling

## Classification

- **Public:** approved public feedback forms and approved publication content.
- **Internal:** ordinary project metadata, schedules, tasks, approved reports, and aggregate reach.
- **Restricted:** participant contact data, recruitment decisions, concerns, and Drive references whose visibility is named and audited.
- **Prohibited in ERP storage:** passport, visa, C-Form, and equivalent identity/immigration file binaries.

## Required controls

- Every account has separate operational `Person` identity and authentication-provider identity.
- Roles are effective-dated and scoped to platform, unit, campus, wing, year, or project.
- System administration does not imply restricted-content access.
- Browser mutations use CSRF protection; JSON APIs use same-origin authentication and CSRF headers except rate-limited public token feedback.
- Sensitive links are redacted without named permission and excluded from the service-worker cache.
- Drive validation reads metadata/permissions only and never changes sharing.
- Audit events are append-only and retained for seven years in production.
- Production secrets live in Secret Manager; no default account, password, or signing key is committed.

## Incident minimums

Revoke affected sessions and Drive permissions, preserve audit/log evidence, identify scope, notify the incident owner and OIA faculty owner, document containment and recovery, and obtain approval before restoring access.
