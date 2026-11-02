---
name: mb-site
description: "Triage and build any site shape -- lander (1 page), minisite (~4 pages), or full website -- and graduate between them. Also writes owned-surface sales videos/VSLs, about-page videos, landing-page videos, and embedded pitch scripts. Routes to per-shape build flow, reads from business context files, deploys to Cloudflare Pages with git auto-deploy. Use when:
  (1) Operator says 'I want a site' / 'I want a lander' / 'spin up a one-pager'
  (2) Setting up a new site of any shape from offer + audience material
  (3) Updating / iterating on an existing site
  (4) Graduating a site to a new shape (lander -> minisite -> website -> website + CMS)
  (5) Writing a sales video, VSL, about-page video, landing-page video, or embedded pitch script for an owned conversion surface
  (6) Checking analytics/instrumentation, GA4, GTM/dataLayer, Meta pixel, booking links, HubSpot/forms, conversion-event mapping, form-submit smoke, or paid-traffic readiness
  (7) Previewing or publishing changes

  Triggered by: /mb-site, 'build a site', 'landing page', 'lander', 'minisite', 'website', 'I need a site', 'spin up a site', 'put this online', 'publish site', 'deploy site', 'update my site', 'graduate my site', 'add a CMS to my site', 'analytics', 'instrumentation', 'Google Analytics', 'GA4', 'GTM', 'Meta pixel', 'HubSpot form', 'Calendly', 'booking link', 'form test', 'write a VSL', 'sales video', 'about page video', 'landing page video', 'pitch script'"
loops: [ship]
---

# Site

Pick a site shape, build it from business context, and ship it through a linked site repo. Cloudflare Pages with git auto-deploy is the default deploy path.

**Shared source:** The portable workflow contract lives in
`workflows/mb-site/workflow.md`. This Claude skill is the Claude Code shell over
that source.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Required fact paths:

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

Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`,
`provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`,
`destructive_operations`, `structured_collection`, `public_issue_or_proposal`,
`domain_purchase`, `dns_change`, `pages_project`, `custom_domain_attach`,
`deploy_or_push`, and `account_change`.

Public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_private_dms_or_gated_communities`,
`no_raw_finance_legal_records`, and
`no_absolute_local_paths_in_committed_descriptors`.

Core flow: support plan, brief, build, preview, check, publish, iterate, graduate, or recover modes.
Marker phrase: plan, brief, build, preview, check, publish, iterate, graduate, or recover.
Preserve lander, minisite, website, sales-video surface, and site repo modes;
use `mb site check` readiness states including `ready_for_operator_review`; keep
domain, DNS, Cloudflare Pages, custom-domain, deploy, publishing, provider
mutation, account changes, spend, and customer contact behind explicit gates.
Provider boundary phrase: provider mutation. Broad launch readiness uses
`mb launch check`; paid-traffic measurement detail uses `mb site check`.
Codex support stays read-only planning until runtime smoke proves site writes,
builds, deploys, and publishing.

**CLI facts first:** In business repo mode, run `mb status --json --peek`
before setup/provider/launch-readiness advice. In site repo mode or whenever a
site repo is known, run `mb launch check "$SITE_REPO" --business-repo
"$BUSINESS_REPO" --json` for broad launch truth, then `mb site check
"$SITE_REPO" --business-repo "$BUSINESS_REPO" --json` for paid-traffic
readiness or publish guidance.

## Output destinations and operator vocabulary

Site/lander records that wrap a coordinated push (a launch, drop, or
challenge with a goal and timeline) live under `pushes/<YYYY-MM-DD-slug>/`
on the business-repo side; the wrapping record is `push.md` (`type: push`),
and the site record is typically `pushes/<YYYY-MM-DD-slug>/site.md`. Site
files themselves live in the linked site repo (Cloudflare Pages, etc.) and
are not duplicated in the business repo.

Reverse references from the site repo use the role-neutral `.mainbranch/repo.json` descriptor with engine push paths (`linked.pushes: ["pushes/<...>/push.md"]`); older site repos may still use `.mainbranch/source.json` (its `campaign_path` should point at the current push record). If `core/vocabulary.md` defines display words (e.g. `terms.push.singular: launch`), speak the operator's word while still writing engine files. Legacy `campaigns/` records are migration input: run `mb doctor` and `mb migrate campaigns --plan` before relying on them or creating new push work.

When creating `push.md`, include the validator-required frontmatter and fill
the values from repo truth or operator answers:

```yaml
---
type: push
slug: YYYY-MM-DD-slug
kind: launch
status: planned
health: unknown
goal: { metric: "", target: "", by: YYYY-MM-DD }
owner: ""
audience: ""
offer: core/offers/<offer>/offer.md
promise: ""
---
```

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
Also link named playbooks and outcomes through `linked_playbooks` and
`linked_outcomes`.

## Re-Invoke Often

Say `/mb-site` again after compaction, context loss, or switching focus. It reloads skill context. Do it whenever the conversation feels stale.

## Start Every Run

