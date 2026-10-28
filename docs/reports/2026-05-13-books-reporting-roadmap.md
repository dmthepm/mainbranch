---
title: hledger-backed books reporting roadmap
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/560
linked_linear: MAIN-357
release: unscheduled
status: complete
tags: [bookkeeping, hledger, roadmap, reports]
---

# hledger-backed Books Reporting Roadmap

## Recommendation

Build sample reporting before private-vault reporting.

The first implementation should add a beginner-safe sample monthly report using
hledger and fake packaged data. The command/action should mean "monthly report
using fake sample data." The exact CLI spelling can be settled in the
implementation issue; the preferred scalable shape is:

```bash
mb books report monthly --sample --month 2026-01 --json
```

`mb books report sample-monthly --json` remains an acceptable simpler candidate
if the implementation chooses a named sample action instead of a `monthly`
report subcommand with `--sample`.

The command should run hledger internally against the packaged Acme fixture,
translate hledger JSON into a stable Main Branch JSON envelope, and produce
plain-language output for agents to use in chat.

This is the fastest safe path from the current setup/readiness layer to useful
bookkeeping reports because it proves the full wrapper without touching real
Class B data.

## First Report Experience

User asks in chat:

```text
Show me a sample monthly bookkeeping report.
```

Agent runs internally:

```bash
mb status --json --peek
mb books status --json
mb books check --fixture --json
mb books report monthly --sample --month 2026-01 --json
```

Agent answers:

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

The user-facing UX is plain language. The skill/agent runs CLI commands
internally.

## hledger Commands To Power It

Use:

```bash
hledger -n -f <packaged-fixture> check
hledger -n -f <packaged-fixture> incomestatement -M -O json -b 2026-01-01 -e 2026-02-01
hledger -n -f <packaged-fixture> balance assets:bank assets:cash -H -M -O json -b 2026-01-01 -e 2026-02-01
hledger -n -f <packaged-fixture> balance liabilities:credit-card -H -M -O json -b 2026-01-01 -e 2026-02-01
```

The implementation may call `balancesheetequity -O json` as a broader validation
or future report primitive, but the first chat answer only needs revenue,
expenses, net income, cash, and credit card balance.

Do not parse terminal text. Read hledger JSON and convert it into a stable
Main Branch envelope.

## Sample Data Required

Use a small fake hledger journal with:

- explicit fixture marker in the first 1024 bytes;
- obviously fake company name;
- `commodity 1000.00 USD`;
- account directives with hledger account types for cash, liability, equity,
  revenue, and expense accounts;
- one opening balance;
- one sample customer payment;
- two sample expenses;
- one simple balance assertion.

Store it in:

```text
docs/examples/books/acme-fixture.journal
mb/mb/_data/books/acme-fixture.journal
```

Keep the two files byte-identical and covered by tests. Do not copy the fixture
into generated business repos.

## JSON Shape For Agents

Use this schema name:

```text
mainbranch.books.report.v1
```

Minimum fields:

Build this payload through the shared JSON result helper so standard top-level
fields such as `result_envelope_version`, `ok`, `result_status`, `errors`,
`warnings`, and `actions` stay consistent with other `mb --json` commands.

```json
{
  "schema_version": "1.0",
  "result_schema": {
    "name": "mainbranch.books.report.v1",
    "version": "1.0"
  },
  "mb_command": "mb books report monthly --sample --month 2026-01",
  "safe_to_share": true,
  "source": {
    "kind": "packaged_fixture",
    "fixture": true,
    "engine": "hledger",
    "journal": {
      "label": "acme-fixture",
      "location_kind": "packaged",
      "path_exposed": false,
      "content_read": true
    }
  },
  "report": {
    "kind": "sample_monthly",
    "period": {
      "start": "2026-01-01",
      "end": "2026-02-01",
      "label": "January 2026"
    },
    "currency": "USD"
  },
  "totals": {
    "revenue": {},
    "expenses": {},
    "net_income": {},
    "cash": {},
    "credit_card": {}
  },
  "operator_summary": "This fake sample month shows the reporting shape; it is not your business data.",
  "redactions": {
    "private_paths": true,
    "account_identifiers": true,
    "payees": true,
    "transaction_memos": true
  },
  "findings": []
}
```

Amounts should carry commodity, decimal mantissa, decimal places, and display
string. Do not expose hledger internals directly as the public contract.

## Privacy Boundaries

Allowed in the first implementation:

