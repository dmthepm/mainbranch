# Readiness Assessment Reference

Complete fallback reference for readiness assessment when `/mb-start` needs
detail that `mb status --json --peek` does not expose. Use status `readiness`,
`drift.items`, `onboarding`, `since_last_check`, `content_strategy`,
`money_path`, and
`ranked_actions` first. Only use the checks below for section-level detail or
when status reports that a section is unavailable/degraded.

Do not mix this fallback 0-3 file score with MoneyPath's 0-5 path scale.
MoneyPath reports whether customer progress, offer, proof, CTA, channel, push,
playbook, page readiness, and outcome feedback are legible, supported,
connected, and instrumented. For proof, prefer
`money_path.objects.proof.quality` facts over the fallback testimonial count:
generic testimonials, specific outcomes, permissioned public signals, offer
linkage, typicality context, and outcome feedback are factual signals, not
proof scores.
Use `quality.public_marketing` for public ads/pages readiness. Specific
testimonials with no permissioned public signal are internal strategy proof,
not public marketing proof; route to permission collection before public claims.

---

## 1. Reference File Scoring

Score each file by reading it directly (fast -- no subagent needed). Use line count as primary signal, section markers as quality signal.

### Scoring Rubric

| File | 0 (Missing) | 1 (Skeleton) | 2 (Developing) | 3 (Strong) |
|------|-------------|---------------|-----------------|-------------|
| `soul.md` | File missing or empty | <30 lines | 30-80 lines | 80+ lines OR has "Beliefs" section |
| `offer.md` | File missing or empty | <20 lines | 20-80 lines | 80+ lines OR has "Price" section |
| `audience.md` | File missing or empty | <30 lines | 30-60 lines | 60+ lines OR has "Pains" section |
| `voice.md` | File missing or empty | <20 lines | 20-50 lines | 50+ lines OR has "Never Say" section |
| `testimonials.md` | File missing or empty | <5 testimonials | 5-10 testimonials | 10+ testimonials |
| `angles/` | 0 files (or missing dir) | 1 file | 2-3 files | 4+ files |

### Key Section Markers by File

When checking section markers, search for these headings (case-insensitive). These are the quality signals that distinguish skeleton files from intentional work:

| File | Key Sections to Detect |
|------|----------------------|
| `soul.md` | "Beliefs", "Anti-patterns", "Evolution Markers", "The Test", "The Parts" |
| `offer.md` | "Price" / "Pricing", "Mechanism", "Guarantee", "Value Stack", "Objections", "Deliverables" |
| `audience.md` | "Pains", "Desires", "Psychographics", "Language", "Objections", "Segments" |
| `voice.md` | "Never Say", "Vocabulary", "Rhythm", "Examples", "Tone", "Phrases" |
| `testimonials.md` | Count `###` or `**"` patterns (each indicates one testimonial) |

**How to use:** When a file scores 1 or 2 by line count, check for these markers to identify WHICH sections are missing. This drives the specific gap language in Section 7 and prevents hand-wavy gap messages like "voice.md is thin" when the real issue is "voice.md has no Never Say section."

### How to Score

**CRITICAL: Use absolute paths for ALL file reads and searches.** The repo path from Step 2 is an absolute path (e.g., `/absolute/path/to/my-business`). Always use it — never use `~` or relative paths. The Glob and Read tools do not expand `~`, so `~/Documents/GitHub/repo/core/proof` will silently return 0 results even when files exist.

1. **Read each file** with the Read tool using the absolute repo path (e.g., `[repo-path]/core/soul.md`). If the read fails or returns empty, score 0.
2. **Count lines** for the primary threshold check.
3. **Check for section markers** (case-insensitive grep for key headings from the table above) as a quality override -- a 25-line soul.md with a "Beliefs" section shows intentional work and scores 2, not 1. Use specific markers to identify exactly what's missing.
4. **For testimonials:** Read `[repo-path]/core/proof/testimonials.md`. Count occurrences of `###` or `**"` patterns (each indicates one testimonial).
5. **For angles:** Glob `[repo-path]/core/proof/angles/*.md` to count files, excluding `README.md`.

