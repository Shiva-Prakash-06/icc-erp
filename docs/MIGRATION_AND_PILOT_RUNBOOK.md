# Migration Rehearsal and Pilot Runbook

## Preconditions

- Final migrations applied to a fresh staging PostgreSQL database.
- Controlled vocabularies and source mappings signed.
- Google Drive validation is live and uses the approved OIA service identity.
- No synthetic account, password, project, or fixture exists in staging/production.

## Rehearsal

1. Record source filenames, hashes, sheet counts, importer version, and mapping version.
2. Stage all workbooks and folders; resolve validation errors and person-match candidates without direct table writes.
3. Preview projects, people, rosters, sessions, attendance, actions, documents, checklists, and Drive references.
4. Commit with an authorized importer and retain every source-row target UUID.
5. Reconcile source and target totals by entity, campus, project, and program.
6. Repeat the exact import into the same staging database; assert zero duplicate operational records.
7. Record every difference as zero, corrected, or explicitly approved by the product owner.
8. Restore a clean staging database and repeat once from the signed inputs.

## ICC acceptance pilot

- Create and approve one event.
- Configure sessions, team, tasks, documents, budget, risks, attendance, feedback, and closure requirements.
- Operate it through Active and Closing.
- Resolve or faculty-waive every closure blocker.
- Generate, approve, and publish the event report.

## IGP acceptance pilot

- Create the partner, cohort, program, recruitment applications, and program-specific team.
- Instantiate the approved program checklist and assign all owners/deadlines.
- Validate logistics, buddies, interaction/escalation handling, attendance, documents, and restricted references.
- Complete or faculty-waive every requirement.
- Generate and approve the final program/checklist report.

## Production import

- Create a fresh production database from migrations; never copy demonstrator or staging databases.
- Reuse only signed source hashes, mappings, and importer versions from rehearsal.
- Commit once, reconcile, and obtain product-owner approval before enabling general access.
