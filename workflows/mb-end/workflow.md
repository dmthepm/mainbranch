---
name: mb-end
title: End Checkpoint Save
description: Close a Main Branch session with deterministic status facts, crystallize analysis, owner-facing save states, and an approval-gated checkpoint.
loops: [reflect, ship]
runtime_support:
  claude_code: supported_shell
  codex_cli: owner_loop_shell
  future: planned
runtime_surfaces:
  claude_code: .claude/skills/mb-end/SKILL.md
  codex_cli: global main-branch mb-end skill
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb checkpoint --plan --json
  - mb validate --json
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - validation.file_contracts
  - content_strategy
  - ranked_actions
  - relationship_health.gaps
  - update
  - readiness
  - drift.items
  - runtime.codex_cli
  - runtime.claude_code
  - journal
  - since_last_check
  - checkpoint.pending
  - checkpoint.pending.changed_files
  - checkpoint.pending.blockers
  - checkpoint.pending.proposed_subject
  - summary.changed_files
  - safety.blocks
  - proposal.message
  - validation
approval_gates:
  - updates_repairs_migrations
  - file_writes
  - checkpoint
  - provider_mutation
  - publishing_or_spend
  - customer_contact
  - private_data
  - destructive_operations
  - public_issue_or_proposal
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_raw_transcripts
  - no_customer_member_data
  - no_private_runtime_settings
  - no_raw_finance_legal_records
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# End Checkpoint Save

This workflow source is the portable contract for closing a Main Branch session:
scan what changed, summarize the business work, surface the final thought,
crystallize the lesson when meaningful activity happened, and save only after
approval.

## Intent And Triggers

Use this workflow when the operator says they are done, pausing, wrapping up,
ending the day, saving progress, checkpointing, asking "is that it?", or asking
whether the work is saved.

This is the bookend to start/status. It is not a daily standup, task planner,
or autosave. It closes the current session and keeps business memory durable.

A mid-session save where the operator keeps working -- "save", "save my
progress", "checkpoint this", "yes save", "should we checkpoint everything" -- is
a save, not a close. Run `mb checkpoint --plan`, save on approval through `mb
checkpoint`, and return them to their work, without the crystallize-and-close
sequence. Never save with raw git. Use the full closeout only for an actual end
or pause of the session.

Do not use this workflow for provider mutation, publishing, spend, customer
contact, broad research, ad/site production, or automatic model execution from
`mb`.

## Required Mb Commands

