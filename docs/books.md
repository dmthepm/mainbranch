# Bookkeeping (`mb books`)

This page describes how Main Branch treats bookkeeping today. It is the
operator-facing companion to
[the mb books foundation decision](../decisions/2026-05-11-mb-books-foundation.md).
The command group is named `mb books` because it is short; the business
function is bookkeeping.

## The Short Version

- Main Branch ships the first safe `mb books` setup surfaces:
  `check`, `status`, and `doctor --plan`. They validate and explain
  bookkeeping safety without reading any real ledger contents.
- Main Branch also ships a fake-data sample monthly report:
  `mb books report monthly --sample --month YYYY-MM`. It uses packaged fixture
  data, not the operator's private books.
- Main Branch ships privacy-bounded bet exposure checks:
  `mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md --json` and
  `mb books exposure --repo . --active --json`. Exposure checks read the
  configured private hledger journal through hledger only to return aggregate
  bet totals, cap state, and transaction counts.
- **Main Branch uses hledger as the bookkeeping engine for `mb books`.**
  The hledger journal is the only authoritative ledger.
- hledger is **optional** for base `mb` installs, but it is the chosen
  bookkeeping engine when using `mb books`. `mb` does not require
  hledger to install, onboard, or run.
- CSV and SQLite are import staging, source snapshots, caches, or
  report outputs. They are not the bookkeeping record.
- Real bookkeeping lives in a **private bookkeeping vault**, never in the
  team-visible business repo by default. The default path is still
  `.mb/private/books/`, but the product concept is bookkeeping privacy,
  not a content library. `mb` keeps raw finance out of GitHub unless the
  operator explicitly opts in. You should not need to learn `.gitignore`
  to keep bookkeeping private; `mb` handles it.
- Real ledgers, statements, payroll, tax data, and account identifiers
  are **Class B data**.

## Storage Modes

Three storage modes. `mb` picks one, sets up the ignore rules, and
explains the choice in `mb books status`.

### Solo local (default)

The real bookkeeping lives in a private bookkeeping vault inside your business
repo's local working tree, but the vault is ignored by the business
repo and never pushed to its remote.

```text
.mb/private/books/
  main.journal      # real hledger journal (source of truth)
  imports/          # raw bank/Stripe/PayPal exports
  cache/            # SQLite cache/staging
  reports/          # private detailed reports
  attachments/      # statements, receipts (optional)
```

The vault carries its own local git history for auditability. No
GitHub remote by default. Encrypted local backup is recommended.

### Team private repo

When two or more people need bookkeeping access, the vault graduates to a
separate **private bookkeeping repo** with access restricted to the
finance/admin users who need it.

```text
private-books-repo/
  books/main.journal           # real hledger journal (source of truth)
  books/rules/                 # real import rules
  books/policies.md            # bookkeeping policies
  books/month-close.md         # close runbooks
  books/reports/monthly-summary.md
  books/imports/   # ignored
  books/cache/     # ignored
  books/attachments/  # ignored
  books/reports/detailed/  # ignored
```

PR review by another finance/admin user is the expected workflow for
transaction changes. The main business repo never contains the real
bookkeeping records, even when team mode is active.

Why a separate repo and not a private folder: GitHub permissions are
repo-level. If 20 people have access to the main business repo, then a
"private" folder inside it is not actually private. Real bookkeeping for a
team always lives in its own repo with its own access control.

### Advanced encrypted / off-platform vault

For teams that do not want real bookkeeping on GitHub at all. `mb` points at
an encrypted local volume, network drive, or off-platform store. This
is a deliberate advanced choice, not a default.

### GitHub Warning

Whenever real bookkeeping is tracked on GitHub (team mode or advanced
choice), `mb books status` surfaces:

```text
GitHub private repos are private, not financial vaults.
Anyone with repo access can read the full ledger and history.
Removing a transaction later does not remove it from history.
```

## What Lives Where

### In the business repo (safe to commit)

```text
core/finance/books.md              # bookkeeping policy + storage-mode pointer
core/finance/chart-of-accounts.md  # account-naming convention
core/finance/import-rules/         # safe rule templates (no real account data)
docs/reports/finance/              # sanitized summaries only
```

