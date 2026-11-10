# The agents.json policy and `mb agent check`

`agents.json` lists the agents that run on one computer, as the user that
owns them. `mb agent check` reads it and the files it names, and says whether
the policy is well formed and its paths are trustworthy. A valid policy is not a
safe agent (see the permissive modes below). It is read only: it launches nothing, writes
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
| `options` | no | Claude: `--permission-mode` with `default`, `acceptEdits`, `plan` or `bypassPermissions`. Codex: `--sandbox` with `read-only`, `workspace-write` or `danger-full-access`. A list of strings, one option per entry: `["--sandbox read-only"]`. |
| `start_file` | no | File inside `cwd`, relative, no `..`. Must exist. |
| `declared_work` | no | Scheduled or background work the agent is meant to do: `name`, `kind` (`cron` or `background`), optional `schedule` and `prompt_file`. A list of such objects: `[{"name": "digest", "kind": "cron", "schedule": "0 7 * * *", "prompt_file": "digest.md"}]`. |

## The card rule

A row's role card is `<cwd>/core/roles/<role>.md` when `<cwd>/core/roles`
exists, otherwise `~/.local/share/agent-role-cards/<role>.md`. A Claude row
without a valid card is a problem. A Codex row without one is only noted
(`card: unverified(no-adapter)`), and a card that exists is still validated.

## The most permissive modes

`--permission-mode bypassPermissions` (Claude) and `--sandbox
danger-full-access` (Codex) are allowed. They remove the runtime's own
approval or sandbox limits, so for each such row the check adds a line:

```text
Policy valid.
  note: planner: --permission-mode bypassPermissions is the most permissive mode; allowed, not safe
```

The note appears whether or not the policy is valid, and also for a row that has
an unrelated error, as long as its `options` list names the mode. "Valid" is never
"safe".

The report also prints its other notes, such as a Codex card that is unverified or
a default profile directory that is absent. A note does not fail the check.

## What check proves, and what it does not

It proves the file is well formed and every path it checks is owned by the user or
root, with no group or world writable directory on the way and no symlink hiding a
path that must be plain. The paths it checks are the cards and profiles that are
present or required, each start file and each `PATH` directory. It does not
require every card or profile to exist: a Codex row may have no card, and the
default `~/.claude` and `~/.codex` profile directories may be absent; both are
noted, not failed.

A `PATH` folder that does not exist is skipped, not failed: it appears only in the
report's `skipped` list, which the command does not print. So exit 0
does not prove every listed `PATH` folder exists, only that each one that does exist
passed.

It does not prove an agent is running, that its model or options work, that
its credentials are good, that a card's instructions are wise, or that the
agent is safe. Exit 0 means the policy is valid and nothing more; exit 2 lists
what is wrong.

## Starting a Claude agent: `mb agent up <name>`

`mb agent up planner` starts the Claude agent named in `agents.json` and waits for it.
It is a small holder: it takes the agent's lock, starts one child, records that child
and the launch plan, then lets the child become Claude. When Claude ends, `up` exits
with Claude's own exit status. It never sends a signal, never types into the session,
and never reads or writes the terminal while Claude runs. Ctrl-C reaches Claude only.
A Codex row is refused (exit 2, `unsupported-runtime`): Codex launch is not built yet.

What it claims: the **launch configuration was verified at start**. The program, folder,
role card, profile, session id and the environment names and mb-set values were the ones in
the record. It does not check that the agent behaves like its role, and it does not
re-check a running agent (that is `mb agent check`, a later step).

Options: `--dry-run` prints the command and the plan and writes nothing; `--new` starts a
new session; `--session <id>` resumes a session you name, if its transcript is found.
A Claude row with no stored session and neither flag is refused (exit 5, `no-session`), so a
missed migration never starts a silent fresh session: the first launch needs `--new`.

### What the child gets

