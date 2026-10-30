# Agent usage

Run `mb usage` to read local snapshots of your agents' weekly usage. Main Branch
ships no collector. It reads no credentials, contacts no provider, and never
uses or buys banked resets. The owner or a separate collector writes the files.

Set `usage.dir` in `~/.config/mainbranch/config.toml`, or beneath
`$XDG_CONFIG_HOME/mainbranch/config.toml` when that variable is set:

```toml
[usage]
dir = "/absolute/path/to/snapshots"

[usage.accounts]
example-a = "Main account"
codex = "Tool account"

[usage.role_accounts]
architect = "example-a"
```

The TOML config reader requires Python 3.11 or newer. With no config file,
`--dir` also works on Python 3.10. No directory is assumed.

```bash
mb usage
mb usage --dir /absolute/path/to/snapshots --json
mb usage --dir /absolute/path/to/snapshots --now 2030-01-01T12:00:00Z --json
```

`--now` is for reproducible fixtures and marks `now_overridden: true` in JSON.

## Snapshot format

Only `claude.json` and `codex.json` are opened. Use synthetic account keys such
as `example-a`, never emails or private identifiers. Keys must match
`^[a-z0-9][a-z0-9-]{0,39}$`. All timestamps use UTC with seconds and a `Z` suffix.

Minimal `claude.json`:

```json
{
  "schema_version": 1,
  "written_at": "2030-01-01T11:55:00Z",
  "taken_at": "2030-01-01T11:50:00Z",
  "accounts": {
    "example-a": {
      "taken_at": "2030-01-01T11:50:00Z",
      "used_pct": 40,
      "window_end": "2030-01-02T12:00:00Z"
    }
  }
}
```

Minimal `codex.json`, shown with account key `codex`:

```json
{
  "schema_version": 1,
  "written_at": "2030-01-01T11:55:00Z",
  "taken_at": "2030-01-01T11:50:00Z",
  "used_pct": 30,
  "window_end": "2030-01-02T12:00:00Z"
}
```

Claude readings may add `session_pct` and `session_end`. Codex may add a positive
integer `window_minutes`. Both files may carry `source`, which is never printed.
Codex may carry `reset_credits` with `status: "read"`, `read_at`,
`available_count`, and `credits`, a list of `{expires_at, granted_at, status}`.
Credit status is `available`, `expired`, or `used`. An unread credit block uses
`status: "UNKNOWN"` and a `reason`. Optional credit `source` and `note` are not
printed. Unknown fields or malformed credit fields refuse the file. Stale
credits and counts that disagree with the list are shown as unknown.

Write to a temporary file, set `written_at` last, then rename the file into
place. Keep it owner-writable only, under 16 KiB, and a regular file rather than
a symlink. Update hand-written files when starting a batch.

## Freshness, caps, and exits

A file older than one hour or a reading older than three hours is unknown.
Missing or unsupported schema versions are refused. Future readings and file
writes more than five minutes ahead are unknown. Last numbers can be shown as
stale, but never as available usage. A past window end suppresses cap judgments
and sustainable pace. Fresh windows ending within eight days show sustainable
percentage points per hour. This is not a measured burn rate.

Role profiles in `core/team/*.md` can add structured weekly caps:

```yaml
budget_cap: "stop at 85% of the weekly window"
budget:
  stop_at_pct: 85
  near_within: 5
```

Map the role's filename stem to an account in local `usage.role_accounts`.
Unmapped roles and text-only caps are not verified. `near_within` defaults to
five points. Caps report `under`, `near`, or `at_cap`; they do not stop agents.

Exit codes, in precedence order, are 2 for configuration or flag errors, 1 for
a role at cap or a fresh weekly window at 100%, 3 for unknown facts, and 0 for
healthy facts. A missing file is noted and skipped; both missing means unknown.

Banked resets are information only. A fresh account at 100%, with a future reset
time and a fresh unexpired banked credit, produces a question for the owner.
The question contains no command. Use the runtime's own screen to act.

## In the daily briefing

When `usage.dir` is set, `mb status` adds one usage line and names roles near or
at cap. It uses the same freshness rules. This does not change the status exit
code. With no directory configured the text briefing omits usage and JSON
reports `usage: {"configured": false}`. Fleet checkin does not include usage.
