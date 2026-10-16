---
name: mb-ads
description: "Create and review ads, and prepare provider-safe launch plans/checks. Flexible entry points: full pipeline (copy + images), copy only, images only, creative variations (hook library), video scripts, long-form video ads/VSL-style paid creative, video repurpose, compliance review, launch-plan, instrumentation, check, or optional Meta ad account check. Use when asked to create ads, ad copy, image prompts, video ad scripts, paid sales videos, creative variations, review ads, plan paid traffic, check analytics/GA4/GTM/pixels/booking/form readiness, or check launch performance. Say /mb-ads or describe what you need."
loops: [ship, reflect]
---

# Ads Skill

Create ads, generate creative variations, review for compliance, and check ad account performance.

**CLI facts first:** Find the business repo, run `mb status --json --peek`,
then use status readiness, drift, integrations, measurement, and ranked actions
before scoring creative depth or asking setup/provider questions.

## Shared Workflow Contract

Engine source workflow: `workflows/mb-ads/workflow.md`. This skill is the
Claude Code shell over that source. Preserve the shared source's fact-first
routing, launch-plan boundaries, provider gates, and read/write rules.

Shared source required `mb` commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb connect plan`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Shared source required JSON fact paths:

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

Shared source gates: `updates_repairs_migrations`, `file_writes`,
`checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`,
`private_data`, `destructive_operations`, `structured_collection`,
`public_issue_or_proposal`, `account_change`, `upload_assets`,
`budget_change`, `campaign_publish`, `conversion_upload`, `gtm_publish`.

Shared public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_private_dms_or_gated_communities`,
`no_raw_finance_legal_records`, `no_oauth_tokens`, `no_conversion_uploads`,
`no_account_identifiers_in_public_examples`.

Shared modes: static, copy-only, image-only, hook-library, video-scripts,
long-form-video, review, launch-plan, check, or account-context.
These are the account-context modes and paid creative modes for this shared source.
Use this routing language exactly when needed: route to `mb-think`; route to `mb-site`.
Durable paid artifacts use
`pushes/<YYYY-MM-DD-slug>/ads-batch-001.md`, push playbook runs, research, or
decisions after approval. Google Ads Search uses the google-ads-search-launch
playbook source. Upload assets, provider mutation, spend, publishing, account
changes, GTM publishes, conversion uploads, and customer contact remain gated.
Codex support is read-only planning until runtime smoke proves more.

## Output destinations and operator vocabulary

This skill writes new coordinated work to `pushes/<YYYY-MM-DD-slug>/` (the
engine primitive). Examples below say "push" for the wrapping
record; this is the engine's word. If `core/vocabulary.md` defines a
display word — for example `terms.push.singular: drop` — speak the
operator's word ("drop") in conversation while still writing current
files (`pushes/...`, `type: push`, `linked_pushes`). Never rename folders,
frontmatter, link fields, JSON keys, or commands based on vocabulary.

If the repo still has legacy `campaigns/` records, preview the migration
**before** creating new push work:

```text
mb doctor                       # confirms legacy campaigns/ drift
mb migrate campaigns --plan     # read-only preview of moves
```

