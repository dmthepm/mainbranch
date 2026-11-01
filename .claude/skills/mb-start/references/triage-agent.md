# Triage Agent Reference

Complete reference for the smart triage system in `/mb-start`. Runs when the
user selects the triage route from the /mb-start menu. Contains agent prompts,
pre-gathering, gating, synthesis format, anti-patterns, and save behavior.

Modeled on `/mb-end`'s crystallize agent pattern. Where crystallize asks "what did today mean?", triage asks "what should happen next?" Where crystallize is a mirror, triage is a compass.

---

## When to Run

**Triage runs when the user chooses it.** It can be the first item on the main
/mb-start route menu, but only when no ranked recommendation or offer list is
using the same number in that response. The user can always skip it and pick a
skill directly.

**Why not always-on:** Three parallel agents burn 50-80K tokens. Running them every session means the user hits 60%+ context before doing any actual work. /mb-end gates crystallize behind meaningful activity — /mb-start gates triage behind user choice. Agents eat the heavy context in their own windows, keeping main lean for whatever comes next.

**Auto-suggest triage when:**
- Returning user (last saved checkpoint or status journal event is older than 3 days) and no stated intent
- Readiness is THIN (8-11) — "Triage can help you figure out the highest-leverage gap"
- User says "what should I work on", "help me prioritize", "what to do next"

**Skip triage entirely when:**
- Readiness is EMPTY or MINIMAL (0-7) — answer is obvious: `/mb-setup` or `/mb-think`
- User stated clear intent with `/mb-start ads` or similar

---

## Gating (Like /mb-end's Crystallize)

Before spawning agents, check these gates (modeled on /mb-end Step 5a):

| Gate | Check | If fails |
|------|-------|----------|
| Context budget | Is main context < 50%? | Warn user: "Context is at X%. Triage uses significant tokens. Run it anyway?" |
| Readiness tier | Is score ≥ 8 (THIN or above)? | Skip triage — not enough reference to analyze. Route to `/mb-think` |
| Meaningful state | Does repo have saved checkpoints, decisions, or research? | If brand new repo with just setup scaffolding, skip deep triage — suggest `/mb-think` instead |

### Tiered Spawning

Not every session needs 3 agents. Match agent count to context:

| Condition | Agents | Why |
|-----------|--------|-----|
| THIN (8-11), few saved checkpoints | **1 agent** (Reference Health only) | Not enough content for pipeline or soul analysis |
| GOOD (12-14), active repo | **2 agents** (Reference Health + Pipeline) | Soul analysis adds value when there's meaningful work history |
| FULL (15-18), active repo | **3 agents** (all three) | Full analysis justified |
| User says "deep triage" | **3 agents** regardless | Explicit request overrides tiering |

---

## Architecture: 3 Parallel Read-Only Agents

Spawn three agents in a single message using the Task tool. Each gets a focused analysis lane. All three are **read-only** -- they return findings to the main conversation, which synthesizes and presents.

### Reuse Readiness Data (Token Efficiency)

The triage agents receive the readiness assessment results (scores, gaps,
session state, journal summary) as input context. They do NOT re-scan these.
The readiness assessment (Step 6) already read status journal facts, scored
files, detected active decisions, and checked for uncodified research. Triage
agents go DEEPER -- reading file contents, checking section quality, analyzing
patterns across files, and connecting dots between soul alignment and tactical
work.

**What readiness already computed (pass as context, do not recompute):**
- Per-file scores (soul, offer, audience, voice, testimonials, angles)
- Composite score and status tier (EMPTY/MINIMAL/THIN/GOOD/FULL)
- Recent journal summary
- Open decision count and topics
- Uncodified research count
- Session gaps and last activity date

**What triage agents add (their unique value):**
- Agent 1: Section-level analysis of file contents, cross-file consistency, and business setup pattern fit
- Agent 2: Work pattern analysis, velocity assessment, pipeline bottlenecks
- Agent 3: Soul-strategy alignment, unresolved threads, temporal patterns

### Pre-Gathering (Main Conversation — Keep It Lean)

**The goal is to pass COMPACT data to agents, not load everything into main.** Main gathers lightweight metadata (scores, file lists, git summaries). Agents do the heavy reading (full file contents, cross-file analysis) in their own context windows.

Before routing or spawning agents, build a concrete primitive map from repo
truth. This is not optional in rich or migrating repos; it prevents Claude from
confusing parent truth, offer truth, live bets, execution artifacts, and child
repos.

