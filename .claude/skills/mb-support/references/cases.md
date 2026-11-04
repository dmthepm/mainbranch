# The cases file

`state/support/cases.md` holds one line per case, in a table. A table keeps each
promise and its proof on one row, so "what is overdue" is a scan, not a search.

```markdown
# Support cases

Check every: 2 hours. Flag a missed check after: 6 hours.
Scheduler confirmed by the owner: 2026-11-04.

Check: 2026-11-04 08:00, 2 new, 3 open

| Case | Channel | Asked | Promised | Due | Approved | Proof | Status |
|---|---|---|---|---|---|---|---|
| C-014 | email | swap size, order has wrong fit | first swap free, new item shipped | 2026-11-06 | card D-211 | reply delivered 11-04 09:12, new order noted | waiting |
| C-015 | chat | refund failed last month | retry refund | 2026-11-05 | card D-212 | | open |
```

## Columns

- **Case**: a short id, `C-` and a number. Never an order number or a name.
- **Channel**: email, chat, form, social, phone. Every channel uses this one
  table; a chat case has the same promise, due date, approval and proof as an
  email case.
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
- Each check run appends its `Check:` line above the table.
- If the file grows past a few hundred lines, move `done` cases older than a
  quarter to `state/support/cases-archive.md`; the review reads both.
