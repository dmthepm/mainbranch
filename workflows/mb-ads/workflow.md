---
name: mb-ads
title: Ads And Paid Creative
description: "Plan and review paid creative, launch plans, launch instrumentation checks, account-readiness checks, and provider-safe Google Ads search plans from deterministic Main Branch facts. Short clips and organic social cuts from a sales video go to /mb-organic; keep paid video repurposing here."
loops:
  - sense
  - ship
  - reflect
runtime_support:
  claude_code: supported_shell
  codex_cli: read_only_planning
runtime_surfaces:
  claude_code: .claude/skills/mb-ads/SKILL.md
  codex_cli: global Main Branch mb-ads skill
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb connect doctor --json
  - mb connect plan
  - mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json
  - mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json
  - mb validate --cross-refs --json
  - mb checkpoint --plan --json
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - money_path.objects.cta_path
  - money_path.objects.channel_strategy
  - money_path.objects.active_push
  - validation.file_contracts
  - content_strategy
  - content_strategy.overall_state
  - content_strategy.simple_entry_point
  - content_strategy.layers
  - ranked_actions
  - update
  - readiness
  - drift.items
  - integrations
  - measurement
  - measurement.available
  - measurement.state
  - measurement.facts.expected_events
  - measurement.facts.instrumentation
  - measurement.blocked_count
  - measurement.manual_count
  - relationship_health.gaps
  - checkpoint.pending
  - checkpoint.pending.blockers
  - runtime.codex_cli
  - runtime.claude_code
  - state
  - blocked
  - manual
  - evidence
  - facts.expected_events
  - facts.instrumentation
  - facts.provider_state
  - facts.app_stack
  - facts.deploy
  - facts.commerce
  - facts.email
  - facts.measurement
  - recommended_action
  - source
  - child_descriptor
approval_gates:
  - updates_repairs_migrations
  - file_writes
  - checkpoint
  - provider_mutation
  - publishing_or_spend
  - customer_contact
  - private_data
  - destructive_operations
  - structured_collection
  - public_issue_or_proposal
  - account_change
  - upload_assets
  - budget_change
  - campaign_publish
  - conversion_upload
  - gtm_publish
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_raw_transcripts
  - no_customer_member_data
  - no_private_runtime_settings
  - no_private_dms_or_gated_communities
  - no_raw_finance_legal_records
  - no_oauth_tokens
  - no_conversion_uploads
  - no_account_identifiers_in_public_examples
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Ads And Paid Creative

## Intent And Triggers

Use this workflow when the operator wants paid creative, ad copy, image prompts,
video scripts, long-form paid creative, creative variations, compliance review,
launch planning, launch instrumentation checks, launch checks, read-only
account context, or a Google Ads Search launch plan. Ads work is Ship work, but
this shared contract separates planning, drafting, review, and read-only checks
from provider mutation, publishing, uploads, spend, account changes, GTM
publishes, conversion uploads, and customer contact.

Repurpose a video here when the operator wants paid ad creative from it. Route
short clips, social cuts, and organic posts from a sales video or VSL to
`mb-organic`.

Supported modes:

- `static`: draft image-ad hooks, primaries, headlines, and image prompts.
- `copy-only`: draft ad copy for existing approved creative.
- `image-only`: prepare image prompts or approved provider-generation plans.
- `hook-library`: generate creative variations from accepted offer truth.
- `video-scripts`: draft short paid video scripts.
- `long-form-video`: draft paid sales video or VSL-style paid creative.
- `review`: run quality, proof, policy, visual, voice, and substantiation review.
- `launch-plan`: prepare provider-safe launch plans, including Google Ads Search.
- `instrumentation`: route GA4, GTM, Meta pixel, booking links, HubSpot/form
  tests, conversion-event mapping, and traffic-quality questions to `mb-site`
  / `mb site check` before campaign launch claims.
- `check`: review outcomes, operator exports, or read-only account facts.
- `account-context`: optionally pull compact read-only account context when a
  shipped provider path and operator approval exist.

Research, mining, scraping, transcript extraction, competitor teardown, and
new market synthesis route to `mb-think` before this workflow drafts from the
findings. Landing-page, conversion endpoint, GTM/dataLayer, consent, and
paid-traffic measurement readiness route to `mb-site` and `mb site check`
before a launch plan describes traffic as locally ready for operator review.