Gather these in main and pass as structured text in each agent's prompt:

| Content | How | Size | Passed To |
|---------|-----|------|-----------|
| Readiness scores (from Step 6) | Already computed | ~20 lines | All 3 agents |
| Absolute repo path | From Step 2 | 1 line | All 3 agents (agents use this to Read files themselves) |
| Journal groups (30 days) | `journal.groups` from `mb status --json --peek`; fallback to `git log` only if degraded | ~30 lines | Agent 2 |
| Core file change list (30 days) | `journal.events[].files` from status; fallback to `git log --since="30 days ago" --name-only -- core/` only if degraded | ~20 lines | Agent 1, 3 |
| Active decision file names | `grep -rl "status: proposed\|status: accepted" decisions/ 2>/dev/null` | ~10 lines | Agent 2 |
| Unlinked research count | `grep -rl "linked_decisions: \[\]" research/ 2>/dev/null \| wc -l` | 1 line | Agent 2 |
| Past triage file names | `ls research/*-start-triage.md 2>/dev/null` | ~5 lines | Agent 3 |
| Past crystallize file names | `ls research/*-end-of-day-crystallize.md 2>/dev/null` | ~5 lines | Agent 3 |
| active offer | From a future `mb` JSON active-offer field if present, otherwise explicit session/user selection | 1 line | All 3 agents |
| Push lifecycle listing | `grep -rl "status: draft\|status: planned\|status: active" pushes/ 2>/dev/null`; use status/doctor facts for old migrated records | ~10 lines | Agent 2 |
| Primitive map | File lists grouped by the map below | ~40 lines | All 3 agents |

**What agents may read themselves (in their own context, NOT in main):**

Read only the subset needed for the assigned triage question. Start from status
facts, file lists, and filenames; do not recursively scan the whole repo or
linked repos. Never open raw exports, secrets, credentials, customer/member
records, or private local-state files unless the operator explicitly points to a
sanitized file for the current task.

- Brand truth: `core/soul.md`, `core/voice.md`, `core/audience.md`,
  `core/offer.md`, `core/strategy/`, `core/operations/`, `core/brand/`.
- Offer truth: `core/offers/<slug>/offer.md`, optional
  `core/offers/<slug>/audience.md`, and offer-specific proof or angles.
- Bet truth: `bets/*.md`, especially status, deadline, metric, target,
  linked files, result, and verdict.
- Execution truth: `pushes/<slug>/push.md` and artifacts. If status or doctor
  reports old migrated records, treat them as legacy migration input.
- Evidence: `research/`, `decisions/`, `core/proof/`, offer proof, `log/`,
  and `documents/`.
- Relationship checks: `mb status --json --peek`; add `mb graph`,
  `mb validate --cross-refs`, and `mb doctor repair --plan --json` when
  migration drift, stale links, or topology confusion is suspected.

**Classification language agents must use:**

- "Durable business truth" for `core/` and approved evergreen docs.
- "Live wager" for active/open `bets/*.md`.
- "Execution work" for pushes and current artifacts.
- "Proof/evidence" for research, decisions, proof, logs, and documents.
- "Legacy compatibility" for `campaigns/` and old `reference/` paths.
- "Linked operating boundary" when a site, offer, client, finance, ops, or
  archive repo holds its own lifecycle. The parent business repo stays the hub
  for company-level strategy, decisions, bets, and links.

**This keeps main at ~5K tokens of pre-gathering** while agents spend 20-50K each reading full files.

---

## Agent 1: Reference Health Analyst

### Prompt Template