- **Command:** `claude --model <model> [--effort <e>] [options] --append-system-prompt-file
  <card>` plus `--session-id <id>` (new) or `--resume <id>`. With a new session and a
  `start_file`, the prompt is `Read <start_file> first.`
- **Environment, built from nothing.** Set by mb: `HOME USER LOGNAME SHELL`, `PATH` (only the
  `path` folders that exist and passed), `MB_ROLE`, and `CLAUDE_CONFIG_DIR` for a named
  profile. Passed through if present and valid: `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`,
  `SSH_AUTH_SOCK`, `HEAVY_LOCK`, `LANG LC_ALL LC_CTYPE TZ TERM COLORTERM TERM_PROGRAM
  TERM_PROGRAM_VERSION` and the seven `HERDR_*` names. An invalid one refuses `bad-env:<NAME>`
  (exit 2) and never shows the value. Everything else is dropped, including `ANTHROPIC_*`,
  `OPENAI_*`, `CLAUDE_*`, `CODEX_*` and `MISE_*`. Dropping env-only auth can cause a login
  prompt or a failure, or use the account the profile holds.
- **Records hold no passed value.** The attempt keeps mb-set values and the *names* of the
  passed variables. Dry-run says `value not shown`. Anything you write into `agents.json`
  itself (a path, a model string) is copied into the record.
- The program must be an ELF file reached through checked folders. Scripts (including npm's
  node wrappers), shell wrappers and mise shims are refused (`unsupported-runtime`).

One line each where you will meet them:

- `start_file` is sent as the prompt for a new session and for a `new-retry`, never on `resume`.
- The store check covers what mb creates (`state.json`, `attempts/`, `locks/`, `.store.lock`), not
  `agents.json`, which slice 1 already checks.
- If the default profile folder did not exist at launch, a later search counts it as empty only if
  it is still absent; a profile that went missing or changed is `search-incomplete`.
- A transcript found only under a different profile than the row's current one is `wrong-profile`,
  for any session, including when the row's profile was changed after launch.
- A transcript counts as found when it is a regular file whose first line is a JSON object; the real
  Claude format is not yet confirmed (a file that fails this is `search-incomplete`).
- A runtime process that has exited but is not yet reaped counts as dead.

### The store

`~/.local/state/mainbranch/agents/` holds `state.json`, `attempts/<id>.json` (written once, never
edited), `locks/<name>.lock` and `.store.lock`. Folders are created 0700 and files 0600; every
`up` refuses `unsafe-store` (exit 2, no chmod) if one is owned by someone else, has group or
other bits, or carries an ACL (lock files included), or if mb cannot check for an ACL. Every agent that runs as this user can read it, and so can root
and anything that copies it. Session ids and paths are private identifiers, not credentials.
Attempts are never pruned by mb.

### Exit codes of `up`

| Exit | Meaning |
| --- | --- |
| runtime's own status | A real run returns Claude's status, which can equal a code below. |
| 0 | `--dry-run` printed. |
| 2 | Invalid policy, `unsafe-store`, `unsafe-path`, `bad-env:<NAME>`, `unsupported-runtime`, bad arguments, root. |
| 4 | Refused, state unknown: `holder-lost`, `lock-owner-unknown`, `lock-orphan`, `proc-denied`, `inconsistent`, `session-seen`, `no-session-evidence`, `search-incomplete`, `wrong-profile`, `corrupt-state`, `no-proc`, `wait-lost`, `store-lock-timeout` (another `up` held the store lock for 10 s). |
| 5 | Refused: `no-session` (no stored session, no `--new`/`--session`), `live` (a running agent), `alias` (the id belongs to another row), `record-failed` (nothing was started), `go-failed`. |

Unknown is never treated as dead. `up` starts a replacement only when the earlier process is
shown dead and no same-user process names its session id. Known limit: a runtime that starts a
detached session and exits its own process looks ended; the 60-second check on command lines and
transcripts is a tripwire, not proof.

