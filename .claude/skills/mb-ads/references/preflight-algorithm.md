# Ad Creative Readiness

Read deterministic status first, then score ad-specific reference depth before
generating ads when status lacks the needed creative detail. This prevents thin
context from producing generic output without duplicating repo-health,
provider, drift, or setup checks.

---

## When to Run

- **`/mb-ads` Step 0** — After `mb status --json --peek`, before triage menu appears
- **`/mb-start`** — Only as fallback/detail after status `readiness`; do not
  treat this as a shared CLI readiness contract

---

## Scoring Matrix

First run:

```bash
mb status --json --peek
```

Use status `readiness`, `drift.items`, `ranked_actions`, `integrations`, and
`measurement` as source of truth for setup, stale context, provider readiness,
and repair commands. The scoring below is ad-specific creative depth, not repo
health.

Score each file 0-3 based on line count + section presence.

| Score | Label | Criteria |
|-------|-------|----------|
| **0** | Missing | File does not exist |
| **1** | Stub | File exists but under 20 lines or only has headers |
| **2** | Adequate | 20-80 lines with key sections populated |
| **3** | Rich | 80+ lines with specifics, examples, or proof |

### Files Scored

Use the shared offer-resolution rules in
`.claude/reference/business-primitives/offer-bet-push-proof.md` before scoring
offer and audience files:

1. If a future `mb` JSON field exposes active offer state, use it. Otherwise
   ask the user which offer this work is for; do not silently route from
   `.vip/local.yaml`.
2. If an offer is selected and `core/offers/{offer}/offer.md` exists, score that file
3. Otherwise fall back to `core/offer.md`
4. Same resolution for `audience.md`
5. If `core/` is absent, run `mb doctor repair --plan` and treat old
   `reference/*` paths as migration input before relying on them.

See `docs/system-architecture.md` (current path resolution) for the full algorithm.

| File | Key Sections | Weight |
|------|-------------|--------|
| `offer.md` (resolved) | Price, mechanism, benefits, guarantee | Required |
| `audience.md` (resolved) | Pains, desires, demographics, psychographics | Required |
| `core/voice.md` | Tone, phrases, personality, don'ts | Required |
| `core/proof/testimonials.md` + offer testimonials + `money_path.objects.proof.quality` | Testimonials plus factual outcome and offer-link signals | Required |
| `core/proof/typicality.md` + offer typicality + `quality.typicality` facts | Average-case outcome context, caveats, common failure context, and time-to-outcome | Recommended |
| `core/proof/angles/` | At least 1 angle file beyond README | Required |
| `core/brand/visual-style.md` | Colors, typography, mood, prompt fragments | Optional (affects image gen) |

### Scoring Logic

Resolve offer and audience paths first. Each file: missing = 0, under 20 lines = 1, 20-79 = 2, 80+ = 3. `angles/`: count `.md` files excluding README.md (0 = 0, 1 = 1, 2-3 = 2, 4+ = 3). Composite = sum of all 6 scores (max 18).

---

## Thresholds

| Composite | Status | Action |
|-----------|--------|--------|
| **12-18** | GREEN | Proceed to triage. Full creative diversity possible. |
| **8-11** | YELLOW | Warn user. Show gaps. Allow override: "I know my reference is thin, proceed anyway." |
| **4-7** | RED | Route to `/mb-think` with specific enrichment targets. Offer parallel agents to fill gaps. |
| **0-3** | BLOCKED | Route to `/mb-setup`. Cannot generate meaningful ads. |

---

## Report Format

Display to user at Step 0:

```
Pre-Flight Check:
  offer.md      ███░ 3/3 (rich — 211 lines)
  audience.md   ███░ 3/3 (rich — 165 lines)
  voice.md      ███░ 3/3 (rich — 230 lines)
  testimonials  ███░ 3/3 (rich — 332 lines)
  angles/       █░░░ 1/3 (stub — 1 file, need 4+)
  visual-style  ░░░░ 0/3 (missing)

  Composite: 13/18 — GREEN
  Gaps: angles thin, no visual style

  Image gen:    ✓ provider available for this run
  Ad account:   — not connected (optional — lets me see your live Meta ad performance to inform new ads)
```

**Ad account status line:** Always display after the composite score. Describes the capability, not the tool name. See SKILL.md "User-Facing Display" for the exact wording for connected vs not connected states.

