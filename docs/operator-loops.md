# Operator Loops

Main Branch organizes operator workflow into **four loops**. The audience is
operators and small teams running real businesses: solo founders, small
agencies, course creators, productized services, indie SaaS, and small ecom
teams. The taxonomy works for one person and for two-to-five people sharing
a business repo.

Growth work is the first visible wedge, but the loops are not marketing-only.
The same model covers meetings, fulfillment, bookkeeping summaries, team
updates, repo topology, provider setup, and internal operating pushes.

The four loops:

1. **Sense** — pull state in
2. **Decide** — choose what to wager
3. **Ship** — produce and release the work
4. **Reflect** — extract the lesson

A command, skill, issue, or release should make at least one of these loops better. The full reasoning behind this taxonomy lives in
[decisions/2026-05-05-operator-loops-taxonomy.md](../decisions/2026-05-05-operator-loops-taxonomy.md).

## Loops are workflow phases, not categories

The four loops describe *what an operator is doing right now*. They are
verbs, not buckets. Channels (Paid, Organic, Pages, Ops) live underneath as
the *what you're shipping*. Skills live across the loops as *tools that
traverse 1+ loops*. Most skills span two or three loops.

The cycle isn't strictly linear. Real workflows chain loops — for example,
Reflect → Sense (a retro updates `core/offer.md` so the next time you Sense,
you see the new offer). See "Loops chain together" below.

## The daily loop in loop terms

The normal Main Branch day is a compact Sense -> Decide -> Ship -> Reflect
chain:

- **Sense:** `/mb-start`, `/mb-status`, or `mb status --json --peek` reads
  repo health, graph links, connected-account readiness, recent activity,
  update state, GitHub task/proposal signals, and MoneyPath readiness for the path from
  customer progress to offer, proof, CTA, channel, push, playbook, page, and
  outcome feedback.
- **Decide:** the agent and operator choose the next business move: a bet to
  frame, a piece of research to run, a decision to codify, a push to advance, a
  playbook to draft, or a repair to approve.
- **Ship:** the skill creates or updates the artifact, while `mb` supplies
  deterministic checks, repair commands, validation, connected-account readiness, and
  checkpoint plans.
- **Reflect:** `/mb-end`, bet close/narrate behavior, push review notes, or
  checkpoint guidance records what changed and what the next Sense pass should
  know.

The user-facing nouns are business nouns: bets, goals, offers, pushes,
playbooks, outcomes, and checkpoints. The technical nouns underneath are still
part of the architecture, but they serve the loop: issues are durable work
threads, pull requests are proposals/reviews, commits are saved checkpoints,
graph links are relationship memory, and connected-account handles point to
external systems without copying private account data into the repo.

## 1. Sense

**Question:** What's true right now — about the business, the market, the
inbox, the numbers?

This is the act of pulling state in. Both real-time observation and durable
reference-file reads sit here.

| Sense looks like | Sense doesn't look like |
|---|---|
| Reading what's there | Acting on what you read |
| Observation, capture, monitoring | Choosing the next move |
| Real-time (`mb status`, dashboard) and durable (`core/offer.md`) | Producing new content |

**Current surfaces**

- `mb status` (with `--json` topology, "Business map" line, and MoneyPath
  readiness)
- `mb doctor` and `mb doctor repair --plan` (including migration drift and
  topology-drift previews)
- `mb graph` (with `repo` nodes and hub/child relationship edges)
- `mb connect status`
- `core/`, `research/`, `decisions/`, `pushes/`, `log/`, `documents/`
- GitHub issues, pull requests, release history
- linked business, site, offer, finance, ops, and client repos when the team
  chooses separate operating boundaries, surfaced through topology facts

**Direction**

- provider-readiness signals that become more specific as official paths are
  smoke-tested;
- an optional local dashboard that visualizes existing repo / GitHub / provider
  truth without becoming the source of truth;
- meeting, transcript, fulfillment, and bookkeeping summaries routed into the
  right durable artifacts instead of staying in chat.

## 2. Decide

**Question:** What should I do next, and why?

The act of choosing what to wager — committing to one direction from finite
options. Discrete moments, not continuous activity.

| Decide looks like | Decide doesn't look like |
|---|---|
| Bounded choice from finite options | Open-ended exploration |
| Committing to a direction | Doing the work |
| Discrete moments (start of week, before a launch, when stuck) | Continuous activity |

