# Worked examples

Invented for illustration. Every id, date and case here is made up. They show
what the rules in SKILL.md and `cases.md` ask for; they are not a record of a
run, and they say nothing about how any runtime behaves.

This skill has not yet been exercised on a live business.

## Same request on two channels

A customer emails about a wrong-size item, then asks again in chat.

- The agent reads the open cases, then reads the chat and the mail thread in
  their providers. Same item, same request: one case.
- The line carries both ids and nothing else about the customer:
  `| C-021 | email | mail:t-5120, chat:c-77 | swap size | | | | | open |`
- One reply for the case, after the owner approves the exact text. The chat gets
  no second reply unless the owner approves one, logged in **Approved**.

## An unsure match

Two chats mention "my order is late". Each was logged as its own case when it
arrived, `C-022` for chat:c-80 and `C-023` for chat:c-83. Later the agent
notices they may be one customer.

- Both cases already existed before the match was noticed; nothing here opens a
  case. The agent cannot tell from the providers, so it does not merge and
  leaves both lines as they are.
- It asks the owner: "chat:c-80 and chat:c-83 may be one request. One case or
  two?" Until the answer, both stay open, with `waiting` on the owner.
- A provider whose conversation id is the customer's phone number: stop and ask
  the owner for a safe provider-side reference. Do not save the number.

## A tracker case

`cases.md` says the tracker `support-board` is the case log.

- Its content is the `Check:` lines and that name, no case rows:
  `Check: 2026-11-05 08:00, 1 new, 4 open`
- On a new message the agent searches the tracker for the same request first.
  Found: it updates that item. Not found: it opens one titled `C-024`, with the
  same fields as the table columns and provider ids only.
- The item is synced to a mail thread. The agent drafts the comment as a note
  for the owner and posts it only after approval, because the comment would
  email the customer.
- The weekly review reads the tracker for overdue promises. If it cannot be
  read, the entry opens with "tracker: unreadable since <time>" and lists no
  promise as overdue or clear.