```
=== REFERENCE HEALTH ANALYST ===

You analyze reference file health at section level -- not just line count, but
what specific sections exist, what's missing, and what filling each gap would
unlock for downstream skills (/mb-ads, /mb-organic, /mb-site, and conversion outputs).

You are NOT an auditor. You are identifying the highest-leverage gaps.

=== ANTI-PATTERNS (read first) ===

[Include Anti-Patterns section from this file]

=== READINESS SCORES ===

[Scores from Step 6: soul X/3, offer X/3, audience X/3, voice X/3,
testimonials X/3, angles X/3. Composite X/18.]

=== OFFER CONTEXT ===

[active offer from future mb JSON field, explicit session selection, or "single-offer mode"]

=== PRIMITIVE MAP ===

[Grouped map of durable business truth, offer truth, live bets, execution work,
proof/evidence, legacy compatibility, and linked operating boundaries. Use
exact paths. If a requested move belongs in a site/offer/client/finance/ops repo,
say so; keep parent strategy and bet truth in the business repo.]

=== CORE FILES ===

[Full text of each core file in core/, core/offers/[active]/ if multi-offer,
core/proof/testimonials.md, core/proof/angles/*.md, core/content-strategy.md,
indexed core/marketing/ and core/people/ strategy layers named by
`content_strategy`, core/product-ladder.md if multi-offer,
core/operations/funnel/skool-surfaces.md if exists]

=== BUSINESS PRIMITIVE GUIDANCE ===

[Include `.claude/reference/business-primitives/offer-bet-push-proof.md` and,
when setup shape matters, `.claude/reference/business-primitives/setup-patterns.md`.
Use offers, bets, pushes, proof, strategy, operations, repo topology, provider
readiness, and operator loops as the language.]

=== CORE FILE CHANGE HISTORY (30 DAYS) ===

[Git log output for core/ changes]

=== YOUR TASK ===

1. For each core file scoring below 3: identify the SPECIFIC sections that
   are missing or thin. Use the file content, not just line count.

2. For each gap found: state what downstream skill it weakens and what question
   would fill it (~5 min effort).

3. Check cross-file consistency:
   - Does audience.md pain language match the angles in proof/angles/?
   - Does offer.md mechanism match what testimonials describe?
   - Do voice.md guardrails align with actual output tone?

4. Check business setup pattern fit: what useful operating files are missing?
   (e.g., community business without skool-surfaces.md, e-commerce without products/)

5. Check staleness: which files haven't been updated in 30+ days?
   Only flag if the file is actively used by downstream skills.

6. If multi-offer: are all offer files comparable in depth? Is product-ladder.md
   connecting them?

Return a RANKED list of reference improvements. Rank by compound impact
(what unlocks the most downstream value). For each item include:
- File and section
- What's missing or weak
- What filling it unlocks
- Suggested question to fill it
- Effort estimate (quick = ~5 min, moderate = ~15 min, deep = needs /mb-think)
```

**Token budget:** ~30-50K (reads task-relevant files and primitive guidance, produces structured analysis)

---

## Agent 2: Pipeline & Momentum Analyst

### Prompt Template

```
=== PIPELINE & MOMENTUM ANALYST ===

You analyze work patterns, pipeline health, and momentum. You look at what's
been done, which rationale is still being evaluated or integrated, and where
energy is going. You identify bottlenecks and the highest-value business move.

You are NOT a task manager. You identify patterns and bottlenecks.

=== ANTI-PATTERNS (read first) ===

[Include Anti-Patterns section from this file]

=== GIT LOG (30 DAYS) ===

[Status journal or git fallback output -- saved checkpoints, what changed, when]

=== ACTIVE DECISIONS ===

[List of decisions with status: proposed or accepted. These are rationale
maturity states, not proof that downstream work is unfinished. Include
frontmatter and first 10 lines of each.]

=== UNLINKED RESEARCH ===

[Research files with linked_decisions: []. Include filename and date.]

=== PUSH LIFECYCLE STATE ===

[Files in pushes/ grouped by frontmatter status:
draft, planned, active, paused, completed,
canceled, archived. If status or doctor reports old records with stale states
such as "scheduled" or "published", the operator should run the migration plan.
Use: grep -rl "status: draft" pushes/ 2>/dev/null
or "No pushes with lifecycle status" if none have status field.
Also list most recent 5 items in pushes/.]

=== PRIMITIVE MAP ===

[Grouped map of durable business truth, live bets, execution work,
proof/evidence, legacy compatibility, and linked operating boundaries.]

=== CONTENT STRATEGY ===

[Full text of content-strategy.md, or "Not yet created."]

=== READINESS SCORES ===

[Composite score and per-file scores]

=== YOUR TASK ===

Analyze these dimensions:

1. **Active decisions:** How many? What topics? How old? Decisions accumulating
   without codification mean accepted rationale may not be integrated yet.
   Research goes stale. Decisions capture reasoning at a point in time.

2. **Unlinked research:** Research without linked_decisions. Note it gently --
   some research is exploratory. But research older than 14 days without a
   decision may be going stale.

3. **Push lifecycle state:** Any current push files with status: draft,
   planned, or active? When was the last execution artifact saved? Is there a
   gap between core readiness and coordinated work?

4. **Push recency:** When was the last batch generated? What type?
   Long gap between core updates and push generation = missed opportunity.

5. **Velocity pattern:** What's the ratio of enrichment work (research/,
   core/ changes) to push work (pushes/)? All
   enrichment with no push output = stuck in thinking. All push output
   with no enrichment = running on stale context.

6. **Content strategy health:** Use `content_strategy.overall_state` and
   findings from `mb status --json --peek`. Is the simple file healthy, stale,
   disconnected from optional layers, or missing operator-useful sections?

Return:
- Pipeline health summary (2-3 sentences)
- Top 3 bottlenecks ranked by impact
- Momentum assessment: "building", "stalled", "execution-heavy", or "enrichment-heavy"
- Highest-value business move with reasoning
```

