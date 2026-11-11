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
exists, otherwise `~/.local/share/agent-role-cards/<role>.md`. Both runtimes
require a valid card. Claude receives its path with `--append-system-prompt-file`;
Codex keeps its native instructions. `up` sets `MB_ROLE` for both runtimes;
Codex receives repo card fields through the owner-installed
[SessionStart hook](role-cards.md#codex). Install and trust that hook in the
selected Codex profile. The hook reads repo cards, not the fallback card folder.
A valid fallback card alone does not make hook delivery available.

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

The report also prints its other notes, such as an absent default profile
directory. A note does not fail the check.

## What check proves, and what it does not

It proves the file is well formed and every path it checks is owned by the user or
root, with no group or world writable directory on the way and no symlink hiding a
path that must be plain. The paths it checks are the cards and profiles that are
present or required, each start file and each `PATH` directory. It does not
require the default `~/.claude` and `~/.codex` profile directories to exist;
an absent default profile is noted. Cards and named profiles are required.

A `PATH` folder that does not exist is skipped, not failed: it appears only in the
report's `skipped` list, which the command does not print. So exit 0
does not prove every listed `PATH` folder exists, only that each one that does exist
passed.

It does not prove an agent is running, that its model or options work, that
its credentials are good, that a card's instructions are wise, or that the
agent is safe. Exit 0 means the policy is valid and nothing more; exit 2 lists
what is wrong.

## Starting an agent: `mb agent up <name>`

`mb agent up planner` starts the agent named in `agents.json` and waits for it.
It is a small holder: it takes the agent's lock, starts one child, records that child
and the launch plan, then lets the child become the runtime. When it ends, `up` exits
with the runtime's exit status. It never sends a signal, never types into the session,
and never reads or writes the terminal while the runtime runs. Ctrl-C reaches the runtime only.

What it claims: the **launch configuration was verified at start**. The program, folder,
role card, profile, session id when known and the environment names and mb-set values were the ones in
the record. It does not check that the agent behaves like its role, and it does not
re-check a running agent (that is `mb agent check <name>`, below).

Options: `--dry-run` prints the command and the plan and writes nothing; `--new` starts a
new session; `--session <id>` resumes a session you name, if its transcript is found.
A row with no stored session and neither flag is refused (exit 5, `no-session`), so a
missed migration never starts a silent fresh session: the first launch needs `--new`.

Where to start it: from the user's own login session or the user's service manager, so the
agent inherits the same confinement as everything else that user runs. An administrator
starting it for that user with `sudo -u` or `runuser` is not the same session and may skip
that confinement; do not start agents that way.

In practice:

- The first launch in a new folder shows Claude's folder-trust question. `up` never types, so
  answer it once in the pane.
- After a session ends, wait a minute before `up` resumes it. Claude can still write the
  transcript shortly after it exits, and `up` refuses (`session-seen`) while the transcript
  changed in the last 60 seconds.
- Any process of the same user whose command line holds the session id, even a `grep` for it,
  also makes `up` refuse `session-seen`. Close such commands before resuming.

### What a Claude child gets

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
- A transcript counts as found when it is a regular file whose first line is a JSON object (a file
  that fails this is `search-incomplete`). Claude Code 2.1.309 writes
  `<profile>/projects/<folder>/<session id>.jsonl` in this form.
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
| runtime's own status | A real run returns the runtime's status, which can equal a code below. |
| 0 | `--dry-run` printed. |
| 2 | Invalid policy, `unsafe-store`, `unsafe-path`, `bad-env:<NAME>`, `unsupported-runtime`, bad arguments, root. |
| 4 | Refused, state unknown: `holder-lost`, `lock-owner-unknown`, `lock-orphan`, `proc-denied`, `inconsistent`, `session-seen`, `no-session-evidence`, `search-incomplete`, `wrong-profile`, `wrong-cwd`, `corrupt-state`, `no-proc`, `wait-lost`, `store-lock-timeout` (another `up` held the store lock for 10 s). |
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

## Codex launch and session evidence

Codex launches require a native ELF entrypoint in the policy PATH. npm wrappers,
shell wrappers and mise shims still refuse `unsupported-runtime`. New and resumed
launches force `--no-daemon`; a shared background server does not satisfy the
assumption that the session runs in the process mb started.

New command: `codex --no-daemon -m <model> -c model_reasoning_effort=<effort>
[options] [prompt]`.
Resume command: `codex resume <id>` followed by those same options. The effort
override is omitted when the row has none. No card path or contents enter Codex
argv. The launcher does not set `model_instructions_file`: replacing base
instructions drops Codex's own safety guidance. Native instructions stay, and
`MB_ROLE` selects the card through the owner-installed SessionStart hook linked
above. `check` compares the selected card path with policy, as for Claude; it
does not establish that the hook ran or the card text loaded. `CODEX_HOME` is
set only for a named profile; the default uses `~/.codex` under mb's selected HOME.

A new Codex attempt records a null session id with `spawned` provenance. Discovery
never changes that attempt or the saved state. A subsequent `up` refuses with
exit 5 `no-session` until you give `--session <id>` or `--new`. `check` and the
`no-session` message list matching candidates as `discovered (not adopted)`.
With no id, a live check returns 4 because session evidence is unverified.
Zero, one or several candidates never authorize an automatic resume.

Candidates come only from `<recorded profile>/sessions/**`. Their first line
must be `session_meta`, with equal UUID fields `payload.id` and
`payload.session_id`, the recorded working folder in `payload.cwd`, and a
`payload.timestamp` at or after the attempt's launch time. Another profile,
another folder or older metadata cannot supply a discovery hint. The walk reads
at most 10,000 entries per profile; exceeding that limit or conflicting id fields
returns 4 `inconsistent`. Unsupported metadata, links and special rollout files
are unknown, never accepted. Formats without both equal id fields are not supported.

`--session <id>` validates the rollout under the selected profile and working
folder before recording `owner-confirmed` provenance. Both explicit and saved
resumes refuse 4 `wrong-cwd` for a rollout from another working folder, without
starting a process or changing saved state. An absent rollout refuses with exit 2; one found
only under another policy or historical profile refuses 4 `wrong-profile`.
The source uses the thread id, `payload.id`, as the resume target. Requiring it
to equal `session_id` deliberately excludes child threads with a different root id.
A later resume without `--session` uses that saved id. Missing evidence for a
saved id never starts a new session under that id.

For a recorded id, a live check binds metadata to that id and working folder,
then requires a metadata or transcript-tail timestamp after launch. File
time alone never satisfies live evidence. Evidence is reopened component by
component without following links, with scanned directory and file identities
checked before and after the bounded read. Replacing a directory or rollout
returns 4 `transcript-changed`. For a null id, the transcript tripwire
uses discovered candidates written within the last 60 seconds; it does not scan
command lines for a guessed id. A dead runtime with no recent evidence can still
report ended under the stated lifetime assumption.

Syntax was inspected in Codex 0.164.0 help and its pinned source:
[config loading](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core/src/config/mod.rs),
[config schema](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core/config.schema.json),
[session metadata](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/protocol/src/protocol.rs),
and [resume target](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/tui/src/session_resume.rs).
Fixture tests cover the launcher and smoke verdict. Actual card loading, effective
effort, new/resumed session behavior and lifetime on this version still need the
real disposable-row smoke below. No verified Codex lifetime claim is made here.

## The lifetime smoke: `mb agent check <name> --smoke-marker <marker>`

`up` can only prove that the process it started is alive or dead. That is the session's
lifetime only if the runtime keeps its session in that process. An ELF that forks a child, waits,
and lets the child do the work looks the same to a plain check. The smoke observes the session
doing work and judges it. It is the only thing `--smoke-marker` does, and it is evidence for the
installed version, not a proof for every session or mode. mb does not run it at launch.

The verdict accepts Claude and Codex rows, including a new Codex attempt with no
session id. The verdict reads /proc and passes only if all of these hold:

- the marker pid's parent chain reaches the recorded runtime pid within 8 links;
- every process strictly between them runs a reviewed helper, approved by the device and inode
  of the program it is executing (it must equal that of a listed helper's real path now, and the
  path must agree), and none is the runtime's own program (a forked child that never exec'd shows
  the runtime's exe);
- the recorded pid's exe is still the recorded program, its environment has the attempt's names
  and mb-set values, and its folder is the attempt's;
- when the session id is known, no other process of this user carries it on its command line,
  and every such command line could be read (a process that exited mid-scan does not count);
- the runtime and every process in the chain still have the same parent, start time and program
  after all the reads. A fact that could not be read, or changed while it was read, is unknown
  (4), never a pass.

Exits: 0 pass; 1 fail, naming `not-session-process` (the chain) or `mismatch` (`environ`,
`cwd`); 3 the runtime has ended; 4 unknown (`no-marker`, `no-session-evidence`, `proc-denied`,
`inconsistent`, `exe-changed`, `session-seen`, `scan-incomplete`, `changed`,
`helper-mismatch`); 2 invalid policy or no agent name. Passed values
are not stored and not compared, and no value is printed.

The reviewed helper list is built in and short: `/bin/sh`, `/bin/dash`, `/bin/bash`,
`/bin/zsh` and `/usr/bin/bwrap`, compared by real path. The design keeps the real list per runtime
version with the machine owner and says the first smoke produces it, so treat this one as a
starting point. A helper that is not on it fails the smoke until it is reviewed and added.

`mb agent check <name>` without the flag is the live check, below.

### Running the real smoke (by hand, not in tests)

Do this on a disposable fixture row, never on a working agent, after each pinned runtime update.
For Codex, a plain `check` lists discovery hints while leaving the recorded id
null. Use the hinted rollout to inspect transcript growth. The smoke verdict
itself does not require a known id; it judges the recorded process and tool ancestry.

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

`up` builds `--session-id`, `--resume`, `--append-system-prompt-file` and `--effort`. Confirmed on
Claude Code 2.1.309: all four work, a resume keeps the same session id and transcript, and the role
card text reaches the session. That version's `--help` names `--append-system-prompt-file` only inside
another option's text, so check it by the run below, not by the help alone. Repeat for each new
version: run `claude --help` and check what the flags take. Then do one real run on the fixture row: start it with `--new` and a
short `effort`, check the transcript is named with the id `up` recorded, end it, run
`mb agent up <fixture>` again and check it resumes the same id, and look in the transcript or the
session for the role card text. Record the version and what you saw. Until this is done for a
version, its flags are unconfirmed.

## The live check: `mb agent check <name>`

`mb agent check planner` asks whether a running agent still has the launch configuration it was
given. It reads the attempt `up` recorded and compares it with what /proc shows now. It is read
only: no lock is taken, the lock file is never created, nothing is written, and no signal or
keystroke is sent. `mb agent check` with no name is still the policy check above.

| Field | Match means |
| --- | --- |
| `identity` | The recorded pid is alive with the recorded start time, read twice with no change between. |
| `exe` | The process still runs the recorded program (device and inode). |
| `role` | `MB_ROLE` in the process equals the attempt's. |
| `card` | Policy still names the card file selected at launch. It is not proof the hook ran or the text was loaded. |
| `profile` | The profile directory is the one recorded (device and inode). |
| `cwd` | The process folder is the recorded one. |
| `environment` | The variable names equal the attempt's names, and each value mb set itself is unchanged. |
| `session` | A record in the session's transcript under that profile carries the id and is stamped after the launch. A recent file time alone is not evidence. |
| `row` | The policy row is unchanged since launch (otherwise `mismatch (row)`). |
| `argv` | The command line equals the recorded one. A difference is only `unverified (argv-rewritten)`, because runtimes may rewrite their title. |
| `env-passed` | Always `unverified (not-stored)`. |

Each field is `match`, `mismatch` or `unverified (reason)`. A required field that cannot be
observed makes the answer 4 even when another field mismatches; 1 needs every required field
observed. `argv`, `row` and `env-passed` never block an ok, though a `row` mismatch is itself a 1.

| Exit | Meaning |
| --- | --- |
| 0 | ok: launch configuration verified. |
| 1 | mismatch, fields named. No value is printed, only names such as `env:MB_ROLE`. |
| 2 | invalid policy, `unsafe-store`, unknown agent, root, bad arguments. |
| 3 | `ended`: the lock is free, the runtime identity is dead, and no same-user command line or fresh transcript names the session. |
| 4 | unknown: `proc-denied`, `inconsistent`, `exe-changed`, `lock-orphan`, `lock-owner-unknown`, `holder-lost`, `session-seen`, `scan-incomplete`, `no-session-evidence`, `search-incomplete`, `unsupported-format`, `no-proc`, `corrupt-state`. An agent never launched is also 4 (`no-session-evidence`). |

The lock decides what is judged. Held by the recorded holder with the runtime alive: the fields are
judged. Held by the holder with the runtime gone: `lock-orphan`. Held by anyone else or unreadable:
`lock-owner-unknown`. Free with the runtime alive: `holder-lost`; mb never ends it. Free and dead:
`ended` (3) unless the tripwire fires. The tripwire is a same-user command line naming the session
id, or a transcript written in the last 60 seconds (`session-seen`); a negative result proves
nothing.

`--wait` repeats the check every half second while the answer is 3 or 4, for `--timeout` seconds
(default 30, at most 300), and prints the last answer. A 0, 1 or 2 ends it at once. Use it right
after `up`, before the first transcript record exists.

`--json` prints one object. `shape_version` is 1; the keys are `agent`, `result`
(`ok`, `mismatch`, `refused`, `ended`, `unknown`), `exit_code`, `tag`, `detail`, `attempt`,
`row_rev`, `launched`, `fields` (each `name`, `status`, `reason`, `required`), `problems`,
`assumption`, `limits`, plus the usual result envelope. Keys are only ever added.

**What ok does not prove.** It does not prove the session runs in that process: that is the
lifetime assumption (a supported runtime keeps its session in the process mb started), which the
smoke gives evidence for per runtime version and which every output repeats. A forked waiting
parent can pass `check`; only the smoke sees it. It does not prove the agent behaves like its role.
Passed values (`SSH_AUTH_SOCK`, `HEAVY_LOCK`, terminal and Herdr ids) are not stored, so a re-exec
that changes only one of them is still ok. Anything the runtime changes in memory, files it reads
after start, the model and effort in effect, the account and whether a hook ran are not checked.
Another user's processes may not be readable at all (`proc-denied`, 4).

The observation is a sequence of reads, not an atomic snapshot of a process that can change at any
moment. To bound that, the runtime's identity and program are read again after everything else, the
row lock is read again after the fields (it is opened as an existing file only, never created or
locked, and matched by device and inode in `/proc/locks`), and a transcript whose identity, size or
modification time changes across its read is unknown (`transcript-changed`). The check also compares
hashes of the bytes it read with a re-read: the bounded tail and, for Codex, the metadata line.
Changes outside those bytes or a rewrite restored before re-reading may go unseen.
Any detected change is 4,
which wins over a mismatch. Claude session evidence comes only from
`<profile>/projects/<folder>/<session-id>.jsonl`, where the folder is the recorded working folder's
real path with every `/` and `.` replaced by `-` (confirmed on Claude Code 2.1.309); `up`'s own
search of every project folder is unchanged.

`mb doctor` shows one `agents` row when `agents.json` exists, from a read-only check of every
agent: ended or unknown warns, a mismatch fails, an agent never launched is not a finding.

The Claude flags are confirmed on Claude Code 2.1.309 only. Codex launch and checks
are built with fixture evidence; the real runtime confirmation remains outstanding.
Repeat runtime confirmation after each pinned version update.
