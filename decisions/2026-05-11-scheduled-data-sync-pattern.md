---
type: decision
date: 2026-05-11
status: accepted
topic: First scheduled data sync pattern for business repos
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/471
linked_decisions:
  - decisions/2026-05-11-data-source-registry.md
  - decisions/2026-05-11-connecting-notes-data-and-history.md
  - decisions/2026-05-11-mb-books-foundation.md
  - decisions/2026-05-11-repo-setup-visibility-and-checks-model.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
linked_docs:
  - docs/scheduled-data-sync.md
  - docs/data-source-registry.md
  - docs/business-connections.md
  - docs/books.md
  - docs/dependency-choices.md
participants: [Devon, Claude]
tags: [data, sync, sense, foundation]
---

# Scheduled data sync pattern for business repos

## Decision

The first scheduled data sync pattern for Main Branch business repos is a
**documented operator-owned cron recipe** that calls a one-shot sync script
per provider, writes SQLite/CSV outputs into the existing
[data-source registry](2026-05-11-data-source-registry.md) layout, and
updates the matching `data/<provider>/source.md` record so `mb validate`,
`mb status`, and `mb doctor` can read freshness from the same files agents
already read.

Concretely:

- The default shape is **cron (or `launchd` / Windows Task Scheduler) +
  one-shot script**. `mb` does not start, supervise, or detect a sync
  service.
- The eventual `mb` surface is a **planned** wrapper —
  `mb data sync <provider>` and `mb data status` — that calls the same
  per-provider script, validates output, and updates the source record.
  Neither command ships in this slice. This decision names the shape so
  follow-up implementation issues have a contract to reference.
- **GitHub Actions** is an explicitly-supported alternative for hosted runs
  where the operator already trusts GitHub for secrets, but it is not the
  default and is not required to use Main Branch.
- A **local background service** (daemon, supervisor, always-on agent) is
  out of scope and stays deferred until a separate accepted decision says
  otherwise.
- **Operational state** (last-run timestamps, exit status, run logs) lives
  under `.mb/private/sync/`, mirroring the
  [private bookkeeping vault](2026-05-11-mb-books-foundation.md) ignore pattern.
  The team-visible business repo only carries the data outputs and the
  registry record, never run logs or operator-local paths.
- **Credentials** stay in the OS keychain, the runtime environment, or
  hosted-runner secrets. Repo files never carry tokens, refresh tokens,
  client secrets, service-account JSON, or raw account identifiers.
- **Stale or failed sync** is surfaced through
  `mb status` / `mb doctor` reading the `data_source` record's `freshness`
  vs `cadence` plus the optional `.mb/private/sync/<provider>.json`
  last-run summary. The CLI explains the gap; it does not pretend Main
  Branch ran the job.
- **Reports, decisions, pushes, and outcomes** continue to link the data
  source through the typed `linked_data_sources` frontmatter field plus
  inline links to the specific snapshot that proved the claim.
- The pattern feeds the data-source registry. It does **not** feed the
  hledger journal directly. The
  [`mb books` foundation](2026-05-11-mb-books-foundation.md) keeps the
  authoritative ledger inside the private bookkeeping vault; bookkeeping
  imports remain a separate follow-up scope.

This slice ships docs and a decision. No CLI behaviour changes.

## Why this shape

Main Branch's product spine is:

1. `mb` is a deterministic, inspectable, scriptable, one-shot control plane.
2. Business truth lives in git; local operational state lives outside git.
3. Secrets live in the OS keychain, env, or runtime-specific stores.
4. Provider mutation and spend-affecting work require explicit operator
   action.

Cron + a one-shot script honours all four. The operator owns the schedule
on a host they already control. The script is inspectable and re-runnable
on demand. Failures are visible in repo state (a stale `freshness` date,
an unchanged SQLite/CSV snapshot) and in the local last-run summary that
`mb doctor` can read.

A "let `mb` schedule it for you" shape would either need a background
process (which contradicts the one-shot contract) or push the scheduling
problem into GitHub Actions for every operator. GitHub Actions is a fine
choice when the operator is already running CI; it is the wrong default
for a local-first business OS where many operators run no CI at all and
where some providers require an OAuth/refresh flow that an unattended
runner cannot complete safely.

