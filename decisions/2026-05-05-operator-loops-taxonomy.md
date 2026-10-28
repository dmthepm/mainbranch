---
type: decision
date: 2026-05-05
status: accepted
topic: Operator loops taxonomy
linked_decisions:
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/306
participants: [Devon, Claude (8 research subagents across 2 rounds)]
tags: [v0-3, loops, taxonomy, architecture, foundation]
---

# Operator Loops — Sense · Decide · Ship · Reflect

## Decision

Main Branch organizes operator workflow into **four loops**. The audience is
operators and small teams running real businesses: solo founders, small
agencies, course creators, productized services, indie SaaS, and small ecom
teams. The taxonomy works for one person and for small teams sharing a
business repo.

The four loops:

1. **Sense** — pull state in
2. **Decide** — choose what to wager
3. **Ship** — produce and release the work
4. **Reflect** — extract the lesson

These are workflow phases, not categories. Channels (Paid, Organic, Pages, Ops) live underneath as the *what you're shipping*. Skills live across them as *tools that traverse loops* — most skills span 2-3 loops.

This taxonomy is locked. It feeds skill design, the `mb status` daily briefing, the bets-feed renderer, the verb-prefix commit contract, retros, dashboards, and every public doc that references "what an operator does."

## Why this matters

The operator-loop taxonomy is load-bearing architecture. It determines:

- Which skills exist and what they're called
- How `mb status` groups recent activity
- The verb-prefix commit map (e.g., `[shipped]` → Ship loop, `[closed]` → Reflect loop)
- The bets-feed primitive (a `bets/<slug>.md` file is a Reflect-loop artifact published via Ship)
- The `/mb-start` triage routes
- How docs categorize work for non-technical operators

Get this wrong and every downstream surface inherits the confusion. The taxonomy broke twice in the week leading up to this decision — first at "Narrate" (too jargon), then at "Show vs. Execute" (overlapped). Each time the breakage came from the same root cause: trying to name a 5th loop that didn't structurally exist.

## How we decided

Two parallel research rounds, eight subagents total. Each was told to take a
position rather than fence-sit. The public synthesis below captures the
reasoning, alternatives, and stress-test results without depending on private
scratch files.

### Round 1 — four perspectives

| Agent | Recommendation |
|---|---|
| Theory (frameworks: PDCA, OODA, GTD, EOS, Lean) | 5 loops: Notice · Think · Make · Show · Reflect |
| Empirical (10 real operators across business types) | 4 loops: Sense · Decide · Make · Show |
| Tools (15+ operator templates) | 5 verbs: Sense · Frame · Choose · Ship · Learn |
| Stress-test (20-activity classification) | 5: Know · See · Decide · Make · Narrate |

### Round 2 — four more perspectives

| Agent | Recommendation |
|---|---|
| Garry/gstack | 4 loops: Sense · Decide · Ship · Reflect |
| Garry/gbrain | 4-phase action loop + separate Reflect cadence |
| Runtimes (Hermes / OpenClaw / get-shit-done) | Keep current frontrunner; zero collisions |
| AI-era reframe | 4 loops: Sense · Decide · Ship · Reflect |

### Convergences across all eight agents

1. **Rename Execute → Make/Ship.** Unanimous (8/8). "Execute" is corporate ("execute the plan") and implies top-down execution; operators and small teams do exploratory production. "Make" is honest; "Ship" is the indie-hacker idiom that captures production-and-release in one verb.
2. **Collapse Know + See into Sense.** 3/4 round-1 agents converge; gbrain validates the state-vs-action split. Operators experience pulling state in as one act, not two.
3. **Reflect deserves a name.** The single most-skipped behavior across operator and small-team workflows is calendared review. GTD, EOS, gbrain Dream Cycle, AI-era safety arguments converge here. Naming Reflect is the intervention, not just description.
4. **Ship as the production-and-release verb.** gstack `/ship` empirically collapses build + test + release. AI compresses Make+Show into one session. Marc Lou and Pieter Levels say "I shipped X" to mean "made and released X."

### How we resolved the disagreements

- **Make vs. Ship?** Chose Ship. Indie-operator vocabulary, gstack's empirical pattern, AI compression argument, and operator preference all align.
- **Five loops or four?** Chose four. The 5th-loop instability across rounds is itself proof the slot is fictional. Reflect is its own loop on a different cadence (calendared review, not real-time action).
- **Add an AI-era loop (Direct/Verify)?** No. Direct lives inside Decide; Verify lives inside Ship. Loop names should outlive specific runtimes.

## The four loops in detail

### 1. Sense

**The act of pulling state in.** Read the dashboard. Open the inbox. Skim the support thread. Glance at Stripe. Read your own `core/offer.md` before a sales call. Listen to a customer interview. Check `mb status`.

| Sense looks like | Sense doesn't look like |
|---|---|
| Reading what's there | Acting on what you read |
| Observation, capture, monitoring | Choosing the next move |
| Both real-time (dashboard) and durable (core reference files) | Producing new content |

