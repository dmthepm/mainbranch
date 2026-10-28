---
type: decision
date: 2026-05-06
status: accepted
topic: Main Branch operating spine — taste, volume, identity
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/328
linked_decisions:
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-05-operator-loops-taxonomy.md
  - decisions/2026-05-06-campaign-primitive-and-architecture-model.md
  - decisions/2026-05-06-campaigns-refuse-list.md
tags: [v0-3, foundation, philosophy, voice]
---

# Main Branch Operating Spine

## Decision

Main Branch is built on three operating archetypes, braided. Every product
decision passes through this filter.

| Layer | Archetype | Job |
| --- | --- | --- |
| **The system itself** (CLI, validate, status, doctor, graph) | YC + Linear taste — opinionated minimalism, sharp primitives, refuses bad defaults | Quiet, fast, decisive. Earns trust through restraint. |
| **The operator's daily push** (pushes, ads, organic, sites) | ClickFunnels + Hormozi craft — volume, reps, offer-discipline, double down on winners | The system makes shipping easier, not slower. Reps are the unit. |
| **The operator's identity** (bets, soul, voice, weekly state) | Robbins / Naval / Buffett — long-arc vision, identity-level commitment, one-paragraph state of the business | The system protects this from the noise. Identity is reference, not a goal. |

**The rule when they fight:** taste wins on the system surface, volume wins
on the operator's behalf, identity wins at weekly cadence.

## Audience

Main Branch users are non-technical small business owners — coaches,
creators, agencies, community/membership operators, course sellers,
consultants, local service businesses. Engineering principles can come
from Linear, dbt, YC, ADRs, Diataxis. Operator-facing language must speak
business-owner.

This is a contract. Engine internals can carry their stable engineering
names (`primitive`, `schema`, `frontmatter`, `validate`, `graph`,
`provider refs`, `sidecar`). Beginner and operator workflow copy should
avoid unexplained internal jargon. Command reference, contributor docs,
and technical troubleshooting may name exact commands, file concepts, and
schemas when precision matters.

## Ten Cross-Cutting Principles

These are the durable rules. Future PRs and decisions are graded against
them.

1. **The repo is the business.** Not the dashboard, not the SaaS, not the
   Notion. Files in git are the source of truth. Provider systems and
   dashboards are inputs and views, not memory.

2. **The primitive is the product.** A primitive earns its place by enabling
   a question the operator actually asks. No primitive without a question.
   When in doubt, do not add one.

3. **Every push names its offer and its promise.** A coordinated push without
   a named offer is a task. A push without a one-sentence promise is
   theater. The system enforces both as the schema work lands.

4. **Lifecycle includes doubling down.** Most systems treat "completed" as
   the end. Real operators find a winner and pour fuel. This is a
   first-class state, not an implicit "start another push."

5. **Surface what matters most this week.** Not everything you could do.
   One push, one lever, one number. `mb status` is a triage, not a
   dashboard.

6. **Identity is reference, not a goal.** `core/soul.md` is who the
   operator is. `bets/` are what they're trying. `pushes/` are what
   they're shipping. The system does not blur these layers, and it
   writes `core/` files in timeless language.

7. **The system refuses loudly.** `mb` exits non-zero with a clear reason
   when an operator tries to do the wrong thing. The campaigns refuse-list
   decision is part of this principle. The product is judged by what it
   refuses.

8. **The system asks better questions.** Skills do not fill out forms;
   they have conversations that produce real artifacts. The artifact
   exists from turn one — the operator edits, never starts blank.

9. **Reps are the unit of progress.** Volume is honest. Theater is not.
   The system shows the rep count (pushes shipped, bets closed,
   decisions made), not the hype.

10. **Operator owns the vocabulary. Engine owns the taste.** The operator's
    business calls campaigns *drops*, *launches*, *challenges*, *promos*,
    *plays*, *rounds*, *waves*. The engine speaks the operator's word back
    to them. Engine internals stay stable; operator surface mirrors the
    operator. (The vocabulary-storage mechanism is a follow-up issue; the
    principle lands here.)

## Voice / Tone Profile For Operator-Facing Surfaces

### Do

- "Your active push: Workshop waitlist. Day 14. 11 of 40 signups. Today's
  lever: cold-traffic ad refresh."
- "Closed cleanly. Saved a research note from what surprised you. Want me
  to draft a newsletter post?"
- "I matched a bet — say if I'm wrong."
- "Rough is fine. We can sharpen on the way."
- "This push has no offer. Pick one or skip."

### Don't

- "Awesome!" / "Great job!" / "Let's go ahead and..." / emoji in `mb status`
- Filler phrases that read like tutorials.
- Enterprise jargon: *stakeholder, initiative, alignment, synergy,
  blocker, OKR, KPI, deliverable*.
- Unexplained internal jargon in beginner copy: *primitive, schema, enum,
  provider refs, sidecar, canonical, ADR, runtime, adapter, fixture,
  smoke test*. (Public CLI command names like `mb validate` and `mb graph`
  may appear in command reference; the test is whether a first-time
  operator could read the line without a glossary lookup.)
- Numeric priorities (P0/P1) — see the refuse-list decision.
- False urgency. Scarcity theater. Hype.

## What This Decision Authorizes

- Product-shape PRs should be reviewed against the ten principles. When a
  change bends one of them, the PR description should name the tradeoff.
- The voice profile applies to beginner and operator-facing copy: the top
  of `README.md`, `mb status` conversational output, skill prompts in
  `.claude/skills/*/SKILL.md`, error messages, and onboarding flows.
  Command reference, `docs/` technical material, AGENTS.md, and
  engine-internal docs may use engineering language because their audience
  is operators-as-readers or contributors.
- Issue grooming uses the principles as a rubric. An issue that violates
  a principle either gets reshaped or is rejected with the principle cited.

## What This Decision Refuses

- Dashboards, web UIs, or hosted services as the canonical memory. The repo
  is the business.
- Configurability that papers over a missing decision. Defaults beat knobs.
- Productivity-porn surfaces (streaks, gamification, leaderboards).
- Engineering-blog tone in operator-facing copy.

## Consequences

- Bundle 1 (this issue, #328) ships the refuse-list decision and this spine
  decision together — the philosophy is durable before the schema work in
  the upcoming issues expands.
- Future issues for schema deltas, lifecycle v1.1, operator-vocab rename,
  `mb push close` ritual, `mb push open` interview, and the operate-in-public
  narration loop all inherit this spine. They cite it in their issue body.
- Operator-vocabulary storage (the mechanism that lets a coach's local
  Claude Code session see *drops* instead of *campaigns*) is the first
  follow-up where principle 10 becomes code.
- Skills that already ship (`/mb-ads`, `/mb-organic`, `/mb-site`, `/mb-vsl`,
  `/mb-bet`, `/mb-start`) are graded against the voice profile in their
  next material change. No bulk rewrite — improvements happen on the path
  of normal work.

## Sources

This decision synthesizes research across direct-response operating systems
(Hormozi, Brunson, Walker), product-taste systems (YC, Linear, Stripe,
Basecamp, Apple HIG), and long-arc identity/investing systems (Robbins,
Naval, Munger, Buffett, Dalio, Clear).

The durable artifacts are this decision, the campaigns refuse-list decision,
and the campaign primitive decision they sit alongside.