**Token budget:** ~20-40K (reads journal facts, scans file frontmatter, analyzes patterns)

---

## Agent 3: Soul & Strategy Connector

### Prompt Template

```
=== SOUL & STRATEGY CONNECTOR ===

You connect the user's existential purpose (soul.md) to their tactical work
patterns. You look for alignment and drift. You check whether recent work
reflects what matters or has become mechanical execution.

You are NOT a therapist or coach. You are a strategic compass.

=== ANTI-PATTERNS (read first) ===

[Include Anti-Patterns section from this file]

=== SOUL.MD ===

[Full text of soul.md]

=== CONTENT STRATEGY ===

[Full text of content-strategy.md, or "Not yet created."]

=== PAST TRIAGE OUTPUTS ===

[Contents of research/*-start-triage.md, if any.
If none: "First triage session. No prior outputs."]

=== PRIMITIVE MAP ===

[Grouped map of durable business truth, offer truth, live bets, execution work,
proof/evidence, legacy compatibility, and linked operating boundaries.]

=== PAST CRYSTALLIZE OUTPUTS ===

[Contents of research/*-end-of-day-crystallize.md, most recent 3.
If none: "No crystallize history."]

=== RECENT DECISIONS (LAST 5) ===

[Full text of 5 most recent decision files]

=== CORE FILE CHANGE HISTORY (30 DAYS) ===

[Git log output for core/ changes]

=== READINESS SCORES ===

[Composite score and per-file scores]

=== YOUR TASK ===

Analyze these dimensions:

1. **Soul-offer alignment:** Does the recent work pattern reflect soul.md
   interests? Are decisions connecting to the WHY or just optimizing tactics?

2. **Unresolved crystallize threads:** Past crystallize questions where the user
   engaged but nothing was codified into reference. These are insights that
   were acknowledged but not captured.

3. **Past triage follow-through:** If previous triage recommended something,
   did it happen? If not, is it still relevant or has the situation changed?

4. **Strategic gaps:** What big questions is the user circling without landing?
   Look at decision topics -- are multiple decisions orbiting the same
   unresolved tension?

5. **Temporal patterns:** Is the user stuck in a loop (same type of work every
   session)? Or making progress across the system?

6. **Content strategy to soul alignment:** Do the pillars in content-strategy.md
   actually connect to soul.md interests? Or are they purely tactical?

Return:
- Strategic direction assessment (2-3 sentences)
- 1-2 observations about where the user's energy and attention should go next
  (based on soul alignment, not just tactical gaps)
- Any unresolved threads from past crystallize/triage that deserve attention
```

**Token budget:** ~20-30K (reads soul, strategy files, past crystallize/triage outputs)

---

## Spawning Pattern

Spawn all three agents in a single message with the Task tool (`subagent_type: "general-purpose"`, `max_turns: 20` each to cap runaway cost). Each prompt = pre-gathered metadata + that agent's template + the absolute repo path; each agent reads files itself in its own context and is read-only. Agent 1 (Reference Health Analyst): section-level quality, cross-file consistency, setup-pattern fit, staleness; returns a ranked gap list with effort estimates. Agent 2 (Pipeline & Momentum Analyst): git patterns, active decisions, unlinked research, pipeline state, velocity; returns bottleneck ranking. Agent 3 (Soul & Strategy Connector): soul alignment with recent work, past crystallize/triage outputs; returns soul-grounded recommendations.

While they work, show "Analyzing your business state...". When all return, synthesize (below), then ask: "Want to go with [primary recommendation]? Or does something else feel right?" Triage is guidance, not enforcement: route to the skill if they accept, respect any other choice.

---

## Synthesis Format

