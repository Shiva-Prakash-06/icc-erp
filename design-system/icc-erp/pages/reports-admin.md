# Reports, Imports, Audit and Admin Override

Inherits `MASTER.md`.

- **Imports**: a drop zone, then one row per batch — name, one metadata line, one action. Checksum, row counts and file provenance live behind a per-row "Provenance" disclosure. Provenance stays one click away; it never stands between the operator and the Commit.
- **Audit**: When / Who / What happened. Raw action strings, entity ids and request ids are demoted to `<details>`; the ledger reads as prose, not as identifiers.
- **Alerts**: one flat list, newest first, unread marked by a rule rather than a fill. Delivery preferences sit behind a disclosure.
- **Admin**: pending approvals first with an inline role decision, then the directory. Approving someone is one decision — what they do; scope follows from their campus.
- Print output stays white and high-contrast: no shell, no ground, no rules heavier than hairline.
