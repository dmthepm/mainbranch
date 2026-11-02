# Minisite Brief

Load this for steps 2-4 of the minisite flow: brief draft, pre-lock review, and brief lock.

## Brief Draft

The brief is the locked source of truth for the minisite. Compose it from:

- resolved `offer.md`: framing, value prop, pricing, transformation;
- resolved `audience.md`: pain frame, language, objections;
- `.claude/reference/conversion/offer-sharpening.md`: offer fundamentals,
  style choice, proof/typicality, risk reversal, reason to act, and next step;
- `voice.md`: tone, register, named enemies, "never say";
- persisted research files from [`minisite-research.md`](minisite-research.md);
- any `brief_format: grok-8` researched brief that names the offer, audience,
  journey, competitive gaps, brand story, requirements, assets, and success
  constraints;
- the conversion endpoint kind, once the operator picks it.

Draft the brief into one markdown artifact in the business repo:

```text
decisions/YYYY-MM-DD-minisite-brief-<offer-slug>.md
```

## Pick The Dial

Three values: `convert`, `story`, `brand`.

- `convert`: sales-conversion priority. Full Seven Sweeps plus Expert Panel scoring at review.
- `story`: archetype-faithful storytelling. Drops Prove-It and Zero-Risk sweeps.
- `brand`: voice and brand presence. Only Clarity, Voice, and Heightened Emotion sweeps.

The dial decides review depth and influences paired-imagery style. See [`review.md`](review.md).

## Pick The Archetype

Load [`archetypes.md`](archetypes.md), the index, not all 9 detail files. The operator picks one archetype for the offer and may name a second for `audience_current_archetype` (what the audience is trapped in). Load only the picked detail file.

The archetype unlocks paired-imagery template, headline-formula matches, and the `do_not_state` list: conclusions the audience must reach themselves.

## Pick Headline Formulas

Load [`headline-formulas.md`](headline-formulas.md). Pick 2-3 formulas that match the dial and archetype. The brief draft uses these as scaffolding, not final copy.

## Brief Schema (v0.1)

```yaml
---
type: brief
date: YYYY-MM-DD
slug: <offer-slug>
status: proposed
dial: convert | story | brand          # required
archetype: wounded-healer              # optional but recommended
audience_current_archetype: victim     # optional
copy_framework_tag: Compact-Landing    # optional, see website-build.md
headline_formulas_picked:              # optional, suggested 2-3
  - "outcome-without-pain"
  - "for-audience-who-tried-X"
do_not_state:                          # required when archetype set
  - "Don't give up!"
  - "It's never too late."
four_forces:                           # optional (JTBD)
  push: ""
  pull: ""
  habit: ""
  anxiety: ""
voice_anchor_lines:
  use:
    - ""
    - ""
  avoid:
    - ""
---
```

The brief body still includes:

- headline and subhead, no more than 2 lines, transformation-anchored, using one chosen formula;
- value prop: 3 short reasons or one extended argument;
- mechanism summary for the how-it-works page;
- picked supporting pages: 2-4 from `proof`, `pricing`, `faq`, or operator-added;
- conversion endpoint: kind and URL, or "to be wired in conversion step";
- adjacency map: each section's two images named, with a one-line `do_not_state` caption guard.

Existing minisite briefs created before 2026-04-29 use the older schema with no `dial`, `archetype`, or `do_not_state`. The skill tolerates them. New briefs created on or after 2026-04-29 must include the new fields. `mb validate` enforces the date-based check.

## Review (Pre-Lock)

Run [`review.md`](review.md) sweeps in parallel against the brief draft. Sweeps are dial-gated:

- `convert`: all 7 sweeps plus Expert Panel scoring (every persona >= 7, panel average >= 8).
- `story`: sweeps 1, 2, 3, 5, 6. Drops Prove-It and Zero-Risk.
- `brand`: sweeps 1, 2, 6 only. Clarity, Voice, and Heightened Emotion.

Auxiliary gates always run:

- De-AI'd, against [`anti-patterns.md`](anti-patterns.md): banned phrases, em-dash overuse, overused-verb cluster.
- Framework-true, when `copy_framework_tag` is set.
- Archetype-fidelity: no `do_not_state` line written as a headline.

Synthesize findings and surface them to the operator. They address or proceed.

## Brief Lock

Once review is addressed, or skipped with operator awareness, checkpoint the brief in the business repo:

```bash
cd <business_repo>
mb checkpoint --plan --json
mb checkpoint --validate "[decided] minisite brief -- <slug>" --json
mb checkpoint --message "[decided] minisite brief -- <slug>" --yes
```

The brief is now durable. Move to [`minisite-setup.md`](minisite-setup.md).
