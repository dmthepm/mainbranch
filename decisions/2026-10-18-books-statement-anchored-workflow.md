---
type: decision
date: 2026-10-18
status: accepted
topic: Statement-anchored books workflow
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/128
linked_decisions:
  - decisions/2026-05-11-mb-books-foundation.md
linked_docs:
  - docs/books.md
  - docs/books-workflow.md
participants: []
tags: [books, finance, hledger, workflow, privacy]
---

# Statement-Anchored Books Workflow

## Decision

This extends the [books foundation](2026-05-11-mb-books-foundation.md) with a
standard workflow for a private hledger books repo. Statements and provider
transaction exports are the only evidence for entries and balances. Previous
ledgers and app reports can suggest questions, but an operator must verify
their figures against source evidence.

Classification belongs in `rules/` files. Every rules file starts with a
`Status:` header set to `active recurring`, `migration generator`, or
`template/fallback`. The header also explains its input shape, date and sign
conventions, unknown-row account, transfer or clearing accounts, and fields
that require independent verification. A generator may normalize a difficult
source, but classification still comes from its documented rules. Generated
journals are reviewed as diffs and never hand-edited. Change a rule, regenerate,
and check the result.

Each statement close has a balance assertion. Promote one source lane from
draft to live at a time after its own assertions and the combined entrypoint
pass strict hledger checks. Keep unresolved items in a structured blocker list,
including the evidence needed and close impact. The books repo's own doctor
must pass before a push. One writer works in a books repo at a time, with a
pull before work and before push.

`mb books` stays one layer above the ledger. It may discover the private books
repo, check readiness, run the doctor that repo declares, and summarize close
state without exposing transaction detail. It never posts entries, rewrites
journals, or becomes another ledger engine.

## Why

A source statement can disprove an imported or reported figure. Rules and
generated journals make classification changes reviewable. Balance assertions
make a missing or duplicated row fail at the statement close. A single writer
and a passing doctor make the saved ledger state easier to trust.

## Operator Contract

Follow the [books workflow](../docs/books-workflow.md) for intake, imports,
reconciliation, close review, and private storage. The packaged
`mb/mb/_data/books/repo-template/` is a marked synthetic example, not a place
to keep real books. The existing three storage modes remain in
[books setup](../docs/books.md).

## Scope

This decision sets the workflow and example repo shape. It does not add an
import, reconcile, close, or posting command to `mb books`.