The collapse of "Know" and "See" into one loop is deliberate. The difference between knowing something durably and seeing it in this morning's dashboard is a temporal flavor, not a separate phase.

### 2. Decide

**The act of choosing what to do, including what to wager.** Pick the next bet. Choose which client to drop at renewal. Decide whether to raise prices. Pick the next newsletter topic. Lock the launch date.

| Decide looks like | Decide doesn't look like |
|---|---|
| Bounded choice from finite options | Open-ended exploration |
| Committing to a direction | Doing the work |
| Discrete moments | Continuous activity |

Plain English wins; thinking-without-deciding is procrastination dressed up. Naming the verb "Decide" forces commitment.

### 3. Ship

**The act of producing and releasing work in one motion.** Draft the ad and post it. Build the lander and deploy it. Record the video and publish it. Connect Stripe (the action and the operational result). Run `mb update`.

| Ship looks like | Ship doesn't look like |
|---|---|
| Output reaching a recipient | Reflection on the output |
| One verb covering production and release together | Two separate phases |
| Operational craft as well as growth craft | Picking what to ship |

Indie-operator definition of "ship": anything that goes from your head into the world. Universal across business types — fitness coaches "ship" programs, consultants "ship" deliverables, ecom operators "ship" creatives.

A note on gstack's "ship" baggage: Garry's `/ship` skill specifically means "release code with tests + version + PR." Main Branch's Ship is broader. The two are siblings, not collisions — anyone using both reads context to disambiguate.

### 4. Reflect

**The act of extracting the lesson — usually scheduled.** Close a bet with a verdict. Write a quarterly retro. Review what shipped this month. Update `core/voice.md` after realizing your tone shifted. Render the post-mortem. Hand the lesson back to Sense by updating reference files.

| Reflect looks like | Reflect doesn't look like |
|---|---|
| Extracting from past work | Producing new work |
| Calendared (weekly review, end-of-bet, monthly retro) | Continuous |
| Output that updates Sense memory | Output for external audiences |
| Verdict, lesson, change-of-mind | Status update |

Some Reflect output gets *published* through Ship — that's a chain, not a loop boundary blur. A bet's verdict (Reflect) might be tweeted (Ship the verdict to Twitter). The two loops chain; they're not the same loop because the artifact moves.

## Loops chain together

The cycle isn't strictly linear. Real workflows chain loops:

- **Reflect → Sense.** A retro updates `core/offer.md`. The next time you Sense, you see the new offer.
- **Decide → Ship.** Most bets go straight from decided to shipped within a session.
- **Ship → Reflect → Ship.** Ship the lander, reflect on conversion data after 7 days, ship a revised version.
- **Sense → Decide → Sense.** Sometimes new data prompts more sensing before you can decide.

Loop chains are a normal pattern, not a taxonomy bug. The cycle compounds when chains close (especially Reflect → Sense, where lessons become durable context).

## How skills relate to loops

**Principle: skills are journeys; loops are stations.** A skill traverses one or more loops. Skills can have brand names that don't mirror loop names. There's no requirement for skill-to-loop 1:1 mapping.

| Skill | Loops it spans | Why |
|---|---|---|
| `/mb-status` | Sense | Pure status read |
| `/mb-start` | Sense + Decide | Triages current state and routes to next action |
| `/mb-think` | Sense + Decide + Ship | Research → decide → codify (codify is Ship of the decision into a file) |
| `/mb-bet new` | Decide | Pure framing/wagering |
| `/mb-bet close` | Reflect | Pure verdict-rendering |
| `/mb-bet narrate` | Reflect → Ship | Render the lesson, then publish it |
| `/mb-site` | Ship | Build + deploy in one motion |
| `/mb-ads` | Ship (with Reflect-style review gates) | Draft + post |
| `/mb-end` | Reflect (with optional Ship of the reflection) | Session crystallize |
| `mb status` (CLI) | Sense | Daily briefing |
| `mb checkpoint` | Ship (the commit) | Persists work |

The `/mb-think` skill name is preserved — "Think" is a brand name for a multi-loop research-decide-codify skill, not a loop. Operators say "I'm going to /mb-think this through" — the skill name describes the activity feel, not a phase.

**Future skill convention.** Skills declare which loops they touch in `SKILL.md` frontmatter:

```yaml
---
name: mb-bet
description: ...
loops: [decide, reflect, ship]
---
```

This lets `mb status` and downstream tooling reason about loop coverage without parsing prose.

## Channels (the four pillars) sit underneath loops

Every Ship event happens through a channel. The four channels are durable:

- **Paid** — Meta ads, sponsored placements
- **Organic** — Reels, threads, newsletter, YouTube, Skool posts
- **Pages** — landers, minisites, websites
- **Ops** — bookkeeping, P&L, compliance, operating health

A Ship is `(loop, channel)`. Posting an ad = Ship through Paid. Sending the newsletter = Ship through Organic. Running `mb update` = Ship through Ops.