### Multi-Offer Scoring

When a future `mb` JSON active-offer field or the operator's current session
selects an offer:

1. Score `core/soul.md` and `core/voice.md` from core (these are always brand-level).
2. For offer and audience, resolve using the current path algorithm:
   - Check `core/offers/[offer]/offer.md` first. If it exists, score it.
   - If it does not exist, score `core/offer.md`.
   - Same for `audience.md`.
3. Testimonials and angles: check both `core/proof/` (brand-level) and
   `core/offers/[offer]/proof/` if offer-specific proof exists.

Use `.claude/reference/business-primitives/offer-bet-push-proof.md` for the
shared active-offer contract. If CLI/status facts do not resolve the offer, ask
which offer the current work is about or score brand-level context for routing
only. Do not silently route from `.vip/local.yaml`; treat it as audit input.

If the repo has no `core/`, do not score old paths as current truth. Run
`mb doctor repair --plan`; use `reference/*` only as legacy migration input.

### Composite Score

Sum all six scores. Maximum = 18.

```
composite = soul + offer + audience + voice + testimonials + angles
```

---

## 2. Session State Check

Surface what happened recently so the user sees continuity, not a blank slate.

### Recent Activity

Prefer `since_last_check.journal` and top-level `journal` from
`mb status --json --peek`. Summarize the newest grouped event in one line:
"Last session: [journal summary]".

Only run `git log --since="7 days ago" --oneline --no-merges` as a fallback
when status says the journal section is unavailable or degraded.

If status reports no journal events in 7+ days, note the gap -- this feeds into
the soul health check (Section 3).

### Active Decisions

```bash
# Decisions with frontmatter status: proposed or accepted (anchored parse)
for f in [repo-path]/decisions/*.md; do
  [ -f "$f" ] || continue
  status=$(awk 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{exit} fm&&/^status:[[:space:]]*/{val=$0; sub(/^status:[[:space:]]*/, "", val); gsub(/[[:space:]]+$/, "", val); print val; exit}' "$f")
  case "$status" in
    proposed|accepted) echo "$f" ;;
  esac
done 2>/dev/null
```

For each found, read the frontmatter to extract the topic. Present as:

> "You have [N] decisions still being evaluated or integrated: [topic 1], [topic 2]."

**Why this matters:** Decisions capture reasoning at a point in time. Codifying
locks accepted rationale into durable truth before it decays. Treat this as a
continuity signal, not proof that downstream work is unfinished.

### Uncodified Research

```bash
# Research files without linked_decisions (simplified check)
for f in research/*.md; do
  if [ -f "$f" ]; then
    grep -q "linked_decisions: \[\]" "$f" && echo "$f"
  fi
done 2>/dev/null
```

If found, note it gently:

> "[N] research files haven't led to decisions yet. May be worth reviewing."

Do not nag. Some research is exploratory and never needs a decision. This is informational.

### Content Strategy Gap

Use `content_strategy.overall_state`, `simple_entry_point`, `layers`, and
`findings` from `mb status --json --peek`. Only read raw strategy files when the
operator asks for details or status reports that the section is unavailable.
For community, coaching, and content-driven businesses, route `missing`,
`needs_review`, `disconnected`, or `stale` states to `/mb-think` or validation
repair before content production.

---

## 3. Health Flags

Lightweight metadata checks that catch common decay without reading full file contents. Run AFTER structural scoring (Section 1) and session state (Section 2). Adds 4-5 tool calls.

**Principle:** If you can detect it from metadata, frontmatter, or file stats — it belongs here. If you need to read and compare file *contents* — it belongs in triage.

### Check A: Frontmatter Status Scan (1 call)

```bash
grep -l "status: draft" [repo-path]/core/*.md 2>/dev/null
```

Flag any file that scored 3/3 structurally but has `status: draft` in frontmatter. Highest-signal check — the user explicitly declared this file unfinished.

**Flag:** `! status: draft` (inline next to file)

### Check B: Staleness Detection (1 call)

Use `journal.events[].files` from status first. Fall back to:
`git log --format="%ai" -1 -- [repo-path]/core/soul.md [repo-path]/core/offer.md [repo-path]/core/audience.md [repo-path]/core/voice.md`

