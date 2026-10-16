# Generated Claude Shell: Organic Content

Source workflow: `workflows/mb-organic/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`

Use from `/mb-organic` when the operator wants organic content planning,
scripts, carousels, static posts, sales-video repurposing, or content review.
Preserve the existing Claude skill's mode language, mining handoff, voice
adaptation, content strategy integration, artifact routing, and source/privacy
boundaries.

This snapshot does not replace shipped `.claude/skills/mb-organic/SKILL.md`.

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

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, content strategy health, proof quality,
   relationship gaps, validation, and checkpoint plan.
2. For mining handoff, route to `mb-think` for mining, scraping, competitor
   research, transcript extraction, and outside source collection. Organic drafts from accepted
   `research/` handoffs, operator excerpts, approved transcripts, and current
   business truth.
3. Support plan, video, carousel, static, sales-video-repurpose, or review
   modes. Use content_strategy.overall_state, content_strategy.simple_entry_point,
   content_strategy.layers, and content_strategy.findings before parsing raw
   strategy files.
4. Draft from active offer, audience, voice, content strategy, relevant
   channel/account/person layers, research, sales-video notes, active pushes,
   and money_path.objects.proof.quality. Do not call proof good, bad,
   persuasive, high-converting, or ready to win.
5. Route coordinated content to `pushes/<YYYY-MM-DD-slug>/push.md`, draft
   batches to `pushes/<YYYY-MM-DD-slug>/organic-batch-001.md`, and provider
   mechanics to `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` as plans.
6. Use `mb validate --cross-refs --json` after approved push, draft, playbook,
   typed-link, or related-link edits. Use the checkpoint plan before offering
   an approval-gated save.
7. Keep source/privacy boundaries explicit. Never paste raw provider exports,
   private DMs, gated community threads, raw customer/member records, raw
   transcripts, account details, session cookies, finance/legal records, or
   secrets.
8. Do not publish, schedule, upload to accounts, mutate provider accounts,
   spend, auto-DM, auto-reply, contact customers, or execute provider setup.

## Push Links

When creating or first writing a push, ask once:
"Which bet does this push serve, and which existing decision or research supports it?"
Offer active bets and recent decisions and research by name from status facts or files already read.
Accept "none yet" and continue. For a deliberate one-off with no bet, write
`linked_bets: []` and a one-line `no_bet_reason`. On an approved write, put the
chosen repo-relative paths in `linked_bets`, `linked_decisions`, and
`linked_research` on the push; add its path to `linked_pushes` on each named
bet, decision, and research file. Leave unanswered links empty; do not invent
a reason. Mirror typed links in `## Related links` as relative Markdown links.
Use docs/business-connections.md; never infer links from body-only references.

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
structures are migration input only. Codex support stays read-only planning
until runtime smoke proves organic drafting writes.
