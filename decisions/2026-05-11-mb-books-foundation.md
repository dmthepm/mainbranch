---
type: decision
date: 2026-05-11
status: accepted
topic: mb books bookkeeping foundation and safe ledger contract
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/483
  - https://github.com/dmthepm/mainbranch/issues/128
linked_decisions:
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
  - decisions/2026-05-08-business-repo-topology-map.md
linked_docs:
  - docs/books.md
  - docs/dependency-choices.md
  - docs/system-architecture.md
  - docs/reports/2026-05-11-hledger-vs-beancount-fit.md
participants: [Devon, Claude]
tags: [books, finance, hledger, safety, foundation]
---

# `mb books` Bookkeeping Foundation and Safe Ledger Contract

## Decision

**Main Branch uses hledger as the bookkeeping engine for `mb books`.**
The hledger journal is the only authoritative ledger. hledger is
optional for base `mb` installs, but it is the chosen bookkeeping
engine when using `mb books`.

CSV and SQLite can be import staging, source snapshots, caches, or
report outputs. They are not the bookkeeping record.

`mb books` is a command group whose first shipped surface validates that a
business repo carries **safe bookkeeping metadata**, not real ledgers. Main
Branch owns the operator workflow and wraps hledger in plain-language
commands. Real financial ledgers stay local and gitignored by default. The
team-visible business repo commits only safe metadata, fake fixtures, and
documentation.

The product stance:

- bookkeeping is a Ship loop with stricter data boundaries than the rest
  of the business repo;
- real ledgers, statement exports, account identifiers, payroll detail,
  tax records, and customer/member payment data live in a private
  `finance` child repo, a private business repo, a provider account, or
  local encrypted storage;
- `mb books` starts as a check/contract surface and earns deeper
  surfaces (`summarize`, `import`, `reconcile`, `close`, `report`) only
  behind accepted decisions and smoke evidence;
- nothing in this decision promises a QuickBooks, Xero, or bookkeeper
  replacement.

