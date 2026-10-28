---
type: decision
date: 2026-05-05
status: accepted
topic: Operator-readable git history
linked_decisions:
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-05-operator-loops-taxonomy.md
linked_docs:
  - docs/operator-loops.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/300
  - https://github.com/dmthepm/mainbranch/issues/306
participants: [Devon, Codex]
tags: [v0-3, git-history, checkpoints, operator-loops, reflect]
---

# Operator-Readable Git History

## Decision

Business-repo commits should read like an operator journal. A non-technical
operator should be able to scan `git log --oneline`, a future dashboard
timeline, or a team daily log and understand what happened without learning git
or the Main Branch loop taxonomy.

This contract applies to **business repos** created by `mb init` / `mb onboard`.
The Main Branch engine repo keeps its existing contributor commit style
(`[add] [update] [fix] [remove] [refactor]`). That is an engineering-grammar
contract for contributors, not an operator-grammar contract for business
owners. The two contracts coexist by audience, not by overlap.

Use lower-case, past-tense business verbs as the default commit prefixes:

- `[added]`
- `[updated]`
- `[decided]`
- `[opened]`
- `[closed]`
- `[drafted]`
- `[shipped]`
- `[connected]`
- `[ran]`
- `[fixed]`

Main Branch may still map these commits to the four canonical loops from the
operator-loop taxonomy decision: Sense / Decide / Ship / Reflect. Operational
maintenance is not a fifth loop; it is Ship through the Ops channel unless a
stronger path or body signal says otherwise. Main Branch should not ask
operators to write loop or channel names into normal business commit subjects.

## Why Not Loop Tags

The operator loops are product architecture, defined in
[operator-loops.md](../docs/operator-loops.md) and locked by
[the operator-loop taxonomy decision](2026-05-05-operator-loops-taxonomy.md).
They help Main Branch rank work, group status signals, and design workflows.
They are not the language a business operator naturally uses to remember the
quarter.

The loop names themselves were chosen to be plain enough to read in product
docs (Sense / Decide / Ship / Reflect), but commit prefixes optimize for a
different read: operators scanning their own history months later. Verbs win
that read; loop names do not.

Compare:

```text
[ship] workshop-waitlist lander
[reflect] workshop-waitlist outcome
```

With:

```text
[shipped] workshop-waitlist lander
[closed] bet workshop-waitlist -- 51/40, won
```

The second version says what happened. The loop grouping can be derived later
by tooling from the verb, object, path, and optional trailers.

## Subject Shape

Use this default subject shape:

```text
[verb] object -- plain result
```

The `-- plain result` clause is optional, but useful when the object alone does
not explain why the change matters.

Good subjects:

```text
[opened] bet workshop-waitlist -- target 40 signups
[drafted] 4 ad variants for workshop-waitlist
[shipped] workshop-waitlist lander
[closed] bet workshop-waitlist -- 51/40, won
[updated] offer.md -- raised price to $147
[decided] v0.3 launch date -- May 15
[connected] Stripe -- checkout verified locally
[ran] mb update -- 0.2.6 to 0.3.0
```

Avoid subjects that require Main Branch internals to understand:

```text
[know] update reference
[execute] artifact batch
[checkpoint] work saved
```

## Verb Contract

This table is the initial machine-consumable contract for status grouping,
checkpoint planning, validation, retros, and future dashboard timelines.
Tooling may override the loop or channel when the changed path or
object gives a stronger signal, but it should start here.

| Prefix | Loop | Channel hint | Use when | Common objects |
|---|---|---|---|---|
| `[added]` | Sense or Ship | path-derived | New durable context, state, or reviewable artifact exists | `offer.md`, research note, proof, audience segment, site copy |
| `[updated]` | Sense or Ship | path-derived | Existing durable context or artifact changed | offer, pricing, audience, voice, daily log, ad batch |
| `[decided]` | Decide | - | A choice and its rationale were accepted | bet, launch date, provider choice, offer direction |
| `[opened]` | Decide | - | A bet or public issue became active | bet, public issue |
| `[closed]` | Reflect | - | A bet or public issue got a verdict | bet, public issue |
| `[drafted]` | Ship | path-derived | A reviewable artifact was produced, whether or not it is public yet | ads, VSL, organic batch, site copy |
| `[shipped]` | Ship | path-derived | Work reached a recipient, deploy target, or public surface | site, page, email, ad batch, offer |
| `[connected]` | Ship | Ops | A provider or local integration became usable | Stripe, GitHub, Cloudflare, Meta Ads |
| `[ran]` | Ship | Ops | A maintenance, update, migration, validation, or import ran | `mb update`, migration, import, smoke |
| `[fixed]` | Ship | path-derived | A broken workflow, file, link, provider, or setup path was repaired | checkout copy, skill wiring, provider metadata |

`[fixed]` can describe business work when the object is business-facing, such
as `[fixed] checkout copy -- clarified guarantee`. For grouping, tooling should
prefer stronger path signals over the row default. Path and body signals
should reclassify by default: `core/` and `research/` usually map to Sense,
accepted `decisions/` and opened `bets/` map to Decide, `pushes/` and
published artifacts map to Ship, and bet verdicts, retros, superseded
decisions, and lessons map to Reflect.

## Commit Body

Subjects should stay readable on one line. Bodies carry the detail future
agents need.

Preferred body sections:

