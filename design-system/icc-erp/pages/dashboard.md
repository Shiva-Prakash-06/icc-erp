# Home Override

Inherits `MASTER.md`.

- The page answers one question: what is waiting on me. Greeting, a one-line count, and a single primary action, then the counters, then the queue.
- Counters are `.kpi-card` tiles in an auto-fit grid. Each one with a real destination is an `<a>` to the filtered list behind it; the rest are plain `<div>`s. Never fabricate a filter the server does not offer just to make a tile clickable.
- The decision queue is a real `<table>` — one `<tr>` per record, with a visually hidden header row — laid out as stacked rows. Table semantics matter: the queue is the app's primary list and assistive tech, and the e2e row matcher, both depend on them.
- Each row carries the approve action inline (a `POST` to the entity's existing `.../decision` endpoint with `status`, `version` and a relative `next`), a send-back link to the record, and an open-record link whose accessible name is `Review` and whose `href` ends in the record's anchor.
- Approving must return the approver to where they were. Send-back must not, because it needs a reason.
- Non-approvers get their own open tasks and requests in the same list, not three collapsed disclosures at the foot of the page.
- The aside holds what is next (upcoming sessions, with a roll-call action where permitted), where you left off, and IGP indicators.
- Charts always include a text insight and an accessible data table or disclosure.
