# Generated Codex Workflow Guidance: Organic Content

Source workflow: `workflows/mb-organic/workflow.md`
Runtime support: `codex_cli: read_only_planning`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`

Codex uses the global Main Branch `mb-organic` skill as a read-only planning
and file-guidance route. This guidance is generated from the engine workflow
source and does not claim supported organic drafting writes, publishing,
account mutation, customer contact, or Claude Code entrypoints in Codex.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `validation.file_contracts`
- `content_strategy`
- `content_strategy.overall_state`
- `content_strategy.simple_entry_point`
- `content_strategy.layers`
- `content_strategy.layers.distribution`
- `content_strategy.layers.channels`
- `content_strategy.layers.accounts`
- `content_strategy.layers.people`
- `content_strategy.findings`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `relationship_health.gaps`
- `checkpoint.pending`
- `checkpoint.pending.blockers`
- `runtime.codex_cli`
- `runtime.claude_code`

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, content strategy health,
   proof quality, relationship gaps, validation, and checkpoint plan.
3. For mining handoff, route to `mb-think` in Codex-native language for mining,
   scraping, competitor research, transcript extraction, and outside source
   collection. Organic may plan from accepted `research/` handoffs, operator
   excerpts, approved transcripts, and current business truth.
4. Guide plan, video, carousel, static, sales-video-repurpose, or review modes
   from the shared contract. Use content_strategy.overall_state,
   content_strategy.simple_entry_point, content_strategy.layers, and
   content_strategy.findings before parsing raw strategy files.
   Short clips and social cuts from a sales video or VSL route to `mb-organic`;
   paid ads from it route to `mb-ads`.
5. Codex may draft patch-shaped recommendations, sample copy, review notes,
   and exact file targets, then stop before changing files.
6. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/organic-batch-001.md`, and
   `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`.
7. If the operator wants the proposed content applied, route them to Claude
   Code `/mb-organic` or another supported write surface until Codex
   organic-write smoke proves this route. Do not run checkpoint commands or
   post-change validation as if Codex edited files.
8. Keep source/privacy boundaries explicit. Never paste raw provider exports,
   private DMs, gated community threads, raw customer/member records, raw
   transcripts, account details, session cookies, finance/legal records, or
   secrets.
9. Do not publish, schedule, upload to accounts, mutate provider accounts,
   spend, auto-DM, auto-reply, contact customers, or execute provider setup.

## Push Links

When creating or first writing a push, ask once:
"Which bet does this push serve, and which existing decision or research supports it?"
Offer active bets and recent decisions and research by name from status facts or files already read.
If this is a measurable trial with a review or cut point and no covering bet,
route to `mb-bet` before execution.
Accept "none yet" and continue. For a deliberate one-off with no bet, write
`linked_bets: []` and a one-line `no_bet_reason`. On an approved write, put the
chosen repo-relative paths in `linked_bets`, `linked_decisions`, and
`linked_research` on the push; add its path to `linked_pushes` on each named
bet, decision, and research file. Leave unanswered links empty; do not invent
a reason. Mirror typed links in `## Related links` as relative Markdown links.
Use docs/business-connections.md; never infer links from body-only references.

For Codex, include these as proposed file edits and stop before applying.

## Handoff Shape

```text
Organic mode: <plan, video, carousel, static, sales-video-repurpose, or review>.
Facts read: <status/start/content-strategy/proof/checkpoint facts>.
Source base: <offer, audience, voice, research, sales video, push, account, or missing>.
Channel/account: <platform/account/person layer or not selected>.
Content strategy: <healthy, thin, stale, disconnected, or missing>.
Proof/privacy posture: <public-safe, internal-only, missing permission, or needs summary>.
Artifact route: <push path, batch path, playbook path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. New coordinated work uses pushes. Legacy content
structures are migration input only. Runtime smoke is required before docs say
this workflow is supported for Codex writes.
