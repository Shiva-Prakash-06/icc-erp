# Beta readiness implementation plan

**Source of truth:** [AUDIT.md](AUDIT.md), 8–9 September 2026.
**Target:** beta with 8–10 testers, launch 14 September 2026.
**In scope:** B08–B13 plus the release-hygiene and dataset work the audit implies.
**Out of scope by instruction:** login/security hardening (Section 2 preamble), and every row of Section 4 (UI/UX), including the four "Before beta" UX rows. Two carve-outs are kept because the audit files them as functional defects, not redesign: the submitting-state feedback inside B13, and the error-text/handoff wording inside B10/B11.

Launch gate, quoted from the audit's Day 5: *launch only after upload persistence (B08) and schedule correctness (B09) pass.* Everything else is desirable, not gating.

---

## W0 — Release hygiene (do first, ~1 hour)

The audit records that "changes remain in the working tree; no commit or push was made". Confirmed: B01–B07 exist only as uncommitted edits to `app/__init__.py`, `app/config.py`, `app/services/project_quickcreate.py`, `app/services/upload_sessions.py`, `app/blueprints/erp.py`, `app/blueprints/public.py`, `app/templates/erp/project_detail.html`, plus the untracked `app/templates/public_site/` and the deletion of `app/templates/public/`. Production is running code that is not in version control. Any clean-checkout deploy silently reverts all seven fixes.

1. Commit the audit fixes in one or two reviewable commits; the `public/` → `public_site/` move must be committed as a delete + add together or B03 regresses.
2. Run `make test` (`python -m unittest discover -s tests -p '*test.py'`) — the audit's baseline is 53 targeted tests passing plus two closure-flow tests in `tests.erp_test`.
3. Tag the commit that corresponds to deployment `dpl_Dn2nPQkjoVywmSWkRUnDbKa5s9zU`, so there is a known-good rollback point for the rest of the week.

---

## W1 — B08: real file storage (P1, launch-gating)

The mock provider fabricates an identifier and discards the bytes ([drive.py:165](../../app/services/drive.py:165)). Every "uploaded to Drive and indexed" message in production so far is false.

### W1.1 Owner dependency — request today, it blocks the rest of W1
The audit notes a destination folder and service-account access were already requested and that credential values pulled through Vercel were redacted. Needed:
- A **Shared Drive** folder ID for `GOOGLE_DRIVE_REPOSITORY_ROOT_ID`. Shared Drive rather than My Drive: a service account has no personal Drive storage quota, so `files().create` into a My Drive folder fails on quota. This is the audit's "review the provider's shared-drive options" point.
- A service-account JSON key for `GOOGLE_SERVICE_ACCOUNT_JSON`, with the SA added to that Shared Drive as **Content manager**.
- Confirmation the existing redacted Vercel credential is that same identity, or replacement of it.

Escalate on Day 1 if unanswered — this single dependency is the only thing between the build and launch.

### W1.2 Shared-drive parameters in `app/services/drive.py`
`ensure_project_folder` and `upload_file_to_drive` currently call the Drive API without shared-drive support, so they will 404 against a Shared Drive even with correct credentials:
- `files().list(...)` → add `supportsAllDrives=True`, `includeItemsFromAllDrives=True`, `corpora="drive"`, `driveId=<root drive id>`.
- both `files().create(...)` calls → add `supportsAllDrives=True`.
- `files().get_media(...)` / `export_media(...)` in `download_drive_file` → add `supportsAllDrives=True`, so report assembly ([report_assembly.py:111](../../app/services/report_assembly.py:111)) can read back what was uploaded.

### W1.3 Fail closed
Audit acceptance: *failed uploads must show an error and must not create an Available record.*
- Record ordering is already safe — `upload_file_to_drive` runs before the `DocumentRecord` is constructed ([upload_sessions.py:156](../../app/services/upload_sessions.py:156)) — but the exception type is not. `HttpError` and `RuntimeError` escape as HTTP 500 because the callers only catch `UploadSessionError`/`ValueError` ([erp.py:250](../../app/blueprints/erp.py:250), [erp.py:1264](../../app/blueprints/erp.py:1264), and the resources upload route).
- Wrap the Drive call in `complete_upload_session` and re-raise as `UploadSessionError` with a user-legible cause (not found / no access / quota / network).
- Refuse the upload up front with the same error when `DRIVE_VALIDATION_MODE=live` and `GOOGLE_DRIVE_REPOSITORY_ROOT_ID` is unset, instead of failing mid-flight.