This decision codifies the foundation and named the first `mb books`
surface. `mb books check` shipped in the follow-up implementation issue
(#486).

## Why hledger

Main Branch evaluated hledger, Beancount v3, Ledger CLI, and the
CSV/SQLite option against current primary sources, weighted for the
10-year regret bar (multi-business durability, maintenance velocity,
installability, built-in CSV import, built-in reports, plain-text
durability, operator practicality). hledger won. The full evaluation
is in
[docs/reports/2026-05-11-hledger-vs-beancount-fit.md](../docs/reports/2026-05-11-hledger-vs-beancount-fit.md).

The reasons that decided it:

- **CSV import is built in.** `hledger import` with `.rules` files is
  in core. Beancount's v3 cutover moved importers to a separate
  project (`beangulp`), so a Beancount operator pays for the
  ecosystem split every time they categorise bank rows.
- **Reports are built in.** `hledger balance`, `balancesheet`,
  `balancesheetequity`, `cashflow`, `incomestatement`, `register`,
  and `aregister` all ship in the same binary. Beancount's
  `bean-report` is deprecated in v3; reporting now needs `beanquery`
  or external tooling.
- **JSON output is first class.** Every major hledger report supports
  `-O json` (documented in `hledger/hledger.m4.md` §690–935), which
  matters for Main Branch's agent-driven workflows. Beancount's
  machine output is ecosystem-dependent.
- **Single-binary install.** hledger ships as a pre-built binary;
  the operator does not pay for Python version drift or a flex/bison
  source build. Plain-text durability for the next 10 years is
  cleaner when the engine is one boring binary.
- **Maintenance velocity.** Releases `1.99.2` and `1.52.1` both
  dated 2026-04-28 (from `doc/CHANGES.md` in the upstream hledger
  repo). Actively maintained on a frequent cadence.
- **Built-in optional viewer.** `hledger-web` ships in the same
  project at the same version. No third-party UI dependency for the
  optional viewer.

The one Beancount-favouring criterion — stricter defaults — is real
but small compared to the four ways the v3 ecosystem split makes
operators pay over time. hledger supports balance assertions and
account-type discipline; Main Branch's own `mb books check` adds
enforcement on top.

## Why hledger Stays Optional

`mb` is a deterministic control plane that has to install and run for
operators who do no bookkeeping. hledger must not be a hard install
dependency:

- **Audience.** Many operators will never run `mb books`. The base
  install must not pay for what they do not use.
- **License.** hledger is `GPL-3.0-or-later`; Main Branch is MIT. The
  shell-out boundary keeps Main Branch's licence clean. `mb` core
  does not depend on the hledger Haskell ecosystem.
- **Toolchain.** Pre-built hledger binaries are easy, but a source
  build needs GHC. Either way the base `mb` install should not pull
  it in.

## How hledger Plugs Into `mb`

Three layers, in this order of preference:

1. **Main Branch metadata wrapper (this slice).** `mb books check`
   validates Main Branch's own bookkeeping contract: the policy file,
   the chart-of-accounts shape, gitignore guardrails, and fake fixture
   conformance. Runs without hledger installed.
2. **Shell-out sidecar (future).** When an operator wants ledger
   validation, an optional sidecar runs `hledger -f <journal>
   check`, `hledger balance -O json`, or similar and returns an
   `mb.sidecar.context.v1`-shaped envelope per the
   [sidecar enrichment CLI contract](2026-05-04-sidecar-enrichment-cli-contract.md).
   Raw ledger output stays outside tracked business files. `mb` reads
   hledger's structured `-O json` / `-O csv` output, never scrapes
   terminal-formatted output.
3. **Library bindings: declined for `mb` core.** No Python or
   Haskell hledger library bindings in `mb` core. Adapter sidecar
   implementations may import upstream libraries internally; `mb`
   core must not. The shell-out boundary is what keeps the licence
   and install profile clean.

## Optional Extras Packaging (Deferred)

Deeper-validation paths may later become a small optional extra:

```bash
pip install "mainbranch[books]"
# or:
uv tool install "mainbranch[books]"
```

The first extra to land should be minimal — just whatever Python-side
helper code `mb` needs to shell out to `hledger` cleanly. The base
`mainbranch` install must continue to work, onboard, validate, and
report without it. Importers, deeper reports, and a viewer are not
add-ons that this decision commits to ship.

## Storage Model: Private Bookkeeping Vault

Git history for bookkeeping is valuable for auditability. GitHub-by-default
is **not**. Git is the history engine; GitHub is a remote
collaboration/backup service. For real bookkeeping those are not the same
thing.

The user-facing term Main Branch uses is **private bookkeeping vault**. `mb`
creates and enforces the ignore rules. Operators do not need to learn
`.gitignore` to keep raw bookkeeping out of GitHub. The default path remains
`.mb/private/books/` because the command group is `mb books`.

Three storage modes:

### 1. Solo local (default)

The real bookkeeping lives in a private bookkeeping vault inside the business repo's
local operational area, but are ignored by the business repo's tracked
content and never pushed to its remote. The vault carries its own local
git history.

Default layout:

```text
.mb/private/books/                # private bookkeeping vault (own local git history)
  main.journal                    # real hledger journal (authoritative ledger)
  imports/                        # raw bank/Stripe/PayPal exports
  cache/                          # SQLite cache/staging
  reports/                        # private detailed reports
  attachments/                    # statements, receipts (optional, later)
```

Rules:

- `.mb/private/` is added to the business repo's ignore rules so its
  contents never enter the business repo's tracked history.
- The vault carries its own local git history (operators can run
  `git init`, `git add`, `git commit` inside the vault for
  auditability) with no remote configured by default.
- Encrypted local backup is recommended, not enforced.
- No GitHub remote by default.

### 2. Team private repo (team finance mode)

When more than one person needs bookkeeping access, the vault graduates to a
separate private bookkeeping repo with restricted access.

```text
private-books-repo/               # separate GitHub private repo, restricted access
  books/main.journal              # real hledger journal (authoritative ledger)
  books/rules/                    # real import rules
  books/policies.md               # bookkeeping policies
  books/month-close.md            # close runbooks
  books/reports/monthly-summary.md
  books/imports/                  # usually ignored
  books/cache/                    # usually ignored
  books/attachments/              # usually ignored
  books/reports/detailed/         # usually ignored
```

Rules:

- The real hledger journal is committed in this repo. Raw imports,
  cache, attachments, and detailed private reports stay ignored
  unless the team explicitly decides otherwise.
- Access is restricted to the finance/admin users who need it. The
  main business repo's permissions do not apply here.
- PR review by another finance/admin user is the expected workflow
  for transaction changes.
- The main business repo never contains the real bookkeeping records, even when
  team mode is active.

Why a separate repo and not a private folder: GitHub permissions are
repo-level. If 20 people have access to the main repo, then a "private"
folder inside it is not private. Real bookkeeping for a team always lives in
its own repo with its own access control.

### 3. Advanced encrypted / off-platform vault

For teams that do not want real bookkeeping on GitHub at all. `mb` points
at an encrypted local volume, network drive, or off-platform store.
This is a deliberate advanced choice, not a default; the setup path
is the operator's responsibility.

### GitHub-As-Backup Warning

Whenever real bookkeeping is tracked on GitHub (team mode or advanced
choice), `mb books status` / `mb books doctor` must surface this
warning:

```text
GitHub private repos are private, not financial vaults.
Anyone with repo access can read the full ledger and history.
Removing a transaction later does not remove it from history.
```

### Status Surface

The first `mb books status` shape should describe the storage mode in
plain language:

```text
Books engine:      hledger
Real bookkeeping: Private bookkeeping vault
Git history:       local
GitHub backup:     not enabled
Encrypted backup:  not configured
Last check:        passed
```

Team mode:

```text
Books engine:      hledger
Bookkeeping vault: <repo-name>
Storage mode:      team private repo
Remote backup:     enabled
Access:            restricted
Real ledger:       tracked in books repo
Raw imports:       ignored
Last check:        passed
```

`mb books doctor` repair commands target the ignore rules, the vault
layout, the storage-mode wiring, and the GitHub-as-backup warning.

## Safe Path Contract

The team-visible business repo commits only safe metadata. Real ledger
files do not live here by default.

Safe (committable, business repo):

```text
core/finance/books.md              # bookkeeping policy and storage-mode pointer
core/finance/chart-of-accounts.md  # operator-friendly account-naming description
core/finance/import-rules/         # safe rule templates with no real account data
docs/reports/finance/              # sanitized summaries only
```

All of these are optional in the v0 contract. A business repo without
them is valid; `mb books check` reports their absence as a
recommendation, not an error. `core/finance/import-rules/` and
`docs/reports/finance/` may exist only when their contents contain
no Class B data; the check warns if real account identifiers, real
amounts, or real counterparties appear.

Real ledger material (private bookkeeping vault; not in the team-visible
business repo). Solo default layout:

```text
.mb/private/books/main.journal     # real hledger journal (authoritative)
.mb/private/books/imports/         # raw bank/credit-card/processor exports + .rules
.mb/private/books/cache/           # SQLite cache/staging
.mb/private/books/reports/         # private detailed reports
.mb/private/books/attachments/     # statements, receipts, tax docs (optional)
```

Team mode layout (in a separate private bookkeeping repo):

```text
books/main.journal                 # real hledger journal (authoritative)
books/rules/                       # real import rules
books/policies.md                  # bookkeeping policies
books/month-close.md               # close runbooks
books/reports/monthly-summary.md   # finance-team summaries
books/imports/                     # usually ignored
books/cache/                       # usually ignored
books/attachments/                 # usually ignored
books/reports/detailed/            # usually ignored
```

`core/finance/books.md` declares which storage mode is in use and
points at the vault without copying its contents into the business
repo. A sample frontmatter shape (advisory, not yet enforced):

```yaml
---
type: books
ledger: hledger
operating_currency: USD
fiscal_year_start: "01-01"
reporting_cadence: monthly
storage_mode: solo-local              # or: team-private-repo, advanced-vault
vault_location: ".mb/private/books/"  # for solo-local; or repo name; or local path
github_backup: false
encrypted_backup: false
class_b_data: true
---
```

`vault_location` is a human-readable pointer Main Branch uses to
explain where bookkeeping lives. `mb books check` should refuse to read
the vault's actual contents.

## Class B Examples For Bookkeeping

The
[workspace, repo, and sensitive-data boundary decision](2026-05-04-workspace-repo-sensitive-data-boundaries.md)
already defines the general Class B rule. `mb books` inherits and
sharpens it. The following are Class B in a bookkeeping context and
must not be committed to a team-visible business repo:

- raw ledger transaction rows in any format
  (`*.journal`, `*.hledger`, `*.ledger`, `*.beancount`, etc.);
- bank, credit-card, payment-processor, and merchant-account exports
  (`*.csv`, `*.ofx`, `*.qfx`, `*.qbo`, `*.qif`, `*.pdf`);
- account numbers, routing numbers, card numbers, and provider
  account identifiers tied to real customers/members/vendors;
- payroll runs, employee compensation rows, contractor 1099 detail;
- tax-return data, tax-withholding ledgers, sales-tax filings;
- vendor/customer payment history at row granularity;
- owner draws, distributions, equity events tied to real individuals;
- invoices, contracts, dispute records, and legal-finance
  correspondence;
- any aggregate that would re-identify a real customer or vendor when
  combined with other fields.

These items belong in a private finance repo, a provider account, or
local encrypted storage. `mb books check` should treat any of these
shapes appearing under `core/finance/` (or anywhere in a team-visible
business repo) as a defect to surface.

## Fixtures Vs Real Ledgers

A **fake fixture** is a small `.journal` file with no real data. It
exists in this engine repo to exercise the validation contract and to
give operators a copy-paste starting point.

A **real ledger** is the operator's actual bookkeeping. It never lives
in this engine repo and does not live in the team-visible business
repo by default.

The fixtures shipped with Main Branch must:

- use an obviously fake business name (`Acme`, `Test Co`,
  `Fixture Inc`, etc.);
- use only the conventional plain-text-accounting roots (`assets`,
  `liabilities`, `equity`, `income`, `expenses`) pinned with hledger
  `account ... ; type:<letter>` directives;
- declare one placeholder operating currency (`USD` is fine);
- include a header comment naming the file as a sample, not a real
  ledger;
- contain no Devon-local, vendor, customer, member, payroll, or tax
  data;
- stay small enough to read at a glance.

The first fixture lives under `docs/examples/books/`. Packaging it
into `mb/mb/_data/` is a follow-up concern when `mb books check`
ships.

## First `mb books` Surfaces

The first command shipped in the follow-up implementation issue is:

```text
mb books check [--json]
```

What it must do:

- detect whether `core/finance/books.md` exists and parses as expected
  frontmatter (when present), including the `storage_mode` field;
- detect whether `core/finance/chart-of-accounts.md` exists and
  follows the documented account-naming convention (when present);
- detect whether `core/finance/import-rules/` and
  `docs/reports/finance/` (if present) contain only safe templates
  and sanitized summaries (no Class B data);
- verify that the configured storage mode's ignore rules are present
  and current (e.g., for `storage_mode: solo-local`, that
  `.mb/private/` is ignored from the business repo's tracked
  history);
- warn when files with extensions `.journal`, `.hledger`, `.ledger`,
  `.beancount`, `.csv`, `.ofx`, `.qfx`, `.qbo`, `.qif`, or
  statement-shaped PDFs appear in the business repo's tracked
  content (likely real data leak) unless the file is explicitly
  marked as a fixture in frontmatter or a sibling sample manifest;
- when an operator opts in and hledger is installed, validate a fake
  `.journal` fixture by shelling out to
  `hledger -f <fixture> check -O json` and reading the structured
  output;
- print exact repair commands and a link to `docs/books.md` when a
  check fails;
- emit an `mb` JSON envelope when `--json` is passed, matching the
  pattern used by `mb doctor` / `mb validate`.

A sibling `mb books status` command prints the storage-mode summary
shown above and the GitHub-as-backup warning when appropriate. A
sibling `mb books doctor --plan` produces a non-mutating repair plan
for missing ignore rules, missing vault scaffolding, hledger
availability, and private journal placeholder setup without ever
touching real ledger contents.

What it must not do in the first surface:

- run real imports, reconciliation, month-close, P&L, balance sheet,
  cash-flow, or tax claims;
- import any hledger or other ledger library directly into `mb`
  core;
- scrape human-formatted terminal output from any tool when a
  structured (`-O json` / `-O csv`) path exists;
- parse journal syntax beyond what is needed to recognise an obvious
  fixture vs a real ledger;
- read files outside `core/finance/` (other than the gitignore for
  detection);
- mutate any file.

Exit semantics (advisory; follow-up implementation locks them):

- `0` — checks passed, including the "no real ledger committed" guard;
- `1` — checks failed; the envelope lists each failure and a repair
  command;
- `2` — usage/config error (e.g., `--json` passed with unsupported
  flag combination).

## Non-Goals For This Slice

The following are explicitly out of scope until separate accepted
decisions land:

- real bank, credit-card, or payment-processor importers;
- ledger import from QuickBooks, Xero, Wave, or other accounting
  tools;
- month-end close automation;
- P&L, balance sheet, cash-flow, or tax reporting from real data;
- QuickBooks or bookkeeper replacement claims in any user-facing
  copy;
- tax advice or tax-filing automation;
- payroll runs, contractor payment automation, or 1099 generation;
- provider sync (Plaid, bank APIs, processor APIs);
- scheduled or background imports;
- automatic reconciliation against statements;
- public `hledger-web` deployment or hosted ledger viewing;
- writing ledger files from `mb` (the first surface only reads
  presence/shape).

## hledger-web

`hledger-web` is the optional local viewer that ships with hledger
itself. `docs/books.md` may mention it as the optional local UI for
operators who want one. Main Branch will not start, supervise, proxy,
or detect `hledger-web` in this slice. There is no `mb` command for
it and no readiness check.

## Existing Surfaces To Migrate (Follow-Up)

Earlier Main Branch work landed Beancount-flavoured copy and one
provider entry on the assumption Beancount would be the chosen engine.
This decision supersedes those mentions. The actual migration is
out of scope for this foundation PR; a follow-up issue should sweep:

- `mb/mb/connect.py` — replace the `beancount` provider with an
  `hledger` provider id and metadata fields (`journal_path` rather
  than `ledger_path`). This is a CLI/contract change that needs
  focused CLI tests and a migration path for any existing
  `.mb/connect.yaml` records;
- `mb/mb/educational.py` and
  `mb/mb/_data/educational/beancount.md` — rename to `hledger.md`
  and rewrite;
- `mb/mb/init.py` and
  `mb/mb/_data/templates/.gitignore.tmpl` — add `*.journal`,
  `*.hledger`, and `.mb/private/` to the default ignore rules in
  newly initialised business repos alongside the existing
  `*.beancount` line (keep the old line for defence in depth against
  legacy files). `.mb/private/` is the solo-default vault location
  and must never be tracked by the business repo;
- `docs/ethos.md` running-rails sentence, `docs/system-architecture.md`
  topology row, `docs/operator-loops.md`, and `docs/beginner-setup.md`
  — update the descriptive copy from "Beancount" to "hledger" with
  one short superseded note pointing at this decision.

The `docs/dependency-choices.md` running-choices log is already
updated in this PR (the 2026-05-04 Beancount row is marked
superseded and a 2026-05-11 hledger row points at this decision), so
it is not in the follow-up list.

This decision does the foundation-doc rewrite in this PR and
explicitly leaves the engine code migration to a follow-up so a
foundation slice does not also become a CLI refactor.

## Validation Contract

For this decision slice:

- Level 0 (docs/decision) review is required: frontmatter, links, no
  stale product claims, no private data;
- `scripts/check.sh` (Level 1) must pass before pushing;
- no CLI tests (no CLI behaviour changes);
- no package/install smoke (no packaging changes);
- no fixture-repo smoke (no scaffolding changes);
- no runtime smoke (no skill or runtime changes).

The follow-up implementation issue must add focused CLI tests, a
fixture repo smoke when the check reads a real business repo, and a
package smoke if the fixture is later packaged into `mb/mb/_data/`.

## Consequences

- `mb books` ships with one chosen bookkeeping engine; operators get
  one clear recommendation, not a "choose your ledger" UI.
- Built-in CSV import, built-in reports, and first-class JSON output
  mean fewer add-ons over the next 10 years.
- The licence boundary between Main Branch (MIT) and hledger
  (`GPL-3.0-or-later`) stays clean by routing ledger work through a
  shell-out sidecar.
- The team-visible business repo never accidentally becomes a finance
  database.
- A future P&L dashboard view inherits the same private-source rule:
  data may be summarised into the repo only after the operator opts
  in.
- A follow-up issue tracks the existing-surface migration so this
  foundation does not silently leave Beancount copy contradicting
  it.

## Review Trigger

Revisit this decision only if any of these become true:

- hledger changes licence in a way that closes the shell-out
  boundary, drops the journal format, or removes structured output;
- a sidecar implementation needs a contract change beyond
  `mb.sidecar.context.v1`;
- Main Branch wants to write ledger files (not just read);
- a real-data integration (importers, bank APIs, processor APIs) is
  accepted into core or as a first-party sidecar;
- a hosted P&L or finance-dashboard surface is proposed.