All four are optional. A business repo without them is still valid.
When present, they describe how the operator runs bookkeeping, not
what the numbers are. `core/finance/import-rules/` and
`docs/reports/finance/` may exist only when their contents contain
no Class B data; `mb books check` warns when real identifiers or
amounts appear.

`core/finance/books.md` is a small policy file. A starting shape:

```yaml
---
type: books
ledger: hledger
operating_currency: USD
fiscal_year_start: "01-01"
reporting_cadence: monthly
storage_mode: solo-local              # or: team-private-repo, advanced-vault
vault_location: ".mb/private/books/"
github_backup: false
encrypted_backup: false
class_b_data: true
money_path:
  scale_basis: rolling_30_day_gross_outflow
  exposure_window_days: 7
  appetite_thresholds:
    trivial:
      max_amount: 100
      approval: operator
      ledger_required: false
    small:
      max_amount: 1000
      approval: operator
      ledger_required: true
    material:
      max_amount: 5000
      approval: accepted_decision
      ledger_required: true
    strategic:
      min_amount: 5000
      approval: accepted_decision
      ledger_required: true
      requires_exit_rubric: true
---

# Bookkeeping

This business uses an hledger journal kept in a private bookkeeping vault.
This file is the public-safe pointer. The journal itself is not
committed here.
```

The optional `money_path.appetite_thresholds` block declares decision
thresholds only. It lets `mb status --json --peek` summarize active bet
exposure, unanchored bets, and over-cap bets without exposing raw ledger rows,
payees, account names, or balances. Leave the thresholds blank until the
operator chooses them; Main Branch should then ask before material execution
spend.

`mb onboard` can collect this policy during setup when the operator chooses to
declare it. The safe fields are currency, storage mode, a broad experiment
budget band, appetite threshold amounts, material-approval posture, and whether
non-trivial bets should require ledger anchors by default:

```bash
mb onboard --yes --name "My Business" --path my-business \
  --operating-currency USD \
  --books-storage-mode solo-local \
  --monthly-experiment-budget-band 500-2k \
  --trivial-max-amount 100 \
  --small-max-amount 1000 \
  --material-max-amount 5000 \
  --strategic-min-amount 5000 \
  --approval-required-for-material yes \
  --ledger-anchor-default yes
```

Interim answers live in gitignored `.mb/onboarding.json`. Confirmed thresholds
are written to `core/finance/books.md` because they are policy declarations, not
raw finances. If even threshold policy is private for a business, use
`--threshold-privacy private` or leave thresholds blank; Main Branch will keep
running and ask before material bets instead of inventing numbers.

`core/finance/chart-of-accounts.md` describes the account roots the
operator uses (`assets`, `liabilities`, `equity`, `income`,
`expenses`) and the naming convention beneath them. It does not list
real account numbers, balances, or specific institution names tied
to live accounts.

### In the private bookkeeping vault (Class B; not in the business repo)

The layout depends on the storage mode — see above. The principle is
the same: the vault is where real bookkeeping lives, and the
team-visible business repo never has it.

## Class B Examples For Bookkeeping

The following are Class B and must not be committed to a team-visible
business repo:

- raw ledger transaction rows in any format
  (`*.journal`, `*.hledger`, `*.ledger`, `*.beancount`);
- bank, credit-card, payment-processor, merchant-account exports
  (`*.csv`, `*.ofx`, `*.qfx`, `*.qbo`, `*.qif`, statement-shaped PDFs);
- account numbers, routing numbers, card numbers, provider account
  identifiers tied to real customers/members/vendors;
- payroll runs, employee compensation rows, contractor 1099 detail;
- tax-return data, tax-withholding ledgers, sales-tax filings;
- vendor/customer payment history at row granularity;
- owner draws, distributions, equity events tied to real individuals;
- invoices, contracts, dispute records, legal-finance correspondence;
- anything that would re-identify a real customer or vendor when
  combined with other fields in the repo.

These prohibitions inherit from the accepted
[workspace and sensitive-data boundary](../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md);
`mb books` sharpens them.

## Fixtures Vs Real Ledgers

A **fake fixture** is a small, obviously-fake `.journal` file used to
exercise the `mb books` contract and to give operators a starting shape.
This engine repo ships one under
[`docs/examples/books/`](examples/books/).

