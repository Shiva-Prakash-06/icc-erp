# Role and Scope Matrix

Status: implementation contract; stakeholder signature required before production.

| Role | Administrative capability | Required scope | Sensitive references |
|---|---|---|---|
| System Administrator | Accounts, platform configuration, nonsensitive operational administration, imports, approvals, reports, and audit | Platform | No implicit access |
| OIA Faculty Administrator | Governance, people, projects, imports, approvals, waivers, reports, audit | Platform or campus | Named permission required |
| Faculty Coordinator | Projects, people, imports, approvals, waivers, reports | Campus/unit/project | Named permission required |
| ICC Secretary / USC | ICC governance, people, projects, imports, approvals, reports | ICC + campus/year | No |
| ICC Events Head | Events projects, people, approvals, reports | ICC/Events + campus/year | No |
| ICC Media Head | Media projects, people, approvals, reports | ICC/Media + campus/year | No |
| ICC Culturals Head | Culturals projects, people, approvals, reports | ICC/Culturals + campus/year | No |
| ICC Associate | Assigned work, contributions, personal history | Annual wing roster + assigned projects | No |
| IGP Head | IGP projects, people, imports, approvals, waivers, reports | IGP + campus/year | Named permission required |
| IGP Program Lead | Program delivery, people, approvals, reports | Assigned IGP project | No unless separately granted |
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

Approval record:

| Approver | Name | Decision | Date | Signature/reference |
|---|---|---|---|---|
| Product owner |  |  |  |  |
| OIA faculty owner |  |  |  |  |
| ICC head |  |  |  |  |
| IGP head |  |  |  |  |
