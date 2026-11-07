# Role cards

A role card tells one agent what it is for. A restarted agent reads its card
instead of a generic prompt, so it does not take another agent's role.

Works in Claude Code and Codex. Codex needs one setup step and one review. See
[Codex](#codex).

## The card

One file per agent at `core/roles/<name>.md`, committed in the business repo.
`<name>` is lowercase letters, digits and hyphens (up to 40) and must equal the
`name` field.

```markdown
---
name: scout
role: Research scout for the business
skills: [mb-think]
tools: [mb]
protocols: [save-before-stop]
first_action: Read the checkpoint, then say which role you are.
checkpoint: state/scout-checkpoint.md
---
Anything else the owner wants to say about this role.
```

All seven fields are required. `checkpoint` must be a regular `.md` file under
`state/` or `core/roles/`, with no hidden path segment (nothing starting with
`.`), and not git-ignored unless it is under `state/`. The rule is applied to
the written path and to where a link really points, so a link from `state/` to
`.env` is refused. Any other checkpoint makes the card invalid and the hook
refuses, naming the rule. Unknown fields
are ignored with a warning. The body is for the owner; the hook does not print it.

## Trust: cards enter the model's context automatically

The card fields and the checkpoint file are put into the model's context
automatically on every session start, resume, clear, fork and compaction, with no
prompt. Trust them like `CLAUDE.md`: a bad card or a bad checkpoint is a
prompt-injection path, because whatever it says reaches the model as
instruction. Review changes to `core/roles/` and to checkpoint files as you
would review changes to `CLAUDE.md`. Only the allowed checkpoint locations
above are ever read; the hook reads the first 8 KB, strips Unicode format
controls, and neutralizes checkpoint section markers inside the text.
The location rule isn't a secret detector: anything you put in an allowed
checkpoint file reaches the model, so keep credentials out of it.

## Commands

All are read-only. `--json` uses the standard result envelope.

- `mb role list` lists cards.
- `mb role show NAME` prints one card; exits 1 if it is missing or invalid.
- `mb role check [NAME]` validates one or all cards; exits 1 on any invalid card.
- `mb role hook --source startup|resume|clear|compact|fork` is the hook entry (below).
- `mb role codex-hook` previews the Codex hook; `--apply` installs it, `--remove` removes it (below).

`mb doctor` adds a `role-cards` check, only in repos that have cards. It warns
about invalid cards and about cards with no SessionStart hook found in
`.claude/settings.json` or `.claude/settings.local.json`. An enabled plugin
alone is reported as "not verified": doctor cannot see whether its version has
the hook. A second check, `role-cards-codex`, covers Codex (below).

## Selecting the role

Name the role at launch with the `MB_ROLE` environment variable:

```bash
cd path/to/my-business
MB_ROLE=scout claude
```

The role is never guessed from the repo, the directory, or the only card
present.

## The SessionStart hook

The Main Branch plugin ships `hooks/hooks.json`, which runs `mb role hook` on
session `startup`, `resume`, `clear`, `compact` and `fork`. Claude Code
adds the hook's stdout to the model's context.

| Situation | What the hook prints |
|---|---|
| No cards in `core/roles/` | Nothing. Existing businesses see no change. |
| Cards exist, `MB_ROLE` unset, fresh `startup` | A refusal: stop, tell the owner, ask which role. |
| Cards exist, `MB_ROLE` unset, `resume`, `clear`, `compact` or `fork` | One warning line, no stop. It is informational, not enforcement. |
| `MB_ROLE` invalid, card missing, or card invalid | The same refusal with the reason. |
| Valid card | The card and the contents of its checkpoint file (first 8 KB). |

**A hook cannot block a session.** Claude Code's SessionStart hook has no way to
stop the session; the refusal is text the model is told to obey, not an
enforced stop. It is worded to be unmissable, and in testing the model stopped
and asked. It is still an instruction, not a lock.

Other limits:

- If the hook command cannot run `mb role hook`, it cannot load the card.
  When at least one `core/roles/*.md` file exists it prints a plain refusal
  (role could not be loaded; stop and ask, no cause claimed) on `startup` and whenever
  `MB_ROLE` names a role, and one informational warning line on the other sources when
  no role is named (Codex: only for a flat payload with one top-level source); with none, even
  with an empty folder, it prints nothing. The command is POSIX `sh` and always exits 0.
- With no cards at all, a set `MB_ROLE` is ignored, by design.
- A repo-local `SessionStart` hook running `mb role hook --source <source>`
  in `.claude/settings.json` is read by `mb doctor` as wired only when its whole command is `mb role hook`, but only the
  plugin route was run for this release.
- The plugin takes effect after a plugin update and a Claude Code restart.
- The `fork` trigger follows Claude Code's documented SessionStart sources and is
  unproven live; only startup, resume, clear and compact were run.

## Codex

Tested in a real run on Codex 0.164: startup from a subfolder, resume, clear, compact,
fork, a git worktree, the refusal when no role is set, and silence in a repo with no
cards. Not tested: a bare `codex` that auto-restores a session, subagents, later Codex
versions, a full-length card and checkpoint near the size limit.

The card and `mb role hook` are the same as in Claude Code. Codex only needs a thin
trigger, a user-level `SessionStart` hook in `hooks.json` under `$CODEX_HOME`
(default `~/.codex`). It runs on startup, resume, clear, compact and fork, so a
forked session gets its card too.

```bash
mb role codex-hook            # preview the exact change, writes nothing
mb role codex-hook --apply    # install
mb role codex-hook --apply --remove   # uninstall
```

The install merges into an existing file and keeps every other hook: it changes
only a hook whose command exactly matches the generated one, and tells you if another
hook mentions `mb role hook`. It is idempotent, writes atomically, and leaves a malformed file or a symlinked
`hooks.json` untouched. It never edits Codex's trust state or `config.toml`.
Launch with `MB_ROLE=scout codex` in the business repo.

**What you trust.** Codex reviews the hook once, not each repo. After that it runs in
every Codex session, including folders you have not trusted, and outside Codex's
sandbox. With `MB_ROLE` set, any repo with a matching card gets that card and its
checkpoint into the session, so a repo you cloned can give the agent instructions,
much as its `AGENTS.md` can. Do not leave `MB_ROLE` set in a shell you use for repos
you have not read. The hook also runs whichever `mb` comes first on your `PATH`, so
keep repo folders off `PATH`. Replacing `mb` needs no new review.

The hook walks up from the session folder to the git root looking for
`core/roles`, so a session in a subfolder or a git worktree finds its repo. In a
folder with no `core/roles` it exits at once without starting `mb`. Codex hands the
hook its session folder on stdin and sets no project variable, so the Codex route
never reads `CLAUDE_PROJECT_DIR`.

`mb doctor` reports `role-cards-codex` in a repo with cards. It counts the hook as
wired only when the user-level file holds the exact command `mb` generates. It
always says trust is "not verified": doctor cannot see Codex's trust store.

Limits:

- **Runs outside the sandbox.** Codex warns that trusted hooks can run outside its
  sandbox. This one runs `mb role hook` and prints text.
- **Trust review.** Codex records a hash of each hook and skips a new or changed
  one until you approve it. It prints a startup warning telling you to open `/hooks`;
  review and trust the Main Branch hook there. Until you do, no card is loaded. A
  Main Branch update that changes the hook command asks for review again.
- **Restart needed.** Install, then restart Codex.
- **Subagents are not covered.** Only the session itself is told its role.
- **User-level only.** A user-level hook works in git worktrees (tested). Repo-level
  hooks need a trusted project and have been reported ignored in worktrees, so the
  repo's `.codex/hooks.json` is not used.
- **A bare `codex` that auto-restores a session** may fire no source on some
  versions. Use `codex resume` to be sure. Not proven on 0.164.
- **Size.** Past the hook's 4,000-token setting, Codex sends a shortened preview and
  saves the full text to a file. A usual card with an 8 KB checkpoint fits; a very long
  card may not. Nothing limits a card field's length yet.
- **Same refusal limit as Claude.** A hook cannot block a session; the refusal is text.
- POSIX shell only; no Windows command is installed.