Reusing the data-source registry as the metadata-of-record means sync
state is durable (it lives in the same markdown the rest of the business
already links to), portable across hosts, and inspectable by the same
validators agents and `mb` already trust. There is no second source of
truth for "is this data fresh."

## Tradeoffs by sync shape

The first pattern documents four shapes so operators and agents can pick
the one that matches the work. The default and recommended starting
shape is **operator-owned cron**.

| Shape | When it fits | When it does not | What ships |
| --- | --- | --- | --- |
| Operator-owned cron (`launchd`, `cron`, Task Scheduler) | Single-operator local sync; data folder is part of the operator's regular host; secrets in the OS keychain or env. | Operator's machine is rarely on; multi-machine teams that need a common schedule; jobs that need long-running compute. | Documented recipe + per-provider script template. |
| Manual `mb data sync <provider>` (planned, not shipped) | Same machine as cron, but the operator wants the same wrapper from any shell or skill. | Continuous always-on sync; jobs that should run while the operator is away from the host. | Decision shape only. Implementation tracked in a follow-up issue. |
| GitHub Actions workflow | The operator already runs CI, secrets are stored in GitHub, providers tolerate hosted-runner credentials, and the data outputs are safe to commit through a PR. | Providers that require interactive OAuth refresh, secrets the operator does not want in a hosted runner, or data outputs that cannot be public-safe even in a private repo. | Documented recipe + a sanitised reference workflow. |
| Local background service | Always-on capture, sub-minute cadence, push-style provider webhooks. | Default Main Branch use. Adds supervisor/state-model complexity that requires its own accepted decision. | Out of scope. Deferred. |

Operators may mix shapes per provider — for example, `cron` for daily
Google Ads, `gh actions` for a weekly public dataset refresh, manual
re-run for everything else.

## Layout

The sync pattern reuses the existing data-source registry layout and
adds one local-only sibling for run state.

```text
data/<provider>/
  source.md                           # data-source record (already shipped)
  daily.sqlite                        # storage.primary (already shipped)
  snapshots/
    2026-05-10.csv                    # storage.snapshots entries

.mb/private/sync/                     # local-only; should not be tracked
  <provider>.json                     # last-run summary
  logs/<provider>/2026-05-10.log      # raw provider/CLI output
```

`.mb/private/sync/` is intended to live inside the business repo's
working tree but never be tracked. Today the default `mb onboard`
gitignore template does **not** yet include `.mb/private/`: the
[`mb books` foundation](2026-05-11-mb-books-foundation.md) named the
template update as a deferred follow-up, and this slice does not change
the template either. Until a follow-up patches
`mb/mb/_data/templates/.gitignore.tmpl`, operators following this
pattern must add `.mb/private/` to their business repo's `.gitignore`
themselves. The planned `mb data` surface will own the ignore
enforcement when it ships. Treat this gap as the first follow-up
implementation issue for the pattern, not an inherited guarantee.

The last-run summary is intentionally a small JSON shape so any wrapper
language can write it:

```json
{
  "provider": "google-ads",
  "run_started": "2026-05-10T07:00:00Z",
  "run_finished": "2026-05-10T07:00:42Z",
  "status": "ok",
  "exit_code": 0,
  "outputs": [
    "data/google-ads/daily.sqlite",
    "data/google-ads/snapshots/2026-05-10.csv"
  ],
  "freshness": "2026-05-10",
  "notes": "Pulled last 31 days; appended into ads_daily."
}
```

`status` is one of `ok`, `failed`, or `skipped`. The schema is
intentionally narrow; richer fields can be added when the planned `mb`
wrapper lands.

## Where credentials live

Credentials never live in repo files, frontmatter, run logs that ship in
PRs, or `.mb/private/sync/<provider>.json`. The supported homes are:

- **OS keychain** (macOS Keychain, GNOME Keyring, Windows Credential
  Manager) read by the per-provider script via the provider's CLI/SDK.
  This is the recommended default for solo local cron.
- **Environment variables** for the sync process — set by the operator's
  shell profile, the cron entry, or a small `.env` kept outside the
  repo. The script reads `os.environ`, never a tracked file.
- **GitHub Actions secrets** when running the GitHub Actions shape.
- **Provider-native auth** (gcloud, AWS, Stripe CLI, etc.) when the
  provider already manages a local credential store.