```text
Changed:
- core/offers/workshop.md
- pushes/2026-05-06-workshop-waitlist/ads.md

Why:
- Captures the next paid-traffic test before site generation starts.

Next:
- Draft the lander in /mb-site.

Refs:
- bets/2026-05-06-workshop-waitlist.md
- decisions/2026-05-05-workshop-price.md
- https://github.com/dmthepm/mainbranch/issues/300
```

Use `Refs:` when the commit touches or advances a durable object with an
identifier: a bet, decision, campaign, GitHub issue, provider setup note, or
release. Future beginner mode should add missing refs when it can infer them
and warn when it cannot. Future strict mode may fail validation for missing
refs on recognized object types.

## AI Attribution

Do not add AI attribution to every commit by default. Git already records the
local author. Requiring an attribution trailer on every checkpoint makes the
history noisier than the work.

Use an `Agent:` trailer only when it materially changes interpretation of the
work, such as generated copy, generated site code, synthetic research summary,
or compliance review:

```text
Agent: Claude Code /mb-ads
```

Do not use `Agent:` for purely mechanical maintenance unless the operator or
repo policy asks for it.

## Daily Checkpointing

Do not add a `[day]` prefix. Daily checkpoints should use normal verbs and put
the daily context in the object or body.

Examples:

```text
[added] daily log -- 2026-05-05
[updated] daily log -- captured launch blockers
[ran] daily checkpoint -- no open work after /mb-end
```

If there are no file changes, do not create an empty commit just to mark the
day. `mb status` and future dashboards can show "no checkpoint today" from git
facts without inventing a fake event.

## Beginner And Power Modes

Beginner mode should prefer one readable checkpoint per meaningful work
boundary. It should generate a normal verb subject, explain the proposed
checkpoint in plain English, and treat missing refs or imperfect grouping as
warnings unless there is a safety risk.

Power mode should allow concern-separated commits and stricter validation. In
power mode, missing refs for recognized bets, decisions, campaigns, provider
setups, issues, and releases can become errors when the operator or CI opts in.

Both modes must block commits when safety gates find likely secrets, local
machine files, private account data, merge conflicts, or changes outside the
intended repo.

## Examples By Work Type

### Bets

```text
[opened] bet workshop-waitlist -- target 40 signups
[updated] bet workshop-waitlist -- added Meta Ads learning
[closed] bet workshop-waitlist -- 51/40, won
```

### Offers

```text
[updated] offer.md -- raised price to $147
[decided] refund policy -- keep 14-day guarantee
```

### Decisions

```text
[decided] v0.3 launch date -- May 15
[decided] provider boundary -- keep secrets outside repo
```

### Sites

```text
[drafted] workshop-waitlist lander copy
[shipped] workshop-waitlist lander
[fixed] lander measurement -- consent event firing again
```

### Ads

```text
[drafted] 4 ad variants for workshop-waitlist
[updated] ad batch workshop-waitlist -- removed compliance risk
[shipped] workshop-waitlist ad batch -- operator approved
```

### Provider Setup

```text
[connected] Stripe -- checkout verified locally
[connected] Cloudflare -- pages deploy linked
[fixed] Meta Ads metadata -- restored customer id note
```

### Migration And Update

```text
[ran] mb update -- 0.2.6 to 0.3.0
[ran] mb migrate -- normalized .mb state
[fixed] skill links -- repaired stale personal symlink
```

### Daily Checkpoint

```text
[added] daily log -- 2026-05-05
[updated] daily log -- captured pricing decision and launch blockers
```

## Implementation Slices

1. Publish this contract and keep checkpoint PRDs aligned with it.
2. Add a shared verb contract in code for `mb checkpoint`, `mb status`, and
   future timeline consumers.
3. Teach `mb checkpoint --plan --json` to propose these subjects, infer loop
   grouping, and include ref/agent trailer suggestions.
4. Add beginner warnings and opt-in strict validation for unknown verbs,
   missing refs, unsafe files, and non-business-readable subjects.
5. Update `/mb-start`, `/mb-end`, `/mb-think`, `/mb-site`, `/mb-ads`, and
   `/mb-bet` to call the checkpoint contract instead of inventing per-skill
   commit prefixes.
6. Teach `mb status` and future dashboards to group recent git history by the
   four-loop map while displaying the original operator-readable subject.

## Validation Contract

For this decision slice:

- Level 0 docs/decision review is required for frontmatter, links, examples,
  and public/private boundary.
- `scripts/check.sh` must pass before pushing.
- CLI tests, package/install smoke, fixture repo smoke, and runtime smoke are
  not required because this branch does not change command behavior, packaged
  data, repo scaffolding, skill discovery, or runtime invocation.

## Consequences

- Business git history has a public language contract before checkpoint
  validation ships.
- Future tooling can group by operator loop without exposing loop labels as
  default commit prefixes.
- Beginner checkpointing can be readable without being lax about safety.
- Power users and CI can opt into stricter reference and prefix validation
  without making the first-run path feel like developer ceremony.
- The verb contract becomes the basis for the public bets feed:
  `[opened]` commits with `Refs: bets/<slug>.md` are Decide events, and
  `[closed]` commits with the same ref are Reflect events. Publishing those
  outcomes is a chained Ship event. Renaming or removing these verbs after
  v0.3.x requires coordinated migration across `mb checkpoint`, `mb status`,
  the bets-feed module, and any operator wikis or dashboards consuming git log.
