# ICC — user testing guide

This guide is for people testing the app before it goes live. The test site
has made-up records. Do not type in real student, staff, money, health or
private details.

Each role has one short journey below. If anything takes more presses than
the journey says, or a word on screen is hard to understand, write it down —
that is a finding.

The first part is for the **coordinator** who sets the site up. Testers can
skip to [Before you begin](#before-you-begin).

## For the coordinator: set up the test site

Faculty, the wing heads and the USC test on the hosted site, so they need
nothing installed. The local site is for the coordinator's own checks.

Both use the same command, `flask seed-beta`. It **empties the database it
points at** and fills it with the beta accounts and records, then writes each
account's one-time password to `instance/BETA_CREDENTIALS.txt`, which only you
can read. The passwords are not printed and are stored nowhere else; running
the command again replaces all of them.

### Hosted site

Do these in order. Each one is checked before the next.

1. A Redis store exists. It is **icc-beta-redis** (Upstash, Tokyo), made
   from Vercel → Storage and connected to the project, which gives it the
   `BETA_REDIS_URL` variable. The app uses that ahead of the older
   `RATELIMIT_STORAGE_URI` and `UPLOAD_SESSION_STORAGE_URI`, which name a
   deleted store and can be removed. If the store is ever replaced, connect
   the new one with the prefix `BETA`. Without a store the site loads, but
   every file upload fails.
2. Drive is set up, so the Media and Culturals heads can add files. The
   test folder is **ICC Test Drive**,
   `18ae3pJi2NiEC3yL-R9aVmocZXewC6ENH`.
   - The folder must sit inside a **Shared Drive**, not someone's My Drive:
     a service account has no storage of its own, so uploads to a My Drive
     folder fail. If it is in My Drive, make a Shared Drive and move it in.
   - In Google Cloud, create a service account, add a JSON key, and add the
     service account's email to the Shared Drive as **Content manager**.
   - Set in Vercel (Production): `DRIVE_VALIDATION_MODE=live`,
     `GOOGLE_DRIVE_REPOSITORY_ROOT_ID=18ae3pJi2NiEC3yL-R9aVmocZXewC6ENH`,
     and `GOOGLE_SERVICE_ACCOUNT_JSON` = the whole key file. Keep
     `DISABLE_EXTERNAL_INTEGRATIONS=true`.
   - The folder is currently viewable by anyone with its link, and files
     uploaded into it inherit that. That is fine for made-up beta records;
     set it to **Restricted** before any real document goes in.
3. The version under test is on `main`, and Vercel has finished deploying
   it (Vercel → Deployments shows it **Ready**). Then every line below must
   print 200:

   ```bash
   for p in /healthz /readyz /login; do curl -s -o /dev/null -w "$p %{http_code}\n" https://icc-platform-2.vercel.app$p; done
   ```

   If not, open the failed request in Vercel → Logs and fix the cause first.
4. Seed the hosted database from your own computer. This deletes
   everything in it. Vercel will not show `DATABASE_URL` again, so use the
   Supabase CLI's short-lived login for the linked `icc-erp` project
   (`supabase login` once, then `supabase link`):

   ```bash
   cd /Users/Shiva_1/Desktop/icc-platform-2
   export APP_ENV=production MIGRATION_ONLY=true BETA_SEED=1
   export SECRET_KEY="seed-only"   # needed to start; not the site's key
   export DATABASE_URL="$(python3 scripts/supabase_db_url.py)"
   .venv/bin/flask --app run.py db upgrade
   .venv/bin/flask --app run.py seed-beta
   ```

   Last seeded: 14 November 2026.
5. Send each tester their username and one-time password privately, one
   person at a time — never in a group chat or a shared document.

### Local site

```bash
cd /Users/Shiva_1/Desktop/icc-platform-2
export DATABASE_URL="sqlite:////Users/Shiva_1/Desktop/icc-platform-2/instance/beta_local.db"
export APP_ENV=testing TESTING=true SECRET_KEY="local-uat-only-change-me"
.venv/bin/flask --app run.py db upgrade
BETA_SEED=1 .venv/bin/flask --app run.py seed-beta
.venv/bin/flask --app run.py run --host 127.0.0.1 --port 5010
```

Then open [http://127.0.0.1:5010/login](http://127.0.0.1:5010/login). Keep
Terminal open while you test; press **Control+C** to stop. Run only the last
command next time — the first two reset everything. On the local site an
added file ticks its item, but the file itself is not kept and cannot be
opened again.

### Test accounts

| Usernames | Role | What they do |
|---|---|---|
| `faculty1` – `faculty4` | Faculty | Say yes to money, finished events and the website. Make people heads. |
| `usc`, `secretary` | USC | Type in event details for any ICC event. Approve nothing. |
| `events1`, `events2` | ICC Events head | Run ICC events. |
| `media1`, `media2` | ICC Media head | Do the Media team's work on any ICC or IGP event. |
| `cultural1`, `cultural2` | ICC Culturals head | Do the Culturals team's work on any ICC or IGP event. |
| `igp1`, `igp2` | IGP head | Run IGP programmes. |

There is no volunteer account. To test as a volunteer, sign up as someone new
(below).

## Before you begin

1. Get your username and one-time password from the coordinator. Every
   account has its own password. Do not share it.
2. Use a current Chrome, Firefox, Safari or Edge. Try at least one journey on
   a phone as well — event-day work is done on phones.

## Sign in

1. Open the link the coordinator gave you.
2. Type your username and the one-time password, and press **Sign in**.
3. Pick your own new password when asked. It must be at least 12 characters.
   Press **Go to My work**. My work is where you do things, and where every
   journey below starts.
4. Check that the bottom of the sidebar shows your name and role.
5. Press **Campuses** in the sidebar: four campus tiles. Press one to see its
   ICC events and IGP programmes, and press a programme to see its actions.
   These pages are for looking only — nothing is ticked there. From your next
   sign-in on, this is the page you land on; press **My work** to get back to
   your list.

## ICC Events head

1. Sign in as `events1`. My work says how many things you have to do today.
2. Press **New event** (in the sidebar, or the Menu on a phone). Type a name.
   Leave the date as today, or pick one. Press **Create event**.
3. You are on the new event. Its to-do list is already filled in. Press the
   circle next to one item. It is ticked. *(1 press.)*
4. In **What needs doing?** type "Order T-shirts", pick **Who? → Media
   team**, and press **Add**.
5. Open **People**. Paste three names, one per line, and press **Add these
   people**. They are on the event.
6. Open **Schedule** and press **Take attendance** for the main session.
   Everyone starts ticked. Untick one person, type a walk-in, put 2 in
   **hours**, and save.
7. Open **Money**. Type "Snacks" and 500, and press **Ask**. It shows as
   Asked. *(3 presses from My work.)*
8. Remove a to-do, then press **Undo** in the message that appears.

You should see: nothing asks for the same thing twice, every save brings you
back to the same card, nothing is lost by Remove, and there is no way to
approve money or finish an event.

## Media head (and Culturals head)

1. Sign in as `media1`. My work lists your team's items from every event —
   both ICC and IGP — and nobody else's.
2. Find "Order T-shirts" from the Events head's journey. Press its circle.
   *(1 press.)*
3. Find an item about a poster or photos. Press **Add file** and pick any
   image. The file is sent and the item is ticked. *(2 presses.)*
4. Open an event from **Your events**. You see only your team's to-dos and
   the files you added. You do not see People, Money or Schedule.

Repeat with `cultural1`: you see only Culturals items.

## Faculty

1. Sign in as `faculty1` and open My work. **Needs your OK** is at the top.
2. Press **Approve** on the Snacks money request. It disappears and you stay
   on My work. *(1 press.)*
3. Press **Not now** on another item. It opens the event; write a short
   reason and send it back.
4. If an event is waiting to be finished, press **Sign off**.
5. Open **People** (in the sidebar, or the Menu on a phone). Find someone,
   press **Change**, make them a Culturals head and save. Change them back
   afterwards.
6. Open **Reports**. Check this year's five numbers and that finished events
   have a **Report (PDF)**.
7. Open **Who changed what**. Your approval is there as a sentence.

You should see: only money, finishing an event and the website ever need
your OK, and you are never asked to approve something you asked for
yourself.

## USC

1. Sign in as `usc`. My work shows items handed to the USC and today's
   event, if there is one.
2. Open **Events**, pick an ICC event, open **Event details** and fix a
   spelling. Save. You come back to the same card.
3. Open **Upload a sheet**. Download the empty People sheet, add two rows,
   and upload it. It is checked, and it says it is waiting for Faculty to
   save it.
4. Try to approve anything — there is no button for it.

## IGP head

1. Sign in as `igp1`. Under Events and My work you see IGP programmes only.
2. Make a new event from an itinerary file, or open an IGP programme.
3. Open **Buddies** and pair a buddy with a student.
4. Open **Feedback** and press **Make feedback link**. Open the link in a
   private window and answer it without signing in. The answer shows on the
   card.
5. When the programme's last day has passed, press **Finish event**, tick
   "Also show on the public website", and send it to Faculty.

## Sign up as someone new (Volunteer)

1. Sign out. Press **New here? Sign up**.
2. Use a `@christuniversity.in` email. You go straight in as a volunteer and
   land on **My activities**.
3. An email from any other domain is refused.
4. You see only the events you are on, with when and where, your job and
   your buddy — nothing about anyone else. Ask Faculty to add you to an event
   if the list is empty.
5. The sidebar has only My activities and Account (and the Menu). Opening
   Campuses is refused.
6. Open **Account**, open **Your details**, add a phone number and your
   register number, and press **Save**. It says "Saved ✓".

## Public website check

1. Open `/public/` in a private window, without signing in.
2. Open an event and a published report.
3. You see only what Faculty put on the website. Names of people, register
   numbers, money, buddy pairs and private Drive links never appear.

## If something goes wrong

- Too many wrong passwords locks the account for a few minutes. Wait, or ask
  the coordinator. Do not keep trying. Password-reset emails are not sent
  during testing, so a forgotten password also goes to the coordinator, who
  can run `seed-beta` again only if everyone is told first — it resets the
  whole site.
- If a save seems to work but the value is gone after you reload, stop and
  report the event, the card, the field and the time.
- If you can see something you think you should not, tell the coordinator
  straight away. Do not work around it.
- When testing ends, delete the password sheet and ask the coordinator to
  switch the test accounts off.

## What this guide does not prove

Passing these journeys is not sign-off for the real site, university
sign-in, real email or Drive, a security test, or a backup-and-restore drill.
Those are recorded separately.