### W1.4 Production configuration
Set on Vercel production: `DRIVE_VALIDATION_MODE=live`, `GOOGLE_DRIVE_REPOSITORY_ROOT_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`.
Keep `DISABLE_EXTERNAL_INTEGRATIONS=true`. Verified in [config.py:170](../../app/config.py:170): that flag only gates startup validation, it does not force mock mode at runtime — so Drive can go live without also having to provide `INTERNAL_JOB_AUDIENCE`, the GCP task vars, and SMTP, which would otherwise make boot fail.

### W1.5 Acceptance (audit's wording, verbatim requirements)
- A unique PDF and a unique image, uploaded in **separate sessions**, remain readable after logout/login and a **fresh serverless invocation** (wait out or force a cold start; do not test within one warm instance).
- Download each and byte-compare against the original.
- Then re-run the report path: upload → include in report → download, to close the audit's "generated summaries can download when no authoritative report exists" gap.
- Force one failure (revoke folder access briefly, or upload to a bad folder id) and confirm an error flash with no new Available/Indexed record.

### W1.6 Existing mock records
`mock-*` documents are metadata with no recoverable bytes, including `eb95f5e6-fbf1-4976-9437-8c86c3af6d07` (BETA-AUDIT-report). Do not migrate them. Mark them Superseded or delete them as part of W7 so testers never open a dead link. Any real document uploaded before this fix must be re-uploaded.

---

## W2 — B09: one timezone convention (P1, launch-gating)

Two entry paths disagree. `app/services/itinerary.py` attaches `Asia/Kolkata` ([itinerary.py:520–526](../../app/services/itinerary.py:520)); manual session creation parses `datetime-local` into a **naive** datetime and stores it as-is ([erp.py:567–568](../../app/blueprints/erp.py:567)). The column is `DateTime(timezone=True)` ([erp.py model:191](../../app/models/erp.py:191)), so on PostgreSQL the IST-aware value converts to 03:30Z while the naive value lands as 09:00Z. Templates then call `.strftime()` directly on the stored value ([home.html:112](../../app/templates/dashboard/home.html:112), [attendance_roll_call.html:9](../../app/templates/erp/attendance_roll_call.html:9), [project_detail.html:85,209,658](../../app/templates/erp/project_detail.html:85), [project_setup.html:44](../../app/templates/erp/project_setup.html:44)), so imported sessions read 03:30 and manual ones coincidentally read correctly. SQLite keeps everything naive, which is exactly why the audit's local run did not reproduce it.

### W2.1 Convention
**Store UTC-aware, render campus-local with an explicit label.** Manual entry is the path that is actually wrong internally; the import path is right.

1. Add `APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")` to `BaseConfig`.
2. New `app/services/timeutil.py`: `to_campus(dt)` (treat naive as UTC, convert to `APP_TIMEZONE`) and `to_utc(naive_local)`. Register Jinja filters `localdate`, `localtime`, `localdatetime`, each emitting an `IST` label.
3. **Ingress:** `erp.py:567–568` attaches `APP_TIMEZONE` then converts to UTC. `itinerary.py:520–526` adds `.astimezone(timezone.utc)`. Audit the other `strptime` sites in `erp.py` (lines 136, 199, 238, 526, 703, 826, 1347) — the date-only ones are fine; do not silently convert a date into a datetime.
4. **Egress:** replace every `starts_at.strftime(...)` / `ends_at.strftime(...)` in the four templates above with the filters. Also apply to the schedule export and the public calendar/event detail so the public site and the ERP agree.

### W2.2 Existing rows
Manually created sessions hold IST wall-clock stamped as UTC and shift +5:30 the moment display is corrected. Rather than a heuristic backfill that guesses each row's provenance, fold this into W7: rebuild the beta dataset cleanly, and hand-correct only rows that must be kept. If any survive, a one-off script subtracting 5:30 from manually-created sessions is the fallback — run it once, against a backup, never twice.

