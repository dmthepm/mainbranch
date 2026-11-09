# The agents.json policy and `mb agent check`

`agents.json` lists the agents that run on one computer, as the user that
owns them. `mb agent check` reads it and the files it names, and says whether
the policy is safe to trust. It is read only: it launches nothing, writes
nothing and sends no signal.

## Where it lives

`~/.local/state/mainbranch/agents/agents.json`, owned by the user who runs the
agents, at most 64 KB, at most 50 rows. Run `mb agent check` as that user,
never as root. `mb agent check <name>` also requires a row with that name.

## Fields

Top level: `version` (must be `1`), `agents` (list of rows), and optional
`path` and `profiles`. Unknown fields are refused.

| Field | Meaning |
| --- | --- |
| `path` | Absolute directories agents get on `PATH`. Default: `/usr/local/bin`, `/usr/bin`, `/bin`. |
| `profiles` | Named config directories: `{"name": {"claude": "/abs/dir", "codex": "/abs/dir"}}`. `default` is reserved for the user's own `~/.claude` and `~/.codex`. |

Each row:

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Lowercase letters, digits, hyphens, unique in the file. |
| `runtime` | yes | `claude` or `codex`. |
| `cwd` | yes | Absolute path under the home folder, written as its real path. |
| `role` | yes | Role card name, same naming rule as `name`. |
| `profile` | yes | `default`, or a name from `profiles` that has this runtime. |
| `model` | yes | Model id, letters, digits, `.`, `_`, `-`. |
| `effort` | no | Claude: `low` to `max`. Codex: `minimal` to `xhigh`. |
| `options` | no | Claude: `--permission-mode` with `default`, `acceptEdits`, `plan` or `bypassPermissions`. Codex: `--sandbox` with `read-only`, `workspace-write` or `danger-full-access`. Written as one string, `"--sandbox read-only"`. |
| `start_file` | no | File inside `cwd`, relative, no `..`. Must exist. |
| `declared_work` | no | Scheduled or background work the agent is meant to do: `name`, `kind` (`cron` or `background`), optional `schedule` and `prompt_file`. |

## The card rule

A row's role card is `<cwd>/core/roles/<role>.md` when `<cwd>/core/roles`
exists, otherwise `~/.local/share/agent-role-cards/<role>.md`. A Claude row
without a valid card is a problem. A Codex row without one is only noted, and
a card that exists is still validated.

## The most permissive modes

`--permission-mode bypassPermissions` (Claude) and `--sandbox
danger-full-access` (Codex) are allowed. They remove the runtime's own
approval or sandbox limits, so for each such row the check adds a line:

```text
Policy valid.
  note: planner: --permission-mode bypassPermissions is the most permissive mode; allowed, not safe
```

The note appears whether or not the policy is valid. "Valid" is never "safe".

## What check proves, and what it does not

It proves the file is well formed, every path it names is owned by the user or
root, no directory on the way is group or world writable, no symlink hides a
path that must be plain, and each card, profile, start file and `PATH`
directory is where the policy says.

It does not prove an agent is running, that its model or options work, that
its credentials are good, that a card's instructions are wise, or that the
agent is safe. Exit 0 means the policy is valid and nothing more; exit 2 lists
what is wrong.