### Recovery, in one paragraph

After an interruption `up` reads `state.json`, checks that it agrees with its last attempt
(otherwise `corrupt-state`), and decides from where the session id came. A transcript found
under the row's profile means `resume`. An id mb chose itself with no transcript, after a complete
search of every profile that could hold one (at most 10,000 entries each), is run again as
`new-retry` with the same id. An id you gave with `--session` and no transcript is refused. An
incomplete search is `search-incomplete`, never "no transcript", including before `--new`
and before a resume. A transcript that is not a regular file (a pipe, device or link) is never
opened and counts as an unsupported format.

## The lifetime smoke: `mb agent check <name> --smoke-marker <marker>`

`up` can only prove that the process it started is alive or dead. That is the session's
lifetime only if the runtime keeps its session in that process. An ELF that forks a child, waits,
and lets the child do the work looks the same to a plain check. The smoke observes the session
doing work and judges it. It is the only thing `--smoke-marker` does, and it is evidence for the
installed version, not a proof for every session or mode. mb does not run it at launch.

The verdict reads /proc and passes only if all of these hold:

- the marker pid's parent chain reaches the recorded runtime pid within 8 links;
- every process strictly between them has an exe on the reviewed helper list, and none is the
  runtime's own program (a forked child that never exec'd shows the runtime's exe);
- the recorded pid's exe is still the recorded program, its environment has the attempt's names
  and mb-set values, and its folder is the attempt's;
- no other process of this user carries the session id on its command line.

Exits: 0 pass; 1 fail, naming `not-session-process` (the chain) or `mismatch` (`environ`,
`cwd`); 3 the runtime has ended; 4 unknown (`no-marker`, `no-session-evidence`, `proc-denied`,
`inconsistent`, `exe-changed`, `session-seen`); 2 invalid policy or no agent name. Passed values
are not stored and not compared, and no value is printed.

The reviewed helper list is built in and short: `/bin/sh`, `/bin/dash`, `/bin/bash`,
`/bin/zsh` and `/usr/bin/bwrap`, compared by real path. The design keeps the real list per runtime
version with the machine owner and says the first smoke produces it, so treat this one as a
starting point. A helper that is not on it fails the smoke until it is reviewed and added.

`mb agent check <name>` without the flag is still the policy check. The live check of a running
agent is not built.

### Running the real smoke (by hand, not in tests)

Do this on a disposable fixture row, never on a working agent, after each pinned runtime update.

1. Add a fixture row to `agents.json` with its own role card and a `start_file` containing:
   `Run this one foreground command and wait for it: sh -c 'echo $$ > /path/to/marker; sleep 120'`.
   (An invented scratch path; the marker file is the only thing the smoke reads from the session.)
2. In a scratch pane run `mb agent up <fixture> --new`. Wait until the marker file exists.
3. From another pane, while the command sleeps, run
   `mb agent check <fixture> --smoke-marker /path/to/marker`. Record the exit and output.
4. End the session from the pane, then confirm the runtime pid is gone and the transcript for the
   session id stops growing.
5. A pass for this exact version goes in the machine owner's record. A fail removes the version from
   verified support until fixed. Add any helper the verdict names only after reading what it is.

### Confirming the Claude flags on the installed version (by hand)

`up` builds `--session-id`, `--resume`, `--append-system-prompt-file` and `--effort`. These are
not yet confirmed against the installed Claude. Run `claude --help` and check that all four are
listed and what they take. Then do one real run on the fixture row: start it with `--new` and a
short `effort`, check the transcript is named with the id `up` recorded, end it, run
`mb agent up <fixture>` again and check it resumes the same id, and look in the transcript or the
session for the role card text. Record the version and what you saw. Until this is done the flags
are unconfirmed.

Not built yet: the live `check` that compares a running agent with its record (`--wait`,
`--json`, doctor), and Codex.
