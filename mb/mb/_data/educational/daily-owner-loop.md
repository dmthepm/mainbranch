---
type: educational
topic: daily-owner-loop
status: draft
last-updated: 2026-05-08
---

# The daily owner loop: what Main Branch asks you to do first

Main Branch starts from the normal owner day, not from tool theory.

The goal is simple: open the business folder, let Claude ground itself in repo
facts, choose the next useful business move, ship or repair the next thing, and
save what changed.

## The beginner version

After setup, the daily loop is:

```bash
cd /path/to/your-business
claude
/mb-start
```

That is the front door.

`/mb-start` should make Claude read deterministic `mb` facts before advice:
repo health, status, updates, graph links, provider readiness, runtime wiring,
recent activity, and checkpoint readiness.

## What happens in the loop

1. **Open Terminal or Claude Code safely.**
   Start in the business repo, not in the engine repo or a random downloads
   folder.

2. **Install or update through the product path.**
   Use `mb onboard`, `/mb-update`, or `mb update --repo .` when Main Branch
   tells you to. Do not start by debugging Python packaging or git internals.

3. **Choose or create a business folder.**
   That folder is the business brain: `core/`, `research/`, `decisions/`,
   `bets/`, `pushes/`, `log/`, and `documents/`.

4. **Run `/mb-start` or `mb status`.**
   Claude should ground itself in `mb` facts before giving strategic advice.

5. **Route work into a business primitive.**
   A messy thought dump should become a bet, research note, decision, push,
   playbook, outcome, log entry, or checkpoint plan.

6. **Close with `/mb-end` or checkpoint guidance.**
   The point is not to leave a long chat behind. The point is to preserve the
   useful business record in files and git history.

## Why the tools exist

- **Markdown files** make the business record readable.
- **Git history** turns saved work into a timeline.
- **GitHub** gives durable tasks, blockers, proposals, and reviews.
- **`mb`** checks the facts and prints exact next commands.
- **Claude Code skills** do the judgment-heavy writing, routing, and review.
- **Provider rails** connect outside tools only when a business job needs them.

The philosophy matters because it protects the loop. Main Branch is not asking
you to learn infrastructure for its own sake.

## What Main Branch does not claim

Main Branch does not expect beginners to manually manage branches, package
repair, hidden git commands, or provider internals as the default workflow.

When something needs repair, `mb` should explain what broke, why it matters,
and the next exact command. When behavior depends on Claude Code runtime
discovery, package install, provider mutation, or release quality, it needs
matching evidence before Main Branch claims it works.
