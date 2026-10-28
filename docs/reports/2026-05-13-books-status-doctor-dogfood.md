---
title: mb books status and doctor plan dogfood
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/510
release: next patch candidate after v0.3.19
status: complete
tags: [bookkeeping, dogfood, hledger, privacy]
---

# `mb books status` And `doctor --plan` Dogfood

## Summary

Post-#553 bookkeeping dogfood confirms that the current `mb books` setup
surface is safe enough for the next slice: keep the CLI group named `books`,
use "bookkeeping" in operator-facing prose, and route setup/check requests
through deterministic `mb books` facts before drafting finance files.

The dogfood also produced two focused fixes:

- `/mb-start` now uses the shipped positional command shape:
  `mb books check "$REPO_PATH" --json`.
- `mb books status` and `mb books doctor --plan` now flag
  `team-private-repo` / `advanced-vault` policy files that omit a safe private
  vault label.

## Scope Exercised

Fake business repos covered:

- hledger missing and available;
- no books policy;
- invalid books policy, including unknown `storage_mode` and broken
  frontmatter;
- team-private books policy with no configured vault label;
- configured external vault;
- default `.mb/private/books` vault;
- configured local vault missing;
- configured local vault present;
- missing `.gitignore` protections;
- force-tracked fake journal-shaped file;
- missing chart of accounts;
- external absolute path redaction.

No real ledgers, bank exports, provider credentials, account identifiers,
financial amounts, or private absolute paths were committed. Raw evidence lives
only in ignored `.context/` scratch output.

## Answers

**Is `ok: true` with `state: warn` understandable?**

Yes for this slice. `ok` means the command can complete and no hard error was
found; `state: warn` means the operator should review setup before using real
books. Human output makes this legible enough when the warning has an exact
repair. Broken frontmatter still returns `ok: false` / `state: error`.

**Are status findings clear enough for a normal operator?**

Mostly. Good cases: missing hledger, missing policy, invalid storage mode,
missing local vault, missing ignore protections, and tracked journal-shaped
files all explain the issue in business-safe language. The dogfood found one
gap: non-local storage with no `vault_location` looked configured in prose but
had no repair. This report's branch fixes that.

**Is `doctor --plan` obviously non-mutating?**

Yes. The command name, human heading, and each JSON action's `mode: plan` plus
`safe_to_apply: false` make the posture clear. The command exits `2` without
`--plan`, so there is no accidental apply path.

**Are repair actions useful and safe?**

Useful for setup. They name the files or local ignored paths they would touch
and avoid reads from real vault contents. The unsafe tracked-file action is
safe because it tells the operator to move the file and run `git rm --cached`;
it does not mutate history or rotate data automatically.

**Do `mb status`, `mb start`, and relevant skills route bookkeeping setup/check
requests?**

Skills now route correctly. `/mb-start` and its router reference tell agents to
run `mb books check "$REPO_PATH" --json` before inventing structure and to keep
raw finance records out of the team-safe hub. `mb start --json` runs, but it
does not include books readiness. `mb status --json --peek` also has no
top-level `books` object yet. Follow-up #555 covers adding a compact books
readiness summary to `mb status` / `mb start` once the product wants
bookkeeping readiness in the daily briefing rather than only intent-triggered
routing.

**Does output avoid private absolute paths and real financial data?**

Yes. External absolute vault paths render as `external private path`. The
status surface reports whether a private `main.journal` placeholder exists but
does not read or print its contents. hledger availability reports the command
name, not the local binary path.

**Should docs use "books," "bookkeeping," or both?**

Both. Keep `mb books` as the short CLI group. Use "bookkeeping" in headings,
operator explanations, and safety language. This matches the current docs:
"The command group is named `mb books` because it is short; the business
function is bookkeeping."

## Recommendation

Next slice should improve daily-loop surfacing, not add accounting product
depth:

- ship #555 for read-only books readiness in `mb status --json --peek` and
  `mb start` only if it stays compact and privacy-safe;
- keep `/mb-start` intent-triggered routing through `mb books check` until
  status owns a stable books summary;
- do not add imports, reconcile, close, reports, Mercury, provider credentials,
  or real financial data yet.