Flag any core file not modified in 30+ days. Not a score penalty -- an observation.

**Flag:** `! stale (Xd)` (inline next to file)

### Check C: Angle Count Mismatch (1 call)

```bash
ls [repo-path]/core/proof/angles/*.md 2>/dev/null
```

Compare actual .md file count (excluding README.md) against angles README if it exists. Flag if counts differ.

**Flag:** `! 3 files vs 5 in README` (inline next to angles row)

### Check D: Decision Lifecycle Audit (shared script)

```bash
# Resolve engine script path (settings.local.json first, then ~/.config/vip/local.yaml)
AUDIT_SCRIPT=$(python3 -c "
import json, os
path = '.claude/settings.local.json'
target = ''
try:
    with open(path) as f:
        dirs = json.load(f).get('permissions', {}).get('additionalDirectories', [])
    for d in dirs:
        candidate = os.path.join(d, '.claude/scripts/decision_lifecycle_audit.sh')
        if os.path.isfile(candidate):
            target = candidate
            break
except Exception:
    pass
print(target)
" 2>/dev/null)

if [ -z "$AUDIT_SCRIPT" ] && [ -f "$HOME/.config/vip/local.yaml" ]; then
  vip_path=$(awk -F': *' '/^vip_path:/ {print $2; exit}' "$HOME/.config/vip/local.yaml" | tr -d '"')
  [ -n "$vip_path" ] && AUDIT_SCRIPT="$vip_path/.claude/scripts/decision_lifecycle_audit.sh"
fi

if [ -n "$AUDIT_SCRIPT" ] && [ -f "$AUDIT_SCRIPT" ] && bash "$AUDIT_SCRIPT" --repo "[repo-path]" --format text; then
  : # Shared script output includes machine-friendly summary + human bucket lines
else
  echo "Decision lifecycle audit unavailable; falling back to strict frontmatter counts."
  codified=0
  accepted=0
  invalid_or_missing=0

  for f in [repo-path]/decisions/*.md; do
    [ -f "$f" ] || continue
    status=$(awk 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{exit} fm&&/^status:[[:space:]]*/{val=$0; sub(/^status:[[:space:]]*/, "", val); gsub(/[[:space:]]+$/, "", val); print val; exit}' "$f")
    case "$status" in
      codified) codified=$((codified + 1)) ;;
      accepted) accepted=$((accepted + 1)) ;;
      proposed) ;;
      *) invalid_or_missing=$((invalid_or_missing + 1)) ;;
    esac
  done

  printf "Decisions: %s codified, %s accepted\n" "$codified" "$accepted"
  [ "$invalid_or_missing" -gt 0 ] && printf "Decisions with invalid/missing status: %s\n" "$invalid_or_missing"
fi
```

Use `.claude/scripts/decision_lifecycle_audit.sh` as the single source of truth for lifecycle classification in both `/mb-start` and `/mb-end`.
The script parses frontmatter only (between `---` delimiters), ignores body `status:` text, classifies accepted decisions into `needs_review|action_needed|stale_orphaned`, and reports invalid/missing status explicitly.
Never auto-flip statuses from evidence alone. Status changes remain manual-confirmed.

**Flag:** `Decisions: X codified, Y accepted` (below file scores)
**Flag:** `Needs review: N` (accepted with implementation evidence)
**Flag:** `Action needed: A` (accepted with no evidence and not stale)
**Flag:** `Stale/orphaned: S` (accepted, stale threshold crossed, weak/no evidence)
**Flag:** `Decisions with invalid/missing status: I` (only when `I > 0`)

### Check E: Naming Convention Spot-Check (1 call)

```bash
ls [repo-path]/research/ [repo-path]/decisions/ 2>/dev/null
```

Pattern-match filenames against `YYYY-MM-DD-slug.md`. Only flag if >20% violations.

**Flag:** `Naming: X% violations in research/` (below file scores)

### Display Rules

