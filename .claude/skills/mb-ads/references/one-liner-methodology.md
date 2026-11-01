# One-Liner Methodology

> The user-facing names are "creative variations" and "hook library"; use them in headers and file names. This file keeps the original "one-liner" terminology from the cold-traffic methodology. Mode entry and output format: [mode-hook-library.md](mode-hook-library.md).

## Why Diversification Matters

Meta's Andromeda algorithm (July 2025) rewards true creative diversification, not surface variations.

Surface variations (penalized, one ad to Andromeda): "Struggling with lead generation? We can help." / "Need more leads? We've got solutions."

True diversification (rewarded), each a different psychological conversation:
- **Referral dependency:** "If you're still waiting for referrals to grow, that's why you're stuck at the same revenue."
- **Time freedom:** "Spending 20+ hours a week on marketing when you should be doing what you do best?"
- **Competitive pressure:** "Watching competitors with less experience win deals because they have better marketing?"
- **Revenue predictability:** "Tired of the feast-or-famine cycle where you never know if you'll make payroll?"

30 one-liners = 30 different psychological conversations, each anchored in offer-specific details. Voice: if `voice.md` exists, extract tone markers, words to use or avoid, and personality, so the lines sound like the brand. If no reference files exist, ask whether there is a business repo or materials to work from.

## Steps

### 1. Core Outcome
The single transformation every buyer achieves (not features or process): "What does every successful buyer walk away with?" Example: barber coaching -> barbers making $10K+/month working fewer hours. This is the throughline; each line approaches it from a different angle.

### 2. Extract Specifics (REQUIRED)
Prevents generic lines. Fill this from reference files, testimonials and offer details; these become the required anchors for Step 5.

| Category | What to extract (example) |
|----------|---------------------------|
| Roles/Outcomes | job titles, results, companies (DevOps Engineer, AWS, 60k+) |
| Timelines | how fast results come (8 weeks, within a year) |
| Niche Pains | pains specific to this audience (stuck on service desk 2+ years, no CS degree, 40k ceiling) |
| Value Props | what makes this offer different (mock interviews with Principal Engineers, 500+ community) |
| Failed Alternatives | what they tried (YouTube tutorials, cheap courses, self-study) |
| Proof Points | numbers, stats, community size |

### 3. Reasons to Buy
List 15-20 fundamentally different reasons someone would buy (the protein-powder exercise: muscle building, busy professional, weight loss, health-conscious, athlete, budget-conscious are six different conversations about one product). Each reason is a different person or mindset, psychological driver, pain or desire, and trigger moment. Brainstorm across: functional benefits, emotional benefits, identity shifts, pains to escape, fears driving action, desires pulling them, trigger moments, past failures, competitive pressure, life circumstances. Need at least 15 before writing.

### 4. Hook Categories
Vary the type; don't write 30 "If you're..." lines.

| Category | Pattern |
|----------|---------|
| Problem Agitation | Identify and amplify a specific pain |
| Emotional State | Meet them in their feeling |
| Situational Context | A specific circumstance |
| Transformation | Paint the after |
| Contrarian | Challenge conventional wisdom ("You don't need a CS degree to land a DevOps job. You need a system.") |
| Curiosity Gap | Create an information gap |
| Reframe | Shift perspective ("You don't have a skills problem. You have a structure problem.") |
| Identity | Call out who they are |
| Comparison | Before/after or vs competitors |
| Urgency/Timing | Why now matters |
| Direct Identity Callout | Who they are + situation + direct invitation |

**Direct Identity Callout (high performer; use for 8-10 of 30):** `If you're a [specific identity] + [specific situation/pain/desire], [direct close].` Stack specificity in the first part (not "parent" but "mom of a child ages 2-12"). Closes: "we built this for you", "this is for you", "you're in the right place", "this was made for you". Example: "If you're a barber doing 60-hour weeks and still stuck at $4K/month, this was made for you."

