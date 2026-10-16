---
name: mb-site
title: Site And Page Production
description: "Plan owned pages, landers, minisites, websites, sales-video surfaces, analytics/instrumentation checks, site readiness checks, and provider-gated deployment paths from deterministic Main Branch facts."
loops:
  - sense
  - ship
runtime_support:
  claude_code: supported_shell
  codex_cli: read_only_planning
runtime_surfaces:
  claude_code: .claude/skills/mb-site/SKILL.md
  codex_cli: global Main Branch mb-site skill
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb connect doctor --json
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
  - domain_purchase
  - dns_change
  - pages_project
  - custom_domain_attach
  - deploy_or_push
  - account_change
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_raw_transcripts
  - no_customer_member_data
  - no_private_runtime_settings
  - no_private_dms_or_gated_communities
  - no_raw_finance_legal_records
  - no_absolute_local_paths_in_committed_descriptors
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Site And Page Production

## Intent And Triggers

Use this workflow when the operator wants to plan, create, review, preview, or
prepare owned conversion surfaces: a lander, minisite, full website, page
update, site graduation, sales video, VSL, about-page video, landing-page video,
embedded pitch script, analytics/instrumentation check, booking-link wiring, or
form-submit readiness. Site work is Ship work, but this shared contract
separates planning and readiness checks from domain, DNS, Cloudflare Pages,
deploy, publishing, provider mutation, account changes, spend, and customer
contact.

Supported modes:

- `plan`: choose site shape, goal, offer, CTA, measurement posture, and route.
- `brief`: draft or review a durable site brief from accepted business truth.
- `build`: plan page structure, copy, components, and implementation targets.
- `preview`: inspect local readiness and remaining review work.
- `instrumentation`: check GA4, GTM, Meta pixel, booking widgets, CRM/form
  widgets, conversion-event mapping, and submit/booking smoke requirements.
- `check`: run paid-traffic and conversion-readiness facts from `mb site check`.
- `publish`: prepare a provider-gated publish plan without bypassing approval.
- `iterate`: update an existing site from accepted evidence or operator edits.
- `graduate`: move lander -> minisite -> website -> website plus CMS only when
  the current site and business evidence justify the shape change.
- `recover`: resume from repo descriptors, site check facts, and checkpoint
  state after context loss.

## Required Mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Read `mb status --json --peek` before direct markdown reads in business repo
mode. Use `mb start --json` when runtime readiness, repo boundary, or handoff
facts matter. Use `mb doctor repair --plan` when status facts name repair or
migration blockers. Use `mb connect doctor --json` before any Cloudflare,
domain, DNS, Pages, custom-domain, deploy, provider, or account-change plan.
Use `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json` for
broad local launch truth: app stack, deploy rail, commerce rail, email rail,
measurement summary, and one recommended smoke. Use `mb site check
"$SITE_REPO" --business-repo "$BUSINESS_REPO" --json` for paid-traffic
measurement detail once a site repo exists; add `--site <slug>` for one site in
a repo whose `.mainbranch/repo.json` lists several `sites`. When the operator
runs several site repos or businesses, `mb fleet status --json` (after
`mb fleet refresh`) reports each site's framework or engine pin, main's CI,
what is live (deployed commit, dirty-tree flag, commits behind main) and each
repo's Dependabot counts. It is read-only and needs a user-level hub list; see
`docs/fleet.md`.

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

Use `money_path.objects.cta_path`, channel strategy, active push, proof quality,
content strategy, integrations, readiness, and `measurement.*` facts from
`mb status --json --peek` before giving business-repo site or launch-readiness
advice. Use top-level `state`, `blocked`, `manual`, `evidence`,
`facts.expected_events`, `facts.provider_state`, `source`, and
`child_descriptor` from `mb site check ... --json` as the measurement source for
site repos. Use `facts.app_stack`, `facts.deploy`, `facts.commerce`,
`facts.email`, `facts.measurement`, and `recommended_action` from
`mb launch check ... --json` for broad local launch truth. Do not invent
`ready_for_launch`.

## Routing Rules

Start with deterministic facts, then read only the business and site files
needed for the requested shape, offer, push, page, sales-video surface,
instrumentation question, or site repo.

Mode routing:

1. For `plan`, identify business repo mode or site repo mode, then choose one
   route: lander, minisite, website, iteration, graduation, sales-video surface,
   instrumentation check, readiness check, or recovery.
2. For `brief`, draft from accepted repo truth: offer, audience, voice, content
   strategy, proof facts, active push, research, decisions, and operator
   constraints. If the offer is thin or claims are unsupported, route to
   `mb-think` before page copy. Conversion-mechanism gate: before drafting any
   page copy, pin what the visitor does to convert (lead form, book a call, or
   buy) and whether the operator takes calls. If the operator has not stated
   it, stop and ask — never assume a model; the headline, value prop, and
   mechanism copy are all shaped by it. Record it on the brief.
3. For `build`, propose page structure, sections, copy direction, components,
   and file targets. In Codex, stop at planning and patch-shaped guidance until
   site-build runtime smoke proves writes. Click-ID capture invariant
   (operating-principles §6): any lead-capturing surface snapshots the click
   IDs and campaign params by default — `gclid`, `gbraid`, `wbraid`, `fbclid`,
   and the five UTMs (`utm_source`/`utm_medium`/`utm_campaign`/`utm_term`/
   `utm_content`) — hydrated from the landing querystring and forwarded on
   submit, even before any campaign runs. Missing the set is permanent,
   unrecoverable attribution loss the day paid traffic starts.