- Maximum 5 flags total
- File-level flags (A, B, C) appear inline next to the relevant file score
- Pipeline flags (D, E) appear as a separate line below file scores
- No "WARNING" or "ISSUE" language — factual observations only
- If any flags exist, append: "Pick the triage route for deeper analysis"
- Flags inform; they do NOT gate routing or change the structural score

---

## 4. Soul Health Check

Modeled on /mb-end's crystallize pattern. For returning users, reconnection at session open is as important as reflection at session close.

### When to Trigger

**Trigger conditions (ALL must be true):**
1. `core/soul.md` exists and has substance (score 2+)
2. Last status journal event or saved checkpoint was >3 days ago (returning after absence)
3. This is not the user's first session ever (config exists with `user.name`)

**Skip conditions (ANY skips this check):**
- First-time user (no repo history)
- Active user (saved or updated work within last 3 days)
- User explicitly stated intent already (e.g., `/mb-start ads` -- they know what they want)
- Context window is already heavy (>70%)

### How to Check

Use the newest status journal event date. If journal facts are unavailable,
fall back to `git log -1 --format="%ar"`.

### The Ask

Read `core/soul.md` (first 50 lines is enough to get the WHY). Then ask:

> "Welcome back. Your last session was [N] days ago.
>
> Quick check-in: Is your current work still feeling like pull or push? If things have shifted, we can revisit soul.md."

**Why this language:** "Pull or push" comes directly from soul.md's offer-fit test. Users who have written their soul.md will recognize this language. It is not generic coaching -- it references their own framework.

### If They Say Push/Obligation

This is valuable information. Do not dismiss it.

> "That's worth paying attention to. Some options:
>
> 1. Explore what shifted through /mb-think
> 2. Review soul.md together and see if the offer still fits
> 3. Proceed anyway and revisit later
>
> (hit a number)"

If they choose 1 or 2, route to `/mb-think` with the soul exploration context. If they choose 3, proceed normally but make a mental note -- the crystallize agent at `/mb-end` should revisit this.

### If They Say Pull/Discovery

Brief acknowledgment, then move on:

> "Good. Let's keep building."

No ceremony. Get out of the way.

---

## 5. Smart Routing Gates

The readiness score determines which skills are available. This prevents users from jumping into output skills with thin reference -- the #1 source of bad outputs.

### Score Interpretation

| Composite | Status | Routing Behavior |
|-----------|--------|------------------|
| **0-3** | EMPTY | Route to `/mb-setup`. "No reference files found. Let's set up your business repo." |
| **4-7** | MINIMAL | Block output skills. Route to `/mb-think`. "Reference isn't ready for generating yet. Let's build the core first." |
| **8-11** | THIN | Warn before output skills. "Reference is thin. /mb-ads and /mb-organic work best with richer context. Want to enrich first with /mb-think?" Allow override if user insists. |
| **12-14** | GOOD | All skills available. Note gaps: "Angles could use expansion" or "No content strategy yet." |
| **15-18** | FULL | All skills available. Present full options. |

### What "Block" Means

MINIMAL (4-7) does NOT show output skills in the numbered options list. If the user explicitly asks for /mb-ads, explain why reference needs work first and offer to route to /mb-think instead. They can override -- this is guidance, not enforcement.

### What "Warn" Means

THIN (8-11) shows output skills in the list but adds a note:

> "3. Create ads  /mb-ads (reference is thin -- results will improve with richer context)"

### Active Decisions Override

If active decisions exist (status: proposed or accepted, not codified), surface
them regardless of score. These statuses describe rationale maturity, not a
general work list:

> "You have [N] decisions still being evaluated or integrated. Want to review whether any should be accepted, codified, or left as-is before we choose today's move?"

This is a suggestion, not a gate. User can proceed to any available skill.

### Content Strategy Nudge

If score is GOOD or FULL but `content-strategy.md` is missing or thin:

> "You have strong reference but no content strategy. When you're ready, /mb-think can help build `core/content-strategy.md` -- known-for target, audience, pillars, asset jobs, and distribution links."

One-time mention per session. Do not repeat.

---

## 6. Skill-Specific Readiness

Beyond the composite score, some skills have specific requirements. Check these when routing to a specific skill.