- fake packaged journal;
- fake generated report totals;
- hledger availability checks without printing the binary path;
- Main Branch JSON summaries marked as fixture data.

Disallowed in the first implementation:

- reading real private books vaults;
- reading private finance repos;
- importing provider exports;
- committing raw ledgers or statement exports;
- showing private paths;
- storing raw hledger JSON from private books;
- claiming accuracy, reconciliation, tax readiness, GAAP compliance, or
  bookkeeper replacement.

Future private reporting requires an explicit permission prompt before reading
the private vault:

```text
I can generate this from your private bookkeeping vault, but that means reading
real financial records on this machine. I will keep it read-only and summarize
only high-level totals unless you ask for detail. Do you approve reading the
private books vault for this report?
```

## Allowed And Disallowed Claims

Allowed:

- "sample bookkeeping report";
- "hledger-backed sample report";
- "fake packaged data";
- "setup/readiness";
- "private bookkeeping vault";
- "read-only report";
- "agent uses CLI facts internally";
- "chat-first bookkeeping experience".

Disallowed:

- "your finances are healthy";
- "your books are accurate";
- "tax ready";
- "GAAP compliant";
- "reconciled";
- "audited";
- "QuickBooks replacement";
- "bookkeeper replacement";
- "automated accounting".

## Implementation Issue Sequence

### 1. Add hledger-backed sample monthly report

```md
## Goal

Add a beginner-safe sample books report using hledger and fake packaged data.

## Scope

- monthly sample report command syntax, likely
  `mb books report monthly --sample --month 2026-01`
- hledger-backed sample report
- human output for chat/agent UX
- stable JSON output for agents
- fake packaged journal only
- no real vault reads

## Acceptance Criteria

- output is clearly sample/fake data
- hledger is used as the engine
- JSON is stable and public-safe
- human output is beginner-safe
- no private financial data is committed
- tests cover missing hledger, invalid month, fixture success, JSON shape,
  package data, and privacy boundary
```

Validation:

- focused `mb/tests/test_books.py` coverage;
- chosen sample monthly report command with `--json`;
- chosen sample monthly report command in human mode;
- missing-hledger path;
- package fixture byte-identity test;
- `scripts/check.sh`;
- package/install smoke because packaged data and CLI behavior change.

Runtime smoke: not required unless generated skill behavior changes.

### 2. Route `/mb-start` and books skill guidance to sample reports

```md
## Goal

Teach agents to answer sample bookkeeping prompts through the shipped sample
report command.

## Scope

- `/mb-start` bookkeeping route update
- generated repo guidance if needed
- runtime command reference tests
- no private-vault reporting
```

Validation:

- tests that skill/guidance references use the shipped command shape;
- `scripts/check.sh`;
- Claude Code runtime/manual note if bundled skill behavior changes.

### 3. Design private-vault read-only report permission gate

```md
## Goal

Specify and test the permission boundary for future private books summaries.

## Scope

- permission prompt copy
- report envelope for real private data
- redaction rules
- no import/reconcile/mutation
- no raw transaction rows in public output
```

Validation:

- CLI tests for denied permission / no-read path;
- redaction tests for private paths, binary paths, account identifiers, and raw
  row markers;
- fixture repo smoke with fake private vault only;
- no runtime smoke unless skill behavior changes.

### 4. Add read-only private monthly summary

```md
## Goal

Generate a private, read-only monthly bookkeeping summary after explicit
operator approval.

## Scope

- real private vault read after approval
- high-level totals only by default
- `safe_to_share: false`
- no import, reconcile, close, or mutation
```

Validation:

- fake private-vault fixture repo smoke;
- tests proving status/start do not read the ledger;
- tests proving report mode does read only after explicit approval path;
- redaction and no-public-output tests;
- package/install smoke if packaged behavior changes;
- runtime/manual validation if bundled skill guidance changes.

## Follow-up To Track Separately

The current Acme fixture works for the shipped basic check. The first sample
report implementation should add a `commodity` directive and strict fixture
validation so `hledger check -s accounts commodities ordereddates` can pass.

Do not broaden the first implementation into import, reconcile, close, tax,
payroll, dashboard, or provider work.

## Success Metric

An implementation agent can build the sample report without re-deciding product
shape:

- command name is known;
- hledger command families are known;
- fake data location is known;
- JSON envelope is known;
- chat output is known;
- privacy boundary is known;
- validation ladder is known;
- private-vault reporting is explicitly later.
