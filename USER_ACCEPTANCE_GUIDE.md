# ICC — user testing guide

This guide is for people testing the app before it goes live. The test site
has made-up records. Do not type in real student, staff, money, health or
private details.

Each role has one short journey below. Every journey starts on **My work**,
the page you see after signing in. If anything takes more presses than the
journey says, or a word on screen is hard to understand, write it down — that
is a finding.

## Start the test site on this computer

Open Terminal and run these commands from the project folder:

```bash
cd "/Users/Shiva_1/Desktop/ICC ERP/icc-platform-2"
export DATABASE_URL="sqlite:////Users/Shiva_1/Desktop/ICC ERP/icc-platform-2/instance/uat_acceptance.db"
export DEMONSTRATOR=true
export APP_ENV=testing
export TESTING=true
export SECRET_KEY="local-uat-only-change-me"
.venv/bin/flask --app run.py run --host 127.0.0.1 --port 5010
```

Then open [http://127.0.0.1:5010/login](http://127.0.0.1:5010/login). Keep
Terminal open while you test. To stop the site, go back to Terminal and press
**Control+C**. Do not reset or delete this test database; ask the coordinator
if the sample records need putting back.

## Before you begin

1. Get your username and one-time password from the private sheet the
   coordinator gives you. Every account has its own password.
2. Use a current Chrome, Firefox, Safari or Edge. Try at least one journey on
   a phone as well — event-day work is done on phones.

## Sign in

1. Type your username and the one-time password.
2. Press **Sign in**.
3. Pick your own new password when asked.
4. You land on **My work** (volunteers land on **My activities**). Check that
   the badge at the bottom of the left rail says your role.

## Test accounts

| Username | Role | What they do |
|---|---|---|
| `uat_faculty_admin` | Faculty | Says yes to money, finished events and the website. Makes people heads. |
| `uat_usc` | USC | Types in event details for any ICC event. Approves nothing. |
| `uat_icc_events_head` | ICC Events head | Runs ICC events. |
| `uat_igp_head` | IGP head | Runs IGP programmes. |
| `uat_media_head` | ICC Media head | Does the Media team's work on any ICC or IGP event. |
| `uat_culturals_head` | ICC Culturals head | Does the Culturals team's work on any ICC or IGP event. |
| `uat_volunteer` | Volunteer | Only looks at the events they are on. |

Accounts are made by an operator with `DEMONSTRATOR=true` and
`PROVISION_UAT=1` (`flask provision-uat`); the passwords are written to
`instance/UAT_CREDENTIALS.txt`, readable only by that operator. The command
refuses to run anywhere else, so it cannot make test accounts on the real
site.

## ICC Events head

1. Sign in as `uat_icc_events_head`. My work says how many things you have
   to do today.
2. Press **+ New event**. Type a name. Leave the date as today, or pick one.
   Press **Create event**. *(2 presses.)*
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
back to the same card, and nothing is lost by Remove.

## Media head (and Culturals head)

1. Sign in as `uat_media_head`. My work lists your team's items from every
   event — both ICC and IGP — and nobody else's.
2. Find "Order T-shirts" from the Events head's journey. Press its circle.
   *(1 press.)*
3. Find an item about a poster or photos. Press **Add file** and pick any
   image. The file is sent and the item is ticked. *(2 presses.)*
4. Open an event from **Your events**. You see only your team's to-dos and
   the files you added. You do not see People, Money or Schedule.

Repeat with `uat_culturals_head`: you see only Culturals items.

## Faculty

1. Sign in as `uat_faculty_admin`. **Needs your OK** is at the top.
2. Press **Approve** on the Snacks money request. It disappears and you stay
   on My work. *(1 press.)*
3. Press **Not now** on another item. It opens the event; write a short
   reason and send it back.
4. If an event is waiting to be finished, press **Sign off**.
5. Open **People** (in the rail, or the Menu on a phone). Find the volunteer,
   press **Change**, make them a Culturals head and save. Make them a
   volunteer again afterwards.
6. Open **Reports**. Check this year's five numbers and that finished events
   have a **Report (PDF)**.
7. Open **Who changed what** from the Menu. Your approval is there as a
   sentence.

You should see: only money, finishing an event and the website ever need
your OK, and you are never asked to approve something you asked for
yourself.

## USC

1. Sign in as `uat_usc`. My work shows items handed to the USC and today's
   event, if there is one.
2. Open **Events**, pick an ICC event, open **Event details** and fix a
   spelling. Save. You come back to the same card.
3. Open **Upload a sheet** from the Menu. Download the empty People sheet,
   add two rows, and upload it. It is checked, and it says it is waiting for
   Faculty to save it.
4. Try to approve anything — there is no button for it.

## IGP head

1. Sign in as `uat_igp_head`. You see IGP programmes only.
2. Make a new event from an itinerary file, or open an IGP programme.
3. Open **Buddies** and pair a buddy with a student.
4. Open **Feedback** and press **Make feedback link**. Open the link in a
   private window and answer it without signing in. The answer shows on the
   card.
5. When the programme's last day has passed, press **Finish event**, tick
   "Also show on the public website", and send it to Faculty.

## Volunteer

1. Sign in as `uat_volunteer`. You see **My activities**: each event you are
   on, its time and place, your job and your buddy.
2. Open an event. You see when and where, your job and your buddy — nothing
   about anyone else, and nothing to fill in.
3. The rail has only My activities and Account (and the Menu).
4. Open **Account**, open **Your details**, add a phone number and your
   register number, and press **Save**. It says "Saved ✓" and the numbers
   show on the folded card.

## Sign up as someone new

1. Sign out. Press **New here? Sign up**.
2. Use a `@christuniversity.in` email. You go straight in as a volunteer.
3. An email from any other domain is refused.

## Public website check

1. Open `/public/` in a private window, without signing in.
2. Open an event and a published report.
3. You see only what Faculty put on the website. Names of people, register
   numbers, money, buddy pairs and private Drive links never appear.

## If something goes wrong

- Too many wrong passwords locks the account for a few minutes. Wait, or ask
  the coordinator. Do not keep trying.
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
