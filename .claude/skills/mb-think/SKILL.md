---
name: mb-think
description: "Combined research, decision, and codification workflow. Use when: (1) Exploring a question before committing (2) Making a decision that needs documentation (3) User says research, decide, figure out, explore, codify, enrich, retire stale source, sharpen this offer, improve the offer, add context, keyword gate, analyze this VSL, extract the pitch, script teardown, objection mining, or sales video research (4) Updating reference files based on decisions (5) User wants to add testimonials, angles, proof, mechanisms, objections, guarantees, or pitch context. Supports modes: full flow, research-only, keyword-gate, decide-only, codify."
loops: [sense, decide, ship]
---

# Think

Research, decide, and codify knowledge into reference files.

## Don't Overthink Think

This skill is for: **"I don't know what happens next. I just need to start."**

Something came your way — a video, a voice memo, a vague feeling, a problem to solve. You don't need a plan. Just start. The skill finds the overlap between your interest and your offer.

**Re-invoke often.** Saying `/mb-think` again is normal. It reloads context. Do it after:
- Reading a large transcript (burns tokens)
- Compaction (context window reset)
- Switching focus
- Anytime you feel lost

**Save progress at natural boundaries.** After a research batch, accepted
decision, codify pass, or major reference-file update, ask whether to checkpoint.
Run `mb checkpoint --plan --json`, show the proposed message, validate with `mb checkpoint --validate "..." --json`, then save with `mb checkpoint --message "..." --yes` only after approval; no hidden checkpoints.

**Shared source:** The portable thinking workflow contract lives in
`workflows/mb-think/workflow.md`. This Claude skill is the Claude Code shell
over that source.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb checkpoint --plan --json`

Required fact paths:

- `money_path`
- `money_path.objects.offer`
- `money_path.objects.proof`
- `money_path.objects.proof.quality`
- `money_path.objects.product_ladder`
- `money_path.objects.cta_path`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `money_path.objects.outcome_feedback_loop`
- `money_path.ranked_actions`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `books`
- `runtime.codex_cli`
- `runtime.claude_code`

Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`,
`provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`,
`destructive_operations`, `structured_collection`, and `public_issue_or_proposal`.

