---
title: "PRD: v0.3 Agent Checkpoints + Git Memory"
status: shipped
date: 2026-05-04
release: v0.3.x
linked_issue: https://github.com/dmthepm/mainbranch/issues/288
---

# PRD: v0.3 Agent Checkpoints + Git Memory

## Summary

Main Branch should make git feel like an invisible save system for business
work. The operator should be able to work with an agent for hours, survive
context compaction or a new runtime session, and have the next session
reconstruct what happened from repo history instead of asking the operator to
re-explain the whole conversation.

The current product has the right ingredients:

- the business repo is durable memory;
- `mb status` can summarize repo state;
- `/mb-start` can reorient from repo facts;
- `/mb-end` can close a session and commit work.

The gap is timing. `/mb-end` is too late for long runs. Checkpointing needs to
be woven through execution.

## Problem

Agents lose conversation context. Users pause, resume, compact, start fresh
sessions, or switch repos. When important work only lives in chat, the next
agent has to reconstruct it from memory or ask the user to explain again.

That creates a visible failure mode:

- "We already talked about this."
- "Claude forgot what we built Friday."
- "I have to remind it of the plan before it can continue."
- "ChatGPT history feels more continuous than Claude Code."

Main Branch should not try to make chat history the source of truth. It should
make the repo and git history strong enough that chat history matters less.

## Product Stance

Users should not need to understand git to benefit from git.

Git history is:

- the session memory;
- the undo stack;
- the work log;
- the audit trail;
- the source for `/mb-start`, `mb status`, future dashboards, and team daily
  logs.

The agent should create readable checkpoints throughout meaningful work. Those
checkpoints should feel like "saved progress," not developer ceremony.

## Goals

- Make meaningful work durable before context is lost.
- Let `/mb-start` reconstruct recent work from commits, diffs, status, and
  repo files.
- Let `/mb-end` use the same checkpoint flow instead of owning all
  checkpoint behavior itself.
- Give agents deterministic rules for when to checkpoint.
- Keep commit history readable and business-shaped.
- Protect users from accidental secret, private-data, or broken-work commits.
- Keep power-user git control available.

## Non-Goals

- No background daemon or file watcher in this slice.
- No commits after every small edit.
- No fully automatic commits when the agent is uncertain about privacy, scope,
  or correctness.
- No model invocation from `mb`.
- No hosted sync layer.
- No replacing GitHub issues, PRs, or git history with an app database.

## Target Users

### Beginner Operator

They do not know git. They should experience checkpoints as safe progress
saves:

> "I saved this work as a checkpoint so we can pick it up later."

They should see plain-English summaries and exact next commands. They should
not be asked to choose between obscure git strategies.

### Power User

They understand commits and branches. They should be able to inspect the plan,
choose concern-based commits, disable automatic prompts, or run a scriptable
`mb checkpoint --plan --json`.

### Agent Runtime

Claude Code is the reference runtime today. Future runtimes should get the
same deterministic checkpoint contract through `mb`, not runtime-specific prose
rewrites.

## Checkpoint Triggers

An agent should consider a checkpoint when any of these happen:

| Trigger | Example | Default behavior |
|---|---|---|
| Meaningful file write | `core/offer.md` updated, site files generated | Propose checkpoint |
| Decision locked | decision created or accepted | Propose checkpoint |
| Research batch complete | research files saved from a deep work loop | Propose checkpoint |
| Task boundary | moving from research to ads, site to deploy, setup to execution | Propose checkpoint |
| Context threshold | long agent run, compaction risk, or >30K token block completed | Propose checkpoint |
| Before risky action | deploy, provider mutation, migration apply, broad rewrite | Require checkpoint prompt |
| Before repo switch | business repo -> site repo, one workspace -> another | Propose checkpoint |
| Before session end | `/mb-end`, "pause", "done", "wrap" | Checkpoint or explain no changes |

The key is not "commit every write." It is "commit before the useful shape can
be lost."

## Commit Grouping

Commit subjects should follow the accepted
[operator-readable git history contract](../../decisions/2026-05-05-operator-readable-git-history.md).
The system should support two modes.

### Beginner Mode: One Checkpoint

Use one commit per meaningful run segment:

```text
[drafted] paid traffic site plan
[updated] flagship offer and audience
[added] competitor positioning research
```

The commit body can carry the detail:

```text
Changed:
- core/offer.md
- pushes/2026-05-04-paid-site/push.md
- decisions/2026-05-04-paid-site-plan.md

Why:
- Captures the campaign plan before site generation starts.

Next:
- Run /mb-site from the business repo.
```

### Power Mode: Concern Commits

When the agent can separate concerns cleanly:

```text
[updated] offer.md -- clarified guarantee
[added] paid site measurement plan
[decided] GTM conversion rubric -- require consent events before launch
```

Power mode is useful for contributors and technical operators, but it should
not be the beginner default. Loop names such as Sense, Decide, Ship, and
Reflect are internal grouping signals, not default commit prefixes.

## Privacy and Safety Gates

Before checkpointing, the agent or future `mb checkpoint` command must check:

- no obvious secrets, tokens, service-account JSON, bearer tokens, or `.env`
  files are staged;
- no machine-local bridge files such as `.claude/settings.local.json` or skill
  symlinks are staged;