### /mb-ads

| Requirement | Minimum | Why |
|-------------|---------|-----|
| offer.md | Score 2+ | Needs pricing, mechanism, or clear value prop |
| audience.md | Score 2+ | Needs pain points to write hooks |
| voice.md | Score 1+ | Needs at least basic tone direction |
| 1+ angle file | Required | Angles frame the ad creative |

**If missing:** "To generate quality ads, I need [what's missing]. Want to build that through /mb-think first?"

### /mb-organic

| Requirement | Minimum | Why |
|-------------|---------|-----|
| offer.md | Score 2+ | Needs clear positioning |
| audience.md | Score 2+ | Needs to know who content is for |
| voice.md | Score 1+ | Organic content must sound authentic |
| content-strategy.md | Exists | Needs recognition target, pillars, asset jobs, and platform/account direction |

**If content-strategy.md missing:** "Organic content works best with a content strategy. Want to build one through /mb-think? It defines what you want to be known for, your pillars, asset jobs, platform/account direction, and cadence."

### Conversion script outputs

| Requirement | Minimum | Why |
|-------------|---------|-----|
| offer.md | Score 3 | Conversion scripts need pricing, mechanism, guarantee, full offer stack |
| audience.md | Score 2+ | Needs psychographics for pain/desire framing |

Route by surface after the readiness check:

- Page, about-page, lander, or embedded conversion script: `/mb-site`
- Paid long-form video ad or hook variants: `/mb-ads`
- Teardown, pitch extraction, objection mining, or codification: `/mb-think`
- Clips, excerpts, or short-form repurposing: `/mb-organic`

**If offer thin:** "Conversion scripts need a complete offer -- pricing, mechanism, guarantee. Your offer.md needs more depth. Route to /mb-think to flesh it out?"

### /mb-site

| Requirement | Minimum | Why |
|-------------|---------|-----|
| offer.md | Score 2+ | Landing pages need clear value prop |
| voice.md | Score 2+ | Site copy must sound right |

**If voice thin:** "Landing page copy needs strong voice direction. `/mb-site` walks brief→site as one flow and will pull from your `voice.md` — but if it's thin, the output will be too. You can keep going (`/mb-site` has its own brief phase) or strengthen voice first via `/mb-think`."

### Newsletter planning

| Requirement | Minimum | Why |
|-------------|---------|-----|
| content-strategy.md | Exists | Newsletter needs pillar and distribution framework |
| voice.md | Score 2+ | Long-form writing needs strong voice |

No bundled newsletter skill ships today. Route newsletter strategy or email
planning to `/mb-think`; route derivative social output to `/mb-organic`.

---

## 7. Display Format

Adapt by experience level. **Every gap is actionable:** `[specific missing section/file] + [what it unlocks downstream] + [concrete offer to fix it now]`, using the per-file tables in Section 8. For any score below 18, name exactly which files scored below 3 under a "Gaps:" heading after the score line. This applies at GOOD (12-14) and FULL (15-17) too; users at 13/18 need to know what the missing 5 points are.

- **Beginner:** score and tier, one sentence on why richer files help (output skills work best at 12+), then each gap in full:
  > "**Repo Health: THIN** (score: 9/18) ... **Gaps:** - **voice.md** (1/3): Missing "Never Say" section -- the #1 guard rail for authentic output. Want me to ask you 3 questions to build it? (~5 min) - **angles/** (1/3): 1 angle file. 3+ gives /mb-ads real variety. Want to explore a new angle through /mb-think?"
- **Intermediate:** score and gaps with brief detail: "**voice.md** (1/3): No "Never Say" section. 3 questions to build it? (~5 min)"
- **Advanced:** one line, always, even at GOOD/FULL, no explanation: "**9/18** -- voice (1, no Never Say), testimonials (1, only 2), angles (1, single angle)."
- **18/18:** no structural gaps, but don't claim perfection ("locked", "mature", "production-ready", "all set" are out): "**Repo Health: FULL** (18/18). All reference files present and substantive. For deeper analysis (staleness, cross-file consistency, pipeline health), pick the triage route."

