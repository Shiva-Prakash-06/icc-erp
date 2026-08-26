# Role and Scope Matrix

Status: implementation contract; stakeholder signature required before production.

| Role | Administrative capability | Required scope | Sensitive references |
|---|---|---|---|
| System Administrator | Accounts, platform configuration, nonsensitive technical administration, imports, general approvals, reports, and audit; no operational-request business approval from technical status alone | Platform | No implicit access |
| OIA Faculty Administrator | Governance, people, projects, imports, approvals, waivers, reports, audit | Platform or campus | Named permission required |
| Faculty Coordinator | Projects, people, imports, approvals, waivers, reports | Campus/unit/project | Named permission required |
| ICC Secretary / USC | ICC governance, people, projects, imports, reports, and operational-request submission; no operational-request approval | ICC + campus/year | No |
| ICC Events Head | Events projects, people, general approvals, reports, and scoped operational-request approval | ICC/Events + campus/year | No |
| ICC Media Head | Media projects, people, general approvals, reports, and scoped operational-request approval | ICC/Media + campus/year | No |
| ICC Culturals Head | Culturals projects, people, general approvals, reports, and scoped operational-request approval | ICC/Culturals + campus/year | No |
| ICC Associate | Assigned work, contributions, personal history | Annual wing roster + assigned projects | No |
| IGP Head | IGP projects, people, imports, approvals including scoped operational requests, waivers, reports | IGP + campus/year | Named permission required |
| IGP Program Lead | Program delivery, people, general approvals, reports; no operational-request approval | Assigned IGP project | No unless separately granted |
| Volunteer / Buddy | Assigned work, resources, logs, personal history | Assigned project | No |
| Participant | Personal schedule, permitted resources, feedback | Personal/project membership | No |
| Auditor | Read-only reports and audit search | Explicit audit scope | No implicit access |

Rules enforced by the service layer:

- Scope order is platform → operating unit → campus → wing → academic year → project.
- More specific assignments never broaden a parent scope.
- ICC roles do not grant IGP access, and IGP roles do not grant ICC access.
- Expired, inactive, rejected, or archived accounts and assignments grant no access.
- System administration is separated from restricted operational content.
- Every permission-changing action and restricted-reference access is audited.
- Volunteers, buddies, associates, and participants require an assignment or personal relationship to view a project.
- Operational-request approval is limited to an explicitly eligible role in the request's project scope. USC, IGP Program Lead, and System Administrator status alone are insufficient.
- An operational request's creator or submitter cannot approve it; incomplete legacy maker/submission history must be reconciled before a decision.

Approval record:

| Approver | Name | Decision | Date | Signature/reference |
|---|---|---|---|---|
| Product owner |  |  |  |  |
| OIA faculty owner |  |  |  |  |
| ICC head |  |  |  |  |
| IGP head |  |  |  |  |
