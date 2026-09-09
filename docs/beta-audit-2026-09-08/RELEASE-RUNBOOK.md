# Beta release runbook — remaining operator steps

Everything in [BETA-READINESS-PLAN.md](BETA-READINESS-PLAN.md) that is code is implemented and tested
on branch `beta-readiness`. What is left needs credentials, a hosting decision,
or production data access.

Rollback point: tag `beta-audit-fixes` (matches deployment `dpl_Dn2nPQkjoVywmSWkRUnDbKa5s9zU`).

## 1. Drive credentials — the launch gate (W1.1, W1.4)

Blocking. Without this, document upload is disabled rather than silently
discarding files, which is safe but not shippable.

Ask the owner for:

1. A **Shared Drive** folder ID. Not a My Drive folder: a service account has no
   personal Drive storage quota, so a My Drive upload fails outright.
2. A service-account JSON key.
3. That service account added to the Shared Drive as **Content manager**.

Then set on Vercel production:

```
DRIVE_VALIDATION_MODE=live
GOOGLE_DRIVE_REPOSITORY_ROOT_ID=<shared drive folder id>
GOOGLE_SERVICE_ACCOUNT_JSON=<service account json>
```

Leave `DISABLE_EXTERNAL_INTEGRATIONS=true`. It only gates startup validation, so
Drive can go live without also supplying the GCP task and SMTP variables that
would otherwise stop the app booting.

Until those are set, production refuses uploads with a legible error and creates
no document record. It can no longer report a success that did not happen.

### Acceptance, per the audit

- [ ] A unique PDF and a unique image, uploaded in **separate sessions**, are
      still readable after logout/login and a **cold start** (wait out the warm
      instance; a warm-instance test proves nothing).
- [ ] Download each and byte-compare against the original.
- [ ] Generate a complete report that includes an uploaded source document, and
      download it.
- [ ] Force a failure (revoke folder access briefly): an error is shown, and no
      Available/Indexed record is created.

## 2. Vercel region (W6.2) — decision needed

The function runs in `iad1` (Washington); the Supabase pooler is in Tokyo. Every
query pays a trans-Pacific round trip. Query counts are now much lower (home went
from 103 to 39), but the round trip remains.

Not changed here, because the plan says to confirm plan-level region availability
first, and because a region change late in the week is exactly the kind of thing
that destabilises a working deployment.

- Cheapest: pin the function to Tokyo (`"regions": ["hnd1"]` in `vercel.json`) to
  match the pooler.
- Better for Indian testers, but not a 5-day change: move Supabase to Mumbai and
  the function to `bom1`. That is a new project plus a data migration.

If you make this change, do it before Day 3 and keep the rollback tag handy.

## 3. Production data cleanup (W7)

Needs production access.

- [ ] Repair or retire the B02 orphan: `78500263-763d-4d2d-aab7-6c82aab812d6`
      (`ICC-2026-CEN-0004`), wing unset, invisible to its Events Head creator.
- [ ] Retire the Section 6 synthetic records so testers do not mistake them for
      real events — in particular the fake upload record
      `eb95f5e6-fbf1-4976-9437-8c86c3af6d07`, whose link points at nothing.
- [ ] Re-upload any real document uploaded before the storage fix. Existing
      `mock-*` records are metadata only; the bytes were never stored.
- [ ] Existing manually created sessions hold IST wall-clock stamped as UTC and
      will read 5.5 hours later once display is correct. Rebuild the dataset
      rather than backfilling; correct individually anything that must be kept.
- [ ] Seed what the audit could not exercise: an open assigned volunteer task, a
      buddy pairing with a log, and an approved published report document.

## 4. Migration

One new migration, `b1c4d7e9f210`, widens `import_batches.idempotency_key` from
120 to 255 characters. It runs automatically through the Vercel build command.
Verified against a clean PostgreSQL 17 database.

This is not cosmetic: the ICC attendance and buddy importers build 129- and
122-character keys, so **both were failing outright in production**. SQLite
ignores a VARCHAR length, which is why only PostgreSQL showed it.

## 5. Measuring latency (W6.1)

Instrumentation is in, off by default:

```
REQUEST_TIMING_ENABLED=true
REQUEST_TIMING_SLOW_MS=1000   # log only requests at or above this
```

Each qualifying request logs one JSON line with endpoint, status, duration and
query count. Turn it on for the Day 3 load run, then off again.

## 6. Still not covered

Unchanged from the audit, and not addressed by code:

- Simultaneous 8-10 user load (Day 3).
- Offline behaviour, exhaustive permission combinations, every export format,
  cross-browser and physical-device testing.
- The UI/UX work in audit section 4, deferred to the later redesign.
