# Generated Claude Shell: End Checkpoint Save

Source workflow: `workflows/mb-end/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_raw_finance_legal_records`

Use from `/mb-end` when the operator is done, pausing, closing a work block, or
asking whether the work is saved. Preserve slash-command-native language for
Claude Code only.

This snapshot does not replace shipped `.claude/skills/mb-end/SKILL.md`.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb checkpoint --plan --json`
- `mb validate --json`

## Required JSON Fact Paths

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

## Routing

Mid-session save vs close: if the operator only wants to save progress and keep
working — "save", "checkpoint this", "yes save" mid-flow — this is a save, not a
close. Run `mb checkpoint --plan`, save on approval through `mb checkpoint`, and
return them to work. Never save with raw git. Use the full closeout below only
when the session is actually ending or pausing.

1. Run a status scan first. Use deterministic status, checkpoint, validation,
   readiness, drift, recent-work, and runtime facts before reading raw git
   details.
2. Build the checkpoint plan from `mb checkpoint --plan --json`; use
   `mb validate --json` for blockers and cite `mb doctor repair --plan` when
   repairs are needed.
3. Give a short session summary in business language: decisions, research,
   offers, pushes, outcomes, changed core truth, and unsaved work.
4. Ask once for final thought capture before closeout. Offer to save a brief
   research note only after operator approval.
5. Run crystallize when meaningful activity happened. Claude may use a Task
   subagent for deep crystallize; light sessions may use crystallize-lite.
6. Present save state before plumbing: drafted, saved locally, ready to send
   up, sent for review, landed in main, or blocked by unrelated cleanup.
7. Make checkpointing an approval-gated save. Validate the subject, ask before
   saving, and use `mb checkpoint`, not raw git commands.
8. End with a warm close: one sentence naming the most important saved or
   drafted business outcome, without tomorrow planning.

## Handoff Shape

```text
Closeout state: <one owner-facing save state>.
Status scan: <status/checkpoint/validate facts read>.
Session summary: <3-6 bullets or one compact paragraph>.
Final thought: <none, captured, or approved research note target>.
Crystallize: <deep, lite, skipped with reason>.
Checkpoint plan: <subject, changed surfaces, blockers, approval needed>.
Warm close: <one sentence>.
```

Use business language first. Git, branch, pull request, merge, and working-tree
details are secondary unless the operator asks for plumbing.