A **real ledger** is the operator's actual bookkeeping. It never lives in
this engine repo and does not live in the team-visible business repo by
default.

Telling them apart should be easy:

- the company name is obviously fake (`Acme`, `Test Co`, `Fixture Inc`);
- the file is small (a chart-of-accounts, opening balances, a handful of
  transactions, maybe one balance assertion);
- a header comment names the file as a sample.

`mb books check` treats anything that looks like a real ledger or
statement export committed in the business repo (including under
`core/finance/`) as a defect, not a feature.

## Optional Local Viewer

`hledger-web` is an optional local web viewer that ships with hledger
itself. Install and run it yourself if you want a UI over your journal;
Main Branch does not start, supervise, proxy, or detect `hledger-web`.
There is no `mb` command for it.

## What `mb books` Does Today

The shipped safe setup surfaces are:

```bash
mb books check [REPO] [--fixture] [--fixture-path PATH] [--json]
mb books status [REPO] [--json]
mb books doctor [REPO] --plan [--json]
```

The shipped sample reporting surface is:

```bash
mb books report monthly --sample --month YYYY-MM [--json]
```

The shipped privacy-bounded exposure surface is:

```bash
mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md [--json]
mb books exposure --repo . --active [--json]
```

`mb books check` runs read-only checks against a business repo. It:

- detects whether `core/finance/books.md` exists and parses (including
  the `storage_mode` field);
- detects whether `core/finance/chart-of-accounts.md` exists;
- verifies the configured storage mode's ignore rule (`.mb/private/`
  for `solo-local`) so the vault stays out of the business repo's
  tracked history. Unknown or typo'd `storage_mode` values fail
  closed — they are treated as `solo-local` for vault enforcement so
  a misconfigured policy cannot silently allow a leak;
- warns when ledger-shaped files (`.journal`, `.hledger`,
  `.ledger`, `.beancount`) or statement-shaped files (`.csv`,
  `.ofx`, `.qfx`, `.qbo`, `.qif`) are tracked in the business repo
  (likely Class B leak). This is `warn`, not a hard fail, because
  non-finance CSVs (audience research, content exports) are
  legitimate. Files carrying an explicit fixture marker in their
  first 1024 bytes — `MB-FIXTURE`, `SAMPLE FIXTURE`, or
  `NOT A REAL LEDGER`, case-insensitive — are exempted;
- with `--fixture`, validates a fake hledger journal fixture by
  shelling out to `hledger -f <fixture> check` — uses the bundled
  fake fixture by default, or any path passed via `--fixture-path`;
- if hledger is not installed, prints a clean informational finding
  and does not break the rest of the check;
- prints exact repair commands when something is off;
- emits a JSON envelope with `--json` for scripts and skills, with
  every finding carrying `audience` and `operator_summary` fields.

`mb books status` shows readable setup/storage health:

- hledger availability, without printing the local binary path;
- configured storage mode from `core/finance/books.md`;
- sanitized private-vault location labels. Relative paths inside the
  business repo may be shown; external absolute vault paths are
  reported as external private paths instead of printed;
- a warning when team/private or advanced storage mode is selected but
  the policy does not name a safe private repo or vault label;
- whether the configured local vault exists;
- whether a private `main.journal` placeholder exists, without
  reading its contents;
- whether `.gitignore` includes the expected private-vault and
  ledger-extension protections;
- the GitHub private repo warning when team-private mode or GitHub
  backup is configured.

`mb books doctor --plan` prints a non-mutating repair plan for setup
gaps:

- install hledger when deeper local journal checks are needed;
- add a safe `core/finance/books.md` policy when the operator is
  ready;
- add or fix `storage_mode`;
- add a safe private repo or vault label for non-local storage modes;
- add bookkeeping ignore protections;
- create the private books vault directory;
- create a private hledger journal placeholder from a safe template
  shape;
- move unsafe tracked finance artifacts out of the business repo.

It does not apply repairs yet. The plan is designed for operator
review and avoids printing private external vault paths or real
financial data.

`mb books report monthly --sample` generates a beginner-safe monthly report
from packaged fake hledger data through hledger. If hledger is unavailable, the
command fails with install guidance instead of falling back to a non-hledger
report. It emits stable JSON with `--json`, redacts fixture internals that
should not train operators to paste private paths or account identifiers, and
keeps `safe_to_share: true` because the data is synthetic.

