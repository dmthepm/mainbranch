---
title: hledger capability map for mb books reports
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/560
linked_linear: MAIN-357
release: unscheduled
status: complete
tags: [bookkeeping, hledger, reports, planning]
---

# hledger Capability Map For `mb books` Reports

## Summary

Main Branch should wrap hledger's read-only report commands before any import,
reconcile, or private-vault mutation workflow.

The first reporting slice should be a fake packaged monthly sample report. It
should run hledger against bundled fixture data, normalize hledger's structured
output into a small Main Branch JSON envelope, and let skills explain the result
in chat. Real private-vault reporting should follow only after the sample
report path proves command routing, JSON shape, redaction, and beginner-safe
copy.

Use hledger for accounting math. Use `mb books` for privacy, command routing,
JSON contracts, and plain-language summaries.

## Sources Checked

- Local `hledger 1.52.1` help for `check`, `balance`, `incomestatement`, and
  `register`.
- The official hledger manual: <https://hledger.org/hledger.html>.
- The hledger error guide: <https://hledger.org/ERRORS.html>.
- Existing Main Branch books docs and decisions:
  - [docs/books.md](../books.md)
  - [decisions/2026-05-11-mb-books-foundation.md](../../decisions/2026-05-11-mb-books-foundation.md)
  - [docs/reports/2026-05-11-hledger-vs-beancount-fit.md](2026-05-11-hledger-vs-beancount-fit.md)
- Current fake fixture:
  [docs/examples/books/acme-fixture.journal](../examples/books/acme-fixture.journal).

## First Command Families To Wrap

Wrap these first, always with an explicit journal path and no local hledger
config:

```bash
hledger -n -f <journal> check
hledger -n -f <journal> incomestatement -M -O json -b <start> -e <end>
hledger -n -f <journal> balance assets:bank assets:cash -H -M -O json -b <start> -e <end>
hledger -n -f <journal> balancesheetequity -M -O json -b <start> -e <end>
hledger -n -f <journal> register <account-query> -H -O json -b <start> -e <end>
```

Use `hledger print -O json` only for internal parse diagnostics. Do not expose
or persist its raw output in public docs, status, or chat summaries because it
contains full transaction rows and can include source locations.

## Report Mapping

| User need | hledger command family | Main Branch handling |
| --- | --- | --- |
| Monthly revenue | `incomestatement -M -O json` | Read hledger's revenue section; present as sample or private summary. |
| Monthly expenses | `incomestatement -M -O json` | Read hledger's expense section; preserve hledger sign handling. |
| Net income | `incomestatement -M -O json` | Use hledger's report total, not Main Branch arithmetic. |
| Cash/bank ending balance | `balance <cash/accounts> -H -M -O json` | Query configured cash/bank roots; `-H` keeps ending balances historical. |
| Balance sheet | `balancesheet -O json` or `balancesheetequity -O json` | Prefer high-level commands when account types are declared. |
| Account-level balances | `balance -H -O json <query>` | Use for configured account groups, not broad private detail by default. |
| Register detail | `register <query> -H -O json` | Keep detail private; use for debugging or approved private workflows later. |
| Parse/check | `check` and sometimes `print -O json` | `check` has human stderr, not JSON; wrap return code and redacted diagnostics. |

Do not use `cashflow` as the first answer for bank balance. `cashflow` reports
cash movement; `balance -H` is the better primitive for ending balances.

## Structured Output

The official hledger manual lists JSON support for the report families Main
Branch needs first: `balance`, `balancesheet`, `balancesheetequity`,
`cashflow`, `incomestatement`, `register`, `aregister`, and `print`.

Use `-O json` for machine reads. hledger's JSON is verbose and shaped around
hledger internals, so `mb books` should translate it into a small stable
schema. Preserve amounts as decimal parts from hledger JSON:

```json
{
  "commodity": "USD",
  "decimal_mantissa": 18250,
  "decimal_places": 2,
  "display": "$182.50"
}
```

Do not treat `floatingPoint` as the durable numeric value. It is convenient for
display checks but not the stable representation.

CSV/TSV can be useful for future exports. They are not the best first agent
contract because report-specific layouts vary. Text tables are for humans only;
Main Branch should never scrape terminal-formatted report tables.