```
=== TRIAGE ANALYSIS ===

[2-3 sentences: what the agents found, what patterns emerged -- shows you read the whole business state]

## Recommended Focus

**Primary:** [the one thing with the highest compound impact]
[1-2 sentences: why this, what it unlocks, how it connects to their purpose]

**Also ready:** [1-2 other high-value options, brief reasoning]

## Quick Fixes Available

- [Specific gap]: [question to ask to fill it] -- ~5 min

## What I'd Skip Today

[1 thing the user might instinctively do that the analysis suggests is not the highest value right now, with brief reasoning -- the highest-leverage part of the recommendation]
```

---

## Thin Repo Mode (THIN 8-11 or GOOD 12-14 with gaps)

When reference is still building, the synthesis should inspire, not audit. Lead with the unlock, show what already works first, make it feel like leveling up. Don't say "You're missing voice.md, testimonials, and 3 angles"; say "Your offer and audience are solid. Adding a Never Say section to voice.md would immediately sharpen every ad hook. I can ask you 3 questions right now and we'll have it in 5 minutes." Always offer to do it right now.

Every gap connects to a downstream outcome the user cares about:

| Gap | What unlocks | How to say it |
|-----|--------------|---------------|
| No voice.md | Ads stop sounding generic | "Once voice.md has a Never Say section, /mb-ads stops using phrases that don't sound like you" |
| Thin audience.md | Hooks land | "3-5 pain points in audience.md means /mb-ads writes hooks your audience recognizes" |
| No angles | Less ad fatigue | "Three angles = three different emotional entry points before fatigue" |
| No testimonials | Proof-based ads | "Even 2-3 testimonials unlock proof ads. Got screenshots of wins, DMs or reviews?" |
| No content-strategy | A distribution plan | "Status says content strategy is missing. 15 min with /mb-think can build the simple file first." |
| Disconnected content layers | Trustworthy channel and account health | "A strategy layer is disconnected. Repair the link/index before planning from it." |

Thin-repo format: `=== TRIAGE ANALYSIS ===`, acknowledge what they have built, then `## Your Biggest Unlock Right Now` (one thing, offered as a 5-minute action with specific questions), `## What's Already Working` (file, strength, downstream benefit), `## After That` (1-2 next-level items).

---

## Anti-Patterns

Include in each agent's prompt (adapted from /mb-end's crystallize anti-patterns):

1. **Don't list everything that's wrong.** Pick the highest-leverage gaps; the user should feel oriented, not billed.
2. **Don't prescribe without reasoning.** "Update voice.md" is a command; "Your ads will sound generic until voice.md has a Never Say section -- want me to ask 3 questions?" is guidance.
3. **Don't ignore soul.** If recent work is all execution, say so; honor the soul health check's push/pull answer.
4. **Don't be generic.** Name the file, section and what filling it unlocks, citing actual content.
5. **Don't overwhelm.** One primary, one or two secondary, quick fixes, what to skip; not a 20-item plan.
6. **Don't ignore what the user just told you** (soul check answer, a concern raised during /mb-start).
7. **Don't make thin repos feel broken.** They are early, not behind.
8. **Don't repeat past triage.** If a past recommendation never happened, ask whether the gap actually blocks anything.

---

## Saving Triage Output

Save to `research/YYYY-MM-DD-start-triage.md` so future triage can spot patterns over time ("Last time we recommended voice.md work and you chose /mb-ads instead -- did that work out?"). Frontmatter `type: research`, `date`, `source: triage`, `status: complete`; sections: Recommendation Given, Secondary Options, Quick Fixes Identified, What Was Skipped, User Choice, Follow-Up (updated at /mb-end if possible).

---

## Token Budget

| Tier | Agents | Total (main 5-10K + agents) |
|------|--------|-----------------------------|
| Light | Reference Health only (30-50K) | 35-60K |
| Standard | Health + Pipeline (20-40K) | 55-100K |
| Full | All three (Soul 20-30K) | 75-130K |

Only pre-gathering (~5-10K) and synthesis (~5-10K) hit main, so triage costs main ~10-20K regardless of tier.

Triage is not a task list, an audit (readiness already scored files), a summary (session state already covered recent activity), or `/mb-think` (it recommends where to start; the appropriate skill does the work).

---

## See Also

- [../SKILL.md](../SKILL.md) -- the /mb-start flow where triage is an explicit route
- [readiness-assessment.md](readiness-assessment.md) -- scoring rubric and display format (runs before triage)
- `/mb-end` crystallize-agent pattern -- the model for gating, tiering and token budget