The word "campaign" elsewhere in this skill refers to Meta Ads campaigns
(the provider's term for its object) — not the Main Branch primitive.

When creating `push.md`, include the validator-required frontmatter and fill
the values from repo truth or operator answers. When finished creative
already exists outside git (a Drive folder, an export), ask "where do the
finished files live?" and record `media_location` plus a `media_backend`
hint (google-drive, r2, local, mb-media):

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
media_location: ""   # optional — where binary creative lives
media_backend: ""    # optional hint; requires media_location
---
```

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
Also link named playbooks and outcomes through `linked_playbooks` and
`linked_outcomes`.

When an ad-adjacent workflow needs a resource-delivery plan, provider setup
recipe, launch checklist, or external automation approval record, draft it
as `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` with `type: playbook`
— plans and approval records only. Do not publish, schedule, DM, reply,
mutate ad accounts, or claim a provider is supported unless `mb` and a
shipped provider adapter prove that path with docs, tests, approval gates,
and smoke evidence.

## Step 0: Pre-Flight Readiness

**Before triage, find the business repo, read deterministic Main Branch
facts, then score ad-specific reference depth only when needed.** This
prevents generic ads from thin reference without duplicating repo-health or
provider checks that `mb` already owns.

### 0a. Find Business Repo (REQUIRED — do this first)

**NEVER search the filesystem. NEVER use Explore or Task agents to find repos. NEVER scan ~/Documents/GitHub/.**

**CWD-first:** If current Main Branch markers exist in CWD, use it. If CWD looks like an old Main Branch repo, run `mb status --json --peek` and/or `mb doctor repair --plan` before saved config or discovery. Do not write to old repo structure.

If CWD is NOT a business repo, run:

```bash
mb status --json --peek
```

- If status identifies a usable business repo, ask the user to confirm it.
- If status cannot identify one, ask: "Which business repo should I use?"
- If `/mb-ads` was invoked from `/mb-start`, the repo is already identified —
  use it without asking.

**Always confirm the repo before proceeding.** Never assume.

After confirming, run `mb status --json --peek` from that repo. Use
`readiness`, `drift.items`, `integrations`, `measurement`, and
`ranked_actions` as the source of truth for setup, stale context, GitHub,
provider readiness, and repair commands. Only run the direct scoring below
when status is unavailable or lacks the needed ad-specific detail.

When the request depends on a new, thin, or underperforming offer, load
`.claude/reference/conversion/offer-sharpening.md` before writing hooks or
launch-plan claims. Route to `/mb-think` when audience, outcome, mechanism,
proof, risk reversal, objections, reason to act, or next step is unclear.

### 0b. Score Reference Files (fast — direct Read only, NO agents)

**NEVER spawn Explore or Task agents for pre-flight.** Read files directly at the known repo path. Pre-flight should complete in under 10 seconds.

At the repo path, resolve offer context first with
`.claude/reference/business-primitives/offer-bet-push-proof.md`, then check
these files and count lines:

```
[resolved offer.md]          → 0 (missing), 1 (<20 lines), 2 (20-80), 3 (80+)
[resolved audience.md]       → same scoring
core/voice.md                → same scoring
core/proof/testimonials.md → same scoring
core/proof/angles/*.md  → count .md files EXCLUDING README.md: 0=0, 1=1, 2-3=2, 4+=3
core/brand/visual-style.md → same scoring (optional)
```

In multi-offer mode, score the offer-specific `offer.md` and `audience.md` (resolved via path resolution), not the brand-level `core/offer.md`.

Composite = sum of all 6 scores (max 18).

### 0c. Route on Score

| Composite | Status | Action |
|-----------|--------|--------|
| **12-18** | GREEN | Proceed to triage |
| **8-11** | YELLOW | Warn user, show gaps, allow override |
| **4-7** | RED | Route to `/mb-think` with enrichment targets |
| **0-3** | BLOCKED | Route to `/mb-setup` |

Display the readiness report, then proceed. See [references/preflight-algorithm.md](references/preflight-algorithm.md) for gap guidance and smart mix recommendations.

### 0d. Check Image Generation Readiness

For Facebook image-ad generation, load the MAIN-374 decision and
[references/image-generation-workflow.md](references/image-generation-workflow.md)
for ad readiness, source bites, playbook routing, review boards, and
`image-index.md`.

```bash
mb connect doctor --json
```

Use status/connect facts first for Google/Workspace readiness. For provider rail
smokes, use `mb image smoke-openai --repo "$BUSINESS_REPO" --json` (default rail) or `mb image smoke-fal` (explicitly selected fal.ai rail); see [references/image-generation-workflow.md](references/image-generation-workflow.md)
for the `--generate`, credential, media-storage, and `image-index.md` boundary.
Never ask the operator to paste API keys into chat or public issue text.

### 0e. Paid-Traffic Measurement Gate

If this ad work is for Google Ads, paid traffic to a site/minisite/lander, retargeting, or any request that asks whether a campaign is ready to launch, check broad launch truth and measurement readiness before saying "launch."

1. Load `docs/google-ads-gtm-conversion-rubric.md`.
2. Run `mb connect plan` or `mb connect doctor --json` from the business repo when provider readiness matters.
3. If a site repo is known, run broad launch truth first, then measurement detail:

```bash
mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json
mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json
```

Use the returned `state`:

- `blocked`: do not recommend launch; list the blocked checks and exact next command/manual step.
- `ready_for_preview`: ads can be drafted, but traffic should not launch; tell the operator to run GTM Preview/Tag Assistant and finish provider metadata/approvals.
- `ready_for_operator_review`: ads can be prepared for review, but launch still needs explicit operator approval for GTM publication, conversion actions, consent posture, budget, billing, and spend.
- `ready`: local readiness checks passed, but do not mutate accounts or launch campaigns.

Do not invent `ready_for_launch` or treat `ready` as campaign launch permission. Main Branch can prepare and review; the operator launches manually.

Never ask the operator to paste Google Ads/GTM tokens, OAuth secrets, conversion uploads, or customer data into chat. Quote `mb connect` repair commands instead.

---

## Meta Ad Account Readiness (Lazy)

Check Meta ad account access only when the user's request needs live ad account
context. Do not duplicate provider setup or health checks in prose.

### Readiness Flow

```
1. Read `mb status --json --peek` → integrations/providers/measurement facts.
2. If the operator needs setup choices, run `mb connect plan`.
3. If something looks broken, run `mb connect doctor --json`.
4. If `mb` says Meta Ads account context is `ready`, ask whether to pull a
   compact read-only account summary before generating.
5. Never block generation on missing ad account access.
```

**Graceful degradation:** If Meta Ads account context is not `ready`, mention
the optional account context once, quote the `mb` repair command when useful,
then continue from repo reference files, exported screenshots, or manual Ads
Manager notes.

### User-Facing Display

Describe the capability: connecting a Meta ad account, pulling a compact
read-only account summary, or auditing active campaigns. Keep status
capability-first and do not name connector vendor details. If the user asks,
offer `mb connect plan` or continuing from reference files.

---

## Triage (Flexible Intent Detection)

Detect what the user wants from natural language. Route internally to the right component pipeline. See [references/entry-points.md](references/entry-points.md) for the complete entry point detection table and component composition.

### Intent Detection

| User Says | Entry Point | What Happens |
|-----------|-------------|-------------|
| "static ads", "full from scratch", "image ads" | Full Pipeline | Copy + compliance + images (classic flow) |
| "I already have images, just need copy" | Copy Only | Skip image gen, primaries + headlines |
| "Just need images for existing copy" | Image Only | Image prompts and optional provider generation |
| "creative variations", "hook library", "one-liners", "50 hooks" | Hook Library | Bulk creative variations (flexible quantity) |
| "video scripts", "ad scripts", "spoken word" | Video Scripts | Spoken-word script pipeline |
| "video ad script", "turn this offer into a video ad", "paid sales video", "long-form video ad", "VSL-style paid creative" | Long-Form Video Ads | Load [references/long-form-video-ads.md](references/long-form-video-ads.md) |
| "I'm repurposing a video", "I shot a video" | Video Repurpose | Transcribe + extract hooks + copy variants |
| "I want ideas for an ad", "brainstorm" | Ideation | Account check (if available) + concept generation |
| "research winning ads", "mine reviews", "analyze competitors first" | Research / Mining | Route to `/mb-think` winning-ad research before generation |
| "launch ads", "paid traffic plan", "Google Ads launch", "$X/day for Y days" | Launch Plan | Provider-safe plan/check mode, no account mutation |
| "analytics", "instrumentation", "GA4", "Google Analytics", "GTM", "Meta pixel", "HubSpot form", "Calendly", "booking link", "form test" | Instrumentation | Route through `/mb-site` and `mb site check`; no provider mutation. Real GA4 sessions/conversions: `mb google ga4 report --json`, see [references/ga4-search-reads.md](references/ga4-search-reads.md) |
| "check launch", "how are ads doing", "continue or kill" | Launch Check | Read status/outcomes/operator exports, recommend continue/change/stop |
| "weekly pack", "daily read", "stop rules", "day-14 verdict" | Launch Plan / Check | Meta pack loop: [references/meta-pack-loop.md](references/meta-pack-loop.md) |
| "Google Ads daily check", "search terms", "negatives" | Launch Check | Scored rubric: [references/google-ads-check.md](references/google-ads-check.md) |
| "Check my ad performance", "what's working" | Account Check | Read-only Meta Ads context if `mb connect` and runtime tools are ready |
| "Give me 5 variations of this winning ad" | Performance Iteration | Pull winner + generate variants if account context is ready |
| "What's working before we create?" | Pre-Gen Account Check | Account overview + creative audit if account context is ready |
| "review", "audit", "compliance check" | Review | 6-lens compliance review |

**Also accepts:** "static", "static ads", "video", "video scripts", "one-liners", "review" -- these route to the same pipelines.

**If unclear,** ask: "What do you have and what do you need? (e.g., 'I have images, just need copy' or 'full from scratch')"

**If research/mining is requested before generation:** Route to `/mb-think` and
load `mb-think/references/winning-ad-research.md`. Customer language, review
mining, competitor gap maps, comment mining, and winning script teardown should
save to `research/` and codify into `core/` before this skill generates ads.
Do not paste raw review/comment dumps or copied prompt libraries into ad output.
If the selected research file has `brief_format: grok-8`, use its downstream
handoff first: business/offering for the promise, ICP for hooks, journey for
funnel stage, competitive landscape for differentiation, brand story for voice,
content/assets for proof and creative inputs, and metrics/constraints for the
review bar. If the brief names a resource-delivery or provider workflow, draft
or update a push playbook as a plan only; do not execute provider mutation.

**If launch/check is requested for paid traffic:** Load
[references/launch-plan-check.md](references/launch-plan-check.md). Prepare
campaign materials, policy findings, measurement readiness, manual provider
steps, and approval records; do not mutate ad accounts or start spend.

### Proactive Account Awareness

If `mb status --json --peek` / `mb connect doctor --json` reports Meta Ads
ready and the current runtime exposes the read-only ad account tools:

**Before generating:** Ask before pulling live account context:
> "Meta appears connected for read-only checks. Do you want me to pull a compact account summary before making recommendations?"

If user says yes, run Account Check component (see [references/meta-ads-integration.md](references/meta-ads-integration.md)):
- Say: "I'll pull a read-only summary and avoid saving raw account data."
- Pull only the compact account summary the current runtime supports
- Use safe readiness, activity, and naming-pattern context only

If user says no, proceed to generation with reference files only.

**After generating:** If the operator approved a read-only summary, use it to
frame next steps without exposing raw account data or implying account mutation.

Account awareness is currently read-only. Write operations are on the roadmap
and require explicit operator approval gates -- see
[references/meta-ads-integration.md](references/meta-ads-integration.md).

---

## Pre-Flight: Special Ad Categories

**Before generating any ads, ask:**

> "Will this campaign run as a Meta Special Ad Category? (Housing, Employment, Credit, or Social Issues/Politics)"

If **Employment** (job training, career coaching, hiring, job boards):

1. **Load additional rules:** See Meta Policy lens → Employment section
2. **Warn user:** "Employment category has strict restrictions. I'll avoid salary assertions, 'if you've been...' patterns, and job-seeking status claims."
3. **Tag the output:** Add `special_ad_category: employment` to frontmatter

For Employment, avoid any assertion about current status such as job,
salary, employment state, job-seeking status, or dissatisfaction. Use
aspirational framing only.

---

## Offer Context And Required Reference

Before loading reference files, resolve active offer context with
`.claude/reference/business-primitives/offer-bet-push-proof.md` and the
file list in [references/preflight-algorithm.md](references/preflight-algorithm.md).
Use current `core/` paths first; treat old paths as migration input only.

Before outcome-claim or substantiation recommendations, read
`money_path.objects.proof.quality`. If `quality.public_marketing.status` is
`blocked`, do not draft proof-backed public ad claims; route to `/mb-think` for
permission collection before ads, pages, or public claims use that proof.

If content strategy layers or Skool surface notes exist, use them to decide the
paid role and keep ads congruent with visible offer, pricing, and proof. Angles
are additive; mix established angles with any newly codified ones.

---

## Mode: Static Ads

Create campaign batches with image prompts + ad copy. Each batch = 5-6 angles, each angle = 3 image creatives (graphic, lo-fi, interrupt). Hook = a complete first sentence within 44 chars (Reels), short primary under 125, no yes/no questions at the viewer, no "you/your" in first 3 lines, no emojis. 5 ad styles (Deep, UGC, DR, Pattern Interrupt, Testimonial). Format pair: 4:5 + 9:16 ([references/ad-media-specs.md](references/ad-media-specs.md)). Meta text slots, names and UTMs: [references/meta-text-slots.md](references/meta-text-slots.md), [references/naming-and-utm.md](references/naming-and-utm.md).

See **[references/mode-static-ads.md](references/mode-static-ads.md)** for the full workflow: campaign structure, hook formulas, copywriting batch sequence, ad styles by length, image prompt types, and the file save convention.

---

## Mode: Hook Library (Creative Variations)

Generate punchy, truly diversified creative variations for static image ads (Andromeda-optimized). Users can request any quantity. Also called "one-liners" — same methodology, same pipeline.

**The core rule:** Every variation must include at least one specific anchor (role, niche pain, value prop, or proof point). The Specificity Test: if it could sell a gym membership, it fails.

See **[references/mode-hook-library.md](references/mode-hook-library.md)** for the full 6-step process, anchor rule, input modes, output file format with full generation context, and links to one-liner-methodology.md / one-liner-examples.md.

---

## Mode: Video Scripts

Create diverse spoken-word scripts for camera delivery. 15-30 scripts across 3-4 buyer avatars, ~5th grade reading level, contractions, fragments. Each ad = a fundamentally different reason to buy.

See **[references/mode-video-scripts.md](references/mode-video-scripts.md)** for the 6-step process, script structure (Hook / Body / CTA), spoken delivery optimization, and save convention.

For long-form paid sales videos, video ad scripts that need VSL structure, or
VSL-style paid creative, load
[references/long-form-video-ads.md](references/long-form-video-ads.md).

---

## Mode: Review

Review ads through 6 compliance and quality lenses before shipping (FTC, Meta Policy, Copy Quality, Visual Standards, Voice Authenticity, Substantiation). Spawns 6 parallel Task agents (read-only), synthesizes a unified P1/P2/P3 report, presents proposed P2/P3 copy changes as a diff, and applies them only after explicit approval.

See **[references/mode-review.md](references/mode-review.md)** for the full lens table, review process, severity levels, and status determination.

---

## Automatic Post-Generation Pipeline

**Every generation entry point (Full Pipeline, Copy Only, Hook Library, Video Scripts) runs this pipeline automatically after saving output.** Do not ask the user whether to run compliance review -- it is automatic.

See **[references/post-generation-pipeline.md](references/post-generation-pipeline.md)** for the complete pipeline: checkpoint pre-review, lens tier selection, optional image-provider check, parallel agent spawning (compliance + image), synthesis, proposed-change approval gate, unified report, and post-review checkpoint.

**Quick summary:** Save a checkpoint for the pre-review state after operator approval, spawn 5-6 compliance agents + optional image agents in parallel, synthesize P1/P2/P3 findings, surface P1 to user, show proposed P2/P3 copy edits as a dry-run diff, apply copy edits only after explicit approval, present unified report, and offer a post-review checkpoint.

**"While You Wait" pattern:** When spawning parallel agents that take >30 seconds, show a brief note so the user knows what's happening:
> "Running compliance review across 6 lenses + generating images in parallel. This takes about 2-3 minutes. These run as sub-agents so they won't eat into your session context."

## Compliance (All Modes)

**Never say:** cures/treats/heals [condition], guaranteed results, will eliminate [problem].
**Safe to say:** many have found this helpful, supports/complements an existing approach, a framework for understanding, education and guidance.

## Quality Checklist (All Copy Modes)

Before saving any batch, verify:

| Check | Requirement |
|-------|-------------|
| **Anchor specificity** | Every hook/variation has at least one offer-specific anchor |
| **Cold traffic language** | No insider jargon — would a stranger understand in 3 seconds? |
| **Hook length** | First sentence complete within 44 characters; short primary under 125 |
| **Questions** | A question only about the product or in the buyer's own first-person voice; never one aimed at the viewer |
| **No you/your** | First 3 lines avoid direct address |
| **Angle diversity** | Each concept uses a genuinely different psychological entry point |
| **Voice match** | Copy matches `voice.md` tone (if available) |
| **Compliance** | No banned claims, proper testimonial attribution |
| **Skool congruence** | Claims match live about page + pricing cards (if `skool-surfaces.md` exists) |
| **Save-ability** | Would someone save this ad to reference later? Educational, actionable hooks drive purchase intent |
| **Enemy framing** | Does at least one concept use a named enemy from voice.md? Enemy-driven contrast creates identity alignment |

## Recovery from Compaction

If context was compacted mid-task, check: offer, entry point, stage, partial
work in `pushes/`, ad account status (`mb status --json --peek`; then
`mb connect doctor --json` if needed), and resume from the last completed step.
If old `campaigns/` records exist, run `mb migrate campaigns --plan` before
relying on them. Do not silently route from `.vip/local.yaml`. Check unfinished
counts for full pipeline, hook-library, or video-script work.
## Quick Reference

**Full/static:** 5-6 concepts x 5 primaries x 5 headlines x 3 image prompts.
**Hook/video/review:** default 30 hooks, 15-30 scripts, or 6-lens P1/P2/P3 review.
**Account/launch:** read-only Meta summary or provider-safe paid plan/check; no account mutation without shipped adapter and explicit approval.