- no customer/member/account data is being committed accidentally;
- generated files are in the intended business or site repo, not the engine;
- repo state is not already in merge/rebase conflict;
- changes fit the current user task.

If risk is detected, do not commit. Explain the issue and give the next safe
command.

## Proposed CLI Surface

### `mb checkpoint`

Create or preview a business-repo checkpoint.

Candidate options:

```bash
mb checkpoint --plan
mb checkpoint --json
mb checkpoint --message "[drafted] paid traffic site plan"
mb checkpoint --yes
mb checkpoint --mode beginner
mb checkpoint --mode concern
mb checkpoint --repo .
```

Expected behavior:

- inspect git status;
- classify changed files by business section;
- run privacy/safety gates;
- propose one or more commit messages;
- produce machine-readable JSON for skills;
- commit only when explicitly approved or `--yes` is passed in a context where
  safety gates pass.

### `mb checkpoint status`

Optional follow-up surface for agents:

```bash
mb checkpoint status --json
```

Returns recent checkpoint facts:

- last checkpoint commit;
- changed files since last checkpoint;
- whether work is dirty;
- suggested checkpoint urgency.

## Skill Integration

### `/mb-start`

At start:

- read recent checkpoint commits;
- summarize what changed since last session;
- show dirty work if present;
- recommend continuing, checkpointing, or repairing before new work.

### `/mb-end`

At close:

- call the same checkpoint planner;
- commit any remaining meaningful work after user confirmation;
- save crystallize output as repo memory;
- close with a summary.

`/mb-end` remains valuable, but it is no longer the only checkpoint moment.

### Execution Skills

Skills that write meaningful files should call the checkpoint planner at
natural boundaries:

- `/mb-think` after a research batch or decision;
- `/mb-site` after site brief, first generated site, and before deploy;
- `/mb-ads` after generated ad batch and after compliance review;
- `/mb-bet` after bet creation, update, close, or narration;
- migration/setup flows before and after applying broad changes.

## User-Facing Copy

Beginner language:

> "I saved a checkpoint. That means the work is in your repo history, so a
> future Claude session can pick it back up."

Before commit:

> "I changed 4 files. Want me to save a checkpoint before we move on?"

When refusing:

> "I found something that looks like a secret or local machine file, so I did
> not checkpoint this yet."

At next start:

> "Last checkpoint: paid site plan. Since then, 2 files changed and nothing is
> committed yet."

## State Model

Checkpoint truth is normal git history. Main Branch should not create
a second source of truth for commits.

Optional local state may live under `.mb/` only for rebuildable helper data,
such as:

- last checkpoint prompt seen;
- checkpoint preference mode;
- ignored temporary files;
- cached classification from the latest plan.

Any `.mb/` checkpoint state must be rebuildable from git and safe to delete.

## Validation

Implementation should include:

- unit tests for dirty/clean repos;
- tests for staged secret-like files refusing to commit;
- tests for noob one-commit and concern-commit planning;
- JSON contract tests;
- fixture business repo smoke:

```bash
tmpdir="$(mktemp -d)"
mb onboard --yes --name "Test Business" --path "$tmpdir/test-business"
cd "$tmpdir/test-business"
# modify core/offer.md
mb checkpoint --plan --json
mb checkpoint --message "[updated] test offer" --yes
mb status --json --peek
```

- runtime smoke for a skill writing files, asking for checkpoint, and then
  `/mb-start` reconstructing the checkpoint in a fresh session.

## Implementation Slices

### Slice 1: Spec and Docs

This PRD plus small updates to ethos, roadmap, and operator loops.

### Slice 2: Deterministic Planner

Build `mb checkpoint --plan --json` with file classification and safety gates.
No committing yet.

### Slice 3: Commit Execution

Add `mb checkpoint --yes` and human rendering. Keep approval and safety gates
strict.

### Slice 4: Skill Wiring

Update `/mb-start`, `/mb-end`, and one high-write skill such as `/mb-think` or
`/mb-site` to use the checkpoint contract.

### Slice 5: Dashboard and Team Daily Log

Future dashboard surfaces can read checkpoint history as the "what happened"
timeline. Team daily logs should build from checkpoint commits and explicit log
files, not chat transcripts.

## Open Questions

- Should beginner mode default to one checkpoint per task boundary or one per
  context threshold?
- What is the right prompt threshold: 10K tokens, 30K tokens, or runtime-
  reported context percentage?
- Should `mb checkpoint` ever stage untracked generated output automatically,
  or should untracked files require explicit mention?
- Should checkpoint preferences live in `.mb/` or runtime-local config?
- How should multi-repo work checkpoint when a business repo drives a separate
  site repo?

The prefix list, daily checkpoint prefix question, reference trailer stance, AI
attribution stance, and beginner-vs-power validation stance are settled in the
[operator-readable git history decision](../../decisions/2026-05-05-operator-readable-git-history.md).

## Acceptance Criteria

The first implementation is successful when:

- a user can ask an agent to checkpoint mid-run;
- the agent can preview exactly what will be committed;
- sensitive/local files are blocked;
- the commit message is readable to a non-technical operator;
- `/mb-start` can summarize recent checkpoint history;
- a new Claude Code session can continue without the user re-explaining the
  last work block.
