---
name: mb-start-status
title: Daily Start And Status
description: Ground daily start, status, what changed, and next-route prompts in deterministic Main Branch facts before business routing.
loops: [sense, decide, ship]
runtime_support:
  claude_code: supported_shell
  codex_cli: owner_loop_shell
  future: planned
runtime_surfaces:
  claude_code: .claude/skills/mb-start/SKILL.md and .claude/skills/mb-status/SKILL.md
  codex_cli: global main-branch mb-start and mb-status skills
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
json_facts:
  - money_path
  - money_path.policy
  - money_path.policy.thresholds_declared
  - money_path.active_bets
  - money_path.active_bets.unanchored
  - money_path.active_bets.over_cap
  - money_path.objects.proof.quality
  - validation.file_contracts
  - content_strategy
  - ranked_actions
  - relationship_health.gaps
  - update
  - readiness
  - readiness.dimensions.repo_runtime
  - readiness.dimensions.business_memory
  - drift.items
  - runtime.codex_cli
  - runtime.claude_code
  - since_last_check
  - git_activity
  - journal
  - checkpoint
  - onboarding
  - integrations
  - github
  - topology.repo_boundary
  - brain.bets
  - brain.bets.active
  - brain.bets.due_soon
  - brain.bets.overdue
  - brain.bets.exit_criteria
  - brain.bets.exit_criteria.missing
  - brain.bets.exit_criteria.triggered_failure_signals
  - brain.bets.exit_criteria.triggered_double_down_signals
  - vocabulary
approval_gates:
  - updates_repairs_migrations
  - file_writes
  - checkpoint
  - provider_mutation
  - publishing_or_spend
  - customer_contact
  - private_data
  - destructive_operations
  - status_marker
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_customer_member_data
  - no_private_runtime_settings
  - no_raw_finance_legal_records
writes_business_files: false
provider_mutation: false
publishing_or_spend: false
---

# Daily Start And Status

This workflow source is the portable contract for the normal daily Main Branch
entry point: start from facts, explain what changed, surface readiness and
drift, then route one clear next business move.

## Intent And Triggers

Use this workflow when the operator starts the day, returns to a business repo,
asks what to do next, asks what changed, asks for status, asks whether anything
is stale, or asks whether the repo is ready for work.

Do not use this workflow for a full research run, setup write, repair apply,
package update, checkpoint save, provider mutation, publishing, spend, customer
contact, or direct model execution from `mb`.

## Required Mb Commands