**Flags** (Section 3) appear alongside scores: file-level flags (status, staleness, count mismatch) inline, pipeline flags (codification rate, naming) below, after gaps. Beginner/intermediate list them under "Flags:" (for example `soul.md -- status: draft`, `audience.md -- stale (41d since last update)`, `Decisions: 8 codified, 55 accepted`, `Needs review: 4`) and end with "Pick the triage route for deeper analysis." Advanced puts them on the score line ("**18/18** -- flags: soul.md draft, audience.md stale (41d), 4 need review. Triage route for details."). When no flags fire, omit the section entirely (no "Flags: none").

**Session state:** if items exist, append "**Since last session:** last work: [topic from recent checkpoint or journal event]; [N] decisions still being evaluated or integrated; [N] research files without decisions". Show only items that exist.

---

## 8. Per-File Gap Tables

Use these tables to determine the specific gap language for each file at each score level. The formula is always: **[Specific missing section/file] + [What it unlocks downstream] + [Concrete question or offer to fix it now]**.

### soul.md

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | File doesn't exist | "No soul.md yet. This is the foundation -- your WHY. Let me ask you 3 questions to draft it." | "What do you research when no one's watching? What intersections excite you? What work feels like discovery vs obligation?" |
| 1 | <30 lines, skeleton | "soul.md exists but is thin. Missing: Beliefs section, Anti-patterns, Evolution Markers." | "What do you believe about [domain] that most people get wrong? What patterns make you lose energy?" |
| 2 | 30-80 lines, developing | "soul.md has substance but is missing [specific section: Evolution Markers or Anti-patterns or The Parts]." | Depends on missing section: "When did your thinking about this shift? What was the before/after?" (Evolution Markers) |
| 3 | Strong | At 3, only surface if qualitative issues exist: "soul.md is strong. Last updated [date] -- still resonates?" | No question unless returning after long absence (soul health check handles this) |

### offer.md

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | File doesn't exist | "No offer.md. /mb-ads, /mb-site, and conversion outputs can't generate without knowing what you sell." | "What do you sell? What transformation does the buyer get? What does it cost?" |
| 1 | <20 lines | "offer.md exists but is missing: [check for Pricing, Mechanism, Guarantee, Value Stack sections]." | "Your offer mentions [what exists] but I don't see [missing section]. What's your guarantee? What makes your mechanism unique?" |
| 2 | 20-80 lines, developing | "offer.md is developing. [Specific weak area: e.g., 'Mechanism section is one sentence -- this is what makes conversion scripts compelling.']" | "Walk me through HOW your product/service actually works. What's the step-by-step transformation?" |
| 3 | Strong | "offer.md has enough structure for `/mb-ads`, `/mb-site`, and conversion workflows to use as source context." | No question. Note if Price section hasn't been updated in 60+ days. |

### audience.md

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | File doesn't exist | "No audience.md. Hooks and ad copy will be generic without knowing who you're talking to." | "Who are the 2-3 people you've helped most? What was their life like before?" |
| 1 | <30 lines | "audience.md is a skeleton. Missing: [Pains section, Desires section, Psychographics]." | "What keeps your audience up at 2am? Not their stated problem -- their actual fear." |
| 2 | 30-60 lines, developing | "audience.md has [what exists] but is missing [specific section: e.g., 'No Objections section -- /mb-ads hooks work best when they preempt resistance.']" | "What do people say right before they decide NOT to buy? What's their go-to excuse?" |
| 3 | Strong | "audience.md is strong." | No question. Note if segments could be refined for multi-offer routing. |

### voice.md

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | File doesn't exist | "No voice.md. Generated content will sound like generic AI until voice is defined." | "Send me 3 pieces of content you've written that sound most like you. I'll extract the patterns." |
| 1 | <20 lines | "voice.md exists but is missing: [check for Never Say, Vocabulary, Rhythm sections]." | "What phrases do you NEVER want to see in your content? What words feel wrong for your brand?" |
| 2 | 20-50 lines, developing | "voice.md has tone direction but is missing [specific: e.g., 'No Never Say section -- this is the most important guard rail for authentic-sounding output.']" | "Read this draft [show example output] -- what sounds wrong? What would you change?" |
| 3 | Strong | "voice.md is strong." | No question. Could note: "Last voice calibration was [date]. Want to run a quick test with a sample output?" |