### W2.3 Verification (the audit is explicit that SQLite is not sufficient)
- Run the timezone tests against **PostgreSQL**. `compose.yaml` already provides `postgres:16-alpine`; point `DATABASE_URL` at it for the run. Add a `tests/itinerary_test.py` case asserting stored UTC and rendered IST for both entry paths.
- Re-import `BETA-AUDIT-itinerary.csv` in production and confirm 13 Sep 09:00–10:00 and 14 Sep 10:00–11:00 on: project schedule, home upcoming sessions, roll call, and export.
- Check date boundaries deliberately: a session at 00:30 IST and one at 23:30 IST must not slide onto the adjacent day anywhere.

---

## W3 — B10: supplied import sources absent from the deployment (P2)

`SOURCE_PATHS` resolves against `Path(__file__).resolve().parents[3]` ([imports.py:44–60](../../app/services/imports.py:44)), which is the folder **above** the repo locally and `/var` on Vercel. The workbooks genuinely live outside the repo, in `../references/`, so they are never packaged.

1. Copy `2026 ICC EVENTS REPORT SUMMARY.xlsx` (36 KB) and `_Summer School- Check List.xlsx` (56 KB) into the package, e.g. `app/data/import_sources/`, and commit them. Change `_resolve_source_path` to check that directory first, keeping the existing `ROOT` lookup as a dev fallback.
2. **Do not bundle `COFFEE MEET & GREET`** — it is 79 MB and will blow the function bundle. Remove it from the supplied-source list and route it through the existing custom-upload flow, which the audit confirms works.
3. Confirm `vercel.json` `excludeFiles` does not strip the new directory (`.xlsx` is currently not excluded, but re-check after the path change).
4. Replace the bare-path error: catch `FileNotFoundError` in `stage_import` ([erp.py:1503](../../app/blueprints/erp.py:1503)) and flash a message naming the source and pointing at the template download + upload flow. Never surface a server filesystem path.

---

## W4 — B11: USC is shown a Commit button that 403s (P2)

`commit_import` requires the global `approve` permission ([erp.py:1516](../../app/blueprints/erp.py:1516)), but `imports.html` renders the Commit button for anyone who reached the page, which is anyone with `manage_imports`.

The audit deliberately performed no access broadening, so the **default is to keep the permission as-is and fix the UI**, which also matches "make the intended handoff explicit":
1. `imports()` ([erp.py:1455](../../app/blueprints/erp.py:1455)) passes `can_commit=has_permission(g.user, "approve")` to the template.
2. In `imports.html`, render Commit only when `can_commit`; otherwise show an **Awaiting faculty commit** badge on the same row.
3. Confirm with the owner whether USC is *meant* to commit. If yes, that is a permission change, not a UI change, and should be decided explicitly rather than inferred — flag it and leave it for after beta unless the owner says otherwise.

---

## W5 — B12: publication requests missing from the faculty queue (P2)

`build_action_queue` has ten sources and no project-publication source ([action_queue.py:49–91](../../app/services/action_queue.py:49)), while `submit_project_publication` sets `Project.publication_status = "Pending"` ([publication.py:24](../../app/services/publication.py:24)). Nothing links the two, so the queue silently under-reports.

1. Add an eleventh entry to `ACTION_QUEUE_KINDS`, e.g. `"Project publication"`.
2. Add a source: projects in the user's scope with `publication_status == "Pending"` where `has_permission(user, "manage_governance", project)`. Exclude requests the viewer submitted themselves — `decide_project_publication` already refuses self-review ([publication.py:47](../../app/services/publication.py:47)), so showing them would reproduce the same visible-action-then-denied trap as B11.
3. Item payload must carry project title and requester, per the audit, and link to the project overview where the approval controls already work.
4. Update `tests/action_queue_test.py` and the e2e "oversight includes every pending category" expectation. The module docstring warns that the `{kind,title,project,tab,anchor,due_at}` shape and `tab` values are load-bearing for those tests — add a source, do not reshape existing ones.