4. For broad launch readiness, run or cite `mb launch check` and report app
   stack, deploy rail, commerce/email rails, measurement summary, and its one
   recommended action. For `preview`, `instrumentation`, and paid-traffic
   `check`, run or cite `mb site check` and report `facts.instrumentation`:
   GA4/GTM/Meta pixel identifiers, booking widgets, CRM/form widgets,
   conversion-surface state, and whether a submit/booking smoke is still
   required. Then report the
   readiness state exactly: `missing`, `blocked`, `ready_for_preview`,
   `ready_for_operator_review`, or `ready`.
5. For `publish`, separate local readiness from provider execution. A ready
   local check still needs operator review and explicit approval before git
   push, deploy, Pages mutation, custom-domain attach, DNS, publishing, spend,
   account changes, or customer contact.
6. For `iterate`, use current site state, accepted operator edits, status facts,
   content strategy, proof facts, site-check evidence, and outcome feedback.
   Do not turn weak feedback into proof or rewrite offer truth without a
   decision.
7. For `graduate`, require an accepted business reason and current site
   evidence. Do not expand a lander into a website or add CMS rails because the
   workflow can; connect the shape to the operator's goal.
8. For `recover`, inspect `.mainbranch/repo.json` or legacy
   `.mainbranch/source.json`, run `mb site check`, identify business repo and
   site repo roles, then resume from the last durable brief, push/site record,
   or checkpoint state.

## Read Boundaries

Read:

- deterministic status, start, repair, connection, validation, checkpoint, and
  site-check facts first;
- active offer/audience files, `core/voice.md`, `core/content-strategy.md`,
  relevant content strategy layers, approved proof summaries, active push files,
  decisions, research, logs, and documents that directly support the site;
- `.mainbranch/repo.json`, legacy `.mainbranch/source.json`, and
  `.mainbranch/conversion.json` in a site repo;
- source files needed to review or plan the requested page/site change.

Do not read or paste secrets, raw provider exports, account tokens, private
browser traces, private DMs, gated community content, raw customer/member
records, raw transcripts, finance/legal records, local runtime settings, or
absolute local paths intended for committed descriptors. Route sensitive source
material through approved summaries, manifests, or operator-provided excerpts.

## Write Boundaries

This workflow may write business files only after approval. Durable business
write targets are:

- `pushes/<YYYY-MM-DD-slug>/push.md` for coordinated site, launch, drop,
  challenge, or page work;
- `pushes/<YYYY-MM-DD-slug>/site.md` or the relevant offer note for reverse
  site records, deployed URL, domain, provider project, measurement state,
  launch status, and next manual approval step;
- `research/` files for site research handoffs;
- `decisions/` files for locked briefs or site-shape decisions;
- typed links and body-level `## Related links` mirrors on directly related
  pushes, bets, decisions, research, outcomes, logs, or documents;
- approved checkpoints after validation and checkpoint planning.

Site repo code changes, placeholder commits, previews, build steps, git pushes,
Cloudflare Pages project creation, DNS changes, custom-domain attach, deploys,
domain purchase, account mutation, publishing, spend, and customer contact are
outside the Codex read-only site route. Claude Code may follow existing
provider-specific site references only after explicit approval, provider
readiness checks, and runtime evidence for the exact surface.

Use `.mainbranch/repo.json` for new site repo descriptors and keep
`parent.local_checkout` relative when present. Treat legacy `.mainbranch/source.json`
as compatibility. Do not commit absolute local paths, secrets, raw provider
caches, or permission claims in descriptors.

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
- `domain_purchase`
- `dns_change`
- `pages_project`
- `custom_domain_attach`
- `deploy_or_push`
- `account_change`

Approval must be explicit before creating or editing business files, site repo
files, typed links, related-link mirrors, descriptors, conversion config,
migrations, repair applies, structured source collection, public issue/proposal
submission, checkpoints, git pushes, deploys, domain/DNS changes, Cloudflare
Pages changes, account mutation, publishing, spend, or customer contact.

## Handoff Format

```text
Site mode: <plan, brief, build, preview, check, publish, iterate, graduate, or recover>.
Repo mode: <business repo, site repo, both linked, or unclear>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Shape: <lander, minisite, website, sales-video surface, or unknown>.
Offer/CTA: <resolved, thin, blocked, or needs decision>.
Readiness: <missing, blocked, ready_for_preview, ready_for_operator_review, ready, or not checked>.
Provider posture: <read-only, connected, blocked, approval needed, or unsupported>.
Artifact route: <business push/site/decision/research path, site repo target, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

## Validation Commands

After approved business-repo site, push, brief, typed-link, or related-link
edits:

1. Run `mb validate --cross-refs --json`.
2. If a site repo exists, run
   `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json` and
   `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`.
3. If the checkpoint surface is available, run `mb checkpoint --plan --json`.
4. Show blockers in owner-facing language before offering to save.
5. Save business-repo changes only after approval, using checkpoint tooling
   rather than raw git commands.

Codex read-only planning must not run post-change validation, checkpoint saves,
git pushes, deploys, provider mutation, or publish commands as if it edited the
files. Runtime smoke is required before docs say this workflow is supported for
Codex site writes, builds, deploys, or publishing.

## Runtime-Specific Notes

Claude Code uses `.claude/skills/mb-site/SKILL.md` as the supported shell over
this source. Preserve slash-command-native site language there, plus existing
shape references, foreground subagent workflow, Cloudflare readiness gates,
business repo vs site repo mode, and checkpoint contract.

Codex uses the global Main Branch `mb-site` skill as read-only planning and
file-guidance. Codex may inspect facts, site-check readiness, descriptors, and
current files; propose patch-shaped recommendations; and name exact file
targets. Codex must stop before file edits, site repo code writes, build/deploy
execution, provider mutation, account changes, publishing, spend, customer
contact, checkpoints, and public issue/proposal submission unless a later issue
adds runtime smoke and updates this support boundary.