1. Load [`references/pull-engine-updates.md`](references/pull-engine-updates.md) and run the standard Main Branch update check.
2. Detect business repo mode vs site repo mode. Load [`references/site-repo-workflow.md`](references/site-repo-workflow.md) for repo boundaries, source links, and reverse site records.
3. When a business repo is known, run `mb status --json --peek` and use its `readiness`, `drift.items`, `integrations`, `measurement`, and `ranked_actions` facts before inventing setup, provider, or launch-readiness checks in prose.
4. Before any domain purchase, DNS, Cloudflare Pages project, custom-domain attach, or deploy work, run `mb connect doctor --json` from the business repo and check `provider:cloudflare`.
   - If Cloudflare is not `ready`, stop before dispatching site tools and present exactly three choices:
     - **connect now:** `printf '%s' "$CLOUDFLARE_API_TOKEN" | mb connect cloudflare --token-stdin --metadata token_type=account --metadata account_id=... && mb connect test cloudflare`
     - **continue read-only:** availability checks, naming, brief, and research only; no buy, DNS, Pages, custom-domain, or deploy calls.
     - **skip for now:** record the blocker in the push/site notes and stage a follow-up task.
   - `cfat_` account tokens route automatically when `account_id` is present; keep `token_type=account` in examples because it is explicit and works on older `mb` versions. User API tokens remain supported as a fallback by omitting `token_type=account`.
5. Resolve the active offer and required business context with [`references/site-context.md`](references/site-context.md).
6. When the page, sales video, or lander depends on a weak offer, load
   `.claude/reference/conversion/offer-sharpening.md` and route to `/mb-think`
   before writing page copy from thin claims.
6a. **Conversion-mechanism gate (before any page copy):** confirm what the
   visitor does to convert — submit a lead form, book a call, or buy — and
   specifically whether the operator takes calls. If the operator has not
   stated it, STOP and ask; never assume a model. Copy is shaped by the
   mechanism, so it is pinned before drafting (the brief records it; see
   `mb-skill-brief-draft`). A real business we built lost a full day when an
   agent invented a call-booking flow the operator never chose.
7. When the site, blog, wiki, changelog, or launch page depends on content or
   recognition strategy, read `core/content-strategy.md` and relevant
   `core/marketing/` files if present. Owned site content should support the
   same known-for target, asset jobs, channel plan, and CTA path rather than
   duplicating publishable site copy into the business repo. When the goal
   includes ranking, organic search traffic, keyword research, blogging for
   SEO, backlinks, or AI-search visibility, load
   [`references/seo.md`](references/seo.md) before promising SEO outcomes.
8. Ask what the operator is building, then load only the shape reference needed next.

## Operating Principles

Four behaviors `/mb-site` uses on every run:

1. **One flow: brief to site.** Do not route the operator to a separate brief skill and then ask them to come back. `/mb-site` walks research, brief draft, review, lock, concept variations, publish, and iteration as one flow.
2. **Foreground subagents.** Research, concept, and review subagents run in the foreground. Background subagents can appear to write files that do not persist.
3. **Parallel by default.** Multiple research questions, concepts, or review passes should run in parallel.
4. **Publish-first, then iterate.** Checkpoint the rawest durable business-repo brief and commit the rawest working site-repo concept before iterating. Git history is the memory across context clears.

When research subagents record findings, they follow the `/mb-think` research pattern: dated `research/YYYY-MM-DD-slug-claude-code.md` files with frontmatter and `linked_decisions: []`.
When the operator needs a broad researched brief before the site brief, run or
reuse `/mb-think --brief-format=grok-8`. Its eight categories feed the site
flow directly: offering, ICP, journey, competitive landscape, brand story,
technical requirements, assets, and metrics/constraints. Keep the `grok-8`
brief in `research/`; the locked site brief still belongs in `decisions/`.

Business-repo saves use `mb checkpoint`, not raw git commits. For accepted
research files, locked briefs, and reverse site records, run
`mb checkpoint --plan --json`, validate a subject such as
`[drafted] minisite research -- <slug>`, `[decided] minisite brief -- <slug>`,
or `[connected] site repo -- <slug>`, then save with
`mb checkpoint --message "<subject>" --yes` after operator approval. Site repo
code commits still use that site's normal git flow.

## Invocation Mode

Use [`references/site-repo-workflow.md`](references/site-repo-workflow.md).

- **Business repo mode:** CWD has current Main Branch markers. Say: "I'm reading business context here and will create or select a site repo." If CWD looks like an old Main Branch repo, run `mb status --json --peek` and/or `mb doctor repair --plan` before saved config or discovery. Do not write to old repo structure.
- **Site repo mode:** CWD has `.mainbranch/repo.json` or legacy `.mainbranch/source.json`. Say: "I'm editing the site here and reading business context from the linked business repo."

Business repo mode plans, researches, drafts the brief, picks an offer, records push/site state, and creates or selects the site repo. Site repo mode edits code, reviews pages, previews, deploys, and runs `mb site check`.

## Triage

Ask the operator. Do not assume.

