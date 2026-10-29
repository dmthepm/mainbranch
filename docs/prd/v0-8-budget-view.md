---
title: "PRD: budget view (agent usage in mb, read-only)"
status: draft
date: 2026-10-29
issue: "none yet (operating-team PRD #1258, batch B)"
related: "#1258 operating team (duty map, role profiles, section 6 sketch), #1259 source health (reader pattern, exit precedence), #1247 machine doctor (not_verified rule), docs/json-output-contract.md"
---

# PRD: budget view

## One-screen summary

- **Problem.** Agents run on accounts with weekly and session usage windows.
  When a window runs out, work stops mid-batch. Today the owner or a platform
  reads usage by hand, and a role's budget cap is a sentence in its charter
  that nothing compares with live use.
- **Split of work.** Something outside `mb` writes a small usage snapshot. `mb`
  reads it, judges how old it is, and shows used %, window end, pace and which
  roles are near their cap. `mb` never reads provider accounts, never holds
  credentials, and never redeems anything.
- **The reader.** `mb usage`. Read-only, stateless, no network, no sudo, no
  writes. It reads one directory named in local config.
- **Unknown is never "available".** A missing, stale, malformed or
  unknown-version snapshot is `not_verified`, shown as unknown.
- **Never redeem.** No code path calls a redeem or consume endpoint. A static
  test fails the build if one appears. Banked resets are shown for
  information only.
- **The one suggestion.** Only when a weekly window reads 100% used and a
  banked reset is fresh, `mb` asks the owner a question. It never acts on the
  answer.
- **In `mb status`.** One line per account, plus a "near cap" line when a role
  is close to its cap. It doesn't change the status exit code.
- **Standalone businesses.** The snapshot format is documented. The owner's
  own script, or the owner by hand, writes it. `mb` ships no collector.
- **Status today:** designed, not built. Nothing in this PRD is shipped.

## Goals

1. Show, in business language, how much agent usage is left and when it comes
   back, without starting an agent or touching a provider.
2. Compare each standing role's budget cap (#1258) with live use, so the owner
   sees which roles should pause before a window runs out.
3. Judge snapshot age the same way the platform's own reader does, so a
   platform and `mb` never disagree about whether a number is current.
4. Make redeeming banked resets impossible from `mb`, and test that.

## Non-goals

- Collecting usage. No provider API calls, no reading runtime session files,
  no cookies, no credentials.
- Redeeming, consuming, buying or scheduling resets.
- Stopping or pausing agents. `mb` reports; the orchestrator or the owner acts.
- Cost in money. This is usage-window percentage only.
- History or trends. The reader keeps no state between runs.
- Alerting. Same rule as source health: the platform or the owner decides who
  to tell.

## Who carries this duty

