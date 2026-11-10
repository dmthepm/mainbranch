# Scheduled data sync

This page describes how Main Branch wants you to keep business data
fresh. It is the operator-facing companion to
[the scheduled data sync pattern decision](../decisions/2026-05-11-scheduled-data-sync-pattern.md).

## The Short Version

- Pick a schedule yourself (cron, `launchd`, Task Scheduler, or a
  GitHub Actions workflow). Main Branch does not run a background
  service for you.
- Each provider gets a small one-shot script that pulls fresh data,
  writes a SQLite file plus a dated CSV snapshot under
  `data/<provider>/`, and updates `data/<provider>/source.md`.
- Credentials stay in the OS keychain, your shell env, or hosted-runner
  secrets. They never live in repo files.
- Last-run logs and timestamps live under `.mb/private/sync/` and are
  not tracked by the business repo.
- **Planned:** `mb doctor` and `mb status` reading freshness from
  `source.md` and the local run summary. No code reads `.mb/private/sync/`
  today, so nothing reports a source as stale. Keep `freshness` honest in
  `source.md` yourself.
- The `mb data sync` and `mb data status` commands are **planned**, not
  shipped. The pattern works today with a hand-rolled cron entry.
- Real bookkeeping data (bank, processor, payroll, tax) does **not**
  go through `data/<provider>/`. It belongs in the private bookkeeping vault
  per [`docs/books.md`](books.md).

## How The Pieces Fit

```text
data/<provider>/
  source.md            # data-source record; durable handle for decisions/outcomes
  daily.sqlite         # storage.primary; SQLite the team can query locally
  snapshots/
    2026-05-10.csv     # storage.snapshots; portable cuts the team can audit

.mb/private/sync/      # local-only; you must add `.mb/private/` to .gitignore today
  <provider>.json      # last-run summary (status, exit code, outputs, notes)
  logs/<provider>/
    2026-05-10.log     # raw output from the per-provider script

cron / launchd / Task Scheduler / .github/workflows/<provider>.yml
                       # the schedule itself — owned by the operator's host or CI
```

`source.md` is already the readable record the rest of the business
repo links through. The sync pattern just keeps its `freshness` and
`storage.snapshots` fields honest.

**Confirm `.mb/private/` is in your `.gitignore` before you start syncing.**
New folders from `mb onboard` or `mb init` already ignore it. A folder
created earlier may not, so open its `.gitignore` and check the actual rule.
An operator who skips this will commit run logs and the last-run JSON to
their business repo.

## Pick A Schedule Shape

Four shapes; same outputs. The default is **operator-owned cron**.

### Operator-owned cron (default)

For a single operator running Main Branch on a machine they control.
Example crontab entry:

```cron
# Pull yesterday's Google Ads data each morning at 07:00 local time.
0 7 * * * /Users/me/code/my-business/scripts/sync-google-ads.sh \
    >> /Users/me/code/my-business/.mb/private/sync/logs/google-ads/$(date +\%F).log 2>&1
```

The script:

1. Reads credentials from the OS keychain or the environment.
2. Pulls fresh rows from the provider.
3. Writes a SQLite transaction into `data/google-ads/daily.sqlite`.
4. Writes a new CSV snapshot into `data/google-ads/snapshots/`.
5. Edits `data/google-ads/source.md` so `freshness` matches today and
   the new snapshot is listed under `storage.snapshots`.
6. Writes `.mb/private/sync/google-ads.json` with `status`,
   `exit_code`, `outputs`, and a short `notes` line.

`launchd` (macOS) and Windows Task Scheduler work the same way. The
script is what matters; the scheduler is the operator's choice.

### Manual command (`mb data sync` — planned)

When the planned `mb data sync <provider>` and `mb data status`
wrappers ship, they will call the same per-provider script, validate
the outputs, and update `source.md` for you. Until then, run the
script directly:

```bash
./scripts/sync-google-ads.sh
mb validate
mb status
```