**Current surfaces**

- `/mb-start`
- `/mb-think`
- `mb status` ranked actions and MoneyPath blockers
- GitHub issues and priorities
- `mb issue draft` (frame friction or a feature gap clearly enough to commit
  to acting on it)

**Direction**

- Explicit pin, skip, and defer controls
- Decision trees for provider choices, paid-SaaS exceptions, sensitive data,
  and workspace/repo boundaries
- clearer repo-boundary choices: when a site, offer, client, finance, or ops
  surface graduates into its own repo

## 3. Ship

**Question:** What work are we putting into the world?

The act of producing and releasing in one motion. Indie-operator definition:
anything that goes from your head into the world. Universal across business
types — fitness coaches ship programs, consultants ship deliverables, ecom
operators ship creatives, SaaS founders ship features.

| Ship looks like | Ship doesn't look like |
|---|---|
| Output reaching a recipient | Reflection on the output |
| One verb covering production and release together | Two separate phases ("make" then "show") |
| Operational craft (`mb connect`, `mb update`) and growth craft (ads, sites) | Picking what to ship |

**Current surfaces**

- `/mb-ads`
- `/mb-organic`
- `/mb-site`
- `/mb-books` (read-only close and reconciliation review)
- `/mb-seo` (public-site review, plus experimental optional OpenSEO research)
- `mb connect`
- `mb checkpoint`
- `mb doctor repair --plan` / `--apply` (Ship through Ops: cleaning up a stale
  repo is the released artifact)
- `mb issue open` (Ship through Ops: turning a reviewed draft into a public
  GitHub issue)
- `mb update`
- `/mb-wiki` (specialty: personal/atomic-notes wiki, not part of the core daily
  loop)

**Channels — the four pillars**

- **Paid** — Meta ads, sponsored placements
- **Organic** — Reels, threads, newsletter, YouTube, Skool posts
- **Pages** — landers, minisites, websites
- **Ops** — bookkeeping, P&L, compliance, meetings, fulfillment, provider setup,
  repo topology, team updates, and operating health

A Ship event is `(loop, channel)`. Posting an ad = Ship through Paid.
Sending the newsletter = Ship through Organic. Running `mb update` = Ship
through Ops.

**Direction**

- Skills leaning more heavily on CLI facts instead of duplicate checks
- Optional provider and sidecar contracts
- Beginner-safe connector flows for GitHub, Cloudflare, Google, Meta, Apify
- deeper site/CMS rails on top of `mb site check` over Cloudflare, GitHub, and
  operator-approved measurement
- richer Paid, Organic, Pages, and Ops surfaces (bookkeeping through
  `mb books`, P&L, meetings, fulfillment, compliance)

## 4. Reflect

**Question:** What did we learn, and what changes because of it?

The act of extracting the lesson — usually scheduled. Output that updates
Sense memory (offer, voice, audience, decisions) and feeds the next round
of work.

| Reflect looks like | Reflect doesn't look like |
|---|---|
| Extracting from past work | Producing new work |
| Calendared (weekly review, end-of-bet, monthly retro) | Continuous |
| Output that updates Sense memory | Output for external audiences |
| Verdict, lesson, change-of-mind | Status update |

**Current surfaces**

- `/mb-end`
- `/mb-bet close` and `/mb-bet narrate`
- `bets/` and the bet lifecycle (verdicts go here)
- `decisions/` (when superseding a prior decision is itself a reflection)
- `CHANGELOG.md` (release-as-retro)
- `mb checkpoint` and history — business-readable saved checkpoints at meaningful
  boundaries

**Direction**

- Bet-to-offer graduation rules
- Status and dashboard visibility for active bets, deadlines, and outcomes
- Public bets pages generated from repo truth
- Quarterly retro skills that scan recent bets and decisions