### testimonials.md

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | File doesn't exist | "No reusable testimonials found." | "Do you have any permissioned testimonials, screenshots, DMs, or reviews we can save as proof material?" |
| 1 | <5 testimonials | "[N] testimonials found. Check MoneyPath before using them for outcome claims." | "Do any testimonials mention a specific outcome, timeframe, metric, or offer?" |
| 2 | 5-10 testimonials | "[N] testimonials found. Check whether proof is permissioned, offer-linked, and supported by typicality context." | "Which testimonials are approved for public use, and which offer does each one support?" |
| 3 | 10+ testimonials | "10+ testimonials found. Use MoneyPath proof-quality facts before calling them specific, offer-linked, or outcome-backed." | If `typicality.md` is missing: "You have testimonials, but no average-case context. What typical outcome, caveat, common failure case, or time-to-outcome can we document?" |

### angles/ (proof/angles/)

| Score | What's Missing | Actionable Gap | Question to Ask |
|-------|---------------|----------------|-----------------|
| 0 | No angle files | "No angles defined. Angles are messaging entry points -- each one frames your offer differently for different motivations." | "Why do your best customers buy? Not the feature -- the emotional trigger. Is it fear? Status? Relief? Curiosity?" |
| 1 | 1 angle | "One angle defined ([name]). Ads and organic content need variety -- 3+ angles prevent fatigue." | "You have [existing angle]. What's the SECOND most common reason people buy? Different motivation = different angle." |
| 2 | 2-3 angles | "Decent angle variety. Review: do angles cover different emotional territories? (e.g., if all three are fear-based, missing opportunity-based.)" | "Look at your angles: [list names]. Are there buyer motivations not covered? What about [suggest missing emotional territory]?" |
| 3 | 4+ angles | "Strong angle library." | No question. Could note: "Which angles have been tested in ads? Performance data would inform prioritization." |

### content strategy (domain, not in composite but checked)

| State | Actionable Gap | Question to Ask |
|-------|----------------|-----------------|
| Missing | "No content strategy yet. Content generated by /mb-organic and /mb-ads works better with a known-for target, pillars, asset jobs, and channel/account direction." | "Want to build content-strategy.md through /mb-think? It starts from offer clarity, audience, proof, and what you want to be recommended for." |
| Needs review | "`content_strategy.findings` names the missing or thin section." | "Want to tighten the missing section through /mb-think before creating more content?" |
| Disconnected | "Layered content strategy files exist but are not indexed, or an account cannot resolve its channel/person reference." | "Want to repair the disconnected layer so status and future dashboard views can read it cleanly?" |
| Stale | "A channel or account strategy describes platform rules that need review." | "Want to review the stale channel/account notes before planning the next push?" |
| Healthy | "Content strategy health is clean in `mb status`." | No question unless the operator asks to work on content strategy. |

---

## Anti-Patterns

1. **Scoring as audit.** It is a routing tool: "here's what you can do," not "here's what's wrong."
2. **Blocking too aggressively.** MINIMAL hides output skills from the numbered list but does not stop a direct request: explain why reference matters, suggest /mb-think, and let them insist.
3. **Over-explaining to advanced users.** "9/18 -- voice thin" is enough.
4. **Skipping the check.** Even with clear intent (`/mb-start ads`), run the scoring silently; MINIMAL makes the gate matter, GOOD+ routes immediately.
5. **Nagging about research.** Frame "12 research files without decisions" as opportunity, not debt.
6. **Soul check as therapy.** "Pull or push?" is a quick calibration: ask, accept, move on.

---

## See Also

- [../SKILL.md](../SKILL.md) -- The /mb-start flow that invokes this assessment
- [config-system.md](config-system.md) -- Config reading for experience level and default repo
- [mcp-preflight.md](mcp-preflight.md) -- MCP check that runs before this assessment
- `/mb-end` crystallize-agent pattern -- The soul awareness pattern this assessment draws from
