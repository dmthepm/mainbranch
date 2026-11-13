---
title: "PRD: source health (data freshness records and a read-only reader)"
status: draft
date: 2026-10-29
issue: "#1255"
related: "#1247 machine doctor design (exit precedence, not_verified rule), #1258 operating team (duty map), docs/data-source-registry.md, docs/scheduled-data-sync.md, docs/json-output-contract.md"
---

# PRD: source health

## One-screen summary

- **Problem.** An agent can read a data store without learning that the feed
  behind it stopped days ago, or lost access to part of what it covered.
  "Fresh", "stale" and "failed" look the same from inside the data.
- **Split of work.** A collector writes a small status record after every run.
  `mb` reads the records and judges each source. An alerter, outside `mb`,
  decides who to tell. `mb` never runs collectors and never sends alerts.
- **Where it is declared.** A `health:` block in the existing
  `data/<provider>/source.md` record. No new file type.
- **The reader.** `mb data health`. Read-only, stateless, no sudo, no writes.
  It reads local files by default. It reads a remote record only through a
  read route the owner configured on this machine.
- **States.** `fresh`, `degraded`, `failed`, `stale`, `not_verified`. A source
  that can't be read is `not_verified`, never a pass.
- **Exit codes.** The machine doctor's precedence: `2` > `1` > `3` > `0`.
  This moves `not_verified` from `2` (interface v0.1) to `3`. See open
  question 1.
- **Standalone businesses.** The record format is documented, so any script
  or cron job can write one. `mb` ships no collector.
- **Status today:** designed, not built. Nothing in this PRD is shipped.

## Goals

