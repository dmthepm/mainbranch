# Books review modes

Apply the CLI-first and privacy rules in the parent SKILL.md in every mode.
Run `mb books check . --json` from the business repo, then
`mb books doctor --repo "$BOOKS_REPO" --json` after discovery. Do not paste
either command's full output into the hub or chat.

## Setup

Start from the documented storage choice in `docs/books.md`: solo local,
restricted team repo, or advanced encrypted/off-platform vault. The packaged
`mb/mb/_data/books/repo-template/` is a synthetic learning template. Copy it
to a newly created private books repo outside the hub only after the operator
chooses a location and access model. Review the copied `AGENTS.md` and README.
Record only the repo link and safe policy in the hub's `core/finance/books.md`.
Ask the operator to create the restricted evidence archive separately.

## Monthly close review

Read the books repo's close protocol, `docs/blockers.md`, and doctor receipt.
Use doctor JSON for shape, declared doctor, blocker count, and receipt freshness.
Summarize which close gates are passed, blocked, or unverified, without details
from statements, journals, reports, or evidence. Suggest the next operator
check by name. Never mark a period closed solely from a passing shape check.

## Reconciliation review

Read process docs and blocker states. Check whether the repo's protocol calls
for statement assertions, source-lane checks, and a combined doctor pass. Use
the declared doctor's aggregate result; ask the operator to investigate any
failing assertion inside the books repo. Propose a rules change as a diff for
operator approval when classification needs correction.

## CPA handoff prep

Identify the controlling assembly, receipt freshness, unresolved blocker count,
and delivery checklist from the books repo's protocol. Prepare a safe handoff
summary: period, gate state, receipt state, open question count, and private
repo/evidence links. The operator handles the detailed schedules and delivery
from the restricted books environment.