## Required Mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb connect plan`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Read `mb status --json --peek` before direct markdown reads. Use `mb start
--json` when runtime readiness, repo boundary, or handoff facts matter. Use
`mb doctor repair --plan` when status facts name repair or migration blockers.
Use `mb connect plan` or `mb connect doctor --json` before provider setup,
read-only account context, Google/Workspace, Meta Ads, Google Ads, GTM, upload,
publishing, or account-change discussion. Use `mb launch check` when a site repo
exists and the request asks broad launch readiness, deploy rail, commerce,
email, or smoke-test posture. Use `mb site check` when paid traffic, Google
Ads, measurement, or GTM detail is part of the request.

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

Use `money_path.objects.proof.quality` before turning proof into public ad
claims. Use `content_strategy.*` and active push facts to decide whether paid
work should create demand, amplify a proven owned/organic asset, or drive a
direct conversion path. Use `integrations` and `measurement.*` from status as
business-repo readiness facts. Use top-level `state`, `blocked`, `manual`,
`evidence`, `facts.expected_events`, `facts.instrumentation`,
`facts.provider_state`, `source`, and `child_descriptor` from
`mb site check ... --json` for site-repo measurement readiness. Use
`facts.app_stack`, `facts.deploy`, `facts.commerce`, `facts.email`,
`facts.measurement`, and `recommended_action` from `mb launch check ... --json`
for broad launch truth. Do not invent `ready_for_launch`.

## Routing Rules

Start with deterministic facts, then read only the business, research, push,
site, playbook, or account-summary files needed for the requested ad shape.

Mode routing:

1. For mining, scraping, competitor research, transcript extraction, or outside
   source collection, route to `mb-think`. Ads may draft from accepted
   `research/` handoffs, operator excerpts, approved transcripts, and current
   business truth.
2. For `static`, `copy-only`, `image-only`, `hook-library`, `video-scripts`,
   and `long-form-video`, resolve the active offer and draft from accepted
   offer, audience, voice, content strategy, proof facts, relevant research,
   decisions, and active push facts. Route thin offers or unsupported outcome
   claims to `mb-think` before copy.
3. For image-provider work, check provider readiness first. Preparing prompts
   is allowed; generating, uploading, publishing, or storing provider assets
   requires explicit approval and the shipped provider path named by `mb`.
4. For `review`, report P1/P2/P3 quality, policy, proof, voice, visual, and
   substantiation findings. Proposed edits are drafts until the operator
   approves file changes.
5. For `launch-plan` and `instrumentation`, separate campaign materials from
   provider execution. Analytics tags, booking widgets, HubSpot/forms, and
   conversion events may be detectable in local markup, but launch still needs
   submit/booking smoke, provider review, and explicit approval.
   Include settings, keywords, negatives, ad assets, sitelinks, callouts,
   structured snippets, manual provider steps, approval gates, budget cap,
   review window, and continue/change/stop criteria.
6. For Google Ads Search, load the reusable
   `google-ads-search-launch` playbook source and the Google Ads campaign-plan
   reference. Verify load-bearing platform facts against official Google Ads
   docs when limits, policy, targeting, or feature mechanics matter.
7. For `check`, use status facts, outcomes, logs, sanitized exports, or
   approved read-only account summaries. Recommend continue, change, or stop;
   do not mutate campaigns or budgets.
8. For `account-context`, ask before pulling compact read-only provider facts.
   If no shipped provider adapter or approved runtime tool exists, continue
   from repo truth, sanitized exports, screenshots, or manual operator notes.

Offer context resolves from current `mb` facts and current files. In
multi-offer repos, read the named offer under `core/offers/<offer>/` when
present. In single-offer repos, use `core/offer.md`. If active offer context is
unclear, ask instead of inferring from legacy state.

## Read Boundaries

Read:

- deterministic status, start, repair, connection, measurement, validation,
  relationship, checkpoint, and site-check facts first;
- active offer/audience files, `core/voice.md`, `core/content-strategy.md`,
  relevant content strategy layers, approved proof summaries, active push files,
  decisions, research, logs, documents, and reusable playbook sources that
  directly support the ad or launch plan;
- sanitized provider exports, screenshots, or compact read-only account
  summaries only when the operator approves that source and private account
  details are not copied into durable public artifacts.

Do not read or paste OAuth tokens, API keys, session cookies, raw provider
exports, conversion uploads, account identifiers, billing details, private DMs,
gated community content, raw customer/member records, raw transcripts,
finance/legal records, or private runtime settings. Route sensitive material
through approved summaries, manifests, or operator-provided excerpts.

## Write Boundaries

This workflow may write business files only after approval. Durable write
targets are:

- `pushes/<YYYY-MM-DD-slug>/push.md` for coordinated paid creative, launch,
  or proof-run work;
- `pushes/<YYYY-MM-DD-slug>/ads-batch-001.md` or a similar draft artifact for
  paid creative batches;
- `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` for provider setup,
  launch, approval, review-window, or resource-delivery run records;
- `research/` files for paid-search, creative, competitor, customer-language,
  or account-summary handoffs;
- `decisions/` files for accepted launch, budget, conversion-path, or provider
  tradeoffs;
- typed links and body-level `## Related links` mirrors on directly related
  pushes, bets, decisions, research, outcomes, logs, or documents;
