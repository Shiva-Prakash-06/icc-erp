# Supplied-Data Demonstrator Reconciliation

Run date: 2026-07-16  
Environment: isolated SQLite demonstrator database  
Production impact: none

| Source | Staged | Valid | Errors | Committed | Difference |
|---|---:|---:|---:|---:|---:|
| 2026 ICC Events Report Summary | 8 | 8 | 0 | 8 | 0 |
| Coffee Meet & Greet folder | 58 | 58 | 0 | 58 | 0 |
| Summer School checklist | 50 | 50 | 0 | 50 | 0 |

## Reproduced operational records

### Event summary

- 8 dated ICC project records, each with one main session.
- Venue, target audience, event time range, and available source links.
- 12 Coffee Meet document records after folder and summary links are combined.

### Coffee Meet & Greet

- 31 people and 31 project-team assignments.
- 9 action items.
- 8 timed programme segments plus the overall event session.
- 9 additional folder files indexed as metadata; binary content remains outside the database.
- Actual reach of approximately 175 imported from the narrative report.
- Audience breakdown from the report: 75 international/OCI students, 85 parents, and 15 other guests/team within the stated total.
- Narrative report stored as a versioned **Draft** snapshot with source references.

### Summer School

- 50 populated requirements: 27 OIA operational items and 23 IGP-team items.
- 50 project checklist statuses with source file, sheet, and row provenance.
- The passport/visa/C-Form requirement is classified sensitive. No passport, visa, photograph, or C-Form binary is stored.

## Idempotency evidence

Each batch key includes importer schema version, import type, and a SHA-256 digest of the source file/folder. Re-staging the same source and importer version returns the existing batch. Automated tests run the sequence and assert zero reconciliation differences.

## Approval status

This is demonstrator evidence, not a production migration sign-off. The product owner must review mappings and sign a staging reconciliation report before any production commit.