### GitHub Actions

A reasonable shape when you already use CI, your team uses GitHub
secrets, and the data outputs are safe to commit through a PR. Rough
shape:

```yaml
# .github/workflows/sync-google-ads.yml
name: Sync Google Ads
on:
  schedule:
    - cron: "0 14 * * *"   # 14:00 UTC daily
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run sync script
        env:
          GOOGLE_ADS_REFRESH_TOKEN:   ${{ secrets.GOOGLE_ADS_REFRESH_TOKEN }}
          GOOGLE_ADS_CLIENT_ID:       ${{ secrets.GOOGLE_ADS_CLIENT_ID }}
          GOOGLE_ADS_CLIENT_SECRET:   ${{ secrets.GOOGLE_ADS_CLIENT_SECRET }}
        run: ./scripts/sync-google-ads.sh
      - name: Commit and open PR
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "[data] Refresh Google Ads daily snapshot"
          branch: data/google-ads-${{ github.run_id }}
          title: "[data] Refresh Google Ads daily snapshot"
```

Notes:

- For a live Google Ads read, the Cloud project that owns the OAuth client must
  have [Explorer, Basic, or Standard API access](https://developers.google.com/google-ads/api/docs/api-policy/access-levels).
  The authorized identity also needs the right
  [Google Ads account role](https://developers.google.com/google-ads/api/docs/oauth/access-model).
  Confirm both with a read before scheduling the script. Google
  [sunset developer tokens](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)
  for the Google Ads API; use a current client library if an older version
  still requires a token setting locally.
- Use a hosted runner only when the provider tolerates unattended
  credentials. Some providers require interactive OAuth refresh that
  a hosted runner cannot complete safely.
- GitHub Actions PRs go through the same human review path as any
  other change. The pattern keeps `data/` review-able instead of
  silently auto-committing to `main`.

### Local background service

Out of scope. A daemon needs its own state model, supervisor, and
restart behaviour. That conversation lives behind a separate accepted
decision; do not introduce one as part of a sync script.

## Where Credentials Live

| Storage | Use it for | Avoid it for |
| --- | --- | --- |
| OS keychain (macOS Keychain, GNOME Keyring, Windows Credential Manager) | Solo local cron; long-lived OAuth refresh tokens. | Hosted runners. |
| Shell environment / `.env` outside the repo | Quick local runs and dev iterations. | Anything that should outlive the shell session. |
| GitHub Actions secrets | The GitHub Actions shape, with provider-issued long-lived tokens. | Tokens you would not want hosted by GitHub. |
| Provider-native auth (`gcloud`, `aws`, `stripe`) | Providers that manage their own local credential store. | Multi-tenant setups where the operator account differs from the business account. |

What never works:

- Tokens in `data/<provider>/source.md` frontmatter.
- Tokens in `.mb/private/sync/<provider>.json`.
- Tokens in commit messages or run logs that get committed.
- Service-account JSON committed to the repo (public **or** private).

`mb validate` already rejects secret-shaped frontmatter on the
data-source record. The sync pattern stays inside that boundary.

## Writing Outputs Safely

The script you run on a schedule is responsible for:

1. **Atomic SQLite writes.** Wrap changes in a transaction. SQLite's
   atomic commit keeps concurrent readers safe.
2. **Atomic CSV writes.** Write to `snapshots/.tmp-2026-05-10.csv`,
   then `os.replace` into place. `os.replace` is atomic on POSIX and
   NTFS for same-volume replacements, and unlike `os.rename` it
   overwrites an existing destination on Windows — which matters when
   you re-run the same day's sync.
3. **Frontmatter-only edits to `source.md`.** Use a round-trip YAML
   loader so the body, comments, and key order survive.
4. **Last-run summary written last.** Write
   `.mb/private/sync/<provider>.json` only after every other output is
   on disk, so a failed run never reports success.

If the script fails halfway, the next `mb doctor` run will see a stale
`freshness` and a `status: failed` summary. That is the correct signal.

## How `mb` Surfaces Freshness

`mb doctor` and `mb status` read freshness from two places:

- `data/<provider>/source.md` — `cadence` (expected window) and
  `freshness` (most recent successful pull).
- `.mb/private/sync/<provider>.json` — most recent run status,
  including failed runs that did not advance `freshness`.

When a planned `mb doctor` freshness check ships, you will see lines
like:

```text
data-source: google-ads
  cadence:    daily
  freshness:  2026-05-07 (3 days stale)
  last run:   failed at 2026-05-10T07:00:42Z
  next:       re-run ./scripts/sync-google-ads.sh and inspect the log
```

Until that lands, the same information is available by reading the
two files. The contract is intentionally inspectable: a human or
agent should be able to answer "is this data fresh?" without running
anything.

## Linking Reports, Decisions, Pushes, And Outcomes

The connection rules in
[`docs/business-connections.md`](business-connections.md) do not
change. Three habits keep synced data legible:

- **Typed link to the record, not the file.** Decisions, pushes,
  playbooks, and outcomes link `data/<provider>/source.md` through
  the `linked_data_sources` frontmatter field. That is what `mb graph`
  understands.
- **Inline link to the snapshot that proved the claim.** Reports and
  outcomes link the specific CSV (or the dated report summarising it)
  so an auditor can re-read the number.
- **Run logs are not durable evidence.** `.mb/private/sync/logs/...`
  is local-only and gitignored. Do not link it from a decision or
  outcome; it will not be there when someone reads the record later.

Example outcome snippet:

```markdown
---
type: outcome
linked_data_sources:
  - data/google-ads/source.md
linked_pushes:
  - pushes/2026-05-08-google-ads-test/push.md
---

# 2026-05-10 — Google Ads test outcome

Spend held at the planned daily cap; see the
[2026-05-10 snapshot](../data/google-ads/snapshots/2026-05-10.csv)
for the row-level cut.
```

## Relationship To `mb books` / hledger

Real bookkeeping data does **not** go through `data/<provider>/`.

- Marketing, ads, analytics, CRM, and email-engagement data → fine
  to sync into the team-visible `data/<provider>/` registry.
- Bank exports, processor settlements, payroll, tax, raw customer
  payment rows → these are **Class B** per
  [`docs/books.md`](books.md). They belong in the private bookkeeping
  vault (`.mb/private/books/imports/` for solo, the books repo for
  team mode), never in `data/<provider>/`.

The sync pattern and the bookkeeping vault stay separate on purpose. A
future `mb books import` command will read from the vault's
`imports/` directory and feed the hledger journal. It will not read
from `data/<provider>/`. The team-visible registry never becomes a
finance database.

If your script could write either kind of output (for example, a
Stripe sync that pulls both marketing aggregate metrics **and** raw
settlement rows), split it into two scripts: one writes to
`data/stripe/` with the safe aggregate; the other writes to
`.mb/private/books/imports/` with the raw rows. Two scripts, two
audiences, two storage locations.

## What This Page Does Not Promise

- A shipped `mb data sync` or `mb data status` command. Both are
  planned; neither has been implemented yet.
- A shipped `mb doctor` freshness check. The shape is documented
  here; a follow-up issue will implement it.
- Provider-specific scripts. Each provider is its own follow-up.
- A background service. That requires its own accepted decision.
- An automatic credential-management story. The pattern names where
  credentials live; the operator is still responsible for putting
  them there.

## Related

- [Scheduled data sync pattern decision](../decisions/2026-05-11-scheduled-data-sync-pattern.md)
- [Data-source registry shape](data-source-registry.md)
- [Business connections](business-connections.md)
- [Books](books.md)
- [Workspace and sensitive-data boundary](../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md)
- [Sidecar enrichment CLI contract](../decisions/2026-05-04-sidecar-enrichment-cli-contract.md)
