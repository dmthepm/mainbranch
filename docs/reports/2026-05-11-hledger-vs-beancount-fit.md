---
title: hledger vs Beancount fit for mb books
date: 2026-05-11
linked_issue: https://github.com/dmthepm/mainbranch/issues/483
linked_linear: MAIN-320
release: unscheduled
status: complete
tags: [bookkeeping, hledger, beancount, finance, foundation]
---

# hledger vs Beancount Fit For `mb books`

## Summary

**Main Branch chooses hledger as the bookkeeping engine for `mb books`.**
hledger is optional for base `mb` installs, but it is the chosen
engine when using `mb books`. This is a one-and-done product choice,
weighted against the 10-year regret bar: multi-business durability,
maintenance velocity, installability, built-in CSV import, built-in
reports, plain-text durability, and operator practicality.

Beancount v3, Ledger CLI, and CSV/SQLite were considered and not
chosen. Their evaluations are recorded below so the choice is auditable.

The chosen shape:

- `mb books` owns the operator workflow (policy, paths, safety,
  metadata checks) and wraps hledger in plain-language commands;
- the first surface, `mb books check`, validates Main Branch metadata
  only — no hledger binary required to run;
- deeper validation, when it lands, shells out to `hledger ... -O json`
  and reads structured output, behind an optional sidecar that mirrors
  the accepted
  [sidecar enrichment CLI contract](../../decisions/2026-05-04-sidecar-enrichment-cli-contract.md);
- hledger libraries are never imported into `mb` core.

CSV and SQLite are source snapshots, import staging, caches, or report
outputs. They are not the books. Markdown is for explanations and
decisions. Git is for history. `mb` is for checks and workflow.

## Primary Sources

