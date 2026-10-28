# Claude Code Invocation Contract

This is the supported Claude Code invocation contract for Main Branch. It is
based on Claude Code 2.1.126 runtime smoke from a fresh `mb onboard` business
repo on May 7, 2026, plus the Stage 3 plugin rail contract from June 2026.

## Supported Path

The reliable daily path is:

```bash
cd /path/to/your-business-repo
claude
```

Then type:

```text
/mb-start
```

Main Branch skills are Claude Code skills under `.claude/skills/<name>/SKILL.md`.
`mb onboard`, `mb init`, and `mb skill link --repo .` create project-local
bridge links such as `.claude/skills/mb-start` in the business repo. Those
bridge links keep the supported, friendly slash-command surface.

Main Branch also wires the Claude Code plugin in tracked `.claude/settings.json`
so skill distribution survives fresh git worktrees and works across the Claude
Desktop app and the terminal. Claude Code plugin-native skills are namespaced,
so the direct plugin smoke command is:

```text
/mainbranch:mb-start
```

That command is for release validation and diagnostics. Public setup and support
docs should still tell users to type `/mb-start` for the daily entrypoint while
Main Branch keeps the project-local bridge wired.

`.claude/settings.local.json` also points Claude Code at the active Main Branch
engine through `additionalDirectories`. That setting gives the runtime file
access to the engine, but it is not sufficient by itself for `/mb-start`
slash-command discovery. If `.claude/skills/mb-start` is missing, current
Claude Code can report `Unknown command: /mb-start`.

## Extra Text

`/mb-start` may be followed by normal instructions:

```text
/mb-start I only have five minutes and want to keep this read-only.
```

Runtime smoke showed that Claude Code still invokes the `mb-start` skill and
the extra text is treated as conversational instruction. Do not depend on
Claude Code project-command `$ARGUMENTS` behavior here; Main Branch is not
scaffolded as `.claude/commands/` project commands today.

The only structured positional hints `/mb-start` currently teaches are an
explicit repo path/name and, where relevant, an offer name. For beginner docs
and first-run handoff, teach plain `/mb-start`.

## Natural Language

Natural-language requests such as "I am opening Main Branch for the day and I
am not sure what to do next" can route into `mb-start` through the skill
description. Runtime smoke confirmed that this works in Claude Code 2.1.126.

That routing is useful, but it is not the beginner contract. Public setup and
support docs should still tell users to type `/mb-start` when they want the
daily entrypoint.

## Repair Contract

If `/mb-start` is missing or returns `Unknown command`, run these from the
business repo:

```bash
mb skill link --repo .
```

Then restart Claude Code from the business repo and type `/mb-start` again.
Claude Code loads skill discovery at session start, so relinking usually
requires a restart before the slash command appears.

If the plugin itself needs verification, install or refresh it with
`claude plugin marketplace add dmthepm/mainbranch`, enable it, restart or
run `/reload-plugins`, and check `/mainbranch:mb-start`. Do not replace the
user-facing `/mb-start` guidance with the namespaced command unless the bridge
contract is intentionally removed.

`mb skill link --repo .` creates the project-local bridge links and also moves
known stale or broken Main Branch personal-skill shadows to backups. If
`/mb-start` is still missing afterward, run `mb skill repair --repo .` to
inspect unresolved personal-skill conflicts. Use
`mb skill repair --repo . --apply` only when you intentionally want the
standalone repair command to move repairable shadows.

`mb start --json` and `mb doctor` perform static checks for this wiring. Static
checks prove the files are present and not shadowed by known personal skill
conflicts; runtime smoke is still required when changing discovery,
invocation, packaging, or first-run handoff behavior.

## Runtime Evidence

Fresh-repo smoke covered:

- plain `/mb-start`: recognized `mb-start`, read the business repo, and used
  `mb status --json --peek` facts;
- `/mb-start` plus extra text: recognized `mb-start`, preserved CWD-first repo
  routing, and treated extra text as instruction;
- natural language: selected `/mb-start` from the skill description and read
  business repo context;
- missing project-local bridge: after removing `.claude/skills/mb-start` while
  leaving `additionalDirectories`, Claude Code returned
  `Unknown command: /mb-start`;
- relink repair: `mb skill link --repo .` restored the project-local bridge and
  `/mb-start` was recognized again.

Plugin-native command discovery (`/mainbranch:mb-start`) is covered by the
manual plugin-load release gate in `docs/release-agent-contract.md` whenever a
release changes plugin wiring, manifests, or plugin-first runtime guidance.
