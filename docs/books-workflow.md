# Statement-Anchored Books Workflow

Use this protocol inside a private hledger books repo. Start with
[books setup](books.md) to choose solo local, team private repo, or advanced
encrypted/off-platform vault storage. The
[workflow decision](../decisions/2026-10-18-books-statement-anchored-workflow.md)
sets the boundary: `mb books` checks and summarizes; the books repo and hledger
own entries and controls.

## Settle a Statement Period

1. Pull the books repo before editing. Allow one writer in that repo at a time.
2. Download the statement and any provider transaction export. Give each file
   a stable date-and-source name as it arrives. Keep the bytes in the private
   evidence store and verify a SHA-256 after transfer.
3. Add a manifest pointer, hash, and short statement of what the file proves.
   Keep evidence bytes out of the repo.
4. Preview recurring CSV imports with `hledger import --dry-run` and the
   source's `.rules` file. For one-time or difficult inputs, generate a dated
   draft journal. Keep any import state with its source lane.
5. Put a balance assertion on every statement close for bank, card, debt, and
   major clearing lanes.
6. Classify unknown rows by editing `rules/`, regenerate the journal, and
   review the diff. Never edit a generated journal by hand.
7. Check and promote one draft source lane at a time. Run strict hledger checks
   on that lane and the combined entrypoint, including date order.
8. Record missing evidence and unresolved decisions in a blocker list with an
   id, owner, status, evidence needed, close impact, and a check command. Keep
   resolved items with their resolution.
9. Run `./bin/books doctor`. Investigate any unexpected movement in reports.
   Pull again before pushing, then push only a passing books repo.
10. Build one controlling assembly for accountant handoff. Distinguish settled
    questions from genuinely open ones. Add a dated adjustment only when the
    entry and its supporting schedule agree.

## Rules and Account Patterns

Keep one rules file per source family or account. Its header states `Status:`
as `active recurring`, `migration generator`, or `template/fallback`, plus the
export shape, filename, date format, sign convention, default unknown account,
transfer or clearing accounts, and fields that cannot be trusted without a
statement. A fallback must remain visibly distinct from an active feed.

Route unknown rows to named, visible accounts such as
`expenses:unknown:source`, `liabilities:unknown:source`, or
`assets:clearing:source`. Explain material unknowns before close. Transfer
both imported sides through a transfer or clearing account. A card payment
reduces the card liability; only the charge records the expense. For a payment
service, reconcile opening position, provider activity, proven settlements,
and ending position instead of treating each deposit as sales. Keep principal,
financing cost, and cash settlement separate until evidence proves their split.

Use accounts for statement categories and tags for source, order, payout, and
other reporting dimensions. Avoid personal data in descriptions. Put a
one-off judgment in a precise rule or review journal, not a broad match. If
account names need cleaning, make a dedicated rename pass through rules and
regeneration, then run doctor.

## Reconciliation and Close Checks

- Keep every closing balance assertion. A failed assertion is a finding to
  investigate, not a line to remove.
- Run `hledger check --strict` on each entrypoint and `ordereddates` on source
  overlays. Declare accounts and the operating commodity before importing.
- Put ordered includes in check-only entrypoints under `checks/` so a close
  candidate can be reproduced without shell history.
- Check source overlays separately before combining them. Doctor should run
  the live year, candidate assembly, each source overlay, and the relevant
  clearing and financing controls.
- Keep readiness, source review, and final close gates distinct. A final gate
  can fail while blockers remain.
- Generate reports from one assembly. Record each delivered artifact's hash,
  assembly commit, and control totals before delivery.

## Mistakes and Fixes

| Mistake | Fix |
| --- | --- |
| Used a prior app balance as proof | Reconcile to the statement and mark the app figure provisional. |
| Put category decisions inside an import script | Move classification to `rules/`, regenerate, and review the diff. |
| Edited a generated journal to make it pass | Correct the rule or source handling and regenerate. |
| Let a fallback rules file look live | Give each file a required `Status:` header. |
| Treated an entire debt payment as principal | Hold it in named clearing until the split is proven. |
| Booked a card payment as another expense | Reduce the card liability and reconcile both sides. |
| Mixed two commodity spellings | Declare one operating commodity and normalize imports. |
| Let temporary investigation names reach reports | Run a dedicated rename pass with a map and doctor. |
| Repeated a settled accountant question | Record the answer where the next reviewer starts; ask only open questions. |
| Treated an explanatory note as a posting | Require a dated entry and supporting schedule. |
| Combined reports from different assemblies | Choose one controlling assembly and label comparisons separately. |
| Let concurrent edits move figures silently | Use one writer, pull before and after, and require doctor before push. |

## hledger Repo Conventions

Use a year entrypoint that includes a declarations-only accounts journal and
the live source journals. Keep draft overlays separate until promoted. Declare
the five typed roots, `assets`, `liabilities`, `equity`, `income`, and
`expenses`, with hledger `; type:` directives. Declare one operating
`commodity $`; add another only when an actual source requires it. Use stable
professional account names, and use tags for details rather than multiplying
accounts. Keep mapping comments simple so punctuation cannot change how a
tool reads them.

Keep `rules/`, generated `imports/`, `checks/`, `manifests/`, `docs/`, and
`bin/books` together. Use dated workpapers and generated reports where the
work needs them. A replacement of an old system can use a separate historical
mirror, source overlays, narrow adjustments, and named gap accounts. New years
start from sources. Accountant adjustments go in dated files, separate from
source lanes. Pin a stable hledger version and make doctor report it.

The [synthetic repo template](../mb/mb/_data/books/repo-template/README.md)
shows the file shape and a small passing check. Its rows are invented and are
only for learning and tests.

## Read-only books doctor

Run `mb books doctor --repo PATH` to check a books repo. Set `books_repo` in
the business repo's `core/finance/books.md` to use `mb books doctor` from that
repo. The configuration may use a relative or absolute path; output uses only
a generic books repo label. The command checks the repo shape, runs the declared
doctor when hledger is available, and counts blockers without printing their
summaries. It never reads evidence bytes or writes to the books repo.

Declare the doctor in a root `books.toml`:

```toml
[mb]
doctor_command = "bin/books doctor"
```

If `books.toml` is absent, an executable `bin/books` supplies the same default
command. The command runs from the books repo with standard input closed, no
shell, a 600-second default timeout, and `PYTHONPATH` removed. Set
`--doctor-timeout SECONDS` for a different positive timeout. Its standard
output and standard error are discarded. When hledger is unavailable, the
declared doctor is not run (reported as `not_run` at level `info`); shape
checks and the receipt still work.

An optional `reports/doctor-receipt.json` records a doctor run on another host:

```json
{
  "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "finished_at": "2026-10-18T00:00:00Z",
  "exit_code": 0,
  "hledger_version": "hledger version",
  "controls": 4
}
```

Use exactly these five fields: a 40-character hex commit, an ISO 8601 time
with timezone, an integer exit code, a hledger version string, and a
nonnegative integer control count. The receipt is stale when its commit differs
from the books repo HEAD. Invalid receipts produce a finding; unknown fields
are never printed. This format records aggregate control status only, never
transaction rows or doctor output.

## Keep Real Records Private

The business repo holds safe policy and summaries. Real journals and detailed
reports belong in the chosen private books storage mode. Statements, exports,
signed papers, and other evidence bytes belong in a restricted evidence store,
with hashes and backups. A books repo can hold pointers, rules, journals,
workpapers, and private reports, but it needs its own access control. Never put
credentials, account identifiers, customer rows, or raw evidence in a public
repo. A public guide can carry the protocol and an invented fixture only.