`mb connect` and the upcoming `provider_config` / `secret_handle`
registry record types remain the right place to describe **how** the
operator wired credentials in plain language without exposing them.
Sync scripts read those wired credentials at runtime; they do not store
them.

## Writing outputs safely

The per-provider sync script is responsible for:

1. Writing SQLite changes inside a transaction. SQLite's atomic commit
   keeps in-flight reads safe; readers do not need to coordinate.
2. Writing CSV snapshots to a temp path in the same directory, then
   `os.replace` into place. `os.replace` is atomic on POSIX and on
   NTFS for same-volume replacements and, unlike `os.rename`, overwrites
   an existing destination on Windows without raising
   `FileExistsError` — important for the idempotent-retry rule below.
3. Updating `data/<provider>/source.md` frontmatter so `freshness`
   matches the run date and `storage.snapshots` lists the new CSV.
   The script edits frontmatter only, never the body, and uses a
   round-trip YAML loader that preserves comments and key order.
4. Writing `.mb/private/sync/<provider>.json` last so a half-finished
   run never reports success.

Scripts should be **idempotent on retry**. A second invocation on the
same date should overwrite the same snapshot file rather than creating
a duplicate-with-suffix. Agents and operators rerunning the job by hand
should see the same outputs they would have seen from cron.

## How `mb doctor` and `mb status` surface freshness

Stale or failed sync is a Sense signal, not a hidden background concern.
The pattern reuses primitives already in the registry:

- `data_source.cadence` declares the expected refresh window
  (`daily`, `weekly`, etc.).
- `data_source.freshness` declares the date of the most recent
  successful pull.
- `.mb/private/sync/<provider>.json` carries the most recent run
  status, including failed runs that did not advance `freshness`.

A planned `mb doctor` check (tracked as a follow-up to this decision)
should:

- Warn when `freshness + cadence` is older than the host clock.
- Warn when the most recent `.mb/private/sync/<provider>.json` `status`
  is `failed`, including the run's `notes` and the next command the
  operator can re-run.
- Stay silent when the registry record exists but no sync history is
  present yet, treating that as "the operator has not started syncing
  this source" rather than as a failure.

`mb status` surfaces the same signals in ranked next actions through
the existing `audience: operator_decision` channel — Main Branch tells
the operator the data is stale; it never claims it ran the sync.

The doctor check does **not** rely on Main Branch being live. It only
reads files. A repo where the operator has not synced in three weeks
will produce three weeks of staleness warnings on the next `mb doctor`
run, which is the correct behaviour for an inspection tool.

## How records link to synced data

The connection rules from
[`docs/business-connections.md`](../docs/business-connections.md) do
not change. The pattern adds three habits:

1. **Decisions and pushes that depend on a provider** link the
   data-source record through `linked_data_sources`, not the raw
   SQLite or CSV files. The typed link is what `mb graph` and
   `mb suggest links` know how to reason about.
2. **Reports and outcomes that prove what happened** add an inline
   Markdown link to the specific snapshot CSV (or the dated report
   that summarises it) so a reader can audit the number. The typed
   link still goes through the registry record.
3. **Run logs are not durable evidence.** Operators link the snapshot
   or the report, not `.mb/private/sync/<provider>/logs/...`. Run
   logs are local-only and gitignored; treating them as durable
   evidence would re-introduce the "secrets in repo" risk the
   pattern is built to avoid.

## Relationship to `mb books` / hledger

The [`mb books` foundation](2026-05-11-mb-books-foundation.md) chose
hledger as the bookkeeping engine and put the authoritative ledger in
a **private bookkeeping vault** (`.mb/private/books/main.journal` for solo
mode, a separate restricted-access repo for team mode).

This pattern does not change that. In particular:

- Scheduled sync **may** write Stripe, PayPal, payroll, or bank
  exports into the **private bookkeeping vault's** `imports/` directory
  when the operator's script targets that location. That happens
  entirely inside the vault and inherits the vault's storage rules.
- Scheduled sync **must not** write raw bank, processor, payroll, or
  tax exports into the **team-visible business repo's**
  `data/<provider>/` folder. Those file shapes are Class B per the
  books decision and the
  [workspace/sensitive-data boundary](2026-05-04-workspace-repo-sensitive-data-boundaries.md);
  putting them in the team-visible registry would leak them.