Run or preserve these deterministic facts before interpreting business files:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`

`mb status --json --peek` is the default first read. Use `mb start --json` when
runtime handoff, repo-boundary, or adapter-readiness facts matter. Use
`mb doctor repair --plan` when status reports drift, stale guidance, broken
wiring, or setup/repair blockers.

`mb doctor repair --plan` is read-only. A nonzero plan exit can still include a
usable plan; inspect `plan_interpretation`, `summary`, `sections`, and
`actions` before describing it as a failed command.

## Required JSON Fact Paths

The runtime shell must preserve these paths from the workflow source:

- `money_path`
- `money_path.policy`
- `money_path.policy.thresholds_declared`
- `money_path.active_bets`
- `money_path.active_bets.unanchored`
- `money_path.active_bets.over_cap`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `relationship_health.gaps`
- `update`
- `readiness`
- `readiness.dimensions.repo_runtime`
- `readiness.dimensions.business_memory`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `since_last_check`
- `git_activity`
- `journal`
- `checkpoint`
- `onboarding`
- `integrations`
- `github`
- `topology.repo_boundary`
- `brain.bets`
- `brain.bets.active`
- `brain.bets.due_soon`
- `brain.bets.overdue`
- `brain.bets.exit_criteria`
- `brain.bets.exit_criteria.missing`
- `brain.bets.exit_criteria.triggered_failure_signals`
- `brain.bets.exit_criteria.triggered_double_down_signals`
- `vocabulary`

Treat these as facts, not strategy. The runtime may recommend the next route,
but it must not claim conversion quality, provider readiness, checkpoint state,
or runtime support beyond the facts.

## Routing Rules

Route agent usage, remaining capacity, and role-cap questions to `mb usage --json` (read-only).

Hard gates win before business routing: required updates, runtime mismatch,
broken repo wiring, repair blockers, validation blockers, private-data
boundaries, unsafe provider operations, destructive-operation requests, and
approval-gated status marker writes.

Route short clips or social cuts from a sales video or VSL to `mb-organic`.
Route a request to make an ad from the video to `mb-ads`.

Keep repo/runtime readiness separate from business-memory completeness.
`readiness.level` and `readiness.score` describe repo shape, install, git, and
runtime handoff. `readiness.dimensions.business_memory` describes onboarding,
validation, file-contract, and drift signals that may still need owner input.

After hard gates, lead with the top `ranked_actions` entry when the operator
asks what to do next. After that action, name the first warn-level
`relationship_health.gaps` item once, with its repair, when one exists.
Use `git_activity` and `since_last_check` from `mb status` to answer what changed;
business repos need no separate latest or changelog index. Use `journal` for
the operator's recorded context. Use `validation.file_contracts` when a file has the right
place in the repo but is missing the business shape needed for the next
workflow; route offer-shape gaps to `mb-think` and ask before durable writes.
Use `money_path` for customer progress, offer, proof, CTA, channel, push, page
readiness, playbook, and outcome feedback questions. Use `content_strategy` for
content strategy, channel, account, freshness, or disconnected-layer questions.
Use `topology.repo_boundary` when the operator is unsure whether work belongs
in this business repo, a separate business repo, or a child repo;
route from the helper instead of inventing a repo classification.
Use `brain.bets` for active, due-soon, overdue, missing exit criteria,
triggered kill, triggered double-down, close, update, and narrate moments
before inventing bet state from prose. Use `onboarding` to resume setup without
inventing a new interview.

An observation or readout ("I noticed", "the numbers show", "this week's
read") routes to `mb-think` research-only for a short, evidence-backed readout;
if the operator also changes course ("we should stop or switch", "change of
plan"), route to research and a linked decision in the same approved session.
Summarize numbers and cite their source; never save raw provider rows, account
IDs, customer data, or exported tables. Ask before either write. A request only
for status ("where are we", "what changed") gets a status answer without
proposing research or a decision.

When the operator asks to run or continue a current channel trial with a
measurable target and a review or cut point (date, spend cap, or number of posts
or sends), check `brain.bets` and relevant `bets/` files for a bet that already
covers it. Use and link that bet if found. Otherwise offer to frame one through
`mb-bet` before execution, using the facts already given and asking only for a
missing target, review or cut point, or owner when unclear. Ask before writing.
A routine scheduled post, reply, or fix without a wager stays in its channel
workflow.
If an observation changes a measurable trial's target or cut point, make the
short readout and linked decision through `mb-think`, then update or link its
existing bet through `mb-bet` after approval before continuing the trial.

Data/ops surface routing: whose-data questions route to `mb spine declare` and
`mb spine show` — the declaration is a committed repo fact that doctor grades,
and `mb spine init --owned` is the triggered build path only, never a default
migration. Money-path-overnight worries, once real money or real leads flow
unattended, route to `mb canary init`. A recurring daily read on the business
routes to `mb pulse init` (deterministic collectors plus a judgment skill:
scorecard, anomalies, exactly ONE recommended action, read-only — it consumes
`mb status` facts rather than re-ranking them). When `core/operations/pulse/`
exists, read today's `log/<date>-*-pulse.md` at session open and carry its ONE
recommended action alongside the status ranked action; if today's paper is
missing, offer the repo's pulse run before routing. At session close, say
whether that action was done, moved into a lane, or untouched.
"Show me the business" routes to
`mb dashboard open` (local, read-only, never committed). Scripts that read
credentials route to `mb connect exec <provider> -- <command>` (credential
in the command's environment only; never echo the value). Tools missing from the provider list route to
`mb connect <id> --custom`. Agents validating their own work in repos with
legacy debt route to `mb validate --paths <prefix>`. Lead with the business
answer, command second; triggered surfaces stay triggered.

Two named `drift.items` ids carry doctrine the runtime must explain rather
than re-derive. `core_propagation` means offer/audience/voice identity files
changed after the active push records were last updated — derived copy such as
ads, pages, and emails may still carry the old identity; re-check active
pushes against the updated core files. `uncodified_decisions` means decisions
accepted more than seven days ago were never codified into reference files —
decided, but reality unchanged; route repair through the mb-think codify mode.

Give one clear route: frame a bet, think through a decision, advance a push,
draft a playbook, repair the repo, review provider readiness, inspect a
specific offer, or plan a checkpoint. In status mode, do not mutate the
last-check marker unless the operator explicitly says this is the daily
check-in and wants it recorded.

## Read Boundaries

Read deterministic `mb` facts before raw markdown. After the fact pass, read
only the business files needed for the route:

- active offer, audience, proof, product ladder, CTA, and content strategy;
- relevant decisions, research, bets, pushes, logs, and documents;
- safe provider-readiness summaries when status says a provider affects the
  route.

Do not inspect secrets, raw provider exports, raw finance/legal records,
customer/member records, local runtime settings, private maintainer notes, or
credentials.

## Write Boundaries

This workflow does not write business files by itself. It may hand off to a
workflow that writes business files after operator approval. The status marker
is local operational state and may be updated only when the operator explicitly
approves recording the daily check-in.

The workflow source does not authorize setup writes, repair applies, package
updates, migrations, checkpoints, provider writes, public issue/proposal
submission, publishing, spend, customer contact, or Main Branch engine edits.

## Approval Gates

Ask before:

- applying updates, repairs, migrations, setup writes, or provider setup;
- creating, editing, moving, deleting, or archiving business files;
- saving a checkpoint;
- mutating the status marker;
- publishing, opening a public issue, submitting a proposal, spending money,
  mutating provider state, or contacting customers;
- reading or moving private, restricted, local-only, finance, legal, customer,
  member, credential, or raw provider data.

Never ask the operator to paste secrets into repo files or workflow sources.

## Handoff Format

When handing off from start or status, include a compact snapshot:

```text
Daily state: <ready, needs attention, blocked, or not a Main Branch repo>.
Facts read: <status/start/repair facts used>.
What changed: <since-last-check or journal summary>.
Main signal: <ranked action, readiness, drift, MoneyPath, content strategy, or onboarding fact>.
Recommended route: <one business route and why>.
Approval needed before writes: <yes/no and what action>.
```

Use business language first. Git, branches, runtime wiring, provider refs, and
repair commands are details after the owner-facing state unless the operator
asks for plumbing.

## Validation Commands

Before changing this workflow or its runtime shells, run:

```bash
cd mb
python -m pytest tests/test_workflows.py -q
```

For repo-level validation, run:

```bash
scripts/check.sh
```

If generated global Codex skills, repo guidance, or runtime discovery changes,
add package/install and runtime/manual smoke evidence.

## Runtime-Specific Notes

Claude Code may use slash-command-native language for `/mb-start` and
`/mb-status`. Preserve the fact-first status preamble, update and repair gates,
session-scoped offer selection, numbered options, and compaction recovery.

Codex uses global Main Branch skills and natural-language routes. Codex should
use the generated global `mb-start` and `mb-status` skills, start from read-only
`mb` facts, stop on runtime mismatch, and avoid claiming Claude Code entrypoints
or broader workflow parity.