In the operating-team duty map (#1258), "usage and caps" is a duty with a
carrier:

| Shape | Who writes snapshots | Who reads | Who acts on a cap |
| --- | --- | --- | --- |
| With a platform | The platform's usage steward | `mb usage` and the platform's own reader | The business orchestrator |
| Standalone | The owner's script, or the owner by hand | `mb usage` | The business agent, at its next batch start |

`mb team check` keeps treating a `platform: <name>` carrier as
`not_verified` (`outside_repo`). `mb usage` is how a business sees the result
of that duty from its own repo.

## 1. Configuration

All in local, per-machine config. Nothing here is committed to a business
repo, because the directory and account labels are machine facts.

```toml
[usage]
dir = "<absolute path to the snapshot directory>"   # required; no default

[usage.accounts]           # optional display labels; keys are snapshot keys
example-a = "Main account"
example-b = "Backup account"

[usage.role_accounts]      # optional: which account each role runs on
architect = "example-a"
security  = "example-b"
```

Rules:

- **No default directory.** With `usage.dir` unset, every account is
  `not_verified` (`usage_dir_unset`) and the human output says how to set it.
  `mb` never guesses a host path.
- **`team.usage_dir` from #1258's sketch becomes `usage.dir`.** Usage is an
  account fact, not a team fact, and a business with no `core/team/` still
  wants the view. #1258 needs a one-line edit (open question 6).
- **Account keys** in snapshots must match `^[a-z0-9][a-z0-9-]{0,39}$`. A key
  that doesn't (an email address, say) refuses the file (`bad_account_key`),
  so a private identifier can't reach output by accident.
- **Role mapping is local** because which account a role runs on can change
  per machine. A role with no mapping shows its cap with "account unknown".

## 2. The snapshot files

`mb` reads the two files the platform already writes, unchanged, at
`schema_version` 1. All times are UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`).

### Single-account file (`codex.json`)

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Must be `1`. |
| `written_at` | yes | When the file was written. |
| `taken_at` | yes | When the reading was taken. |
| `used_pct` | yes | 0-100, weekly window used. |
| `window_end` | no | When the weekly window resets. |
| `window_minutes` | no | Window length; positive integer. |
| `source` | no | Short printable text naming the writer. Not shown in shareable output. |
| `reset_credits` | no | Banked resets, information only (below). |

### Multi-account file (`claude.json`)

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Must be `1`. |
| `written_at`, `taken_at` | yes | As above. |
| `source` | no | As above. |
| `accounts` | yes | Map of account key to a reading. |
| `accounts.<key>.taken_at` | yes | That account's own reading time. |
| `accounts.<key>.used_pct` | yes | Weekly window used. |
| `accounts.<key>.session_pct` | no | Short session window used. |
| `accounts.<key>.window_end` | no | Weekly window end. |
| `accounts.<key>.session_end` | no | Session window end. |

### `reset_credits` block

`status` is `read` (with `read_at`, `available_count`, `credits[]` of
`{expires_at, granted_at, status}` where status is `available`, `expired` or
`used`) or `UNKNOWN` (with a `reason` code). Optional `source` and `note`.

### Validation (refuse, don't guess)

`mb` refuses a file, and shows its accounts as `not_verified`, when:

- `schema_version` is anything but `1` (`schema_unknown`). A missing
  `schema_version` is also refused in `mb`; the platform reader tolerates it
  for legacy files, `mb` has no legacy files to support.
- any field is outside the documented set (`unknown_field`);
- a required field is missing, a time isn't a UTC stamp, a percentage isn't a
  finite number in 0-100, or a count is out of bounds (`malformed`);
- the path is a symlink, not a regular file, group- or world-writable, or over
  16 KiB (`unsafe_file`).

These match the platform reader's rules, so a file one accepts the other
accepts too (except the missing-version case above).

## 3. Freshness rules

Same numbers as the platform reader. `SKEW` is 300 seconds.

| Rule | Result |
| --- | --- |
| File `written_at` older than 1 h | Every reading in it is `not_verified` (`snapshot_stale`). |
| File `written_at` more than `SKEW` in the future | `not_verified` (`clock_skew`). |
| A reading's `taken_at` older than 3 h | That account is `not_verified` (`reading_stale`). A tick can re-publish an old reading unchanged, so a fresh file isn't enough. |
| A reading's `taken_at` in the future, or after the file's `written_at` + `SKEW` | `not_verified` (`clock_skew`). |
| `window_end` in the past | Shown with "this reading predates the reset, so usage is likely lower now"; no pace, and no cap judgment for that account. |
| Credits: file stale, `read_at` older than 3 h or in the future, or count and list disagree | Credits shown as unknown. |

A `not_verified` account still shows its last numbers, labelled stale, never
as current. Unknown is never "exhausted" and never "available".

## 4. What is shown per account

- **Used %** of the weekly window, and **session %** when present.
- **Window end** and time left; **session end** only when it falls within the
  next 6 hours (a session end further out is noise).
- **Reading age.**
- **Pace line:** the sustainable rate to the window end,
  `(100 - used_pct) / hours_left`, as "%/h". Shown only when the file and
  reading are fresh and the window end is in the future and no more than 8
  days away. Stale, past or unknown values never produce a rate.
- **Banked resets:** count and expiry dates, labelled "information only".

There is no "you're burning too fast" judgment in v1: the reader is stateless,
so it has one reading and no rate of its own to compare (open question 3).

## 5. Roles near their cap

#1258 made `budget_cap` text. This PRD adds one optional structured field to
the role profile, next to the text:

```yaml
budget_cap: "stop at 85% of the weekly window"   # text, unchanged, still required
budget:                                          # optional, new
  stop_at_pct: 85        # integer 1-100, weekly window
  near_within: 5         # optional, default 5 points
```

- **States per role:** `under` (used below `stop_at_pct - near_within`),
  `near`, `at_cap` (used at or above `stop_at_pct`), or `not_verified` (no
  mapped account, the account is `not_verified`, or its window has passed).
- A role with text only shows its text cap and `not_verified`
  (`cap_not_structured`). `mb team check` adds a warning, not a failure, for
  a standing role without `budget.stop_at_pct` once this ships.
- `mb` doesn't stop the role. It reports; the orchestrator's runbook decides.
- The role list comes from `core/team/*.md` when the repo has one. Outside a
  business repo, or with no profiles, the roles section is omitted.

## 6. The reader: `mb usage`

```text
mb usage [--json] [--now <UTC stamp>]
```

- No subcommands in v1. `--now` is for tests and fixtures; it sets
  `now_overridden: true` in JSON.
- Reads `usage.dir/claude.json` and `usage.dir/codex.json` if present. A file
  that is absent is skipped and noted; both absent is `not_verified`
  (`no_snapshot`).
- Opens nothing else in that directory and lists nothing.
- Read-only: no writes, no cache, no network, no subprocess.

### Exit codes

Same precedence as the machine doctor and source health: `2` > `1` > `3` >
`0`.

| Exit | Meaning |
| --- | --- |
| `0` | Every shown account is fresh and no role is `at_cap`. |
| `1` | A role is `at_cap`, or a fresh reading shows a weekly window at 100%. |
| `2` | Usage or config error: bad flags, bad `--now`, invalid `budget` block, a `role_accounts` entry naming a key in no snapshot. |
| `3` | Nothing is at cap, but something is `not_verified` (no dir, stale, refused file). |

`near` doesn't change the exit code; it's a heads-up, not a stop.

### Human output

```text
Usage  2 accounts fresh, 1 stale
  Main account     91% used (session 3%)  window ends 30 Oct 02:00Z (in 7 h 49 min)
                   pace: 1.1%/h sustainable (9% left over 7.8 h)  reading 5 min old
  Backup account   STALE, unknown: last reading 4 h old (was 72%)
  Tool account     43% used  window ends 4 Nov 07:06Z (in 5 d 12 h)
                   pace: 0.4%/h sustainable  reading 17 min old
                   banked resets: 2 (expire 29 Oct, 6 Nov), information only
Roles
  at cap   architect   cap 85%, Main account at 91%
  near     security    cap 45%, Tool account at 43%
```

### The redeem question

Shown only when all of these hold for one account: a fresh reading, a future
window end, `used_pct` exactly 100, and a fresh credits block with at least one
`available` credit not yet expired.

```text
Tool account is at 100% for this week. You have 1 banked reset.
Do you want to use one now? mb won't do it; use your runtime's own screen.
```

In JSON this is an `actions[]` entry with `kind: "owner_question"` and no
command. It's never shown below 100%, never for an expiring credit alone, and
never as a command line.

## 7. JSON

`mb usage --json` uses the v1 envelope from
[json-output-contract.md](../json-output-contract.md):

```json
{
  "result_envelope_version": "1.0",
  "result_schema": {"name": "mainbranch.usage", "version": "1.0"},
  "mb_command": "mb usage",
  "ok": false,
  "result_status": "ok",
  "errors": [],
  "warnings": [],
  "actions": [],
  "safe_to_share": false,
  "evaluated_at": "2026-10-30T10:00:00Z",
  "now_overridden": false,
  "summary": {"fresh": 2, "not_verified": 1, "roles_at_cap": 1, "roles_near": 0},
  "accounts": [
    {
      "key": "example-a",
      "label": "Main account",
      "state": "fresh",
      "used_pct": 91,
      "session_pct": 3,
      "window_end": "2026-10-30T02:00:00Z",
      "session_end": "2026-10-29T21:20:00Z",
      "reading_age_seconds": 300,
      "sustainable_pct_per_hour": 1.1,
      "reset_credits": null,
      "reason": null
    }
  ],
  "roles": [
    {"id": "architect", "account": "example-a", "stop_at_pct": 85,
     "state": "at_cap", "reason": null}
  ]
}
```

- `ok` is `true` only when the exit code is `0`.
- `reset_credits`, when present: `{"state": "fresh" | "unknown",
  "available": <n>, "expires": [<stamps>], "information_only": true}`.
- No file paths, no `source` strings, no directory in output. Errors name the
  file by its base name only (`codex.json`).
- `safe_to_share: false`: account labels and role names are business facts.

## 8. In `mb status`, `/mb-start` and fleet checkin

**`mb status`** adds a usage block when `usage.dir` is set:

```text
Usage: Main 91% (resets in 7 h 49 min), Tool 43%, Backup unknown (stale).
Near cap: architect (85%). Run: mb usage
```

- Same rules and same reader code; no second implementation.
- It doesn't change `mb status`'s exit code.
- With `usage.dir` unset it prints nothing (the view is opt-in), and
  `mb status --json` has `"usage": {"configured": false}`.
- `mb status --json` adds `usage` with `summary`, per-account `key`, `state`,
  `used_pct`, `window_end`, and roles that are `near` or `at_cap`.

**`/mb-start`** reads the `usage` block from `mb status --json`. If a role it
is about to start is `at_cap`, it says so before starting and asks the owner.
It doesn't refuse; the owner decides.

**`mb fleet checkin`** doesn't add usage in v1. Usage is per account, and
several repos share an account, so per-repo rows would repeat it (open
question 5).

## 9. Never redeem: how it is enforced

1. **No network or process in the reader.** The usage module imports nothing
   from `urllib`, `http`, `socket`, `requests`, `httpx`, `subprocess` or
   `os.system`/`os.exec*`. A test parses the module's AST and fails on any.
2. **Static scan of the whole package.** A test walks every `.py` file under
   `mb/mb/`, parses it, and fails when a call, attribute, function name or
   string literal matches `redeem` or `consume` (case-insensitive), or a URL
   literal contains `reset` together with `credit`. The only allowlisted
   strings are the display text in the usage module ("information only",
   the owner question), listed by exact value in the test.
3. **No command in the suggestion.** A test checks the owner question's
   `actions[]` entry has no `command` field and that the human text holds no
   shell-like line.
4. **Skills too.** The same scan runs over bundled skills under
   `.claude/skills/` for instructions that tell an agent to redeem (a
   `redeem` word outside a "never" sentence fails, with an allowlist).

## 10. Standalone: no platform

A business with no usage steward can still use the view.

- **The owner writes the file.** The documented format above is the whole
  contract. The owner copies the numbers from their runtime's own usage
  screen into a small JSON file, by hand or with their own script, and points
  `usage.dir` at its folder. `mb` doesn't care who wrote it, only that it is
  valid and fresh.
- **Freshness still applies.** A hand-written file older than 1 h shows as
  stale. That's correct: an old number is unknown. The view tells a
  standalone owner "update the file when you start a batch" rather than
  pretending the number is live.
- **Docs ship a minimal example** for each file (one account, no credits) and
  a checklist for owner scripts: write to a temporary file and rename, set
  `written_at` last, never include an email or account id as a key, keep the
  file owner-writable only.
- **`mb` never reads provider accounts, cookies, tokens or runtime session
  files**, and ships no collector, not even an optional one. A writer for
  standalone owners is a follow-up and needs its own security read.
- **Without any file**, the view says "usage not configured" and points the
  agent at its runtime's own usage screen, as #1258 sketched.

## 11. Fixtures and tests required

Fixtures under `tests/fixtures/usage/`, all synthetic, with a fixed `--now`:

- `fresh/`: both files valid and fresh; three accounts, one with credits.
- `stale-file/`: `written_at` 2 h old.
- `stale-reading/`: fresh file, one account with `taken_at` 4 h old.
- `future/`: a reading stamped 10 min ahead.
- `past-window/`: `window_end` passed; no pace, no cap judgment.
- `schema-2/`, `no-schema/`, `extra-field/`, `bad-pct/`, `email-key/`,
  `symlink/`, `world-writable/`, `oversize/`: each refused with its reason.
- `credits-mismatch/`: count disagrees with the list; credits unknown.
- `full-week/`: one account at 100% with a fresh credit (question shown) and
  a copy without credits (no question) and a copy at 99% (no question).
- `roles/`: a fixture business repo with `core/team/` profiles: one under,
  one near, one at cap, one text-only cap, one with no mapped account.

Tests:

- Exit code for each fixture, including precedence (at cap plus stale = `1`).
- Pace math and every case where pace must be absent.
- JSON matches the envelope; no path or `source` string appears anywhere in
  output.
- `mb status` exit code unchanged across all fixtures; nothing printed when
  unset.
- A read-only run: the directory and repo are made read-only and the command
  still works and writes nothing.
- The never-redeem tests in section 9.
- Parity: for each fixture, the fresh/stale/refused verdict matches the
  platform reader's documented rules (written as a table in the test, not by
  calling any platform tool).

## 12. Docs to change when this is built

- New `docs/usage.md`: the reader, the file formats, the standalone recipe.
- `docs/json-output-contract.md`: add `mainbranch.usage`.
- #1258's PRD section 6: point here; rename `team.usage_dir` to `usage.dir`;
  note the optional `budget` block.
- `/mb-start` skill: the at-cap check before starting a role.

## Open questions

1. **Missing `schema_version`.** `mb` refuses it; the platform reader
   tolerates it. Keep the stricter rule, or match exactly?
2. **Structured cap.** Is `budget.stop_at_pct` (weekly only) enough, or do
   roles also need a session cap?
3. **Burn-rate warning.** A stateless reader can't see its own rate. Should
   the snapshot carry a previous reading (`prev_used_pct`, `prev_taken_at`) so
   `mb` can compare actual pace with sustainable pace? That is a schema v2
   change on the writer side.
4. **Exit `1` at 100% with no role mapped.** Is a full weekly window a failure
   for the business even when no role is tied to it?
5. **Fleet checkin.** Leave usage out (current choice), or add one
   account-level block per checkin?
6. **Config key.** `usage.dir` (this PRD) vs `team.usage_dir` (#1258's
   sketch). This PRD's choice needs #1258 edited before either merges.
7. **File names.** v1 reads `claude.json` and `codex.json` by name. A
   business on another runtime would need a generic file name
   (`usage.json`, multi-account shape). Add it in v1, or wait for a real
   user?