**Why Reflect is its own loop and not a phase inside Ship.** When loops run
fast (especially under AI), the calendared review step is the only protection
against compounding error. Frameworks that treat reflection as automatic
(PDCA, OODA, Lean Startup) find it gets dropped. Frameworks that name it
(GTD's Weekly Review, EOS's Issues, gbrain's Dream Cycle) see operators
actually do it. Naming Reflect is the intervention.

## Loops chain together

The cycle is not strictly linear. Real workflows chain loops:

- **Reflect → Sense.** A retro updates `core/offer.md` in a single-offer repo,
  the portfolio thesis in a multi-offer repo, or
  `core/offers/<slug>/offer.md` for a specific offer. The next time you Sense,
  you see the updated truth.
- **Decide → Ship.** Most bets go straight from decided to shipped within
  a session.
- **Ship → Reflect → Ship.** Ship the lander, reflect on conversion data
  after 7 days, ship a revised version.
- **Sense → Decide → Sense.** Sometimes new data prompts more sensing
  before you can decide.
- **Reflect → Ship.** A bet's verdict (Reflect) might be tweeted (Ship the
  verdict to Twitter). The two loops chain — they're not the same loop
  because the artifact moves through a channel.

Loop chains are a normal pattern, not a taxonomy bug. The cycle compounds
when chains close — especially Reflect → Sense, where lessons become durable
context.

## Skills are journeys; loops are stations

A skill traverses one or more loops. Skills can have brand names that don't
mirror loop names. There is no requirement for skill-to-loop 1:1 mapping.

| Skill | Loops it spans | Why |
|---|---|---|
| `/mb-status` | Sense | Pure status read |
| `/mb-start` | Sense + Decide | Triages current state and routes to next action |
| `/mb-think` | Sense + Decide + Ship | Research → decide → codify (codify is Ship of the decision into a file) |
| `/mb-bet new` | Decide | Pure framing/wagering |
| `/mb-bet close` | Reflect | Pure verdict-rendering |
| `/mb-bet narrate` | Reflect → Ship | Render the lesson, then publish it |
| `/mb-site` | Ship | Build + deploy in one motion |
| `/mb-books` | Sense, Reflect | Review private books readiness and close state |
| `/mb-seo` | Sense, Decide, Ship | Review public pages, research with approval, and save findings |
| `/mb-ads` | Ship (with Reflect-style review gates) | Draft creative and review before approval |
| `/mb-end` | Reflect (with optional Ship of the reflection) | Session crystallize |
| `mb status` (CLI) | Sense | Daily briefing |
| `mb checkpoint` | Ship | The saved checkpoint is itself a Ship event |

The `/mb-think` skill name is preserved — "Think" is a brand name for a
multi-loop research-decide-codify skill, not a loop. Operators say "I'm going
to /mb-think this through"; the skill name describes the activity feel, not
a phase.

**Skill convention:** new skills declare which loops they touch in
`SKILL.md` frontmatter:

```yaml
---
name: mb-bet
description: ...
loops: [decide, reflect, ship]
---
```

`mb skill validate` checks loop declarations and their names today.
Status grouping and downstream use of loop coverage are future work.

## Applying the loops

When opening or working an issue, name the loop it improves:

- **Sense** for status, doctor, graph, drift, integrations, reference-file
  capture
- **Decide** for ranking, triage, recommendations, issue drafting, operator
  overrides
- **Ship** for domain workflows (ads, sites, organic, sales videos), connectors,
  package updates, operational craft
- **Reflect** for bets, retros, verdicts, decision supersession, public bets
  pages

A large branch is acceptable when it improves one coherent loop with one
observable success metric. A tiny branch is not automatically better if it
costs more cold start, review, CI, and release overhead than it returns.

## Channels (the four pillars)

Underneath Ship sit the four channels every operator can recognize:

- **Paid** — paid acquisition, ad creatives, ad accounts, sponsored placements
- **Organic** — owned audience content (Reels, TikTok, threads, YouTube,
  newsletter, Skool posts)
- **Pages** — landers, minisites, websites, public bet pages, deployed assets
- **Ops** — bookkeeping (hledger), P&L, compliance, integrations, meetings,
  fulfillment, repo topology, team updates, and operating health

Skills cluster by channel today (`/mb-ads` for Paid, `/mb-organic` for
Organic, `/mb-site` for Pages, `mb books check` for bookkeeping Ops). Sales
videos/VSLs are conversion outputs inside those workflows, not their own
channel.
Channels grow over time without bloating the loop count — adding new sidecar
CLIs adds new Ship channels, not new loops.

## See also

- [decisions/2026-05-05-operator-loops-taxonomy.md](../decisions/2026-05-05-operator-loops-taxonomy.md) — full reasoning, alternatives considered, research record
- [docs/ethos.md](ethos.md) — product principles
- [docs/roadmap.md](roadmap.md) — release direction
