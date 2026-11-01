# Mode: Hook Library (Creative Variations)

Generate punchy, truly diversified creative variations for static image ads that feed Meta's Andromeda algorithm (July 2025), which rewards different psychological conversations, not surface rewrites. Any quantity works ("give me 5" or "give me 50"). Also called "one-liners": same methodology, same pipeline; both trigger words route here.

## Process

Follow the 6 steps in [one-liner-methodology.md](one-liner-methodology.md): core outcome, extract specifics, 15-20 reasons to buy, hook categories, generate (default 30), output. Real examples by offer type: [one-liner-examples.md](one-liner-examples.md).

**Anchor rule (non-negotiable):** every variation includes at least one specific role, outcome, niche pain, value prop, timeline or proof point. Specificity test: if it could sell a gym membership, a life coaching program or a generic course, rewrite it.

## Input

With a business repo: resolved `offer.md`, resolved `audience.md`, `core/voice.md`, testimonials (for understanding results only; never quote them as hooks). With no repo: ask for materials.

## Output

Save to file, not chat, so review can edit it directly.

1. Ask for the campaign name (required).
2. Confirm quantity: "How many? A few to test (5-10) or a full batch (30+)?" unless already specified.
3. Create `pushes/YYYY-MM-DD-creative-variations-[offer]-{campaign}/` (include the offer slug in multi-offer mode only).
4. Save full generation context plus the variations to `creative-variations-batch-001.md`: frontmatter (`type: output`, `format: creative-variations`, `date`, `status: draft`, `platform: meta`), then Core Outcome, Extracted Specifics table, Reasons to Buy, Hook Categories used, and the numbered Creative Variations. The context lets reviewers check anchors, resume without re-extraction, and see why hooks were chosen.
5. Tell the user: "Saved {N} creative variations. Running automatic post-generation pipeline..." and run the Automatic Post-Generation Pipeline (see SKILL.md).
