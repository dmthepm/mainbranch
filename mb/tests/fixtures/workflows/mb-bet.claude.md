# Generated Claude Shell: Bet Lifecycle

Source workflow: `workflows/mb-bet/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_raw_ledger_rows`

Use from `/mb-bet` when the operator wants to create, update, close, list, or
narrate bets. Preserve the existing Claude skill's mode language, approval
gates, artifact routing, and finance/privacy boundaries.

This snapshot does not replace shipped `.claude/skills/mb-bet/SKILL.md`.

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

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, validation, relationship health,
   checkpoint plan, similar-bets for repeated material theses, and aggregate
   exposure for financially material bets.
2. Bet is a time-boxed wager, not an offer or push. Offers are durable things
   sold; pushes coordinate execution. Bets carry hypothesis, appetite, target,
   deadline, evidence, kill or double-down logic, and verdict.
   For a current channel trial with a measurable target and review or cut point,
   check `brain.bets` and `bets/` first. Use and link a covering bet; otherwise
   offer to frame one from known facts before execution. Ask only for a missing
   target, review or cut point, or unclear owner, and get approval before writing.
   Routine channel work without a wager stays in its channel workflow.
3. Support new, update, close, list, and narrate modes. Create or edit
   `bets/YYYY-MM-DD-slug.md` only after approval, and keep the strict contract:
   frontmatter fields, body sections, typed links, reverse `linked_bets`, and
   `## Related links`.
4. For updates, append dated evidence and links without filling `result` unless
   there is a measured result. For close, record verdict, learning, outcomes,
   and graduation route without rewriting failed bets as success.
5. Use `mb validate --cross-refs --json` after bet or link edits. Use the
   checkpoint plan before offering an approval-gated save.
6. For financially material bets, use aggregate exposure only. Never paste raw
   ledger rows, payees, account names, vault paths, transaction memos, provider
   exports, customer/member records, or secrets.
7. Public-safe narration must come from accepted repo truth. Do not invent
   metrics, results, testimonials, channels, or proof. If `public: false`, ask
   before drafting public copy.
8. Do not publish, spend, contact customers, mutate providers, create dashboard
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
new execution routes through pushes. Codex support stays read-only planning
until runtime smoke proves bet lifecycle writes.
