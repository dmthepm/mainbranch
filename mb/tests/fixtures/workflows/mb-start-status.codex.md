# Generated Codex Workflow Guidance: Daily Start And Status

Source workflow: `workflows/mb-start-status/workflow.md`
Runtime support: `codex_cli: owner_loop_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `status_marker`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_customer_member_data`, `no_private_runtime_settings`, `no_raw_finance_legal_records`

Codex is first-class for the proven owner loop only. This guidance is generated
from the engine workflow source for business-repo `AGENTS.md`; the business repo
does not need to contain `workflows/mb-start-status/workflow.md`. Treat this rendered
route as the Codex shell for natural-language daily operating tasks. It does not
claim Claude Code runtime entrypoints work inside Codex or that all Main Branch
workflows are available in Codex.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`

## Required JSON Fact Paths

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

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep writes approval-gated, and translate git/provider details into business language.
2. Run hard gates before routing: required updates, runtime mismatch, repair blockers, readiness blockers, private-data boundaries, unsafe provider operations, and destructive-operation requests.
3. Use `ranked_actions`, `since_last_check`, `git_activity`, `journal`, `money_path`, `content_strategy`, `validation.file_contracts`, `onboarding`, `readiness`, `update`, `drift.items`, and `brain.bets` as cited facts. Recent activity and `since_last_check` answer what changed without a separate latest or changelog index.
4. Route offer-shape gaps from `validation.file_contracts` to `mb-think` after hard gates, and ask before durable writes.
5. Use due-soon and overdue bet deadlines, missing-exit criteria, triggered failure signals, and triggered double-down signals for update, kill, close, double-down, or narrate routing.
6. Present one clear business route and the signal behind it. Mutate the status marker only when the operator explicitly approves recording the daily check-in.
7. Ask before business-file writes, checkpoints, repairs, updates, migrations, provider mutation, publishing, spend, customer contact, destructive operations, or public issue/proposal submission.

## Handoff Shape

```text
Daily state: <ready, needs attention, blocked, or not a Main Branch repo>.
Facts read: <status/start/repair facts used>.
What changed: <since-last-check or journal summary>.
Main signal: <ranked action, readiness, drift, MoneyPath, content strategy, or onboarding fact>.
Recommended route: <one business route and why>.
Approval needed before writes: <yes/no and what action>.
```

Use business language first. Technical commands, runtime wiring, provider refs,
and file paths are receipts after the owner-facing state unless the operator asks
for plumbing. Do not tell Codex users to run Claude Code entrypoints. Runtime
smoke is required before docs say this selected workflow is supported in Codex.
