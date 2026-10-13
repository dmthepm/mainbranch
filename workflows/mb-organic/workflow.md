---
name: mb-organic
title: Organic Content
description: "Plan organic content, route mining handoffs, draft scripts, review source/privacy boundaries, and name approval-gated artifact writes from deterministic Main Branch facts."
loops:
  - sense
  - ship
runtime_support:
  claude_code: supported_shell
  codex_cli: read_only_planning
runtime_surfaces:
  claude_code: .claude/skills/mb-organic/SKILL.md
  codex_cli: global Main Branch mb-organic skill
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb validate --cross-refs --json
  - mb checkpoint --plan --json
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - money_path.objects.channel_strategy
  - money_path.objects.active_push
  - validation.file_contracts
  - content_strategy
  - content_strategy.overall_state
  - content_strategy.simple_entry_point
  - content_strategy.layers
  - content_strategy.layers.distribution
  - content_strategy.layers.channels
  - content_strategy.layers.accounts
  - content_strategy.layers.people
  - content_strategy.findings
  - ranked_actions
  - update
  - readiness
  - drift.items
  - relationship_health.gaps
  - checkpoint.pending
  - checkpoint.pending.blockers
  - runtime.codex_cli
  - runtime.claude_code
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
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_raw_transcripts
  - no_customer_member_data
  - no_private_runtime_settings
  - no_private_dms_or_gated_communities
  - no_raw_finance_legal_records
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Organic Content

## Intent And Triggers

Use this workflow when the operator wants to create organic content scripts,
social posts, carousels, static posts, newsletter or community planning, or
creator-style excerpts from sales videos. Organic content is Ship work: drafts
and plans may become business artifacts, but posting, scheduling, DM automation,
reply automation, account mutation, and customer contact stay outside this
workflow.

Supported modes:

- `plan`: choose topics, channels, account fit, and a content batch route.
- `video`: draft Reels, TikTok, Shorts, or creator-style scripts.
- `carousel`: draft slide-by-slide carousel copy.
- `static`: draft a single post or caption.
- `sales-video-repurpose`: turn approved sales-video material into short-form
  clips, excerpts, carousel adaptations, or post drafts.
- `review`: check drafts against voice, proof, source, privacy, CTA, and
  approval boundaries.

Mining, scraping, competitor research, transcript extraction, and public/source
collection are not organic drafting. Route those to `mb-think` first so source
observations land in `research/` before this workflow drafts from them.

## Required Mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Read `mb status --json --peek` before direct markdown reads. Use `mb start
--json` when runtime readiness, repo boundary, or handoff facts matter. Use `mb
doctor repair --plan` when status facts name repair or migration blockers. Use
cross-reference validation after push, playbook, or related-link edits. Use
checkpoint planning before offering to save approved content work.

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

Use `content_strategy.overall_state`, `simple_entry_point`, `layers`, and
`findings` as the deterministic source for strategy health before parsing raw
strategy files. Use `money_path.objects.proof.quality` before turning proof
into posts, videos, outcome claims, or social proof. Treat proof facts as
signals, not conversion judgment.

## Routing Rules

Start with deterministic facts, then read only the content source files needed
for the requested channel, account, offer, person, push, or draft.

Mode routing:

1. For mining, scraping, competitor research, transcript extraction, or outside
   source collection, route to `mb-think`. Organic may receive a research
   handoff from `research/`, but it does not collect or scrape source material.
2. For `plan`, use content strategy health, ranked actions, active push facts,
   and account/channel layers to recommend one content route. Ask only for
   missing essentials: target audience, offer or CTA, channel/account, topic,
   batch name, and review moment.
3. For `video`, `carousel`, and `static`, draft from accepted repo truth:
   offer, audience, voice, content strategy, proof facts, relevant research,
   active push, channel/account layers, and person voice when named.
4. For `sales-video-repurpose`, use only approved sales-video material,
   transcripts, operator excerpts, or research handoffs. Route source ingestion
   or transcript extraction back to `mb-think`.
5. For `review`, check source support, proof claims, privacy, voice, platform
   fit, CTA, and publishing boundaries. Do not describe a draft as
   high-converting or ready to win.

Offer context resolves from current `mb` facts and current files. In multi-offer
repos, read the named offer under `core/offers/<offer>/` when present. In
single-offer repos, use `core/offer.md`. If active offer context is unclear, ask
instead of inferring from legacy state.

## Read Boundaries

Read:

- deterministic status, start, content strategy, proof-quality, relationship,
  and checkpoint facts first;
- `core/content-strategy.md`;
- relevant layers under `core/marketing/distribution-strategy.md`,
  `core/marketing/channels/<channel>.md`,
  `core/marketing/accounts/<platform>-<account>.md`, and
  `core/people/<person>.md` when the work names a channel, account, person, or
  weekly content plan;
- `core/voice.md`, active offer/audience files, and approved proof summaries;
- selected research files, sales-video notes, active push files, playbooks,
  documents, and logs when they directly support the draft.

Do not read or paste raw provider exports, private DMs, gated community
threads, raw customer/member records, raw transcripts, account details, session
cookies, finance/legal records, secrets, or private local runtime settings.
Route sensitive material through approved summaries, manifests, or operator
provided excerpts.

## Write Boundaries

This workflow may write business files only after approval. Durable write
targets are:

- `pushes/<YYYY-MM-DD-slug>/push.md` for coordinated content pushes;
- `pushes/<YYYY-MM-DD-slug>/organic-batch-001.md` or a similar batch artifact
  for drafted organic scripts;
- `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` for comment-keyword,
  DM-keyword, reply/link, resource-delivery, newsletter-send, or provider setup
  plans;
- typed links and body-level `## Related links` mirrors on directly related
  pushes, research, decisions, bets, outcomes, logs, or documents;
- approved checkpoints after validation and checkpoint planning.

Do not publish posts, schedule posts, send newsletters, auto-DM, auto-reply,
contact customers, mutate provider accounts, upload assets to accounts, spend
money, or execute provider setup. Drafting a CTA or resource-delivery mechanic
is allowed as a plan; execution needs explicit provider gates outside this
workflow.

New coordinated work uses `pushes/`. If legacy content records exist in old
structures, present repair or migration planning before creating new content
there.

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

Approval must be explicit before creating or editing pushes, drafts, playbooks,
typed links, related-link mirrors, migrations, repair applies, structured
source collection, public issue/proposal submission, or checkpoints.

## Handoff Format

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

## Validation Commands

After approved push, draft, playbook, typed-link, or related-link edits:

1. Run `mb validate --cross-refs --json`.
2. If the checkpoint surface is available, run `mb checkpoint --plan --json`.
3. Show blockers in owner-facing language before offering to save.
4. Save only after approval, using checkpoint tooling rather than raw git
   commands.
5. End by rerunning `mb status --json --peek` when the operator needs refreshed
   content strategy, active push, or checkpoint state.

## Runtime-Specific Notes

Claude Code uses `.claude/skills/mb-organic/SKILL.md` as the project-local shell
for this workflow. Preserve the existing mode language, mining handoff, voice
adaptation, content strategy integration, sales-video repurposing, artifact
routing, approval gates, and source/privacy boundaries from that shell.

Codex uses the global Main Branch `mb-organic` skill generated from this
workflow source. Codex support remains read-only planning and file guidance
until runtime smoke proves organic drafting writes. It may inspect deterministic
facts, explain content strategy and proof/privacy gaps, propose guarded drafts,
review existing drafts, and name exact file targets, but it must not claim
supported organic execution, publish, schedule, upload, mutate provider
accounts, spend, contact customers, or offer Claude Code entrypoints.