`mb books exposure` checks whether bet spending is anchored in the private
hledger journal:

- resolves the private journal from `vault_location` in
  `core/finance/books.md`;
- runs `hledger -f <journal> check` before querying exposure;
- queries `tag:bet=<id>` for one bet or all active bets;
- returns aggregate gross outflow, exposure cap, remaining cap, anchor
  presence, and transaction count;
- withholds private hledger stderr/stdout on failures because hledger can print
  transaction context;
- keeps `safe_to_share: true` by omitting raw rows, payees, descriptions,
  account names, account numbers, transaction memos, provider payloads, private
  vault paths, and absolute business-repo paths.

Exit codes:

- `mb books check`: `0` when there are no error findings (info or
  warn states allowed); `1` when there is at least one error finding
  (e.g. broken policy frontmatter,
  or `.mb/private/` exists without a matching ignore rule).
- `mb books status`: `0` when there are no error findings; `1` when
  status finds an error.
- `mb books doctor --plan`: `0` after printing a plan. Running
  `mb books doctor` without `--plan` exits `2` because applying
  repairs is not implemented.
- `mb books report monthly --sample`: `0` when the sample report is generated;
  `1` for generation failures such as missing hledger or missing fixture;
  `2` for usage errors such as missing `--sample`, missing `--month`, or an
  invalid month.
- `mb books exposure`: `0` when hledger can check the private journal and return
  aggregate exposure facts, including warning states such as a missing anchor;
  `1` for hledger, policy, journal, bet, or query errors; `2` when the operator
  does not choose exactly one of `--bet` or `--active`.

It does **not**:

- run real imports, reconciliation, month-close, P&L, balance sheet,
  cash-flow, or tax claims;
- import the hledger library directly into `mb`;
- scrape human terminal output when structured output exists;
- read the real ledger contents inside the vault except for the explicit
  `mb books exposure` hledger query, which returns only aggregate bet exposure
  facts;
- print raw ledger rows, payees, descriptions, account details, transaction
  memos, provider payloads, private vault paths, or finance/legal records;
- mutate any file.

Later slices may add real imports, reconciliation, month close, or
private-vault reporting only after separate decisions and smoke evidence. They
are not part of the current command surface.

The full first-surface spec lives in
[the mb books foundation decision](../decisions/2026-05-11-mb-books-foundation.md).

## What `mb books` Will Not Do (Until Separate Decisions Land)

- replace QuickBooks, Xero, Wave, or a human bookkeeper;
- give tax advice;
- run payroll;
- import from real banks, credit cards, or payment processors;
- reconcile statements automatically;
- close months automatically;
- generate financial reports from real data;
- sync with provider APIs;
- run scheduled imports.

Each of those is a separate scope conversation. The current foundation
makes those conversations possible without committing anything sensitive
in the meantime.

## When You Are Ready To Keep A Real Ledger

The setup path, when the time comes:

1. Pick a storage mode: solo local (default), team private repo, or
   advanced encrypted vault.
2. Install hledger yourself (download the pre-built binary or the
   install path your environment prefers). Main Branch does not
   install it for you.
3. Optionally install / run `hledger-web` for a local UI.
4. In your business repo, add `core/finance/books.md` with the policy
   shape shown above and the right `storage_mode`. Do not paste the
   journal contents in.
5. Optionally add `core/finance/chart-of-accounts.md` describing your
   account-naming convention.
6. Run `mb books status` to review setup/storage health, then
   `mb books doctor --plan` for safe repair guidance. Run
   `mb books check` when you need the lower-level safety findings.

## Related

- [Statement-anchored books workflow](books-workflow.md)
- [mb books foundation decision](../decisions/2026-05-11-mb-books-foundation.md)
- [hledger vs Beancount fit report](reports/2026-05-11-hledger-vs-beancount-fit.md)
- [Workspace and sensitive-data boundary](../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md)
- [Sidecar enrichment CLI contract](../decisions/2026-05-04-sidecar-enrichment-cli-contract.md)
- [System architecture: topology and `core/finance/`](system-architecture.md)
- [Dependency choices](dependency-choices.md)