This separation keeps the loop count low and stable: channels can grow over time without bloating the loops.

## What AI changes about loops

Most operator-loop frameworks (PDCA, OODA, GTD, EOS, Lean) predate AI agents.

- **AI does NOT add a top-level loop.** Direct (specifying the AI's task) lives inside Decide. Verify (checking the AI's output) lives inside Ship as a gate.
- **AI compresses cadence dramatically.** Week-long Make+Ship cycles become 30-minute sessions. This *increases* loop frequency, not loop count.
- **AI makes Reflect more important, not less.** Speed without verification compounds error. When loops run fast, the only protection is the calendared Reflect step.
- **Main Branch's loops stay AI-agnostic in name.** Sense, Decide, Ship, Reflect work for an operator using AI heavily, lightly, or not at all. The AI-nativeness lives in cadence, gates inside each loop, and the tooling Main Branch provides.

## Compatibility with other agent runtimes

Audited against Hermes, OpenClaw, get-shit-done, gstack, gbrain.

- **Zero name collisions** with Sense / Decide / Ship / Reflect.
- **gstack uses `/ship`** for code-release specifically. Main Branch uses Ship for any "audience reach" event. Siblings, not collisions.
- **get-shit-done has Discuss / Plan / Execute / Verify** as a workflow shape. No name overlap. GSD's "Execute" is what we'd call Ship; GSD's "Verify" is a gate inside our Ship.
- **gbrain has DETECT → READ → RESPOND → WRITE → SYNC** for memory-agent loops. This supports Sense (detect, read) and Ship (write, sync), not a peer taxonomy.

The smallest plug-in surface Main Branch needs to expose: agentskills.io-compatible `SKILL.md` frontmatter that declares `loops:` and works in any runtime that respects the standard.

## Alternatives considered and rejected

Documented for credibility — these were real candidates with real arguments.

### Rejected: 5 loops with Reflect (Sense · Decide · Make · Show · Reflect)

Strongest 5-loop alternative. Forced classification ambiguity ("am I making or shipping right now?") that the four-loop version eliminates by collapsing Make+Show into Ship.

### Rejected: 4 loops without Reflect (Sense · Decide · Ship · iterate-back)

Empirical agent argued Reflect is "Sense applied to your own past." Analytically true. Rejected because the entire point of naming Reflect is the intervention — operators skip reflection if it isn't named.

### Rejected: Notice · Think · Make · Show · Reflect (Theory's 5)

Lost on three grounds: bigger diff from existing draft and CLI vocabulary, "Notice" and "Think" not common in empirical data, marginal clarity gain doesn't justify rename cost.

### Rejected: Sense · Frame · Choose · Ship · Learn (Tools' 5)

Cleaner verb pipeline but renames every slot. "Frame" and "Choose" feel synonymous to operators.

### Rejected: Add a "Direct" loop for AI-era operation

AI-reframe agent argued for it. Direct is a mode within Decide; promoting it bureaucratizes the taxonomy and makes it runtime-specific.

### Rejected: Topical 5-set (Marketing · Sales · Delivery · Ops · Finance)

Notion-OS / dashboard convention. Topical buckets pre-assume a business shape; coordination shapes for big teams; bury the temporal shape where operators and small teams actually fail.

## Implementation slices

What needs to change in the repo to land this taxonomy:

1. This decision file (lands canonical record)
2. Rewrite `docs/operator-loops.md` to four loops with examples, anti-examples, loop-chains
3. Update `docs/ethos.md` 5-loop list to 4
4. Update `docs/roadmap.md` one-line loop reference
5. Update `CHANGELOG.md [Unreleased]` to note the loops decision
6. Add `loops:` frontmatter convention to `AGENTS.md` SKILL.md schema documentation
7. Skill SKILL.md updates handed to `devon/main-218-...` branch
8. Verb-prefix commit map updates handed to `devon/main-237-...` branch
9. `mb status` grouping by loop / `bets/<slug>.md` `loops:` field handed to status-v1 / bets-feed work

## Sources / show our work

The decision was driven by eight parallel research streams covering canonical workflow frameworks, real operator profiles across business types, operator tool taxonomies, classification stress-tests, gstack and gbrain studies, runtime compatibility, and an AI-era reframe.

The engine repo ships decisions and product. Durable research and the streams that led to a decision live in our private planning repo. The decision body above is the public synthesis; future contributors who want to question the taxonomy can read the reasoning, alternatives, and stress-test results captured here without re-running the eight streams.

## Decision authority

Locked by Devon, 2026-05-05, on the basis of two research rounds and a stress-test against 20 real activities + 3 cross-business operators. This taxonomy is durable until either:

- The product audience materially shifts beyond operators and small teams
- A canonical AI-era framework emerges that obviates one of the four loops
- A real-world operator workflow is found that can't be classified into one of the four

In any of those cases, re-open this decision. Otherwise, this is the foundation.
