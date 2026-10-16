# Generated Claude Shell: Ads And Paid Creative

Source workflow: `workflows/mb-ads/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`, `account_change`, `upload_assets`, `budget_change`, `campaign_publish`, `conversion_upload`, `gtm_publish`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_oauth_tokens`, `no_conversion_uploads`, `no_account_identifiers_in_public_examples`

Use from `/mb-ads` when the operator wants paid creative planning, ad copy,
image prompts, video scripts, long-form paid creative, video repurposing for ads,
compliance review, launch plans, launch instrumentation checks, launch checks, optional read-only
account context, or Google Ads Search planning. Preserve the existing Claude
skill's mode language, proof discipline, review workflow, paid-search
launch-plan path, and provider gates.

This snapshot does not replace shipped `.claude/skills/mb-ads/SKILL.md`.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb connect plan`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `money_path.objects.cta_path`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `validation.file_contracts`
- `content_strategy`
- `content_strategy.overall_state`
- `content_strategy.simple_entry_point`
- `content_strategy.layers`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `integrations`
- `measurement`
- `measurement.available`
- `measurement.state`
- `measurement.facts.expected_events`
- `measurement.facts.instrumentation`
- `measurement.blocked_count`
- `measurement.manual_count`
- `relationship_health.gaps`
- `checkpoint.pending`
- `checkpoint.pending.blockers`
- `runtime.codex_cli`
- `runtime.claude_code`
- `state`
- `blocked`
- `manual`
- `evidence`
- `facts.expected_events`
- `facts.instrumentation`
- `facts.provider_state`
- `facts.app_stack`
- `facts.deploy`
- `facts.commerce`
- `facts.email`
- `facts.measurement`
- `recommended_action`
- `source`
- `child_descriptor`

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, provider readiness, measurement readiness,
   site-check readiness, relationship gaps, validation, and checkpoint plan.
2. For mining, scraping, competitor research, transcript extraction, outside
   source collection, thin offers, or unsupported claims, route to `mb-think`
   before drafting paid creative.
3. For landing-page, conversion endpoint, GA4, GTM/dataLayer, Meta pixel,
   booking links, HubSpot/forms, consent, form-submit smoke, or paid
   measurement readiness, route to `mb-site` and use `mb site check` before
   describing traffic as locally ready for operator review.
4. Support static, copy-only, image-only, hook-library, video-scripts,
   long-form-video, review, launch-plan, check, or account-context modes.
   Treat instrumentation as the launch-readiness sub-mode for GA4/GTM/pixels,
   booking links, HubSpot/forms, and submit/booking smoke.
   Short clips or social cuts from a sales video or VSL route to `/mb-organic`.
5. Draft from active offer, audience, voice, content strategy, proof facts,
   relevant research, decisions, active pushes, playbooks, and
   money_path.objects.proof.quality. Do not turn unapproved proof into public
   ad claims.
6. Route coordinated paid work to `pushes/<YYYY-MM-DD-slug>/push.md`, draft
   batches to `pushes/<YYYY-MM-DD-slug>/ads-batch-001.md`, provider or launch
   plans to `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`, research to
   `research/`, and accepted tradeoffs to `decisions/`.
7. For Google Ads Search, use the google-ads-search-launch playbook source and
   official Google Ads docs for load-bearing limits, policy, targeting, and
   feature mechanics. The playbook is a manual recipe, not provider authority.
8. Keep provider gates explicit. Do not publish ads, schedule ads, upload assets,
   perform provider mutation, mutate provider accounts, change budgets, start
   spend, publish GTM, upload conversions, change billing, or contact customers.
   Execution needs explicit approval and runtime evidence for that exact surface.

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

## Handoff Shape

```text
Ads mode: <static, copy-only, image-only, hook-library, video-scripts,
long-form-video, review, launch-plan, instrumentation, check, or account-context>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Source base: <offer, audience, voice, proof, research, push, playbook, account summary, or missing>.
Provider posture: <not needed, read-only, connected, blocked, unsupported, or approval needed>.
Measurement posture: <missing, blocked, ready_for_preview,
ready_for_operator_review, ready, or not checked>.
Proof/privacy posture: <public-safe, internal-only, missing permission,
unsupported claim, or needs summary>.
Artifact route: <push path, ads batch path, playbook run path, research path,
decision path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. New coordinated work uses pushes. Provider
mutation, publishing, spend, uploads, account changes, GTM publishes,
conversion uploads, and customer contact stay approval-gated and manual unless
the exact adapter surface has shipped evidence. Codex support: read-only planning.
Runtime smoke must prove ads writes or provider execution.