`hledger check` does not produce JSON in the local 1.52.1 CLI. It exits `0`
with no output when clean, and exits non-zero with a human error on stderr when
the journal is missing, malformed, unbalanced, or fails assertions.

## Flags To Rely On

- `-n` / `--no-conf`: ignore hledger config so scripted reports are stable.
- `-f <journal>`: always choose the journal explicitly; never fall back to
  `$LEDGER_FILE` or `~/.hledger.journal`.
- `-b YYYY-MM-DD` and `-e YYYY-MM-DD`: use bounded periods. Treat `end` as the
  exclusive bound that hledger expects.
- `-M`: monthly interval.
- `-H`: historical accumulation for ending balances and bounded register views.
- `-O json`: structured output for report commands.
- `--pager=no --color=n`: when a future troubleshooting path captures text.
- `-s` / `--strict`: useful for fixture and private validation once fixtures
  declare accounts and commodities.

## Flags And Commands To Avoid First

- `-I` / `--ignore-assertions`, except as an explicit troubleshooting escape
  hatch. It disables balance assertion checks.
- `--auto`, `--forecast`, `--value`, `-V`, `-X`, and `--infer-*` until valuation
  and generated postings are explicitly in scope.
- `import` without `--dry-run`. Import mutates journals and `.latest.*` state.
- `add`, `close`, `rewrite`, `ui`, `web`, or any command that mutates data or
  starts a UI.
- `-o FILE` in early wrappers. Capture stdout and keep persistence under Main
  Branch's explicit report/privacy contract.
- Raw `print -O json` in public surfaces. It is useful for parsing but too
  detailed for safe summaries.

## Error Behavior To Wrap

hledger's failure mode is useful but not public-safe by default. It can include
file paths, account names, transaction descriptions, and line excerpts. `mb
books` should capture return code, stdout, and capped stderr, then emit a
redacted Main Branch finding.

| Condition | Observed hledger behavior | Main Branch wrapper behavior |
| --- | --- | --- |
| Missing journal file | Exit `1`, stderr says the data file was not found. | Report `journal_missing`; do not print absolute private path. |
| Invalid date / parse error | Exit `1`, stderr points to the bad line. | Report `journal_parse_error`; cap and redact detail. |
| Unbalanced transaction | Exit `1`, stderr shows transaction excerpt and imbalance. | Report `journal_unbalanced`; do not expose row text in shared output. |
| Balance assertion failure | Exit non-zero with assertion context. | Report `balance_assertion_failed`; keep details private unless explicitly requested. |
| Query matches no rows | Exit `0`, empty structured output. | Report `no_matching_activity`, not a failure. |
| `check -O json` | Exit non-zero because `check` does not support `-O`. | Do not call this shape. |

## Sample Journal Shape

The fake sample journal should stay small and obviously synthetic:

```journal
; SAMPLE FIXTURE -- NOT A REAL LEDGER
; Fictional company: Acme Fixture Inc.

commodity 1000.00 USD

account assets:bank:checking          ; type:A
account liabilities:credit-card       ; type:L
account equity:opening-balances       ; type:E
account income:sales                  ; type:R
account expenses:software             ; type:X
account expenses:office:supplies      ; type:X

2026-01-01 opening balance
    assets:bank:checking      1000.00 USD
    equity:opening-balances

2026-01-15 sample customer payment
    assets:bank:checking       250.00 USD
    income:sales

2026-01-20 sample software subscription
    expenses:software           49.00 USD
    liabilities:credit-card
```

The current fixture already works for the shipped basic fixture check. The
first reporting implementation should add a commodity directive so strict
fixture validation can include the `commodities` check.

## What Main Branch Must Not Compute

Main Branch should not compute accounting math itself:

- revenue totals;
- expense totals;
- net income;
- bank/cash balances;
- balance sheet totals;
- running register balances;
- sign normalization;
- balance assertions;
- historical accumulation;
- valuation or currency conversion;
- import overlap handling;
- reconciliation.

hledger owns those results. Main Branch owns the wrapper: privacy boundaries,
redaction, stable JSON, command selection, fixture packaging, repair guidance,
and chat-ready summaries.