- The `data/<provider>/` registry remains the right home for
  marketing, ads, analytics, CRM, and email-engagement data that the
  team is allowed to read.
- A future `mb books import` command — still out of scope — would
  read from the vault's `imports/` directory, not from
  `data/<provider>/`. The two paths stay separate on purpose so the
  team-visible registry never becomes a finance database.

The short rule: synced data with a clean public/team audience goes
through `data/<provider>/`; synced data with a Class B finance
audience goes through `.mb/private/books/imports/` and never leaves
the vault.

## What this slice does not do

This decision is intentionally a foundation slice. It does **not**:

- Ship `mb data sync`, `mb data status`, `mb doctor` freshness
  checks, or any other CLI surface. Each is a separate follow-up
  issue.
- Choose provider-specific clients (Google Ads API library, Stripe
  CLI, Meta Marketing API, GA4 Data API, etc.). Those become
  per-provider follow-ups.
- Define a sidecar enrichment envelope for sync runs. The existing
  [sidecar enrichment CLI contract](2026-05-04-sidecar-enrichment-cli-contract.md)
  may be reused when a provider sync graduates into an optional
  sidecar, but no sidecar ships here.
- Modify `mb onboard` to scaffold `data/` or `.mb/private/sync/`. The
  data-source registry stub at `mb/mb/_data/stubs/data-source.md`
  is still copied on request.
- Introduce a background service. Long-running scheduling is a
  separate accepted-decision conversation.
- Add a new registry record type. The pattern reuses `type:
  data_source`. Sibling record types
  (`provider_config`, `secret_handle`, `integration_account`) remain
  open per the data-source registry decision.

## Follow-up issues

When the pattern proves itself in real use, file separate issues for:

- Patching `mb/mb/_data/templates/.gitignore.tmpl` to add
  `.mb/private/` so new business repos ignore the sync state (and the
  books vault) by default. The
  [`mb books` foundation](2026-05-11-mb-books-foundation.md) already
  named this as a deferred migration; sync is the second consumer that
  needs it.
- `mb data sync <provider>` / `mb data status` wrapper command pair.
- `mb doctor` freshness check that reads `freshness`, `cadence`, and
  `.mb/private/sync/<provider>.json`.
- The first provider-specific sync script template (likely Google
  Ads daily) shipped under `docs/examples/sync/`.
- A reference GitHub Actions workflow under `docs/examples/sync/`
  with a public-safe secret model.
- `mb books import` and the bridge between the private bookkeeping vault's
  `imports/` directory and the hledger journal.
- Optional sidecar envelope for sync runs if a third-party tool
  becomes part of the recommended path.

## Validation Contract

For this decision slice:

- Level 0 (docs/decision) review is required: frontmatter, links, no
  stale product claims, no private data.
- `scripts/check.sh` (Level 1) must pass before pushing.
- No CLI tests (no CLI behaviour changes).
- No package/install smoke (no packaging changes).
- No fixture-repo smoke (no scaffolding changes).
- No runtime smoke (no skill or runtime changes).

Follow-up implementation issues add the appropriate ladder evidence
when they ship CLI behaviour, scaffolding, or runtime wiring.

## Consequences

- Main Branch picks one default schedule shape (operator-owned cron)
  and one default state model (`.mb/private/sync/` + the existing
  data-source record) instead of leaving every operator to invent
  their own.
- The data-source registry becomes the durable record of "what we
  trust" and "how fresh it is." Operators and agents read the same
  files for both.
- `mb` stays one-shot. The product avoids accumulating a background
  process before the rest of the daily loop is boring.
- The pattern does not collide with the private bookkeeping vault.
  Bookkeeping imports remain a separate scope with stricter data rules.
- Future provider follow-ups have a contract to point at instead of
  re-litigating "where do logs go" each time.

## Review Trigger

Revisit this decision when any of these become true:

- A real operator workflow needs sub-daily sync, push-style
  webhooks, or always-on capture that cron cannot handle.
- A provider lands in Main Branch that cannot run a one-shot
  command at all (only persistent connection / streaming).
- The optional sidecar enrichment contract grows a sync-shaped
  envelope that supersedes per-provider scripts.
- `mb books import` lands and reshapes the boundary between
  team-visible `data/` and the private bookkeeping vault's `imports/`
  directory.
- A separate accepted decision approves a Main Branch background
  service.
