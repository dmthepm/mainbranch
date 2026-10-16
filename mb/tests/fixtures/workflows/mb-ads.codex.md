# Generated Codex Workflow Guidance: Ads And Paid Creative

Source workflow: `workflows/mb-ads/workflow.md`
Runtime support: `codex_cli: read_only_planning`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`, `account_change`, `upload_assets`, `budget_change`, `campaign_publish`, `conversion_upload`, `gtm_publish`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_oauth_tokens`, `no_conversion_uploads`, `no_account_identifiers_in_public_examples`

Codex uses the global Main Branch `mb-ads` skill as a read-only planning and
file-guidance route. This guidance is generated from the engine workflow source
and does not claim supported paid creative writes, provider mutation, asset
uploads, publishing, spend, account changes, GTM publishes, conversion uploads,
customer contact, or Claude Code entrypoints in Codex.

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

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate provider details into business language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, provider readiness,
   measurement readiness, site-check readiness, relationship gaps, validation,
   and checkpoint plan.
3. For mining, scraping, competitor research, transcript extraction, outside
   source collection, thin offers, or unsupported claims, route to `mb-think`
   in Codex-native language before drafting paid creative.
4. For landing-page, conversion endpoint, GA4, GTM/dataLayer, Meta pixel,
   booking links, HubSpot/forms, consent, form-submit smoke, or paid
   measurement readiness, route to `mb-site` in Codex-native language and use
   `mb site check` before describing traffic as locally ready for operator
   review.
5. Guide static, copy-only, image-only, hook-library, video-scripts,
   long-form-video, review, launch-plan, check, or account-context modes from
   the shared contract. Treat instrumentation as the launch-readiness sub-mode.
   Codex may draft patch-shaped recommendations, sample copy, review notes, and
   launch-plan specs. Name exact file targets, then stop before changing files
   or running provider tools.
6. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/ads-batch-001.md`,
   `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`, `research/`, and
   `decisions/`.
7. For Google Ads Search, use the google-ads-search-launch playbook source and
   official Google Ads docs for load-bearing limits, policy, targeting, and
   feature mechanics. The playbook remains draft/manual and blocked from direct
   Codex execution by provider gates.
8. If the operator wants proposed ad or launch-plan files applied, route them
   to Claude Code `/mb-ads` or another supported write surface until Codex
   ads-write smoke proves this route. Do not run checkpoint commands,
   post-change validation, provider tools, upload steps, campaign actions, GTM
   actions, budget changes, or customer contact as if Codex edited or executed
   the work.
9. Keep provider gates explicit. Do not publish ads, schedule ads, upload assets,
   mutate provider accounts, change budgets, start spend, publish GTM, upload
   conversions, change billing, or contact customers.

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

Use business language first. Runtime smoke is required before docs say this
workflow is supported for Codex paid creative writes, provider mutation,
uploads, publishing, spend, account changes, GTM publishes, conversion uploads,
or customer contact.
