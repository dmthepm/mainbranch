---
title: books operator UX spec for sample reports
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/560
linked_linear: MAIN-357
release: unscheduled
status: complete
tags: [bookkeeping, hledger, operator-ux, chat]
---

# Books Operator UX Spec For Sample Reports

## Decision

Build a chat-first sample bookkeeping report before private-vault reporting.

The operator should ask the agent for a books summary. The agent should run
deterministic `mb books` commands internally, then answer in plain business
language. The user does not need to know hledger flags, JSON, journal paths,
`.gitignore`, or double-entry mechanics unless they ask.

The first experience should be:

```text
User asks: "Show me a sample monthly bookkeeping report."
Agent runs: mb books report monthly --sample --month 2026-01 --json
Agent says: "Here is a fake sample report so you can see the shape."
```

The command spelling is a recommendation for the next implementation issue, not
a shipped surface in this report. `mb books report sample-monthly --json` is an
acceptable simpler candidate if implementation chooses a named sample action.

## Product Surface

The product surface is the chat answer, not the terminal command.

```text
hledger = accounting/reporting engine
mb books = safe wrapper, JSON layer, privacy boundary, workflow contract
skills/agents = chat UX and operator guidance
```

The agent may mention hledger as a short detail:

```text
Under the hood, Main Branch uses hledger as the reporting engine.
```

Do not make hledger the user-facing noun. The user-facing noun is
bookkeeping.

## Good User Prompts

- "Show me a sample monthly bookkeeping report."
- "What would a Main Branch books summary look like?"
- "Can you show revenue, expenses, and cash for the sample books?"
- "Is my bookkeeping setup ready?"
- "Explain the books status in plain English."

Future private reporting prompts, after the privacy contract ships:

- "Read my private books vault and summarize last month."
- "Show me last month's high-level bookkeeping summary."
- "Check whether my private books are ready for a read-only report."

## Prompts That Need Clarification

Clarify before acting on vague or risky prompts:

- "Run my books."
- "Check my finances."
- "Tell me if my books are right."
- "Am I tax ready?"
- "Reconcile last month."

Recommended clarification:

```text
I can help with a read-only bookkeeping summary, but raw finance needs a
stricter boundary. Do you want the fake sample report, or are you asking me to
read your private bookkeeping vault?
```

## Internal Agent Checks

For the first sample-report slice, the agent should start from safe facts:

```bash
mb status --json --peek
mb books status --json
mb books check --fixture --json
mb books report monthly --sample --month 2026-01 --json
```

If the sample report command does not exist yet, the agent should not improvise
private reporting. It should explain that the sample report is planned and use
current readiness commands only.

For future private-vault reporting, the agent should run readiness checks first:

```bash
mb books status --json
mb books doctor --plan --json
```

Then it must ask permission before reading a private journal.

## What The Agent Says Back

For sample data:

```text
I checked the sample books fixture and generated a fake monthly report. This is
packaged sample data, not your business.
```

Do not say:

```text
I ran hledger with `-f` and parsed `-O json`.
```

Technical detail is available on request, but it should not lead the normal
answer.

## Sample Monthly Report Copy

```text
Here is the sample monthly bookkeeping report for Acme Fixture Inc. This is
fake packaged data, not your business.

January 2026 sample

Revenue: $250.00
Expenses: $67.50
Net income: $182.50
Checking cash at month end: $1,250.00
Credit card balance: $67.50 owed

Plain-English read: the sample business received one customer payment, recorded
two small expenses, and ended the month positive. Because this is fixture data,
do not treat it as financial advice or evidence about your own books.

Next safe step: I can check whether your private bookkeeping setup is ready,
without reading the private ledger yet.
```

This copy is intentionally modest. It explains the reporting shape without
claiming anything about the operator's real business.

## Fake Vs Private Data

Use this distinction:

```text
The sample report uses fake packaged data so you can see the reporting shape
safely. Your private books are different: they live in a private bookkeeping
vault and may contain real transactions, bank exports, customer payments,
payroll, tax records, and account details. I will not read those unless you
explicitly approve it.
```

Short version:

```text
Sample books show the shape. Private books are your real records.
```

## Permission Before Future Private Reads

Before any private-vault read:

```text
I can generate this from your private bookkeeping vault, but that means reading
real financial records on this machine. I will keep it read-only and summarize
only high-level totals unless you ask for detail. Do you approve reading the
private books vault for this report?
```

For team-private repo mode:

```text
This may require access to a restricted finance repo. Only approve if this
chat/session is allowed to see that data.
```

If denied:

```text
No problem. I will stay with the fake sample report or setup readiness only.
```

## Hidden By Default

Hide unless the user asks for technical detail or is debugging setup:

- hledger command flags;
- hledger binary path;
- JSON schema details;
- private vault paths, especially absolute paths;
- `.gitignore` mechanics;
- raw hledger output;
- ledger row details;
- account identifiers;
- vendor, customer, payroll, tax, receipt, and statement details.

## Beginner-Safe Language

Use:

- "bookkeeping";
- "sample books";
- "fake sample data";
- "private bookkeeping vault";
- "read-only report";
- "setup is ready" / "setup needs attention";
- "safe summary";
- "the agent checked the bookkeeping safety rules".

Avoid leading with:

- hledger;
- double-entry;
- journal file;
- gitignored;
- JSON;
- CLI;
- account directives;
- balance assertions.

## Claims To Avoid

Never claim:

- "your finances are healthy";
- "your books are accurate";
- "tax ready";
- "GAAP compliant";
- "reconciled";
- "audited";
- "QuickBooks replacement";
- "bookkeeper replacement";
- "automated accounting";
- "we imported your bank data";
- "we read your private books" unless explicit permission was granted and the
  command actually did.

Allowed claim:

```text
This is a read-only summary from the sample hledger fixture. It is useful for
showing the reporting shape, not for judging a real business.
```

## Non-hledger User Feel

The experience should feel like asking an operations assistant:

- "Show me last month's bookkeeping summary."
- "Is setup ready?"
- "What is missing before we can use real books?"
- "Show me a fake example first."

The agent uses hledger internally. The operator gets a plain-language report
with clear boundaries.