### 5. Generate
Each line addresses a different reason to buy (Step 3), uses varied hook types (Step 4), includes at least one specific anchor (Step 2), meets them where they are, and matches brand voice.

**Anchor rule (mandatory) and specificity test:** see mode-hook-library.md. Generic: "You have the motivation. You're missing the roadmap." (fits anything; fails.) Anchored: "Feeling behind at 27? The guy who just got hired at AWS felt the same way 8 weeks ago." (only this offer; passes.)

Patterns to mix: `If [identity] + [niche pain], [specific outcome]`; `[Affirm]. [Negate]. [Specific reframe].`; `[Niche situation] + [outcome contrast]`; `[Specific pain is fixable]. [Value prop].`; `[Challenge belief with specific proof]`; `[Failed alternative] -> [specific value prop]` ("YouTube taught you Docker. It won't prep you for the 5-stage AWS interview."); `[Niche trigger] + [specific timeline]`.

### 6. Output
Save per mode-hook-library.md, then run the post-generation pipeline.

## What NOT to Do

| Don't | Why |
|-------|-----|
| Generic affirmations ("You're not behind. You just haven't started.") | Could be for any offer |
| Vague value props ("the right system", "accountability", "roadmap") | Empty buzzwords |
| Client quotes as one-liners | Testimonials are proof, not hooks |
| Feature lists with price | Features don't stop the scroll |
| Surface variations of one message | Andromeda penalizes this |
| Yes/no questions ("Want to make more money?") | Binary "no" kills the hook |
| Skip the anchor check | Generic lines waste ad spend |
| Internal vocabulary or mechanism explanations ("Same engine + different data = different outputs.") | Cold traffic doesn't know your jargon; say "AI that knows your business gives outputs that sound like you." |

## Write for Cold Traffic, Not Insiders (CRITICAL)

Reference files use insider language (how the founder thinks, technical terms, internal concepts). Translate it; don't parrot it. "Engine + data model" -> "AI that knows your business"; "Reference files" -> "your offer, audience and voice, documented once"; "Compound context" -> "knowledge that builds instead of resets"; "The architecture" -> "how it works" or cut it.

Test for every line: would someone who has never heard of this offer understand why it matters to them in the first 3 seconds? Use simple words, speak to their pain, desire, fear, identity and transformation (their experience), not your mechanism. After generating all 30, re-read each asking "Am I explaining how it works, or speaking to what they experience?"

## Clarifying Questions (No Repo Mode)

Ask only what is missing after reviewing materials, not all at once: specific results (job titles, salaries, companies, timelines); the top 3 frustrations specific to this audience ("stuck at 40k ceiling", not "feeling stuck"); what is different about the offer; what they tried that failed; price point; how fast people see results.

## Recovery from Compaction

Check which step you were on, whether the Specifics table exists (regenerate if missing), and how many lines are done (`ls -ltd pushes/*-creative-variations-*/ | head -3`). Confirm "I see we were generating one-liners. Continue from #[X]?" and resume.

## Quality Check Before Submitting

- **Specificity (most important):** every line has an anchor from Step 2; none could work for a gym, diet or generic self-help program; pains and outcomes are specific ("stuck on service desk for 2 years", "DevOps Engineer at AWS").
- **Diversification:** each line has a different reason to buy; varied hook types; no surface variations.
- **Formatting:** no client quotes, no feature lists, short punchy sentences.
- **Cold traffic:** no internal vocabulary or mechanism explanations; speaks to what they experience; understandable in 3 seconds.
- **Voice (if voice.md exists):** tone matches brand, no forbidden words, preferred vocabulary applied.

## Compliance

Compliance review runs automatically in the post-generation pipeline (SKILL.md). Common one-liner flags: income/outcome claims ("$10K months", "6-figure"), implied guarantees ("never worry about X again"), unsubstantiated comparisons ("better than", "fastest"). P1 issues go to the user for decision; P2/P3 fixes are proposed as a diff and applied only after approval.
