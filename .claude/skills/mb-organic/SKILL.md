---
name: mb-organic
description: "CREATE organic content scripts (Reels, TikTok, carousels, static posts) and repurpose sales videos/VSLs into short clips or creator-style excerpts. Use when user wants to GENERATE new scripts from concepts or make short clips from a sales video. NOT for research/mining competitor content - that's /mb-think. NOT for paid ads - use /mb-ads instead. Modes: video, carousel, static, sales-video repurpose. If user says \"mine\", \"scrape\", \"research competitors\" → route to /mb-think."
loops: [ship]
---

# Organic

Create organic content scripts in your voice — Reels, TikToks, carousels, static posts.

**Shared source:** The portable workflow contract lives in
`workflows/mb-organic/workflow.md`. This Claude skill is the Claude Code shell
over that source.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

Required fact paths:

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

Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`,
`provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`,
`destructive_operations`, `structured_collection`, and
`public_issue_or_proposal`.

Public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_private_dms_or_gated_communities`, and
`no_raw_finance_legal_records`.

Core flow: support plan, video, carousel, static, sales-video-repurpose, or
review.
Marker phrase: plan, video, carousel, static, sales-video-repurpose, or review.
If the operator wants mining or source collection, route to `mb-think`.
Use `content_strategy.overall_state` and
`money_path.objects.proof.quality` before drafting; keep source/privacy
boundaries visible; route coordinated drafts to
`pushes/<YYYY-MM-DD-slug>/organic-batch-001.md`; Do not publish, schedule,
upload, mutate provider accounts, spend, auto-DM, auto-reply, or contact
customers. Codex support stays read-only planning until runtime smoke proves
organic drafting writes.

**Need help?** Type `/mb-help` + your question anytime. If conversation compacts, `/mb-help` reloads fresh context.

**CLI facts first:** Run `mb status --json --peek` from the business repo before
triage, reference-health checks, or content planning. Use its readiness, drift,
and ranked-action facts instead of hand-rolled repo-health probes.

## Output destinations and operator vocabulary

When this skill produces a coordinated push (a content sequence with a goal,
audience, and review date), write the wrapping record to
`pushes/<YYYY-MM-DD-slug>/push.md` (`type: push`, `linked_pushes` for inbound
links). One-off scripts and source captures route to `documents/transcripts/`
or `documents/prototypes/` per the artifact-routing rules in the system
architecture doc; they don't need a push wrapper.

If a content push uses a comment-keyword, DM-keyword, reply/link, resource
delivery, or external provider setup plan, write the durable plan to
`pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` with `type: playbook`.
The playbook records the plan, approval state, safe provider state, validation
evidence, and outcomes. It does not execute provider mutation.

If `core/vocabulary.md` defines display words (e.g. `terms.push.singular: drop`),
speak the operator's word in conversation while still writing engine files.
If the repo still has legacy `campaigns/` records, recommend `mb doctor` and
`mb migrate campaigns --plan` before creating new push work.

When creating `push.md`, include the validator-required frontmatter and fill
the values from repo truth or operator answers:

```yaml
---
type: push
slug: YYYY-MM-DD-slug
kind: nurture
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

---

## Triage

Mining, scraping, competitor research, transcribing or extracting from video ("mine", "scrape", "research competitors", "what are they saying", "transcribe") is research work: say "Mining is research work — `/mb-think` handles that and saves to your `research/` folder. Should I switch you over?" and route there. "Short clips from sales video", "repurpose this VSL" or "social cuts from this sales video" continue with [references/sales-video-repurpose.md](references/sales-video-repurpose.md). "Create", "generate", "write scripts", "make content" continue here. If unclear, ask: "Are you trying to mine competitor content (research) or create new scripts (generate)?"

---

## Pull Latest Updates

For the standard Main Branch update check and failure warning, see [`references/pull-engine-updates.md`](references/pull-engine-updates.md). Run it at the start of every invocation.

Then run `mb status --json --peek` from the business repo and use its
`readiness`, `drift.items`, and `ranked_actions` facts before asking setup or
reference-health questions. Direct file checks below are content-specific, not
repo-health probes.

---

## Mining Lives In /mb-think

This skill assumes mining already happened: users arrive with concepts from `research/*-competitor-mine.md`, a topic, or their own research. Mining methodology (Visual/Audible/Emotional framework, AI capabilities and limits, why mining flows into reference): [references/mining-methodology.md](references/mining-methodology.md).

If a selected research file has `brief_format: grok-8`, use its downstream handoff before generating: ICP and audience language for hooks, journey stage for format and CTA, competitive landscape for contrast, brand story for voice, content/assets for proof, and metrics/constraints for the success bar. If the brief names a resource-delivery mechanic, write or update a push playbook as a plan only; do not execute provider mutation.

When organic work is meant to sharpen an offer instead of only create content, load `.claude/reference/conversion/offer-sharpening.md`. Use the rubric to turn audience language, objections, proof angles, and soft CTAs into durable offer updates through `/mb-think`; do not treat comments or saves as buyer proof by themselves.

---

## Offer Context Resolution

Before loading reference files, resolve active offer context with
`.claude/reference/business-primitives/offer-bet-push-proof.md`:

1. If a future `mb` JSON field exposes active offer state, use it.
2. Do not treat `.vip/local.yaml` as the source of truth for active-offer
   state. If legacy state exists, confirm the offer with the user instead of
   silently routing.
3. If an offer is selected and `core/offers/[offer]/offer.md` exists, load it as the active offer.
4. If no offer is selected AND `core/offers/` exists: ask which offer.
5. If no `core/offers/` folder: use `core/offer.md` (single-offer mode)
6. If the repo does not have `core/`, do not infer current offer context from
   old paths. Run `mb doctor repair --plan`; use `reference/*` only as legacy
   migration input.

**Always-core files:** `soul.md`, `voice.md`, `content-strategy.md`
**Content strategy layers:** read `core/marketing/distribution-strategy.md`,
`core/marketing/channels/<channel>.md`,
`core/marketing/accounts/<platform>-<account>.md`, and
`core/people/<person>.md` when the run names a channel, account, founder, or
weekly content plan that depends on them. Do not copy person voice into every
account file; reference it.
**Offer-aware files:** `offer.md`, `audience.md`
**Proof files:** company-wide proof in `core/proof/testimonials.md`,
`core/proof/typicality.md`, and `core/proof/angles/`; offer-specific proof in
matching files under `core/offers/[active]/proof/`. Read older offer
testimonial files as compatibility context only.
Before turning proof into posts, videos, or outcome claims, read
`money_path.objects.proof.quality` from `mb status --json --peek`. Treat
generic testimonials, specific outcomes, offer linkage, typicality context, and
outcome feedback as factual signals. Do not describe proof as good,
high-converting, persuasive, or ready to win.

**Offer argument:** `/mb-organic video [offer] "concept"` — e.g., `/mb-organic video community "morning routine"`
If offer specified, it selects the offer for this run only.

---

## First-Time Setup

Requires `core/voice.md` (always core), plus resolved `offer.md` and `audience.md` (offer-aware — checks `core/offers/[active]/` first, falls back to `core/`).

**Optional but recommended:** `core/content-strategy.md` — If present,
/mb-organic reads the recognition target, pillars, asset jobs, non-publishing
rules, and strategy links. If the repo has
`core/marketing/distribution-strategy.md`, channel files, account files, or
`core/people/<person>.md`, read the relevant ones before drafting. Works
perfectly without them.

**Congruence check:** If `core/operations/funnel/skool-surfaces.md` exists, read it. Organic content should echo the same positioning and claims visible on the Skool about page and pricing cards. No contradictions between organic and the landing experience.

**CWD-first:** If current Main Branch markers exist in CWD, use it. If CWD looks like an old Main Branch repo, run `mb status --json --peek` and/or `mb doctor repair --plan` before saved config or discovery. Do not write to old repo structure. Otherwise, run `mb status --json --peek` and use its repo/readiness facts if available. If status cannot identify a repo, ask the user or run `/mb-setup`.

Missing files? See [references/first-time-setup.md](references/first-time-setup.md).

---

## Presenting Options (Keep It Tight)

Don't list all modes in chunky blocks. Check for recent mining in `research/`, recommend ONE path based on context, and mention alternatives in one line. With concepts: "Found recent mining (research/...) with 10 concepts. Recommended: pick a concept and generate a video script. Other modes: `carousel "concept"`, `static "concept"`. Which concept interests you? Or provide your own topic." Without: offer (1) mine first via `/mb-think` and return, or (2) give a topic and generate directly.

---

## Modes

### `/mb-organic` (Default)

Check for existing mined concepts, pick one, generate scripts.

```
Check research/ -> Check content-strategy.md and relevant strategy layers (if present) -> Select concept -> Generate -> Output
```

If content-strategy.md exists and has pillars or asset jobs defined, suggest topics aligned to those pillars when the user has no specific concept in mind.

If no mining exists, prompt: "No mined concepts found. Want to mine competitors first? That's `/mb-think` — should I switch you over?"

### `/mb-organic mine` (Routes to /mb-think)

Redirect: "Mining is research work now. Routing you to `/mb-think` for mining — it'll save to `research/` and you can come back here to generate scripts from those concepts." Then invoke `/mb-think`.

### `/mb-organic video "concept"`

Generate Reels/TikTok script from a concept.

### `/mb-organic carousel "concept"`

Generate multi-slide carousel copy from a concept.

### `/mb-organic static "concept"`

Generate single-post caption from a concept.

**Output path (all script modes):** `pushes/YYYY-MM-DD-organic-[offer]-{slug}/organic-batch-001.md` (include offer slug in multi-offer mode; omit `[offer]-` in single-offer mode). On legacy repos that still have `campaigns/`, run `mb migrate campaigns --plan` first; do not write new content under `campaigns/`.

**Output frontmatter:**
```yaml
---
type: output
format: video | carousel | static
date: YYYY-MM-DD
status: draft
platform: instagram | tiktok
---
```

Campaign name is REQUIRED. Ask user if not provided. Examples: `january-hooks`, `transformation-series`, `pain-point-reels`.

---

## Context Awareness (Check Before Recommending)

**At session start, scan what's been done:**

1. Check `research/*-competitor-mine.md` — Who was mined? When?
2. Check `pushes/*-organic-*/` — What scripts exist? Treat `campaigns/` as a legacy fallback only.
3. Don't suggest re-mining same handles from today
4. Recommend generating from existing mining if concepts unused
5. Check `core/content-strategy.md` — What recognition target, pillars, asset jobs, and strategy links are defined?
6. If the channel/account/person is named, check the matching `core/marketing/` and `core/people/` files before drafting.

Offer remaining concepts, mining new competitors via `/mb-think`, or a fresh topic, and ask what to call the batch (examples: `january-hooks`, `transformation-reels`). More examples: [references/examples.md](references/examples.md).

---

## Transparency

Before generating: show which reference files you're using.
Before saving: show file paths.

---

## Full Flow Walkthrough

1. Check for concepts in `research/*-competitor-mine.md`; if none, ask whether to mine first (route to `/mb-think`) or take a topic directly.
2. User picks a concept or provides their own; map it to their offer, audience and voice.
3. Generate with the matching framework (video, carousel, static).
4. Save to `pushes/YYYY-MM-DD-organic-{slug}/`, never `campaigns/` (legacy compatibility only).
5. Checkpoint prompt: run `mb checkpoint --plan --json`, show the proposed checkpoint and blockers, validate the chosen message with `mb checkpoint --validate "..." --json`, then after operator approval save with `mb checkpoint --message "..." --yes`.

---

## Video Mode

Input: concept from mining, user topic, or research file.

| Framework | Structure | When to Use |
|-----------|-----------|-------------|
| **Educational** | Hook -> Tips -> Takeaway | How-to, lists |
| **Story-based** | Hook -> Trigger -> Outcome | Personal narrative |
| **Transformation** | Before -> Turning Point -> After | Journey, case study |
| **Problem-Solution** | Hook -> Problem -> Solution | PAS for organic |

Structure: Hook (0-3s) → Retain (3-45s) → Reward (final 5-15s)

See [references/organic-frameworks.md](references/organic-frameworks.md) and [references/video-script-template.md](references/video-script-template.md).

---

## Carousel Mode

7-10 slides: Hook → Value (one idea/slide) → Summary → CTA

See [references/carousel-template.md](references/carousel-template.md).

---

## Static Mode

Hook (first line) → Body → Soft CTA → Hashtags (optional)

See [references/static-template.md](references/static-template.md).

---

## Voice Adaptation

Read current voice context. If CWD looks like an old Main Branch repo, run `mb status --json --peek` and/or `mb doctor repair --plan` before relying on it. Match tone, use their vocabulary, avoid their "never say" list.

**Authenticity:** Sounds like creator (not copywriter). Uses contractions. Matches energy. No AI tells ("dive into", "unlock", "game-changer").

See [references/organic-frameworks.md](references/organic-frameworks.md) for soft CTA examples.

---

## Integration with /mb-think

To save winning angles: route to `/mb-think codify` → `core/proof/angles/`.

---

## Content Strategy Integration

If `core/content-strategy.md` exists, /mb-organic uses it to improve output:

- **Pillar alignment:** Suggest topics from defined pillars when user has no specific concept
- **Asset job:** Identify whether the piece should rank, teach, prove, compare, convert, announce, or start a conversation
- **Platform format:** Default to the format matching the target platform from channel or distribution strategy
- **Account fit:** Use account strategy for allowed topics, CTA path, cadence, and content mix when present
- **Person voice:** Use `core/people/<person>.md` for founder/person beliefs, stories, and fabrication boundaries when an account references it
- **Content mix:** Track which pillar types have been generated recently to maintain ratio balance
- **Hooks library:** Pull proven hooks from the hooks library section if populated
- **Enemy-pillar mapping:** Each pillar fights a named enemy. Content should position against the enemy. Check voice.md for declared enemies.
- **Saves-first metrics:** Weight save-ability highest when evaluating content concepts. Saveable = educational, actionable, reference-worthy.

If content strategy files do not exist, /mb-organic works exactly as before --
from mined concepts or user-provided topics. No warnings, no degradation.

---

## Quality Checklist

**Content:** Hook stops scroll. One idea. Value before ask. Soft CTA.

**Saves optimization:** Is this content saveable? Educational, actionable, reference-worthy content drives saves. Saves are the #1 purchase intent signal — weight them above shares and likes.

**Enemy clarity:** Does this content fight a named enemy? Check voice.md for Named Enemies section. Enemy-driven content creates identity contrast.

**Voice:** Sounds like creator. Matches energy. Uses vocabulary. No AI tells.

**Platform:** Appropriate length. Correct structure. Optimized for retention/saves.

**Skool congruence:** If `skool-surfaces.md` exists, claims and positioning match live about page + pricing cards.

---

## Examples & Compaction Recovery

For walkthrough examples (context-aware start, video-only, mining redirect) and the recovering-from-compaction protocol, see [references/examples.md](references/examples.md).

---

## References

**Setup:** [first-time-setup.md](references/first-time-setup.md), [minimal-voice-template.md](references/minimal-voice-template.md), [apify-setup.md](references/apify-setup.md)

**Frameworks:** [organic-frameworks.md](references/organic-frameworks.md)

**Sales video repurposing:** [sales-video-repurpose.md](references/sales-video-repurpose.md)

**Templates:** [video-script-template.md](references/video-script-template.md), [carousel-template.md](references/carousel-template.md), [static-template.md](references/static-template.md)

**Methodology & Examples:** [mining-methodology.md](references/mining-methodology.md), [examples.md](references/examples.md)