---

## W6 — B13: latency measurement and submit feedback (P2)

The audit is careful that 8–19 s figures include automation overhead and are not instrumented metrics, and that the region mismatch is a likely contributor, not a measured root cause. So: measure first, then act.

1. **Instrument.** Log per-request server duration and SQLAlchemy query count for `dashboard.index` and `erp.project_detail` under the planned beta dataset. Capture browser TTFB separately.
2. **Region.** The function is in `iad1` (Washington) and the Supabase pooler is in Tokyo. Cheapest correction is pinning the Vercel function region to Tokyo (`hnd1`) via `vercel.json` `regions`, which removes a trans-Pacific round trip per query. Moving the Supabase project to Mumbai would serve Indian testers better but means a new project plus data migration — not a 5-day change. Confirm plan-level region availability before committing to this.
3. **Query counts.** Attack whatever the instrumentation shows; `build_action_queue` issues at least eleven separate queries plus per-row `db.session.get` lookups in the recruitment and report-approval loops, which is the obvious first N+1 candidate.
4. **Submitting state.** Disable the button and show a pending state on submit for the slow forms. Audit files this under reliability (repeated clicks while waiting), not redesign, so it stays in scope.

---

## W7 — Beta dataset and synthetic-record cleanup

Prerequisite for W2's verification and for the Day 5 rehearsal.

- Repair or retire the B02 orphan: `78500263-763d-4d2d-aab7-6c82aab812d6` / `ICC-2026-CEN-0004`, wing unset, invisible to its Events Head creator. The audit states the fix does not repair it retroactively.
- Retire the rest of Section 6's synthetic records so testers never mistake them for real events, in particular the fake upload record and the withdrawn `ICC-2026-CEN-0006`.
- Rebuild a clean, known dataset with fresh beta accounts, ensuring it contains what the audit could not exercise: at least one open assigned volunteer task, one buddy pairing with a log, and one approved published report document.

---

## Five-day schedule

Mapped to the audit's Section 5 sequence.

| Day | Work | Exit criterion |
|---|---|---|
| **1** (10 Sep) | W0. W1.1 escalation. W1.2–W1.4 built behind the pending credential. W2.1 code + W2.3 PostgreSQL tests. | Fixes committed and tagged; timezone correct against local PostgreSQL; Drive code ready to switch on. |
| **2** (11 Sep) | W1.5 acceptance the moment credentials land. W3, W4, W5. Start W7. | Uploads survive a cold start and byte-compare; imports stage from the deployment; no visible action 403s; publication appears in the faculty queue. |
| **3** (12 Sep) | Full document/report, buddy and recruitment scenarios end to end. W6.1–W6.3. 8–10 concurrent-user run. | Report contains a real uploaded source document; latency numbers measured, not estimated. |
| **4** (13 Sep) | W6.4. Finish W7. Regression pass over B01–B07. Write the participant guide. | Clean dataset with fresh accounts; full suite green; no regression in the seven fixed blockers. |
| **5** (14 Sep) | Role-by-role rehearsal: Events Head, IGP Head, USC, faculty, volunteer, public visitor. | Launch gate met — B08 and B09 both pass. Remaining P2s recorded as known issues. |

The audit's Day 4 was UX polish; that is deferred to the later redesign per your instruction, so Day 4 absorbs the dataset and regression work instead.

## Risks

| Risk | Impact | Response |
|---|---|---|
| Drive credentials/folder do not arrive by Day 2 | Launch gate cannot be met | Escalate Day 1. If unresolved by end of Day 3, either slip the date or launch with document upload disabled outright — never with the mock provider silently reporting success. |
| Service account placed on a My Drive folder, not a Shared Drive | Uploads fail on storage quota after the switch to live | Specify Shared Drive in the request; W1.2 adds the shared-drive parameters. |
| Timezone display correction shifts existing sessions | Testers see wrong historical times | Rebuild the dataset (W7) rather than backfill; correct kept rows individually against a backup. |
| Region change or index tuning destabilises a working deployment late in the week | Regression close to launch | W6 is non-gating. Freeze W6 changes after Day 3 and keep the W0 tag as rollback. |
