# ICC ERP — UAT user acceptance guide

This guide is for operational users testing the UAT environment. UAT is a test environment with sample records. Do not enter real student, staff, financial, health, or confidential information.

## Start the UAT site locally

Open Terminal and run these commands from the project folder. This starts the local UAT database that contains the sample records and the four UAT accounts listed below.

```bash
cd "/Users/Shiva_1/Desktop/ICC ERP/icc-platform-2"
export DATABASE_URL="sqlite:////Users/Shiva_1/Desktop/ICC ERP/icc-platform-2/instance/uat_acceptance.db"
export DEMONSTRATOR=true
export APP_ENV=testing
export TESTING=true
export SECRET_KEY="local-uat-only-change-me"
.venv/bin/flask --app run.py run --host 127.0.0.1 --port 5010
```

When the server is running, open [http://127.0.0.1:5010/login](http://127.0.0.1:5010/login) in your browser. Keep the Terminal window open while testing. To stop the site, return to that window and press **Control+C**.

If port 5010 is already in use, stop the other local Flask process first or use another port in both the command and the browser address. Do not run database reset or deletion commands against this UAT database; ask the project coordinator if the sample data needs to be restored.

## Before you begin

1. Open the UAT web address supplied by the project coordinator.
2. Use the test password `123` with the username assigned below.
3. Use a current version of Chrome, Firefox, Safari, or Edge. If the screen looks crowded, zoom out to 100% and widen the browser window.

## Sign in and change your password

1. On the sign-in page, enter your assigned username from the list below.
2. Enter the one-time password from the private credential sheet.
3. Select **Access platform**.
4. Confirm that your name and role appear in the header. Never share your password with another user.

## UAT usernames and responsibilities

| Username | Role | What to test |
|---|---|---|
| `uat_faculty_admin` | OIA Faculty Administrator | User approvals, scoped oversight, project approvals, reports, audit evidence, and privacy boundaries. |
| `uat_usc` | Central Campus USC | USC/ICC coordination, project basics, people and event operations within the assigned campus and academic year. |
| `uat_igp_head` | Central Campus IGP Head | IGP project setup, sessions, buddy pairing, sensitive-link visibility, attendance, and feedback. |
| `uat_icc_events_head` | Central Campus ICC Events Head | ICC Events project creation and event operations within the Events wing. |
| `uat_volunteer` | Volunteer | Assigned contributions and project activity. |

All five UAT accounts use the test password `123`.

## Faculty Administrator journey

1. Sign in as `uat_faculty_admin`.
2. Open **Oversight** from the navigation.
3. Review the KPI cards and action queue. Select an item; confirm that it opens the exact project tab needing attention.
4. Open **Users and approvals**. Approve a pending test user, then return to the list and confirm the status changed.
5. Open a project from Oversight. Review a submitted task, document, contribution, operational request, budget line, feedback response, recruitment decision, and report approval when present.
6. Reject one test item with a written reason. Confirm that the rejection reason and updated status are visible.
7. Open **Audit** and confirm that the decision is recorded with the actor, time, item, and action.
8. Try to open a project outside the assigned scope if one is available. Confirm that it is not displayed or accessible.

Expected result: every decision has a visible outcome, a reason where required, a version change, and an audit record. Restricted data is not exposed outside the permitted scope.

## USC journey

1. Sign in as `uat_usc`.
2. Open **ERP operations**, then choose the Central Campus ICC project.
3. Open **Basics** and confirm the project title, dates, campus, program, year, and wing.
4. Move through **Sessions**, **Team**, **Checklist**, **Documents**, and **Budget**. Enter a harmless test value and save it.
5. Return to the project page. Confirm the saved value is present after refreshing the page.
6. Submit a draft operational request for approval.
7. Open the attendance roll call, mark a test participant, and save. Open attendance history and confirm the verifier, time, version, and immutable change entry are shown.
8. Open **Insights**, submit a rating and written response, and confirm the response appears as pending moderation.

Expected result: USC can work only within the assigned Central Campus ICC scope and can submit work for approval, but cannot approve restricted decisions reserved for the approving role.

## IGP Head journey

1. Sign in as `uat_igp_head`.
2. Open the Central Campus IGP project and select **Basics**.
3. Review or edit the project details, then continue through sessions, team, checklist, documents, and budget.
4. Open **People** and pair a buddy with an exchange participant. Confirm the pairing appears with dates and status.
5. Open attendance and complete a roll call. Correct one test entry with a written reason; confirm the history shows the original and corrected values.
6. Open **Insights** and create or edit a feedback form. Keep the required 1–5 rating question and add text questions one per line.
7. Submit a response and open the distribution chart. Confirm that the bars, exact-value table, and approved-response count agree.
8. Open a sensitive document link. Confirm that the link is visible only to this role and that access is recorded in the audit trail.

Expected result: IGP operations remain within the Central Campus IGP scope. Sensitive references are available only when the role permits them.

## ICC Events Head journey

1. Sign in as `uat_icc_events_head`.
2. Select **ERP operations**, then **New project**.
3. Complete **Basics** with Central Campus, ICC, the current academic year, and the ICC Events wing. Select **Continue**.
4. Complete sessions, team, checklist, documents, and budget using harmless UAT values. Use **Save and continue** after each step.
5. Use the **Full project page** link, then use the project tabs to confirm that the saved values are present.
6. Submit an operational request and a budget line for approval.
7. Open a project outside the ICC Events scope if one is available. Confirm it is not shown and direct navigation is denied.

Expected result: the ICC Events Head can create and manage ICC Events work in the assigned wing, but cannot see IGP records or approve actions outside the assigned scope.

## Public-site privacy check

1. Open the public calendar without signing in, or use a private browser window.
2. Open an event and a published report.
3. Confirm that public pages show only approved, published descriptions, dates, venues, aggregate charts, and report content.
4. Confirm that rosters, registration numbers, budgets, buddy pairings, restricted Drive links, and personal information are absent.

## Recovery and help

- If you enter the wrong password several times, wait for the lockout message and contact the project coordinator; do not keep retrying.
- If a page reports a conflict, refresh once and repeat the action using the latest visible version. Report the item name and what you were trying to do.
- If a save appears successful but the value disappears after refresh, stop testing that workflow and report the project, tab, field, and approximate time.
- For access, privacy, or unexpected-role issues, contact the UAT coordinator immediately. Do not work around a permission message.
- After acceptance, rotate or delete the private credential sheet and ask the coordinator to disable the UAT accounts.

## UAT status notice

This guide and its accounts are for UAT only. Repository-level automated quality evidence is recorded separately and does not constitute production approval, institutional SSO approval, live email/Drive validation, penetration-test approval, pilot acceptance, recovery rehearsal, or stakeholder sign-off.
