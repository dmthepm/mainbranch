---
title: books privacy and integration plan for hledger reports
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/560
linked_linear: MAIN-357
release: unscheduled
status: complete
tags: [bookkeeping, privacy, hledger, integration]
---

# Books Privacy And Integration Plan For hledger Reports

## Summary

Keep readiness and reporting separate.

Status/readiness answers: "Is bookkeeping configured safely, and what should
the operator do next?"

Report output answers: "What did hledger compute from an explicitly selected
fake or private journal?"

The first report implementation should read only fake packaged data. It should
not read real private books, copy fixture journals into generated business
repos, or expand daily status with private financial totals.

## Where Sample Journals Should Live

Use the existing public/package split:

```text
docs/examples/books/acme-fixture.journal
mb/mb/_data/books/acme-fixture.journal
```

The docs copy is the human-readable public example. The packaged copy is what
installed `mb` can use for fixture-backed checks and sample reports.

Tests already require both journal copies to carry a fixture marker and stay
byte-identical. Keep generated JSON report examples in docs unless runtime code
needs to read a cached output fixture.

Do not copy fake journals into generated business repos with `mb init` or
`mb onboard`. A sample report should be available from the package, not by
placing ledger-shaped files in the user's business repo.

## Package Data Shape

The first implementation generates report output from the packaged fake journal
at runtime. Keep the documented JSON example under the docs namespace and test
it against real hledger output when hledger is available:

```text
docs/examples/books/
  acme-fixture.journal
  reports/
    sample-monthly.json

mb/mb/_data/books/
  acme-fixture.journal
```

If a future implementation needs cached expected output fixtures in package
data, keep them under the same fake-data namespace and make runtime or smoke
tests consume them so they cannot drift silently. Only fake fixture outputs
generated from fake fixture data belong there. Do not package real ledgers, real
statement exports, or private-vault examples.

## Status And Start Integration

Preserve the current split:

- `mb books status --json`: detailed safe setup/storage health.
- `mb books doctor --plan --json`: non-mutating setup repair plan.
- `mb status --json --peek`: compact, safe `books` readiness.
- `mb start --json`: compact, safe `books` readiness for daily-loop agents.
- `/mb-start`: starts from status/start facts and routes explicit bookkeeping
  intent to `mb books` commands.

Do not add report totals to `mb status --json --peek` or `mb start --json`.
Daily-loop status should remain safe to share and route-oriented.

## Proposed Report JSON Envelope

The first sample report command should produce a Main Branch envelope rather
than exposing hledger's raw JSON.

Recommended command shape:

```bash
mb books report monthly --sample --month 2026-01 --json
```

The first implementation issue can still choose `mb books report
sample-monthly --json` if a named sample action proves cleaner, but the
`monthly --sample --month` shape ages better once private monthly reports land.

Recommended schema name:

```text
mainbranch.books.report.v1
```

Recommended sample envelope:

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
    "revenue": {
      "commodity": "USD",
      "decimal_mantissa": 25000,
      "decimal_places": 2,
      "display": "$250.00"
    },
    "expenses": {
      "commodity": "USD",
      "decimal_mantissa": 6750,
      "decimal_places": 2,
      "display": "$67.50"
    },
    "net_income": {
      "commodity": "USD",
      "decimal_mantissa": 18250,
      "decimal_places": 2,
      "display": "$182.50"
    },
    "cash": {
      "commodity": "USD",
      "decimal_mantissa": 125000,
      "decimal_places": 2,
      "display": "$1,250.00"
    },
    "credit_card": {
      "commodity": "USD",
      "decimal_mantissa": 6750,
      "decimal_places": 2,
      "display": "$67.50 owed"
    }
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

For future real private-vault reports, default `safe_to_share` should be
`false` unless the command explicitly produces an approved sanitized summary.
The envelope should still omit private paths and raw transaction rows.

Do not hardcode hledger versions in the JSON schema. If implementation adds an
`engine_version` diagnostic later, populate it from the live `hledger --version`
result for the command run.

## Fields Never To Expose In Readiness

Never expose these through `mb status`, `mb start`, or generated runtime
guidance:

- real ledger contents;
- transaction rows;
- hledger binary absolute path;
- private absolute vault path outside the business repo;
- bank, card, routing, tax, payroll, customer, vendor, invoice, dispute, or
  legal identifiers;
- raw CSV, OFX, QFX, QBO, QIF, or statement contents;
- unsafe artifact filenames in compact readiness;
- private finance repo local paths;
- detailed account balances, payees, memos, or transaction dates from real
  books.

The current readiness adapter already omits contents, hledger binary paths,
external private paths, and unsafe filenames. Keep that property as reporting
lands.

## Private Vault Boundaries

Use the accepted storage model from
[docs/books.md](../../books.md) and the
[books foundation decision](../../../decisions/2026-05-11-mb-books-foundation.md):

- `solo-local`: real books live under `.mb/private/books/`, ignored by the
  business repo. `main.journal`, imports, cache, detailed reports, and
  attachments stay there.
- `team-private-repo`: real books live in a restricted finance repo. The hub
  repo stores only safe policy, topology, and approved summaries.
- `advanced-vault`: real books live in encrypted or off-platform storage. The
  hub repo stores only a safe label/handle, not the literal private path.

Team-visible hub content that can be safe:

- `core/finance/books.md`;
- `core/finance/chart-of-accounts.md`;
- safe import-rule templates with no real identifiers;
- sanitized summaries under `docs/reports/finance/`;
- topology references to a restricted finance repo.

Not safe by default:

- real `.journal`, `.hledger`, `.ledger`, or `.beancount` files;
- bank, payment-processor, payroll, or tax exports;
- detailed reports from real books;
- account identifiers and row-level payment history.

## Tests For The Implementation Issues

Fixture packaging tests:

- sample journals carry explicit fake markers;
- docs and packaged copies are byte-identical;
- packaged report fixtures are generated from fake data only;
- the fake fixture passes `hledger check -s accounts commodities ordereddates`
  once strict reporting fixtures land.

Redaction tests:

- external absolute vault paths never appear in JSON or human output;
- hledger binary paths never appear;
- private journal content markers never appear in status/readiness;
- unsafe artifact filenames do not appear in compact status/start facts;
- real-data report output defaults `safe_to_share: false`.

No-real-data tests:

- committed unmarked `.journal` and statement-shaped `.csv` files still warn;
- marked fixtures remain exempt;
- `.mb/private/books/main.journal` presence is statted but not read by
  `status`, `start`, or readiness;
- report commands read private ledgers only in explicit report mode, not in
  status/start/readiness.

Integration tests:

- `mb status --json --peek` keeps compact `books` schema stable;
- `mb start --json` preserves the same compact `books` object;
- `/mb-start` docs route explicit finance intent through `mb books` facts;
- report output does not get folded into ranked actions except as a safe route
  or summary.

## Reporting Vs Readiness Rule

Report commands may be private. Readiness commands must stay safe to share.

That rule should drive every future `mb books` surface. If a command reads real
ledger rows, it is a report/import/reconcile command with explicit permission
and private output. It is not status, start, or daily-loop readiness.
