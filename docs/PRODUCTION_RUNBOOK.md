# Production Deployment, Canary, and Recovery Runbook

This runbook is executable only after every blocking row in `PRODUCTION_ACCEPTANCE_RECORD.md` has evidence. Production uses a fresh database, immutable image digest, Terraform 1.7+, and four-party release approval.

## 1. Operator inputs

Record these values in the release ticket without copying credentials into it:

- Release Git SHA and signed container digest.
- GCP project, region, Artifact Registry path, Cloud Run service, migration job, import job, and Cloud SQL instance.
- GCS Terraform state bucket/prefix with versioning, retention, uniform access, and an approved operator group.
- Stable HTTPS ERP hostname used for `internal_job_base_url` and OIDC audience.
- Secret Manager versions for Drive credentials, SMTP password, database URL, and Flask signing key.
- On-demand pre-release backup identifier and the previously serving Cloud Run revision.

Copy `terraform/production.tfvars.example` to the ignored `production.tfvars`. Supply `TF_VAR_drive_credentials_json` and `TF_VAR_smtp_password` through the approved secret-aware deployment environment; never save them in shell history or a tracked file.

## 2. Build and immutable-image gate

From the release SHA:

```bash
docker build --pull --no-cache -t "$REGION-docker.pkg.dev/$PROJECT_ID/icc-erp/icc-erp:$RELEASE_SHA" .
docker run --rm "$REGION-docker.pkg.dev/$PROJECT_ID/icc-erp/icc-erp:$RELEASE_SHA" python -m compileall -q app
docker push "$REGION-docker.pkg.dev/$PROJECT_ID/icc-erp/icc-erp:$RELEASE_SHA"
gcloud artifacts docker images describe "$REGION-docker.pkg.dev/$PROJECT_ID/icc-erp/icc-erp:$RELEASE_SHA" --format='value(image_summary.digest)'
```

CI must already show: 100% passing tests, service-layer coverage at or above 80%, migration smoke/drift checks, dependency audit with no known vulnerability, Bandit with no high finding, Terraform validation, container build, and no critical/high Trivy finding. Put the resulting digest—not a mutable tag—in `production.tfvars`.

## 3. Terraform plan and apply

Initialize the secured GCS backend and create a saved plan:

```bash
terraform -chdir=terraform init -reconfigure \
  -backend-config="bucket=$TF_STATE_BUCKET" \
  -backend-config="prefix=icc-erp/production"
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform validate
terraform -chdir=terraform plan -var-file=production.tfvars -out=production.plan
terraform -chdir=terraform show -no-color production.plan > production-plan.txt
```

A second authorized operator reviews resource destruction, public IAM, secret changes, database changes, image digest, scheduler audiences, and alert channel. Apply the exact saved plan:

```bash
terraform -chdir=terraform apply production.plan
```

Do not use `-auto-approve` for production. Store plan/apply logs with the release evidence.

## 4. Database migration

Create and record an on-demand Cloud SQL backup before migration:

```bash
gcloud sql backups create --instance="$SQL_INSTANCE" --project="$PROJECT_ID" --description="pre-$RELEASE_SHA"
gcloud run jobs execute "$MIGRATION_JOB" --region="$REGION" --project="$PROJECT_ID" --wait
gcloud run jobs executions list --job="$MIGRATION_JOB" --region="$REGION" --project="$PROJECT_ID" --limit=1
```

The job runs `flask --app run:app db upgrade` with `MIGRATION_ONLY=true`. A nonzero result blocks deployment. Confirm migration head `9b70b9a2c001` in the job logs. Never run `db.create_all()` in staging or production.

## 5. No-traffic revision and smoke checks

Terraform deploys the reviewed image. Before general traffic, identify the new revision and keep the prior revision recorded for rollback. Run authenticated smoke journeys against the no-traffic revision or an access-restricted staging equivalent:

1. `/healthz` returns 200 and `/readyz` returns 200 after its database query succeeds.
2. Production startup confirms `DEMONSTRATOR=false`; no default/synthetic account exists.
3. Login, password reset, session rotation, CSRF rejection, and lockout work.
4. A campus-scoped user cannot view another campus; ICC cannot administer IGP; a volunteer sees only assigned work.
5. Create a draft project, task, checklist item, attendance row, document metadata row, contribution, operational request, and report job.
6. Verify rejection reasons, faculty waiver audit, restricted Drive hiding, live Drive validation, notification delivery, and report XLSX/DOCX/PDF output.
7. Invoke every Scheduler endpoint with its OIDC identity and verify an untrusted caller receives 401/403.
8. Confirm logs contain request IDs but no passwords, reset tokens, Drive links, or restricted document content.

Delete only the smoke-test draft records through the approved data-correction process. Do not seed production.

## 6. Canary promotion

Route 5% of traffic to the new revision for at least 30 minutes, then 25% for at least 30 minutes, then 100% only with the release technical owner’s approval:

```bash
gcloud run services update-traffic "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --to-revisions="$NEW_REVISION=5,$OLD_REVISION=95"
gcloud run services update-traffic "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --to-revisions="$NEW_REVISION=25,$OLD_REVISION=75"
gcloud run services update-traffic "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --to-revisions="$NEW_REVISION=100"
```

At each gate inspect p50/p95 latency, 4xx/5xx rate, instance restarts, database connections/locks, task failures/retries, SMTP failures, Drive validation, audit writes, and uptime alerts. Any unexplained error increase, data mismatch, authorization failure, or sensitive-data exposure stops promotion.

## 7. Signed production import

Only stage source files whose checksums and mapping versions match the twice-rehearsed staging set. Preview and reconcile before commit. Execute a staged batch as a Cloud Run Job by overriding its required environment variable:

```bash
gcloud run jobs update "$IMPORT_JOB" --region="$REGION" --project="$PROJECT_ID" --update-env-vars="IMPORT_BATCH_PUBLIC_ID=$BATCH_PUBLIC_ID"
gcloud run jobs execute "$IMPORT_JOB" --region="$REGION" --project="$PROJECT_ID" --wait
```

Reconcile events, people, rosters, participants, sessions, attendance, documents, checklist items, and Drive references. Product-owner approval is required before enabling general use. Re-running the same input must create no duplicate operational record.

## 8. Application rollback

If the database remains compatible, route all traffic to the recorded prior revision:

```bash
gcloud run services update-traffic "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --to-revisions="$OLD_REVISION=100"
```

Pause imports and scheduled mutations, preserve logs/audit evidence, and open an incident. Do not downgrade a migration unless its exact downgrade was rehearsed against a copy and the incident owner approves it.

## 9. Data recovery

For corruption, isolate writes and restore the selected backup/PITR point to a new Cloud SQL instance; never overwrite the only production instance. Point an access-restricted recovery service at the restored instance and reconcile the last audit event, project updates, approvals, imports, attendance batches, report jobs, and notifications. Reopen writes only after measured RPO is at most 15 minutes, RTO is at most four hours, and the incident owner plus OIA faculty owner approve.

## 10. Closure evidence

Attach image digest, Terraform plan/apply, migration execution, backup identifier, smoke results, canary metrics, rollback rehearsal, signed reconciliation, accessibility/performance/security results, training attendance, and all four approvals. Start seven-day hypercare using `INCIDENT_RECOVERY_AND_HYPERCARE.md`.