---

## Gap Guidance

When gaps are found, explain WHY each matters for ads:

| Gap | Why It Matters |
|-----|----------------|
| **offer.md missing** | Ads will be generic — no specifics about what you sell, price, or mechanism |
| **audience.md missing** | Can't write hooks that resonate — no pains, desires, or language to use |
| **voice.md missing** | Ads will sound generic AI — no brand personality to apply |
| **testimonials missing** | No social proof angles available — limits creative diversity |
| **angles/ empty** | All ads will use the same entry point — Andromeda penalizes repetition |
| **visual-style missing** | Image prompts will be freestyle only — no brand consistency option |

### /mb-think Enrichment Targets

When the score is YELLOW or RED and the user wants stronger ads before
generating, route to `/mb-think` with the smallest useful target:

| Gap | /mb-think Research Target |
|-----|---------------------------|
| Thin audience language | Customer language mining from calls, surveys, support, onboarding, cancellations |
| Missing objections | Review mining and sales-call objection extraction |
| Generic or unlinked proof | Permissioned testimonial pass, explicit offer links, and `core/proof/typicality.md` for average-case context |
| Empty angles | Competitor gap map and review/comment mining for new emotional territories |
| No hook variety | Winning script teardown and content/comment mining |
| Weak mechanism | Competitor mechanism map and offer codification |

Use `mb-think/references/winning-ad-research.md` for the workflow. Research
must synthesize and codify before `/mb-ads` generates from it.

---

## Smart Recommendations

Based on available data, recommend a creative approach:

| visual-style.md | Recommendation |
|-----------------|----------------|
| Rich (3/3) | "60% on-brand, 40% freestyle for variety" |
| Adequate (2/3) | "50/50 on-brand and freestyle — brand style is basic" |
| Stub (1/3) | "Mostly freestyle — brand style needs enrichment" |
| Missing (0/3) | "All freestyle — no brand style file. Want to create one? (3 questions)" |

---

## Quick Scaffold

If visual-style.md is missing, offer inline creation during pre-flight (don't force `/mb-setup`):

> "No visual style file found. I can create one now with 3 questions:
> 1. What's your brand's visual mood? (minimal/bold/editorial/playful/dark)
> 2. What are your brand colors? (hex codes or descriptions)
> 3. What photography style fits? (lifestyle/product/abstract/editorial)
>
> Or skip — all image prompts will be freestyle."

---

## Media Output Path Check

**Not part of composite score.** This is an informational check that runs after scoring, before image generation begins.

### Detection Flow

```
1. Read current Main Branch media settings when available.
   Legacy local settings may be read as fallback only.
2. Resolve image path:
   a. media.images → use directly
   b. media.root → {root}/images/
   c. neither → prompt user

3. If path resolved and exists:
   → Confirm: "Images will save to {path}/{campaign}/"

4. If path resolved but doesn't exist:
   → "Output folder doesn't exist: {path}. Create it? (y/n)"
   → If yes: mkdir -p

5. If no path configured:
   → "Where should generated images be saved?"
   → Examples: "~/Google Drive/My Drive/Main Branch/images"
   → Use that path for this run
   → mkdir -p {path}
```

Do not write media defaults into deprecated local settings. Keep the choice
session-scoped unless a current `mb` settings command exposes a durable media
path.

**If path is inside git repo:**
→ Warn: "This folder is inside your git repo. Binary images will bloat history. Want me to add a .gitignore entry? (y/n)"

---

## Decisions-Without-Codification Detection

Check for a common stuck state:

```
if decisions/ has 3+ files with status: accepted
AND core/ has gaps (composite < 12)
THEN surface:
  "You have accepted decisions that haven't been applied to core files.
   Want to run parallel agents to codify them?"
```

---

## Integration Points

- **`/mb-ads`** — Step 0, blocks or warns before triage
- **`/mb-start`** — Global scan, surfaces as priority items
- **`/mb-think codify`** — Uses same scoring to detect what needs enrichment
- **Parallel agents** — When RED, offer to spawn agents that fill gaps from existing research/decisions

---

*Ad creative-depth algorithm used by /mb-ads (Step 0). /mb-start may use this
only as fallback interpretation after deterministic status facts.*
