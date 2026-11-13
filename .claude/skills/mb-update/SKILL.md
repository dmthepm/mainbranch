---
name: mb-update
description: Update Main Branch. Use when the user says update, upgrade, pull latest, get latest Main Branch, asks whether they are current, or after Devon announces a new release.
loops: [ship]
---

# Update

Update the installed Main Branch CLI and skills, then refresh this business
folder's Claude Code links.

Use this instead of asking the user to remember whether they installed with
pipx or an old clone. The CLI owns the mechanics. Do not suggest raw package
commands such as `pipx upgrade mainbranch` as the first update path; only use
that as the bootstrap fallback when `mb update` is unavailable or the installed
version is `0.1.x`.

**CLI facts first:** Run `mb update --repo . --json` from the business folder
and use its result before giving install-mode advice.

---

## Step 1: Update Main Branch

Run from the business folder:

```bash
mb update --repo . --json 2>&1
```

Handle the JSON result:

| Result | What to say |
|---|---|
| `manual_update_command` is set (whatever `"ok"` says) | **Check this row first.** This install mode is not one the CLI upgrades for you, so never say "Updated Main Branch" here. Then branch on the version. **`old_version != new_version`:** Main Branch did **not** upgrade itself — say so, read `manual_update_command` out verbatim as the command for the user to run themselves, and show the warning. **`old_version == new_version`:** the install is already up to date and needs no upgrade — say that, and do not present the command as an action item. Skill links were refreshed either way. If `"ok"` is also false that refresh failed: show the first error too, but still keep `manual_update_command` in front of the user — do not fall through to the repair copy below, which assumes a pipx install. |
| `"ok": true`, `old_version != new_version` | "Updated Main Branch and refreshed skill links." |
| `"ok": true`, `old_version == new_version` | "Main Branch is already up to date." |
| `"ok": false` | Show the first error and the repair copy below. |
| Invalid JSON | Run `mb update --check --repo .` yourself if possible; if not, ask the user for that output. |

If the result includes warnings, show them after the main status.

**Tracked files.** Run from an agent, `mb update --json` does not change a
tracked file in the business repo (`AGENTS.md`, `.gitignore`) or create a
missing (or dangling-link) `AGENTS.md`; a post-apply check reports any it missed as an error. When the refresh
would change one, it leaves it alone and reports it:
`surface_refresh.planned.consent` is `no_terminal`,
`surface_refresh.planned.tracked_files` names the files (writes and
deletions), and
`surface_refresh.planned.apply_commands` (also in `operator_actions`, not
`next_actions`) holds the commands that would apply them. Tell the user which files would change and
give them those commands. Applying them is the operator's step: do not run
them yourself unless the user asks you to in this conversation. Gitignored skill
links still refresh on their own.

**For a person only.** `operator_actions` lists steps that change tracked
files, such as the plugin-rail switch. Show each `command` and `note` to the
user as theirs to run at a terminal; never run them yourself. `mb doctor
repair` lists the same switch there and never applies it.

---

## Step 2: If Update Fails

Tell the user:

> "I wasn't able to update Main Branch. This can leave you on old skills or old
> migration behavior.
>
> Try these from your business repo:
>
> ```bash
> mb update --check --repo .
> mb doctor
> ```
>
> If `mb --version` says `0.1.x`, run this once first:
>
> ```bash
> pipx upgrade mainbranch
> ```"

Do not continue as if the update worked.

---

## Step 3: Restart If Skill Links Changed

If `skills_relinked_count` is greater than zero after an actual update, tell
the user:

> "Skill links were refreshed. If a slash command does not appear in Claude
> Code, restart Claude from this repo and run `/mb-start`."

Claude Code loads slash commands at session start, so a restart can be required
after repairing links. In `--check --json` output, treat
`planned_skills_relink_count` as a dry-run preview, not proof that links already
changed.

If `plugin_rail.install.state` is `stale`, `installed_not_enabled`, `disabled`,
or `not_installed`, tell the user the Claude Code plugin cache needs attention
too. Quote the warning, include the plugin repair command from `next_actions`,
and say to restart Claude Code or run `/reload-plugins` before relying on new
slash-skill behavior. Inside a repo, refresh the plugin only with
`claude plugin marketplace update mainbranch && claude plugin install mainbranch@mainbranch --scope user`.
Never run `claude plugin marketplace remove` or `add` inside a repo: remove
empties the repo's tracked `.claude/settings.json` plugin entries. If that
already happened, the restore is `git checkout -- .claude/settings.json`.

---

## Step 4: What Changed

After a successful update, use `release.summary` and `release.url` from the
JSON result when present. Keep it short: 3-5 bullets max, and include the
release URL when the user asks what changed.

If the JSON result has no release summary, read `CHANGELOG.md` from the active
Main Branch engine if available and summarize only the matching version section.

If no changelog is available, do not guess. Say:

> "Update complete. I couldn't find the local changelog, so run `mb --version`
> to confirm the installed version."
