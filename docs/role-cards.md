# Role cards

A role card tells one agent what it is for. A restarted agent reads its card
instead of a generic prompt, so it does not take another agent's role.

Claude Code only. Codex has no role hook and this feature is untested there.

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
automatically on every session start, resume, clear and compaction, with no
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
- `mb role hook --source startup|resume|clear|compact` is the hook entry (below).

`mb doctor` adds a `role-cards` check, only in repos that have cards. It warns
about invalid cards and about cards with no SessionStart hook found in
`.claude/settings.json` or `.claude/settings.local.json`. An enabled plugin
alone is reported as "not verified": doctor cannot see whether its version has
the hook.

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
session `startup`, `resume`, `clear` and `compact`. Claude Code
adds the hook's stdout to the model's context.

| Situation | What the hook prints |
|---|---|
| No cards in `core/roles/` | Nothing. Existing businesses see no change. |
| Cards exist, `MB_ROLE` unset | A refusal: stop, tell the owner, ask which role. |
| `MB_ROLE` invalid, card missing, or card invalid | The same refusal with the reason. |
| Valid card | The card and the contents of its checkpoint file (first 8 KB). |

**A hook cannot block a session.** Claude Code's SessionStart hook has no way to
stop the session; the refusal is text the model is told to obey, not an
enforced stop. It is worded to be unmissable, and in testing the model stopped
and asked. It is still an instruction, not a lock.

Other limits:

- If the hook command cannot run `mb role hook`, it cannot load the card.
  When at least one `core/roles/*.md` file exists it prints a plain refusal
  (role could not be loaded; stop and ask, no cause claimed); with none, even
  with an empty folder, it prints nothing. The command is POSIX `sh` and always exits 0.
- With no cards at all, a set `MB_ROLE` is ignored, by design.
- A repo-local `SessionStart` hook running `mb role hook --source <source>`
  in `.claude/settings.json` is read by `mb doctor` as wired only when its command starts with `mb role hook`, but only the
  plugin route was run for this release.
- The plugin takes effect after a plugin update and a Claude Code restart.
