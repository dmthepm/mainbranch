# Generated Codex Workflow Guidance: Bet Lifecycle

Source workflow: `workflows/mb-bet/workflow.md`
Runtime support: `codex_cli: read_only_planning`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_raw_ledger_rows`

Codex uses the global Main Branch `mb-bet` skill as a read-only planning and
file-guidance route. This guidance is generated from the engine workflow source
and does not claim supported lifecycle writes or Claude Code entrypoints in
Codex.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`
- `mb similar-bets "<thesis>" --repo . --json`
- `mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md --json`
- `mb books exposure --repo . --active --json`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `brain.bets`
- `brain.bets.active`
- `brain.bets.due_soon`
- `brain.bets.overdue`
- `brain.bets.exit_criteria`
- `relationship_health.sections.bets`
- `relationship_health.gaps`
- `checkpoint.pending`
- `checkpoint.pending.blockers`
- `books`
- `runtime.codex_cli`
- `runtime.claude_code`

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, validation, relationship
   health, checkpoint plan, similar-bets for repeated material theses, and
   aggregate exposure for financially material bets.
3. Bet is a time-boxed wager, not an offer or push. Offers are durable things
   sold; pushes coordinate execution. Bets carry hypothesis, appetite, target,
   deadline, evidence, kill or double-down logic, and verdict.
   For a current channel trial with a measurable target and review or cut point,
   check `brain.bets` and `bets/` first. Use and link a covering bet; otherwise
   offer a bet plan from known facts before execution. Ask only for a missing
   target, review or cut point, or unclear owner. Routine channel work without
   a wager stays in its channel workflow; Codex keeps this route read-only.
4. Guide new, update, close, list, and narrate modes from the shared contract.
   Codex may draft patch-shaped recommendations and exact file targets, then
   stop before changing files.
5. Keep the strict contract for `bets/YYYY-MM-DD-slug.md`: frontmatter fields,
   body sections, typed links, reverse `linked_bets`, and `## Related links`.
6. If the operator wants the proposed changes applied, route them to Claude
   Code `/mb-bet` or another supported write surface until Codex lifecycle-write
   smoke proves this route. Do not run checkpoint commands or post-change
   validation as if Codex edited files.
7. For financially material bets, use aggregate exposure only. Never paste raw
   ledger rows, payees, account names, vault paths, transaction memos, provider
   exports, customer/member records, or secrets.
8. Public-safe narration must come from accepted repo truth. Do not invent
   metrics, results, testimonials, channels, or proof. If `public: false`, ask
   before drafting public copy.
9. Do not publish, spend, contact customers, mutate providers, create dashboard
   work, or promote bet learning into offer truth without accepted evidence,
   an accepted decision, and explicit approval.

## Handoff Shape

```text
Bet mode: <new, update, close, list, or narrate>.
Facts read: <status/start/validate/relationship/exposure/similar-bets facts>.
Bet: <path, status, deadline, appetite, metric, target>.
Evidence: <new evidence, missing evidence, or measured result>.
Exit posture: <kill, double-down, continue, close, or unclear>.
Connections: <decisions, research, pushes, outcomes, offers, or none>.
Public posture: <public-safe, private, needs approval, or not narration>.
Write plan: <files to create/edit or none>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Keep legacy campaign links compatibility-only;
new execution routes through pushes. Runtime smoke is required before docs say
this lifecycle is supported for Codex writes.