> **What are you doing?**
>
> **A. New site from scratch.** Pick a shape.
> - **Lander** (1 page, all-in-one). Use for focused one-off offer tests, retargeting, or paid-traffic landers. Load [`references/lander-build.md`](references/lander-build.md).
> - **Minisite** (~4-6 pages, static HTML). V1 default for paid-ad lander tests, single-offer first deploys, payment, lead-form, and booking funnels. Load [`references/minisite-build.md`](references/minisite-build.md).
> - **Website** (full site, usually with build step). Static-first on Cloudflare Pages, with an optional build step. Load [`references/website-build.md`](references/website-build.md).
>
> **B. Iterating on an existing site.**
> - Editing pages, adding sections, updating copy: load the current shape build reference.
> - Publishing existing work: load the current shape build reference and follow its publish step; publishing asks for approval every time (see the approval gates above).
>
> **C. Graduating to a different shape.**
> - Lander -> minisite, minisite -> website, website -> website + CMS. Load [`references/graduation.md`](references/graduation.md).

If the operator cannot articulate the shape, ask: "What goal are you trying to hit? Drive paid traffic to a sale, lead, or booking? Sell a course? Replace your current Squarespace?" Their answer maps to the shape.

## Modes

| Mode | What it does | Load |
|---|---|---|
| setup | First-run for a new site | Shape build ref, then setup step |
| build | Generate or edit content | Current shape build ref |
| preview | Local server/dev environment | Current shape preview step |
| publish | Stage, commit, push | Current shape publish step |
| instrumentation | Analytics, tags, booking/form widgets, and event mapping | [`references/site-measurement.md`](references/site-measurement.md) |
| check | Paid-traffic readiness | [`references/site-measurement.md`](references/site-measurement.md) |
| search data | Which queries or pages bring clicks, is a page indexed, sitemap status, sessions | [`references/search-data.md`](references/search-data.md) |
| recover | Resume after compaction | [`references/site-recovery.md`](references/site-recovery.md) |

## Reference Map

**Repo + context**

- [`references/site-repo-workflow.md`](references/site-repo-workflow.md) - business repo mode vs site repo mode, source links, reverse records.
- [`references/site-context.md`](references/site-context.md) - prerequisites, active offer resolution, required `core/...` files, and section mapping.
- `.claude/reference/conversion/offer-sharpening.md` - universal offer rubric, style spectrum, evidence handling, and stop conditions.
- Engine doc `docs/content-strategy.md` - layered content, distribution,
  channel, account, person, push, and results model.
- [`references/sales-video.md`](references/sales-video.md) - sales video, VSL, about-page video, lander video, and embedded pitch scripts for owned surfaces.
- [`references/site-measurement.md`](references/site-measurement.md) - `mb site check` and paid-traffic readiness states.
- [`references/search-data.md`](references/search-data.md) - real Search Console and GA4 numbers through `mb google ... --json` (queries, indexing, sitemaps, sessions); recorded site and property only.
- [`references/seo.md`](references/seo.md) - SEO doctrine: content silos, keyword selection math, PageSpeed thresholds, blog/backlink rules, AI search, the API-first data layer, and the fulfillment loop.
- [`references/site-recovery.md`](references/site-recovery.md) - compaction recovery and scope boundaries.

**Shape flows**

- [`references/lander-build.md`](references/lander-build.md) - 1-page shape stub.
- [`references/minisite-build.md`](references/minisite-build.md) - minisite step router.
- [`references/website-build.md`](references/website-build.md) - website flow (static-first, optional build step).
- [`references/graduation.md`](references/graduation.md) - paths between shapes and CMS bolt-on.

**Minisite step detail:** [`references/minisite-build.md`](references/minisite-build.md) routes each step (research, brief, setup, conversion, concept variations, build-out, publish, iterate) to its own reference; load only the current step.

**Generation + design**

- [`references/minisite-generation-system.md`](references/minisite-generation-system.md) - load-bearing system prompt for minisite generation.
- [`references/lander-generation-system.md`](references/lander-generation-system.md) - one-page lander generation profile.
- [`references/review.md`](references/review.md) - dial-gated quality gates.
- [`references/anti-patterns.md`](references/anti-patterns.md) - AI tells and generation anti-patterns.
- [`references/archetypes.md`](references/archetypes.md) - 9-archetype picker. Load picked detail lazily.
- [`references/headline-formulas.md`](references/headline-formulas.md) - formulas grouped by frame.

**Visibility, hosting, and checks**

- For screenshots, fixtures and test content, follow `/mb-setup` `references/where-data-lives.md`.

- Site repos default to **private**. Before creating a public site repo,
  ask one visibility question — see the engine docs
  (repo-visibility-rubric) for the rule and exact wording.
- Cloudflare is the deploy rail. GitHub Pages is not part of normal Main
  Branch setup; the checks-and-review model in the engine docs explains
  how local `mb` checks, GitHub Actions, and branch protection layer.

**Setup, examples, help**

- [`references/naming-heuristic.md`](references/naming-heuristic.md) - domain naming playbook.
- [`references/cloudflare-pages-link.md`](references/cloudflare-pages-link.md) - Cloudflare Pages GitHub App handshake.
- [`references/examples.md`](references/examples.md) - usage examples.
- [`references/troubleshooting.md`](references/troubleshooting.md) - common fixes.