Run or preserve these deterministic facts before interpreting changed files:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb checkpoint --plan --json`
- `mb validate --json`

`mb status --json --peek` is the normal status scan. Use its journal,
since-last-check, readiness, drift, update, runtime, MoneyPath, content
strategy, ranked-action, and checkpoint state before raw git inspection.
`mb start --json` is optional when runtime handoff or repo-boundary facts
matter. `mb doctor repair --plan` supplies repair blockers. `mb checkpoint
--plan --json` supplies the checkpoint plan and changed surfaces; it is not
permission to save. `mb validate --json` supplies validation blockers before
the checkpoint is offered.

## Required JSON Fact Paths

The runtime shell must preserve these paths from the workflow source:

- `money_path`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `relationship_health.gaps`
- `update`
- `readiness`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `journal`
- `since_last_check`
- `checkpoint.pending`
- `checkpoint.pending.changed_files`
- `checkpoint.pending.blockers`
- `checkpoint.pending.proposed_subject`
- `summary.changed_files`
- `safety.blocks`
- `proposal.message`
- `validation`

Treat these as facts, not strategy. The runtime may explain what changed,
recommend whether to save, and ask one crystallize question. It must not claim
that a checkpoint, push, proposal, or merge happened unless facts prove it.

## Routing Rules

Hard gates win before closeout: required updates, broken repo wiring, repair
blockers, validation blockers, private-data boundaries, destructive-operation
requests, provider mutation, publishing, spend, and customer contact.

Mid-session save branch: after hard gates, if the intent is a save while the
operator keeps working (not an end or pause), run only the status scan plus `mb
checkpoint --plan`, check changed bet, push, decision, or research files against
`relationship_health.gaps` and offer one named link fix when they match, then
save on approval through `mb checkpoint` and stop. Do not run
crystallize, the final-thought prompt, or the warm close, and never save with raw
git.

After hard gates, when the operator is ending or pausing, close the session in
this order:

1. Status scan: read `mb status --json --peek`, then `mb checkpoint --plan
   --json`, then `mb validate --json`.
2. Checkpoint plan: summarize changed surfaces, proposed subject, validation
   blockers, and whether saving is possible.
3. Session summary: state what happened in business language first. Name
   decisions, research, offer/core changes, pushes, outcomes, and unsaved work.
4. Final thought capture: ask once. Save a brief research note only after
   explicit approval.
5. Crystallize: if meaningful activity happened, run deep crystallize when the
   runtime has a subagent/Task surface; otherwise run crystallize-lite in the
   current thread. Do not silently skip crystallize because the adapter lacks
   Claude's Task tool.
6. Save state: answer "is that it?" with the owner-facing state before
   technical details.
7. Link check: if a changed bet, push, decision, or research file appears in
   `relationship_health.gaps` evidence or records, offer one link fix before
   writing the checkpoint. Name the field and file; ask at most one question.
   Skip this check when no changed file is named by a gap.
8. Approval-gated save: validate the checkpoint subject, ask before saving,
   and save only through `mb checkpoint`.
9. Warm close: end with one sentence naming the most important saved or drafted
   business outcome. Do not plan tomorrow.

Owner-facing save states:

- `drafted`: work exists but is not yet saved as durable business memory.
- `saved locally`: work is saved in the local business folder history.
- `ready to send up`: work is saved locally and ready for shared backup or
  review.
- `sent for review`: work has been sent to the shared proposal/review lane.
- `landed in main`: work is accepted in the main business area.
- `blocked by unrelated cleanup`: the session work is ready, but separate
  cleanup or drift blocks a clean save or handoff.

Use these states even when the underlying facts mention commits, branches,
pull requests, merges, working trees, or remotes. Technical details come after
the business state unless the operator asks for plumbing.

## Read Boundaries

Read deterministic `mb` facts before raw markdown or git details. After the
fact pass, read only files needed for the closeout:

- files named by checkpoint changed-file facts;
- relevant `research/`, `decisions/`, `core/`, `bets/`, `pushes/`, `log/`, and
  `documents/` files changed in the session;
- safe prior crystallize notes when they help avoid repeating the same
  question;
- safe provider-readiness summaries from `mb connect` only when status says
  provider state affects the closeout.

Raw git history is fallback/detail only when `mb` facts are unavailable or when
the runtime needs site-code history the CLI does not expose. Do not inspect
secrets, raw provider exports, raw finance/legal records, raw transcripts,
customer/member records, local runtime settings, private maintainer notes, or
credentials.

## Write Boundaries

The workflow may write business files only after the operator approves the
specific write. Valid write targets live in the business repo:

- `research/` for final thoughts or crystallize notes;
- `decisions/` when the operator explicitly turns an insight into a decision;
- `core/` only when the operator accepts an update to durable truth;
- `bets/`, `pushes/`, `log/`, or `documents/` when the closeout identifies an
  approved session artifact;
- the checkpoint created by `mb checkpoint` after approval.

The workflow source does not authorize raw `git add`, raw `git commit`,
provider writes, publishing, spending, customer contact, public issue/proposal
submission, runtime adapter edits, or Main Branch engine repo changes.

## Approval Gates

Ask before:

- applying updates, repairs, migrations, provider setup, or cleanup;
- creating, editing, moving, deleting, or archiving business files;
- saving final thoughts, crystallize notes, decisions, logs, bets, pushes, or
  core updates;
- validating and saving a checkpoint;
- publishing, opening a public issue, submitting a proposal, spending money,
  mutating provider state, or contacting customers;
- reading or moving private, restricted, local-only, finance, legal, customer,
  member, credential, raw transcript, or raw provider data.

Never ask the operator to paste secrets into repo files or workflow sources.
Never commit raw dumps, full transcripts, private customer/member data,
credential material, session cookies, or unsupported provider exports.

## Handoff Format

When closing a session, include a compact closeout:

```text
Closeout state: <drafted, saved locally, ready to send up, sent for review, landed in main, or blocked by unrelated cleanup>.
Status scan: <status/checkpoint/validate facts read>.
Session summary: <3-6 bullets or one compact paragraph>.
Final thought: <none, captured, or approved research note target>.
Crystallize: <deep, lite, skipped with reason>.
Checkpoint plan: <subject, changed surfaces, blockers, approval needed>.
Warm close: <one sentence>.
```

Use business language first. Avoid "working tree clean", "branch pushed", "PR
merged", or similar plumbing as the lead answer unless the operator asked for
plumbing. The closeout answer should make clear whether the work is drafted,
saved locally, ready to send up, sent for review, landed in main, or blocked by
unrelated cleanup.

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

If generated global Codex skill data, packaged workflow data, or runtime
discovery changes, add package/install and runtime/manual smoke evidence.

## Runtime-Specific Notes

Claude Code may use slash-command-native language and a Task/subagent surface
for deep crystallize when meaningful activity happened. The Task/subagent is
adapter behavior; the shared workflow contract is the status scan, checkpoint
plan, session summary, final thought capture, crystallize intent,
approval-gated save, save-state language, and warm close.

Codex uses global Main Branch skills and natural-language routes. Codex should
run crystallize-lite in-thread or use available subagent tooling when present.
If the current Codex session has no subagent surface, name that limitation and
still produce one specific crystallize question from the session facts. Do not
tell Codex users to run Claude slash commands.

Both runtimes should answer "is that it?" with the owner-facing save state
first, then technical details only as a receipt.
