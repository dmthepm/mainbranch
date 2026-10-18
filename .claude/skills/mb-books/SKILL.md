---
name: mb-books
description: Review private books setup, monthly close, reconciliation, and CPA handoff from safe Main Branch facts.
loops: [sense, reflect]
---

# Books

Use this skill for books repo setup, monthly close review, reconciliation review,
and CPA handoff preparation. Keep the ledger in its separate private repo.

**CLI facts first:** In the business hub, run `mb books check . --json` before
advice. Discover the books repo from `books_repo` in `core/finance/books.md`;
if it is absent, ask the operator for the repo location. Run
`mb books doctor --repo "$BOOKS_REPO" --json` and use its safe aggregate facts.
The human form `mb books doctor --repo "$BOOKS_REPO"` is available for an
operator at their terminal. Do not relay raw command output.

## Hard rules

- Never post or edit journal entries.
- Never run `hledger import` or `hledger add`.
- Never open or read evidence bytes (statements, PDFs, CSVs, OFX/QFX/QBO/QIF).
- Never print or quote doctor stdout/stderr, payees, account numbers, amounts or tax IDs into the hub or chat.
- Rules edits are proposed as a diff for the operator to apply in the books repo.
- The hub repo keeps only safe summaries, decisions and links.

Read the books repo's own `AGENTS.md`, protocol docs, and `docs/blockers.md`
only for process and close state. Blocker descriptions may contain private
details; return counts and states without copying descriptions. Consult
[`references/modes.md`](references/modes.md) for each review mode. The public
`docs/books-workflow.md` is background for the operator; follow the books
repo's current protocol for its actual close.

If the declared doctor cannot run on this host, use its aggregate `not_run`
status and any receipt freshness in the JSON. Say what remains unverified.
Do not treat an old receipt or a shape pass as a completed close.
