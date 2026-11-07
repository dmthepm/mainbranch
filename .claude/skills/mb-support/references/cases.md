# The cases file

`state/support/cases.md` holds one line per case, in a table. A table keeps each
promise and its proof on one row, so "what is overdue" is a scan, not a search.

```markdown
# Support cases

Check every: 2 hours. Flag a missed check after: 6 hours.
Scheduler confirmed by the owner: 2026-11-04.

Check: 2026-11-04 08:00, 2 new, 3 open

| Case | Channel | Conversations | Asked | Promised | Due | Approved | Proof | Status |
|---|---|---|---|---|---|---|---|---|
| C-014 | email | mail:t-4471, chat:c-902 | swap size, order has wrong fit | first swap free, new item shipped | 2026-11-06 | card D-211 | reply delivered 11-04 09:12, new order noted | waiting |
| C-015 | chat | chat:c-915 | refund failed last month | retry refund | 2026-11-05 | card D-212 | | open |
```

## Columns

- **Case**: a short id, `C-` and a number. Never an order number or a name.
- **Channel**: a name from `core/support/channels.md`. Every channel uses this
  one table; a chat case has the same promise, due date, approval and proof as
  an email case.
- **Conversations**: every conversation the case covers, as provider ids only
  (a thread id, a chat id). No names or addresses. One customer asking twice, or
  on two channels, is one case with several ids. The repo keeps only the link;
  the agent matches by reading the providers.
- **Asked**: the customer's request in a few words. No personal detail.
- **Promised**: exactly what the business said it would do. Empty if nothing
  has been promised yet.
- **Due**: the date the promise falls due. A promise without a date is not logged.
- **Approved**: the owner's approval reference (a decision card id, a message
  link, a commit). A send, refund or spend with no reference is a defect.
- **Proof**: the evidence the promise was kept: delivery confirmation of the send,
  the refund id, the replacement order note. Not "done".
- **Status**: `open`, `waiting` (on the customer or a supplier, with who),
  `reopened`, `done`, `closed-no-action`.

## Rules

- A case is `done` only when Proof is filled and the verification in SKILL.md
  passed. A bounce or failure sets `reopened`.
- Never delete a line. Closed cases stay, so the review can count them.
- Detail stays in the provider (the inbox, the store). The line carries the id
  that finds it, never a message body or an address.
- Before adding a line, check the open cases for the same request. If a match is
  unsure, ask the owner; never merge two cases on a guess.
- One reply per case unless the owner approves more. Log the approval for each
  extra reply in **Approved**.
- Each check run appends its `Check:` line above the table.
- If the file grows past a few hundred lines, move `done` cases older than a
  quarter to `state/support/cases-archive.md`; the review reads both.

## Cases that live in a tracker

Some businesses keep cases as issues in a tracker. Then the tracker is the case
log, because `state/` is neither durable nor private for them: the tracker holds
the history and the access list, and a second copy in `state/` would drift from
it and sit in a different place with different readers.

- Keep one tracker item per case, with the same fields as the columns above
  (conversations, asked, promised, due, approved, proof, status). The same
  rules apply: provider ids only, no names, addresses or message bodies.
- Write only what everyone with tracker access may see. Assume it is shared.
- `state/support/cases.md` then holds the `Check:` lines and the tracker's name,
  and no case rows.
- Where the tracker syncs with a mail thread, a comment there may email the
  customer. That counts as a send (see "Always ask" in SKILL.md). Draft it as a
  note for the owner, and post it only after approval.