1. Tell fresh, degraded, failed and stale sources apart without starting an
   agent and without copying business data (issue #1255, "done when").
2. One record format that a platform collector and a hand-written cron script
   can both write.
3. A judgment that is the same every time for the same record and clock. The
   reader keeps no state between runs.
4. Fit the existing data-source registry, the JSON envelope, and the machine
   doctor's exit vocabulary, so owners learn one set of rules.

## Non-goals

- Running, scheduling or repairing collectors. The owner's cron, CI job or
  platform does that ([scheduled-data-sync.md](../scheduled-data-sync.md)).
- Alerting, paging, or remembering whether an alert went out. That stays with
  the platform or the owner (see "Alerting stays outside mb").
- Reading the data itself, or judging whether the numbers are right.
- `mb data sync`. It stays planned and separate.
- Opening network connections or picking a transport by itself. `mb` never
  starts `ssh` or any other remote command unless the owner configured that
  route.

## Who carries this duty

In the operating-team duty map (#1258), source health is a duty with a
carrier:

| Shape | Who writes records | Who reads | Who alerts |
| --- | --- | --- | --- |
| With a platform | The platform's collectors | `mb data health` (and the platform's own reader) | The platform |
| Standalone | The business's scheduled sync script | `mb data health` | The owner, or nobody yet |

`mb team check` treats a `platform: <name>` carrier as `not_verified`
(`outside_repo`). `mb data health` is how a business sees the result of that
duty from inside its own repo, without trusting the platform's say-so.

## 1. The declared source spec

### Where it lives

In the business repo, in the frontmatter of `data/<provider>/source.md`,
under one new optional key, `health`. A source with no `health` block is not
checked and does not appear in the output. Existing records stay valid.

```yaml
---
type: data_source
provider: example-chat
owner: platform          # existing field: who fixes it
privacy: team_private
cadence: hourly          # existing, human-readable
freshness: 2026-10-29    # existing, human-maintained; the reader ignores it
health:
  id: example-chat              # stable, lower-case, [a-z0-9-]{1,64}
  cadence_seconds: 900          # expected interval between runs
  grace_seconds: 1800           # stale after cadence + grace with no success
  record:
    local: .mb/private/sync/example-chat.status.json   # repo-relative
    # or, instead of local:
    # route: platform-records    # a read route name, configured per machine
  expected_coverage: 12         # optional: a count, never a list of ids
  read_command: "sqlite3 data/example-chat/messages.sqlite '.tables'"
---
```

### Rules

- `health.id` must be unique across the repo. Two sources with the same id are
  a spec error (exit `2`).
- Exactly one of `record.local` or `record.route`.
- `record.local` is relative to the repo root, must stay inside it after
  resolving `..` and symlinks, and should sit under `.mb/private/` so records
  are not committed. A path outside the repo is a spec error.
- `record.route` names a route. The route's details live on the machine, not
  in the repo (section 3), so hosts and paths never get committed.
- `expected_coverage` is a count. Channel, account or object ids belong in the
  record the collector writes, which stays local. The tracked spec never
  holds them.
- `read_command` is **display only**. It tells a person how to read the data.
  `mb` never executes it, never passes it to a shell, and never templates it.
  It is printed as text, and `mb validate` warns when it contains a newline or
  is longer than 300 characters.
- `owner` is the existing data-source field. The reader copies it into the
  output so the alerter knows who fixes the source.

`mb validate` checks the block's shape. It reads no records.

## 2. The status record

The interface v0.1 record, unchanged except where marked. The collector writes
it after every run, atomically: write a temporary file in the same directory,
then rename it into place.

```json
{
  "schema": {"name": "mainbranch.source_status", "version": "0"},
  "source": "example-chat",
  "run_at": "2026-10-30T09:15:00Z",
  "last_success_at": "2026-10-30T09:15:00Z",
  "result": "ok",
  "error": null,
  "first_failed_at": null,
  "coverage": {
    "expected": 12,
    "seen": 11,
    "missing": [
      {"id": "<id>", "reason": "missing_access", "first_seen": "2026-10-30T08:00:00Z"}
    ]
  },
  "permissions": {"missing": []},
  "items": 340,
  "collector_version": "1.4.0"
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | Name `mainbranch.source_status`, version `"0"`. Any other name or major version is `not_verified` (`wrong_schema`). |
| `source` | yes | Must equal the spec's `health.id`. A mismatch is `not_verified` (`source_mismatch`). |
| `run_at` | yes | UTC, RFC 3339, `Z` suffix. When this run ended. |
| `last_success_at` | yes, may be `null` | The last run with `result` `ok` or `partial`. `null` if it never succeeded. |
| `result` | yes | `ok`, `partial` or `failed`. |
| `error` | when failed | `{code, message}`. Codes: `auth_revoked`, `rate_limited`, `network`, `unknown`. Message is short and has no secrets. |
| `first_failed_at` | yes, may be `null` | Start of the current run of failures. `null` when the latest run is ok. The collector carries it from its previous record. |
| `coverage` | no | `expected`, `seen`, `missing[]` with `id`, `reason` (`missing_access` or `not_found`) and `first_seen`. |
| `permissions.missing` | no | Scopes the collector lacks. |
| `items` | no | A count. Never content. |
| `collector_version` | no | Free text, for humans. |

Limits the reader enforces:

- Size cap 64 KiB. Larger is `not_verified` (`record_too_large`).
- `missing[]` is read up to 200 entries. More are counted, not listed.
- Strings in the output are cut to 200 characters.
- The record holds no secrets, tokens, message content or customer rows.
  The reader can't prove that, so it never prints `coverage.missing[].id`
  in human output. Ids appear only in `--json`, which is
  `safe_to_share: false`.

**Delta from v0.1, for homelab to confirm:** `last_success_at` counts a
`partial` run as a success. A partial run proves the feed is flowing, and the
gap is reported as `degraded`. See open question 3.

### For a standalone business

[scheduled-data-sync.md](../scheduled-data-sync.md) already tells sync scripts
to write `.mb/private/sync/<provider>.json` last. This PRD keeps that file as
the script's free-form run summary and adds one more file next to it,
`<provider>.status.json`, in the format above. A script that wants health
checks writes both: outputs first, the status record last. The docs ship a
copyable shell function and a Python snippet that write it atomically. `mb`
ships no collector and no daemon.

## 3. Read routes (remote records)

A platform may keep records on another machine. `mb` reads them only through
a route the owner set up on this machine.

- Routes live in user config, outside any repo:
  `~/.config/mainbranch/read-routes.toml` (XDG path on Linux, the same path
  under the home directory on macOS).
- Two kinds:
  - `dir`: a local directory (for example, a synced or mounted folder). The
    record is `<dir>/<id>.json`.
  - `argv`: a fixed command as a list of strings, for a forced-command read
    route the platform provides. `mb` appends one argument, the validated
    source id. No shell, no templating, nothing from the repo goes into the
    command except that id.
- An `argv` route runs with a minimal environment, a 10-second timeout and a
  64 KiB stdout cap, the same probe rules as the machine doctor. Exit non-zero,
  timeout or oversize output is `not_verified` (`route_failed`,
  `route_timeout`, `record_too_large`).
- A route that the spec names but this machine hasn't configured is
  `not_verified` (`route_unconfigured`).
- The route file must be owned by the running user and not writable by group
  or others. Otherwise every route is `not_verified` (`untrusted_route_config`).
- `mb status` never runs an `argv` route (section 6). Only an explicit
  `mb data health` does.

**Security gate:** the `argv` route is the only place this feature runs a
command. It needs a mainbranch-security read before it is built. If security
prefers, v1 ships `dir` routes only and `argv` waits (open question 2).

## 4. The reader: `mb data health`

```text
mb data health [SOURCE_ID ...] [--repo PATH] [--json] [--now RFC3339]
```

- The name doesn't collide. There is no `mb data` group today. The planned
  `mb data sync` and `mb data status` in scheduled-data-sync.md are about
  running and reporting syncs, so `health` is a separate verb (open question 4).
- Reads `data/*/source.md` in the repo, keeps sources with a `health` block,
  and reads each one's record.
- Read-only. Writes nothing, keeps no cache, needs no credentials, never uses
  sudo, never contacts a provider.
- `--now` sets the clock, for fixtures and tests only. It is printed in the
  output when used.
- Naming a `SOURCE_ID` that has no `health` block is a usage error (exit `2`).

### State rules

The reader evaluates in this order. The first rule that matches wins.
`window = cadence_seconds + grace_seconds`. `skew = 300` seconds.

1. **not_verified** if the record is missing, unreadable, too large, not JSON,
   has the wrong schema, names another source, lacks a required field, has a
   bad timestamp, or has any timestamp later than `now + skew`.
2. **stale** if `last_success_at` is `null`, or `now - last_success_at > window`.
   This also catches a collector that stopped running: its last record just
   gets older.
3. **failed** if `result` is `failed` (the last success is still inside the
   window).
4. **degraded** if `result` is `partial`, or `coverage.missing` is not empty,
   or `coverage.seen < coverage.expected`, or `permissions.missing` is not
   empty, or the spec's `expected_coverage` is greater than
   `coverage.expected`.
5. **fresh** otherwise.

### `since` (from the record alone)

| State | `since` |
| --- | --- |
| fresh | none |
| degraded | earliest `coverage.missing[].first_seen`; else `run_at` of the record (open question 5) |
| failed | `first_failed_at`; else `run_at` |
| stale | `last_success_at + window`; if `last_success_at` is `null`, `first_failed_at`, else `null` |
| not_verified | none (the reader can't know) |

### Reasons

Each non-fresh source has one `reason` code:

- degraded: `partial_run`, `coverage_gap`, `permission_missing`,
  `coverage_below_spec`
- failed: the record's `error.code`, else `unknown`
- stale: `no_recent_success`, `never_succeeded`
- not_verified: `record_missing`, `record_unreadable`, `record_too_large`,
  `wrong_schema`, `source_mismatch`, `invalid_record`, `future_timestamp`,
  `route_unconfigured`, `untrusted_route_config`, `route_failed`,
  `route_timeout`

### Exit codes

Same precedence as the machine doctor (#1247): `2` > `1` > `3` > `0`.

| Exit | Meaning |
| --- | --- |
| `0` | Every checked source is fresh, or no source has a `health` block. |
| `1` | At least one source is degraded, failed or stale. |
| `2` | Usage or spec error: bad flags, unknown source id, invalid `health` block, duplicate id. No sources are judged. |
| `3` | Nothing is degraded, failed or stale, but at least one source is `not_verified`. |

An actionable failure outranks an unknown, so a run with one stale and one
`not_verified` source exits `1`. Both still appear in the output.

### Human output

```text
Data health  3 sources  (1 stale, 1 not verified)
  stale         example-ads    since 2026-10-28T07:30Z  no_recent_success  owner growth
  not verified  example-chat   record_missing                               owner platform
  fresh         example-pay
Read the data: sqlite3 data/example-ads/daily.sqlite '.tables'
```

`read_command` is printed for non-fresh sources, labelled as a command for the
owner to run. `mb` doesn't run it.

## 5. JSON

`mb data health --json` uses the v1 envelope from
[json-output-contract.md](../json-output-contract.md):

```json
{
  "result_envelope_version": "1.0",
  "result_schema": {"name": "mainbranch.data_health", "version": "1.0"},
  "mb_command": "mb data health",
  "ok": false,
  "result_status": "ok",
  "errors": [],
  "warnings": [],
  "actions": [],
  "safe_to_share": false,
  "evaluated_at": "2026-10-30T10:00:00Z",
  "now_overridden": false,
  "summary": {"fresh": 1, "degraded": 0, "failed": 0, "stale": 1, "not_verified": 1},
  "sources": [
    {
      "id": "example-ads",
      "state": "stale",
      "since": "2026-10-28T07:30:00Z",
      "last_success_at": "2026-10-28T06:00:00Z",
      "age_seconds": 187200,
      "reason": "no_recent_success",
      "owner": "growth",
      "record": {"kind": "local"},
      "read_command": "sqlite3 data/example-ads/daily.sqlite '.tables'"
    }
  ]
}
```

- `ok` is `true` only when the exit code is `0`.
- `result_status` is `error` only for exit `2`.
- `sources[]` keeps the v0.1 fields (`id`, `state`, `since`,
  `last_success_at`, `age_seconds`, `reason`, `owner`) and adds `record.kind`
  (`local` or `route`, never the path or route details) and `read_command`.
- `coverage` details (`seen`, `expected`, the first 20 missing ids with their
  reasons) appear only for degraded sources.
- Errors never include a filesystem path outside the repo or any route detail.

## 6. In `mb status` and fleet checkin

**`mb status`** adds one line when the repo has any `health` blocks:

```text
Data: 2 fresh, 1 stale (example-ads since 28 Oct). Run: mb data health
```

- It reads `local` records only, using the same rules. Route sources show as
  a count ("1 remote, not checked here") and are not judged, so `mb status`
  stays fast and never runs a command.
- It doesn't change the exit code of `mb status`.
- `mb status --json` adds a `data_health` key with `summary` and the ids and
  states of non-fresh local sources.

**`mb fleet checkin`** (already `safe_to_share: false`) adds a `data_health`
block per repo: the `summary` counts and, for non-fresh sources, `id`,
`state`, `since` and `reason`. No coverage ids, no read commands.

Neither surface alerts. A platform that wants alerts reads
`mb data health --json` or its own records and alerts on its side.

## 7. Alerting stays outside mb

For the record, so nobody builds it into `mb`: the alerter alerts once per
transition into degraded, failed, stale or not_verified, keyed by source id
and state, and sends one recovery line on the way back to fresh. It keeps its
own last-alerted state. Because `since` comes from the record, two readers on
two machines report the same `since` for the same record.

## 8. Fixtures and tests required

Fixtures (synthetic names only, under `mb/tests/fixtures/data_health/`):

- A repo with three sources: one with no `health` block, one `local`, one
  `route`.
- One record per state: fresh, degraded by gap, degraded by partial, degraded
  by permission, failed inside the window, stale after a stop, stale never
  succeeded.
- One record per `not_verified` reason: missing, not JSON, wrong schema name,
  wrong major version, source mismatch, missing required field, future
  timestamp, oversize.
- Spec errors: duplicate id, both `local` and `route`, `local` path escaping
  the repo, a symlink escaping the repo, `expected_coverage` as a list.

Tests:

- The state table: every rule, the rule order, and the window boundary
  (exactly at `window` is fresh, one second past is stale). All with `--now`.
- `since` for every state, including the null fallbacks.
- Exit precedence: every pair of states, plus spec error with sources present.
- JSON envelope shape, `ok` vs exit code, `safe_to_share: false`.
- `read_command` is never executed: a static test that the module never
  passes it to `subprocess`, `os.system` or a shell, and a runtime test with a
  command that would create a marker file, asserting the file never appears.
- Routes: unconfigured, untrusted config permissions, `dir` route, `argv`
  route with a fixture script (timeout, non-zero exit, oversize output), and a
  test that `argv` runs without a shell and with exactly one appended argument.
- `mb status` never runs an `argv` route.
- The reader writes nothing: run it in a read-only copy of the fixture repo.
- Output never contains a path outside the repo, route details, or
  `coverage.missing[].id` in human mode.
- `mb validate` accepts the new block and rejects each spec error.
- Package smoke: the fixture runs from the built wheel, per AGENTS.md.

## 9. Docs to change when this is built

- `docs/data-source-registry.md`: the `health` block.
- `docs/scheduled-data-sync.md`: the status record, the copyable writers, and
  replace the "planned `mb doctor` freshness check" section with
  `mb data health`.
- `docs/json-output-contract.md`: the new surface.
- `docs/source-health.md` (new): the record format as a standalone contract
  any collector can follow.

## Open questions

1. **Exit code for `not_verified`.** Interface v0.1 says `2`. This PRD says
   `3`, to match the machine doctor, and keeps `2` for usage and spec errors.
   Homelab's collector writes records, but its reader or alerter may key on
   the exit code. Needs homelab's yes.
2. **`argv` routes in v1, or `dir` only?** Security's call. `dir` alone
   covers a synced folder. `argv` covers a forced-command route without a
   sync.
3. **Does `partial` count as a success for `last_success_at`?** This PRD says
   yes. If homelab's collector doesn't, a feed that is always partial looks
   stale instead of degraded.
4. **Name.** `mb data health` now, and later fold the planned
   `mb data status` into it, or keep both? Recommend one verb, `health`, and
   drop `mb data status` from the plan.
5. **`since` for a degraded source with no `first_seen`** (a partial run or a
   permission gap). This PRD falls back to `run_at`, which moves every run.
   A record field such as `first_degraded_at` would fix it. Ask homelab
   before the record leaves version `"0"`.
6. **Clock skew of 300 seconds.** Enough for a machine without time sync?
   Flagging it costs nothing; picking it wrong makes a healthy feed
   `not_verified`.
7. **Should `mb doctor` include a data-health line?** scheduled-data-sync.md
   promised a doctor freshness check. Recommend `mb doctor` points to
   `mb data health` rather than judging sources itself.