This report was written against local clones of upstream hledger 1.99
([github.com/simonmichael/hledger](https://github.com/simonmichael/hledger))
and Beancount 3.2.2
([github.com/beancount/beancount](https://github.com/beancount/beancount)).
Citations name the in-tree paths so reviewers can resolve them against
either upstream.

### hledger 1.99 (upstream `simonmichael/hledger`)

- `hledger/package.yaml` — declares version `1.99` (pre-2.0 dev
  cycle); tested GHC versions 9.6–9.12; built as a Haskell package.
- `LICENSE` (and `package.yaml`) — `GPL-3.0-or-later`.
- `doc/CHANGES.md` — release `1.99.2` and bug-fix release `1.52.1`
  both dated 2026-04-28; long, dense changelog confirming active
  maintenance.
- `README.md` line 45 — "Good at importing and exporting CSV." Line
  51 — "Inspired by and partly compatible with Ledger CLI;
  interconvertible with Beancount."
- `hledger/hledger.m4.md` line 650 (output-format table) — confirms
  `balance`, `balancesheet`, `balancesheetequity`, `cashflow`,
  `incomestatement`, `register`, `aregister`, `print` all support
  `txt`, `csv`, `tsv`, `html`, `json`, `fods`, `beancount`, `sql`
  outputs as applicable.
- `hledger/hledger.m4.md` §690–935 — `-O json` is the documented
  machine-readable contract across major report commands; notes JSON
  is verbose and rounds at 10 decimal places.
- `examples/csv/` — built-in CSV rules examples (`sample.csv.rules`,
  banking/cctax/investment subfolders).
- `examples/business.journal`, `examples/accounttypes.journal` —
  confirm current journal syntax: `account name ; type:A/L/E/R/X`
  directives, `YYYY-MM-DD description` headers, two-space-indented
  postings, `100 USD` amounts, `= balance` assertions.
- `hledger-web/` — built-in web viewer subproject at the same
  `1.99` version.

### Beancount 3.2.2 (upstream `beancount/beancount`)

- `beancount/VERSION` — `3.2.2` (tag `3.2.3` also present in
  the local clone); `master` tracks v3.
- `README.rst` — v3 is current stable since June 2024; v2 frozen;
  v1 (2007–2013) obsolete.
- `CHANGES` (entry dated 2024-06-16) — v3 release notes record the
  ecosystem split: importers (`beangulp`), query (`beanquery`),
  prices (`beanprice`), lots/growth (`beangrow`), and
  format-conversion (`beancount2ledger`) all became their own PyPI
  projects.
- `pyproject.toml` — licence `GPL-2.0-only`; `requires-python = ">=3.9"`;
  build backend `mesonpy` with `flex-bin`/`bison-bin`/`winflexbison-bin`;
  console scripts `bean-check`, `bean-doctor`, `bean-example`,
  `bean-format`, `treeify`.
- `examples/simple/basic.beancount` — confirms v3 syntax.

## 10-Year Regret Scorecard

Same primary-source data, weighted by what the operator actually pays
for over a decade of bookkeeping across multiple businesses.

| Dimension (10-year frame) | hledger 1.99 | Beancount 3.2.2 |
| --- | --- | --- |
| CSV import | Built-in (`hledger import`, `.rules`) | Out of core (`beangulp`) |
| Reports (balance, BS, IS, cashflow, register) | Built-in | Out of core (`beanquery`); `bean-report` deprecated |
| Structured output (`-O json` / `-O csv`) | First-class across commands | Ecosystem-dependent |
| Optional viewer | Ships in-tree (`hledger-web`) | Third-party (Fava) |
| Install shape | Single pre-built binary | PyPI wheel; source build needs flex/bison |
| Maintenance velocity | Two releases on 2026-04-28; frequent | Active, but split tooling pushes load to operators |
| Licence (shell-out boundary) | `GPL-3.0-or-later` — fine | `GPL-2.0-only` — fine |
| Strictness defaults | Looser; supports assertions/account types | Stricter; explicit `open`, types, plugins |
| Beancount/Ledger interop | "Interconvertible" with known edge cases | Native Beancount |
| Python-native ecosystem | No (shell-out is clean) | Yes (declined for `mb` core anyway) |

hledger wins on the dimensions Main Branch said matter most for the
10-year choice: CSV import in core, reports in core, machine output
in core, single-binary install, and frequent maintenance. Beancount's
single advantage (stricter defaults) is real but smaller than the
four "out of core in v3" rows that the operator pays for every month.

The licence row is a wash: both engines are GPL-family and both fit
behind the shell-out boundary. `mb` core never imports either
library, so neither tool entangles Main Branch's MIT licence.

## Findings (Issue Questions Answered)

### 1. Should Main Branch adopt hledger as the ledger for `mb books`?

Yes. Built-in CSV import, built-in reports, first-class `-O json`,
single-binary install, and frequent maintenance are the right
defaults for "real multi-business bookkeeping for the next decade."
This is a one-and-done product choice. Main Branch is not designing
a "choose your ledger" surface.

### 2. Required or optional?

**Optional for base `mb` installs.** Many operators will never run
`mb books`; the base install must not pay for what they do not use.
When `mb books` is in use, hledger is the chosen engine — not one
option among several.

### 3. `hledger` CLI vs library vs Main Branch metadata wrapper?

Three layers, in order of preference:

1. **Main Branch metadata wrapper first.** `mb books check`
   validates Main Branch's own bookkeeping contract: policy file,
   chart-of-accounts shape, gitignore guardrails, fixture
   conformance. Runs without hledger installed.
2. **Shell out to `hledger ... -O json`** when (and only when) the
   operator opts into deeper ledger validation. Read structured
   output; never scrape terminal-formatted output. Return an
   `mb.sidecar.context.v1`-shaped envelope.
3. **Library bindings declined for `mb` core.** No Python or Haskell
   hledger library bindings in `mb` core. Adapter sidecars may
   import upstream libraries internally; `mb` core must not.

### 4. hledger v1.99 assumptions that matter

- The pre-2.0 dev cycle is the current release line; 1.x is the
  stable journal format.
- CSV import (`hledger import`), the major reports (`balance`,
  `balancesheet`, `balancesheetequity`, `cashflow`,
  `incomestatement`, `register`, `aregister`), and the web viewer
  (`hledger-web`) all live in-tree.
- `-O json` is the documented machine-readable contract for every
  major report. `-O csv` is also available where useful. Main
  Branch should target these structured outputs, never terminal
  scraping.
- Account types are declared with `account name ; type:<letter>`
  directives (`A`, `L`, `E`, `R`, `X`).

### 5. Stale Beancount v2 assumptions to avoid in the comparison

The Beancount comparison must be against v3, not v2. v3 (June 2024)
intentionally trimmed the engine and moved importers, query,
prices, lot/growth, and format conversion to separate PyPI
projects (`beangulp`, `beanquery`, `beanprice`, `beangrow`,
`beancount2ledger`). Old tutorials describing Beancount as
one-package-does-everything reflect v2 and are misleading for
this evaluation.

### 6. Importer/report/viewer ecosystem boundary

| Surface | hledger 1.99 | Beancount v3 |
| --- | --- | --- |
| CSV import rules | `hledger import` (built-in) | `beangulp` (separate project) |
| Balance / register | built-in | needs `beanquery` or `bean-report` (deprecated) |
| Balance sheet / IS / cashflow | built-in | needs `beanquery` |
| Prices / commodities | `hledger-stockquotes` (separate) | `beanprice` (separate) |
| Web viewer | `hledger-web` (in-tree) | Fava (third-party) |
| Format conversion | built-in (`print --output-format=...`) | `beancount2ledger` (separate) |

For Main Branch's first slice, nothing past `hledger` itself is in
scope. Real importers, deeper queries, hosted viewers, and price
fetching are follow-ups.

### 7. hledger-web: mention or ignore?

Mention as an **optional local viewer** in `docs/books.md`, no
wiring, no detection, no readiness checks. `hledger-web` is the
project's own UI; it ships in-tree. The mention is one paragraph,
exactly: "if you want a local UI over your journal, `hledger-web`
is the optional local viewer; install and run it yourself." Main
Branch will not start, supervise, or proxy it.

### 8. Safe fake fixture shape

A single small `.journal` file is enough to exercise the first
contract — `account` directives declaring types, opening balances,
one or two transactions, one balance assertion. It must:

- use an obviously fake business name (Acme, Test Co, etc.);
- use only the conventional roots `assets`, `liabilities`,
  `equity`, `income`, `expenses`, each pinned with the right
  hledger `account ... ; type:<letter>` directive;
- declare one operating currency (`USD` is fine);
- contain no Devon-local, vendor, customer, member, payroll, or
  tax data;
- include a header comment that the file is a sample.

The fixture lives under `docs/examples/books/acme-fixture.journal`.

### 9. Git vs local/gitignored boundary

The team-visible business repo commits **only safe metadata**:

- `core/finance/books.md` — bookkeeping policy, ledger location
  pointer, workflow notes, reporting cadence, Class B reminder.
- `core/finance/chart-of-accounts.md` — operator-friendly
  description of the account naming convention and roots in use.
- `docs/examples/books/*.journal` (this engine repo only) — a
  fake fixture for testing.
- Links to a private `finance` child repo, provider dashboards, or
  encrypted local storage where the real ledger actually lives.

The team-visible business repo does **not** commit:

- `*.journal`, `*.hledger`, `*.ledger`, or `*.beancount` files
  containing real transactions;
- `*.csv`, `*.ofx`, `*.qfx`, `*.qbo`, `*.qif`, `*.pdf` statement
  exports;
- account numbers, routing numbers, card numbers, payroll detail,
  tax-return data, vendor/customer payment history at row
  granularity, owner-draw rows, legal/IP-sensitive contracts;
- bank/credit-card/payment-processor exports of any kind;
- anything that would harm the operator if every fork, backup,
  agent copy, or future collaborator could read it forever.

These prohibitions inherit from the accepted
[workspace, repo, and sensitive-data boundary decision](../../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md);
`mb books` sharpens them.

Real ledgers belong in one of three places, by operator choice:

1. A **private `finance` child repo** (the topology role already
   named in `docs/system-architecture.md`). Private GitHub repo or
   self-hosted git.
2. A **local-only path outside any tracked repo**, encrypted at
   rest where appropriate.
3. A **private business repo** for a solo operator who has made an
   explicit decision that team visibility never expands. The
   operator owns that choice.

### 10. Privacy/security risks of plain-text bookkeeping in git

Plain-text-in-git is the strongest argument for the metadata-only
default:

- **Git history is forever.** A leaked `.journal` file is hard to
  remove cleanly after the fact; rewriting history breaks forks,
  mirrors, and backups.
- **Forks and mirrors compound the leak.** Public repos can be
  cached by GitHub forks, search indexes, and personal mirrors.
- **Agent copies expand exposure.** Coding agents commonly clone,
  copy, and re-share repos. A team-visible business repo with a
  committed ledger is a much larger blast radius than a private
  finance repo.
- **Account identifiers leak indirectly.** Even pseudonymous
  account labels in a journal
  (`assets:bank:bestbank:checking`) leak relationships with
  specific institutions and customers when transaction
  descriptions travel alongside them.
- **Statement exports leak the most.** CSV/OFX/QBO files
  typically include full account numbers, routing numbers,
  balances, and counterparties.

The mitigation is structural, not procedural: do not put real
ledgers in team-visible repos in the first place. `mb books` should
treat any committed real-ledger-shaped file as a defect to surface,
not a feature to render.

## Alternatives Considered And Not Chosen

### Beancount v3 (considered; not chosen)

The strongest alternative. Primary-source facts above. Strictness
defaults are an honest win. But the v3 ecosystem split moved CSV
import, reports, and prices out of core, and `bean-report` is
deprecated. Over a 10-year horizon, that pushes complexity onto the
operator that hledger absorbs. Beancount is a fine choice for other
products; for Main Branch's "real multi-business bookkeeping" bar,
hledger is the cleaner long-term call.

### Ledger CLI (considered; not chosen)

The original plain-text accounting tool and the inspiration for both
hledger and Beancount. Useful background; less aligned with current
docs and tooling than hledger; not the default first choice today.
hledger's README positions itself as "a more UX/reliability-focused
reimplementation of the best parts."

### CSV / SQLite (rejected as the books)

Great for bank exports, Stripe exports, ads spend, daily snapshots,
source data, reports, and analysis tables. Not the official
double-entry accounting layer. Double-entry bookkeeping needs
balances, account types, postings, assertions, splits, equity, and
close/open behaviour — more than rows in a table.

Main Branch's clean division of responsibility:

| Layer | Role |
| --- | --- |
| hledger journal | Books |
| CSV / SQLite | Source data, snapshots, imports, reports |
| Markdown | Explanations and decisions |
| Git | History |
| `mb` | Checks and workflow |

## Recommendation

1. **Adopt hledger as the bookkeeping engine for `mb books`.** This
   is a one-and-done product choice, not a hedge. Keep it optional
   for base `mb` installs; the base CLI must continue to work
   without hledger present.
2. **Define the safe `mb books` contract** in a new decision and a
   new `docs/books.md` (this branch).
3. **Ship a fake fixture** under
   `docs/examples/books/acme-fixture.journal` so future
   `mb books check` work has something to validate against (this
   branch).
4. **Defer `mb books check` implementation** to a follow-up issue.
   The decision in this branch names the first surface, exit
   semantics, and what the command must not do.
5. **Migrate existing Beancount surfaces in a follow-up.** The
   `mb connect` Beancount provider, the educational doc, and the
   descriptive copy in ethos / system-architecture /
   dependency-choices / operator-loops / beginner-setup all need to
   move to hledger. The decision in this branch lists those targets;
   the foundation PR does not run the migration so it stays a
   foundation PR.
6. **Defer importers, deeper reports, and viewer wiring.** Not part
   of the safe foundation.
7. **Plan to shell out to `hledger ... -O json`, not import.** When
   deeper validation lands, it runs the hledger binary; `mb` core
   does not import hledger libraries.

## Out Of Scope For This Report

- A working `mb books check` CLI.
- An hledger sidecar implementation.
- Real importer evaluation.
- Hosted viewers.
- QuickBooks/Xero/Wave migration paths.
- Anything that would touch a real bank, statement, payroll system,
  tax record, or customer payment ledger.