- approved checkpoints after validation and checkpoint planning.

Do not publish ads, schedule ads, upload assets to ad accounts, start or change
spend, create campaigns, unpause campaigns, change budgets, publish GTM,
upload conversions, mutate provider accounts, change billing, contact
customers, or execute provider setup. Planning manual steps is allowed;
execution needs explicit provider gates outside this workflow.

New coordinated work uses `pushes/`. If legacy content records exist in old
structures, present repair or migration planning before creating new paid work
there.

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

## Approval Gates

Always ask before:

- `updates_repairs_migrations`
- `file_writes`
- `checkpoint`
- `provider_mutation`
- `publishing_or_spend`
- `customer_contact`
- `private_data`
- `destructive_operations`
- `structured_collection`
- `public_issue_or_proposal`
- `account_change`
- `upload_assets`
- `budget_change`
- `campaign_publish`
- `conversion_upload`
- `gtm_publish`

Approval must be explicit before creating or editing pushes, drafts, playbooks,
typed links, related-link mirrors, migrations, repair applies, structured
source collection, public issue/proposal submission, checkpoints, read-only
account pulls, provider uploads, account changes, GTM publishes, campaign
publishes, conversion uploads, or budget/spend changes.

## Handoff Format

```text
Ads mode: <static, copy-only, image-only, hook-library, video-scripts, long-form-video, review, launch-plan, instrumentation, check, or account-context>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Source base: <offer, audience, voice, proof, research, push, playbook, account summary, or missing>.
Provider posture: <not needed, read-only, connected, blocked, unsupported, or approval needed>.
Measurement posture: <missing, blocked, ready_for_preview, ready_for_operator_review, ready, or not checked>.
Proof/privacy posture: <public-safe, internal-only, missing permission, unsupported claim, or needs summary>.
Artifact route: <push path, ads batch path, playbook run path, research path, decision path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

## Validation Commands

After approved push, draft, playbook, research, decision, typed-link, or
related-link edits:

1. Run `mb validate --cross-refs --json`.
2. If paid-traffic measurement or Google Ads launch readiness is part of the
   work and a site repo exists, run
   `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`.
3. If the checkpoint surface is available, run `mb checkpoint --plan --json`.
4. Show blockers in owner-facing language before offering to save.
5. Save only after approval, using checkpoint tooling rather than raw git
   commands.
6. End by rerunning `mb status --json --peek` when the operator needs refreshed
   provider, measurement, active push, MoneyPath, or checkpoint state.

## Runtime-Specific Notes

Claude Code uses `.claude/skills/mb-ads/SKILL.md` as the project-local shell
over this workflow source. The Claude shell may write approved business files
and run approved review/provider-readiness steps only within the gates above.
Provider mutation, publishing, spend, uploads, account changes, GTM publishes,
conversion uploads, and customer contact remain manual or provider-native until
a shipped adapter has tests, approval gates, and runtime smoke for the exact
surface.

Codex uses the global Main Branch `mb-ads` skill as read-only planning and
file-guidance. Codex may inspect facts, propose copy, summarize review
findings, and name exact file targets, then stop before changing files or
running provider tools. Runtime smoke is required before docs say this workflow
is supported for Codex ads writes, provider mutation, uploads, publishing,
spend, account changes, GTM publishes, conversion uploads, or customer contact.