Public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_private_dms_or_gated_communities`, and
`no_raw_finance_legal_records`.

Core route: research depth recommendation, parallel research files for
source-specific research files when multiple source types are needed, decision,
codify, stale source cleanup, public/private handling, checkpoint plan,
checkpoint approval, and explicit write approval.
Do not tell Codex users to run Claude Code entrypoints.

For observations, use research-only for a short, sourced readout; changed steering adds a decision in the same approved session.
Link `linked_research` and `linked_decisions` both ways, plus a known bet or push; update an existing trial bet through `/mb-bet` after approval.
Summarize numbers; exclude raw rows, account IDs, customer data, and tables. A status-only question creates neither research nor a decision.

When research identifies a reusable growth mechanic such as a comment-keyword,
DM-keyword, public reply/link, resource delivery, provider setup recipe, or
approval gate, route the durable plan into
`pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` with `type: playbook`.
Playbooks are plans, approval records, safe provider-state notes, validation
evidence, and outcome hooks. They are not provider execution.

When the operator asks for a researched brief, site brief, launch brief, or
research meant to feed `/mb-ads`, `/mb-site`, or push playbooks, support:

```text
/mb-think --brief-format=grok-8 <topic>
```

Load [references/grok-8-brief-format.md](references/grok-8-brief-format.md).
This mode structures findings across eight categories: business/offering, ICP,
journey, competitive landscape, brand story, technical requirements, content
assets, and metrics/constraints. Use it as an opt-in format, not the default
unless the operator chooses it.

---

`/mb-think` enriches the core (insights -> reference files). To create for the world (ads, scripts, courses, code, posts), use `/mb-ads`, `/mb-organic`, `/mb-site`, or just ask.

---

## Pull Latest Updates

See **[references/pull-engine-updates.md](references/pull-engine-updates.md)** for the standard Main Branch update check. Run it at the start of every /mb-think invocation.

---

## CLI Facts First

Provider readiness comes from `mb` first. Run or reuse:

```bash
mb status --json --peek
mb connect doctor --json
```

Use those facts for GitHub, Google/Workspace, Meta Ads, and other provider
repair language. Apify research remains MCP-first for now: treat it as an
agent-side research tool surface unless a later CLI contract exposes stable
provider-readiness facts. Runtime-local tool checks happen only after a
selected research path needs them and `mb` cannot inspect the tool directly.
Before any large Apify mining run, the owner sees an estimated cost and says OK first
([research-phase.md](references/research-phase.md)).

**Quick gist:** On first `/mb-think` invocation, read status/connect facts. When
the user's intent needs a runtime-local tool, check only that tool, cache
session knowledge, and offer the `mb connect` repair command or a fallback.
Surface a missing-tool option once per session per tool.

See **[references/tool-detection.md](references/tool-detection.md)** for the full status-value table, staleness rules, per-tool detection methods (Apify, Gemini, Grok, whisper, Nano Banana, Meta ad account context, document tools), required config-update format, and the intent-based tool surfacing matrix.

For self-healing semantics (stale false handling, status-change messaging, true-tool degradation), see [tool-status-self-healing.md](references/tool-status-self-healing.md).

---

## Offer Context Resolution

Before loading reference files, resolve the active offer and target file type
with `.claude/reference/business-primitives/offer-bet-push-proof.md`:

1. If a future `mb` JSON field exposes active offer state, use it.
2. Do not treat `.vip/local.yaml` as the source of truth for active-offer
   state. If legacy state exists, confirm the offer with the user instead of
   silently routing.
3. If an offer is selected and `core/offers/[offer]/offer.md` exists, load it as the active offer.
4. If no offer is selected AND `core/offers/` exists: ask which offer.
5. If no `core/offers/` folder: use `core/offer.md` (single-offer mode)
6. If the repo does not have `core/`, do not infer current offer context from
   old paths. Run `mb doctor repair --plan`; use `reference/*` only as legacy
   migration input.

**Always-core files:** `soul.md`, `voice.md`, `content-strategy.md`. See [codify-phase.md](references/codify-phase.md) for content strategy layers.
**Offer-aware files:** `offer.md`, `audience.md`
**Proof files:** company-wide proof uses `core/proof/testimonials.md`,
`core/proof/typicality.md`, and `core/proof/angles/`; offer-specific proof
uses matching files under `core/offers/<slug>/proof/`.
When codifying proof, make permission, offer-link, outcome, timeframe, metric, and typicality facts explicit so `money_path.objects.proof.quality` can see them; use `permissioned_public: false` for internal proof awaiting public permission.
If status reports `money_path.objects.proof.quality.public_marketing.status: blocked`, collect permission before ads, pages, or public claims use that proof.
When `validation.file_contracts` reports offer gaps, use the findings as the
intake checklist and fill missing audience, promise, mechanism, proof,
price/value, or next-step context only after operator approval.

For a live idea, ask whether it is something to keep selling or something to
test before deciding. Use `bets/` for the time-boxed wager, offer files for
durable sellable truth, `pushes/` for coordinated execution, and `decisions/`
for accepted rationale that changes durable truth.

---

## Where Files Go

All files save to YOUR business repo, not the Main Branch engine.

```
your-business-repo/          <- Files saved here
├── research/                 <- Research output
├── decisions/                <- Decision output
├── core/                     <- Brand-level codify updates
│   ├── offers/               <- Per-offer codify updates
│   ├── proof/                <- Testimonials, typicality, angles
│   ├── brand/                <- Visual identity and brand systems
│   └── operations/           <- Fulfillment, classroom, funnel, membership notes

mainbranch/ (engine)          <- Never modified
```

---

## Route by Intent

Detect mode from user's natural language:

| User Says | Mode | Reference |
|-----------|------|-----------|
| "figure out", "explore", "I'm trying to..." | Full Flow | - |
| "research", "investigate", "what do we know about" | Research | [research-phase.md](references/research-phase.md) |
| "--brief-format=grok-8", "researched brief", "site brief", "launch brief" | Research Brief | [grok-8-brief-format.md](references/grok-8-brief-format.md) |
| "sharpen this offer", "improve the offer", "make this offer convert", "pressure-test this offer" | Full Flow | `.claude/reference/conversion/offer-sharpening.md` |
| "what are people saying", "sentiment", "X/Twitter", "trending" | Research (Grok) | [grok-social.md](references/grok-social.md) |
| "analyze this VSL", "extract the pitch", "script teardown", "objection mining" | Research | [sales-video-research.md](references/sales-video-research.md) |
| "winning ads", "review mining", "customer language", "competitor ads", "comment mining" | Research | [winning-ad-research.md](references/winning-ad-research.md) |
| "keyword gate", "kill or build this offer", "search demand", "buyer intent", "validate paid traffic demand" | Keyword Gate Research | [keyword-gate.md](references/keyword-gate.md) |
| "decide", "we chose", "document decision" | Decide | [decide-phase.md](references/decide-phase.md) |
| "codify", "apply", "update reference files" | Codify | [codify-phase.md](references/codify-phase.md) |
| "add context", "enrich", "I have new info" | Codify | [codify-phase.md](references/codify-phase.md) |
| "mine these transcripts", "ingest community posts", "process call recordings", "use Drive/provider exports", "mixed account sources" | Source ingestion privacy rail | [source-ingestion.md](references/source-ingestion.md) |
| "this source/claim/angle is stale", "old source", "obsolete claim", "retire this", "stop using that proof" | Stale-source cleanup | [stale-source-cleanup.md](references/stale-source-cleanup.md) |
| "content strategy", "pillars", "what platforms", "content plan", "cadence", "channel strategy", "account strategy", "founder voice", "weekly content plan" | Full Flow (codify to the right content strategy layer) | [codify-phase.md](references/codify-phase.md) |
| "where was I", "continue", "pick up" | Recovery | [recovery.md](references/recovery.md) |
| "here's a PDF", "ingest this", "convert this document", file path (.pdf/.docx/.pptx) | Document Ingestion | [document-ingestion.md](references/document-ingestion.md) |
For offer, audience, proof, CTA, content strategy, ads/pages, and positioning requests, use [research-depth-ladder.md](references/research-depth-ladder.md) before selecting source tools.

If unclear, ask: "Are you exploring a question, documenting a decision, or updating reference files?"

---

## Research Routing

Pick the source tool from [research-routing-quick-ref.md](references/research-routing-quick-ref.md) (intent table, tool checks, fallbacks, file suffixes, token limits). Never block on a missing optional tool: use web/codebase search, pasted material, manual exports, or the `mb connect` repair command, and offer setup once. See [tool-detection.md](references/tool-detection.md) for tool-specific fallback wording.

When two or more source types are needed, spawn parallel Task agents in a single message (one per source), as in Full Flow step 2.

---

## Active Guidance (Your Job)

**Don't just provide templates. Actively move people through the cycle.**

On every `/mb-think` invocation, detect state and guide the next step:

```bash
# Check for continuity and rationale state
ls -lt research/*.md 2>/dev/null | head -3
grep -l "status: proposed\|status: accepted" decisions/*.md 2>/dev/null
# Also check content strategy state
ls core/content-strategy.md 2>/dev/null
```

| If you find... | Then... |
|----------------|---------|
| Recent research, no decision | "You have research on [topic]. Ready to make a decision?" |
| Proposed decision | "Decision [topic] is proposed. Ready to accept it?" |
| Accepted decision (not yet codified) | "Decision [topic] is accepted. Ready to codify the changes into reference files?" |
| content-strategy.md exists but empty/thin | "Your content strategy file is a skeleton. Want to fill it in? We can define the known-for target, pillars, asset jobs, and distribution links from your offer, audience, proof, and voice." |
| content-strategy.md missing (community biz) | "You don't have a content strategy yet. Want to build one? It'll define what you want to be known for, your pillars, asset jobs, and distribution layers." |
| skool-surfaces.md missing (community biz with live Skool) | "Your Skool about page and pricing card copy aren't in reference yet. Want to add them? Skills check this for congruence." |
| `core/offers/` exists | Multi-offer repo. Use a future `mb` JSON active-offer field if present. Otherwise ask which offer this research/decision is about; do not silently route from `.vip/local.yaml`. |
| Nothing in progress | "What are you trying to figure out?" |

**The goal is reference files.** Research and decisions are waypoints. Keep asking: "What needs to happen to get this into reference?"

---

## Full Flow (Default)

```
Research -> Checkpoint -> Decide -> Checkpoint -> Codify
```

### 1. Define Question

> "What specifically are you trying to figure out?"

### 2. Research

Gather from codebase, web, user input, local recordings.

**When research involves 2+ sources**, spawn one `general-purpose` Task agent per source in a single message, never with `run_in_background` (background agents cannot use MCP tools or prompt for permissions). Each agent gets one source and one question, writes its own dated file, verifies the write, and returns file path, write status and a 5-bullet summary (the full content if the write failed). Afterwards confirm files landed, write any that failed from the returned content, then synthesize. See [research-phase.md](references/research-phase.md) for the agent brief.

**Mining sources:** Use [research-routing-quick-ref.md](references/research-routing-quick-ref.md)
and the source-specific references for tool choice and output suffixes.
Authenticated community, calls, Drive/provider exports, and other private
source mixes route through [source-ingestion.md](references/source-ingestion.md).

### 3. Synthesize (Required)

Every research output needs:
- One-sentence summary (20 words max)
- Key findings (5-10 bullets)
- Implications for reference files
- Open questions

Synthesis works best when the main conversation is clean — which is exactly what subagents provide. Heavy raw content (transcripts, mined posts) lives in the subagent context windows, and only distilled summaries return to main. For authenticated or private sources, run the source-ingestion rail first and keep raw transcripts/provider payloads out of committed files by default.

**Content mining:** AI shows what worked; you judge why. Extract visual, audible and emotional dimensions, judge whether the framework transfers to your context, adapt it to your voice, and codify before creating: Mining -> Human Synthesis -> Reference Update -> THEN Create. See [research-phase.md](references/research-phase.md).

### 4. Checkpoint

> "Ready to make a decision, or need more research?"

### 5. Decide

Present options with pros/cons. Document choice and rationale.

### 6. What Changes

Describe what reference files are affected in the decision file:

```markdown
## What Changes

offer.md gets a guarantee section after pricing. A new angle file (risk-reversal.md) captures the guarantee messaging.
```

See [decide-phase.md](references/decide-phase.md) for format details.

### 7. Checkpoint

> "Ready to update reference files now, or save for later?"

### 8. Codify

Apply changes described in `## What Changes` to reference files. Mark decision as codified.

**Codify targets include:** `core/*.md`, active offer/audience files, proof files, `core/content-strategy.md`, `core/marketing/...`, `core/people/...`, `core/team/<slug>.md`, `core/operations/funnel/skool-surfaces.md`, `core/product-ladder.md`, and `bets/` only when updating the live wager or verdict. See [codify-phase.md](references/codify-phase.md) for layer-specific rules.

---

## Modes

- `/mb-think research "topic"` writes `research/YYYY-MM-DD-topic-claude-code.md` ([research-phase.md](references/research-phase.md)). Ad, customer, review, competitor and comment mining use [winning-ad-research.md](references/winning-ad-research.md); broad briefs set `brief_format: grok-8` ([grok-8-brief-format.md](references/grok-8-brief-format.md)); offer-launch demand uses [keyword-gate.md](references/keyword-gate.md), which writes a Build / Build with caution / Kill verdict with a lander cluster, ready-to-buy terms and negative keyword seeds for `/mb-site` and `/mb-ads`.
- `/mb-think decide "topic"` writes `decisions/YYYY-MM-DD-topic.md` ([decide-phase.md](references/decide-phase.md)).
- `/mb-think codify decisions/YYYY-MM-DD-topic.md`, or "add new testimonials to my files" ([codify-phase.md](references/codify-phase.md)).

---

## Work Continuity Layers

| Layer | Scope | Use For |
|-------|-------|---------|
| **Claude tasks** | Session | Local execution steps and tool progress |
| **Decision files** | Durable | Rationale, options, chosen direction, what changes |
| **GitHub issues** | Durable | Work threads that need cross-session or team visibility |

Decision status is rationale maturity, not a general work-progress board:
`proposed` means a direction is drafted, `accepted` means the operator chose
it, and `codified` means the rationale has been integrated into durable
business or engine truth.

See [decide-phase.md](references/decide-phase.md) for decision lifecycle patterns.
See [recovery.md](references/recovery.md) for resuming sessions.

---

## Recovery

After compaction, check `TaskList`, `ls -lt research/*.md | head -5`, decisions with `status: proposed|accepted`, and (for durable threads) `gh issue list --assignee @me --state open`. Then confirm: "I see you were working on [topic]. Continue from here?" See [recovery.md](references/recovery.md).

---

## Templates

- [references/templates/research-template.md](references/templates/research-template.md)
- [references/grok-8-brief-format.md](references/grok-8-brief-format.md)
- [references/templates/decision-template.md](references/templates/decision-template.md)

---

## When NOT to Use

Quick factual questions, simple file edits, or generating content (use `/mb-ads`, `/mb-site`, `/mb-organic`). Use `/mb-think` when the answer needs investigation and the choice needs documentation.

---

## Why This Matters

Keep what changes the business; leave the rest in research.
