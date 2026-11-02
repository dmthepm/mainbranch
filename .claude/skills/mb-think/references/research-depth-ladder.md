# Research Depth Ladder

Use this before offer sharpening, audience work, proof/typicality work, product
ladder choices, CTA choices, content strategy, ads/pages, or market/category
positioning. The ladder decides how much research is worth spending before the
operator makes the next business move.

This is a decision layer, not a scraping implementation. After choosing the
depth, use [research-phase.md](research-phase.md),
[research-routing-quick-ref.md](research-routing-quick-ref.md), and the source-specific
references for tool routing.

## The Rule

Spend the smallest amount of research that can make the next decision honest.

More depth is not always better. A copy cleanup may only need repo context. A
major repositioning, proof claim, or market entry may need source-backed
research, structured collection, field evidence, or a small push/test.

## Depth Levels

| Level | Name | Use when | Typical sources | Durable output |
| --- | --- | --- | --- | --- |
| 0 | Operator memory | The operator already knows enough and the move is low-risk. | Operator answer in chat. | Optional note or direct codify after confirmation. |
| 1 | Repo context | Existing `core/`, `research/`, `decisions/`, `bets/`, `pushes/`, and `log/` can answer the question. | Business repo files, `mb status --json --peek`, MoneyPath facts. | Research note only if synthesis is useful; otherwise update accepted target files. |
| 2 | Lightweight public/manual research | Repo context is thin but the decision only needs quick outside orientation. | Public web, competitor pages, operator-pasted examples, manual screenshots, short customer snippets. | One research file with source notes and implications. |
| 3 | Multi-source synthesis | Offer, audience, proof, page, ad, or content decisions need repeated public patterns. | Several public sources, reviews, competitor pages, YouTube transcripts, X/social sentiment, ChatGPT/Gemini-style synthesis. | Source-specific files when useful plus a synthesis file. |
| 4 | Structured approved-source collection | Customer language lives in accessible sources and manual collection would miss patterns. | Apify through MCP, approved provider setup, or another structured collection path for public/approved YouTube, reviews, X/public posts, Reddit, Instagram, or operator-approved exports. | Source-specific mining files with access notes, caveats, and no raw dumps. |
| 5 | High-resolution market analysis | The move changes positioning, offer architecture, launch strategy, or MoneyPath confidence. | Multiple source files, parallel agents, structured collection, customer calls, outcome logs, push/page/channel data. Apify/MCP may be one provider rail. | Synthesis file, accepted decisions, and reviewed updates to core/push/playbook/log files. |

## Recommendation Block

Before deeper research, give the operator a compact recommendation:

```text
Research Depth Recommendation
- current_depth: 1
- recommended_depth: 3
- reason: audience language is thin and proof claims are not source-backed
- useful_sources: customer calls, reviews, YouTube transcripts, competitor pages
- optional_tools: Apify, Grok, Gemini
- fallback: manual transcript, screenshots, pasted examples, or public web
- stop_condition: repeated language is clear enough to update audience and objections
- durable_targets: core/audience.md, core/offer.md, core/proof/angles/, decisions/
```

If the operator chooses less depth, proceed with the caveat. If the operator
chooses more depth, explain the cost, token use, source limits, and stop rule.

## Enough Signal By Task

| Task | Minimum useful depth | Escalate when | Stop when | Durable targets |
| --- | --- | --- | --- | --- |
| Offer sharpening | 1 for copy cleanup, 2-3 for meaningful repositioning | Buyer, problem, mechanism, proof, or objections are thin. | The next offer edit is clear and honest. | `core/offer.md`, `core/offers/<slug>/offer.md`, `decisions/` |
| Audience definition | 1 for existing segment cleanup, 3-4 for new segment language | The repo lacks repeated customer words, trigger events, or exclusions. | Repeated situations, pains, desires, and disqualifiers are visible. | `core/audience.md`, `core/offers/<slug>/audience.md` |
| Proof / typicality | 1 only for cataloging existing approved proof, 3-5 for claims | A claim needs outcome, timeframe, metric, permission, or average-case support. | Supportable claim, caveat, and typicality language are clear. | `core/proof/`, `core/offers/<slug>/proof/` |
| Product ladder | 1-2 for naming existing offers, 3-5 for architecture changes | Ascension logic, entry offer, or high-ticket path is speculative. | The ladder has a clear next step and unresolved assumptions are named. | `core/product-ladder.md`, offer files, `decisions/` |
| CTA path | 1-2 for choosing among known paths, 3 when buyer friction is unknown | The next step is unclear, too high-friction, or not proof-backed. | One honest next action and fallback path are selected. | Offer file, page/push notes, `decisions/` |
| Content strategy | 1 for repo cleanup, 2-4 for platform/account strategy | Pillars, account voice, audience behavior, or platform fit are thin. | Recognition target, pillars, jobs, and channel/account caveats are clear. | `core/content-strategy.md`, `core/marketing/...`, `core/people/...` |
| Ads/page launch | 2 for small tests, 3-5 for meaningful spend or new landing page | Claims, objections, proof, search demand, or competitor context are weak. | The launch can be tested with clear caveats and success signals. | `pushes/`, page brief, ad brief, offer/proof files |
| Market/category positioning | 3 minimum, usually 4-5 for durable changes | The business is entering or renaming a category. | Category language, alternatives, gaps, and risks are sourced enough to decide. | `research/*-synthesis.md`, `decisions/`, offer/content strategy |
| Influence/style/playbook capture | 1-2 for operator taste, 3 when sourcing public examples | The operator wants a named style to shape offer, voice, or playbook patterns. | Approved principles are captured without copying protected material. | `core/voice.md`, offer style notes, `pushes/*/playbooks/`, `decisions/` |

## MoneyPath Connection

Use the ladder to explain readiness without making `mb` judge market strength.
`mb status --json --peek` reports deterministic facts; the skill explains what
research depth would improve confidence.

| MoneyPath depth language | What it can rely on | What it cannot prove |
| --- | --- | --- |
| Level 0-1 | Operator memory and repo context are enough to start. | Market demand, typicality, or field performance. |
| Level 2 | Structured offer, audience, proof, CTA, and content files exist. | Whether outside buyers use the same language. |
| Level 3 | Public/source-backed research, testimonials, examples, or typicality notes support the path. | Whether the offer works in the field. |
| Level 4 | Sales calls, customer language, ad tests, real content response, or outcome logs support the path. | Durable performance without instrumentation. |
| Level 5 | Channel/page/push metrics, outcome feedback, and reviewed learning loops support the path. | Future results or claims beyond the evidence. |

These are agent-side explanatory labels, not a parallel MoneyPath score. Do not
convert this into a new score unless a separate CLI issue accepts that contract.
For now, this is skill guidance.

## Source Quality

Prefer sources that are close to buyer behavior:

1. Direct customer/buyer language with permission and context.
2. Outcome logs, sales calls, support, surveys, reviews, and refund/churn notes.
3. Public reviews, comments, questions, competitor pages, and platform posts.
4. Expert frameworks and market reports.
5. Operator taste, beliefs, and preferred influences.

Weak sources can still be useful. Label them as language, inspiration, or
directional signal rather than proof.

## Structured Collection Boundary

Apify is an optional research provider rail, preferably through MCP for now.
Treat MCP as an agent-side tool surface, not automatically as an `mb connect`
provider. Do not add or imply `mb connect apify` behavior unless a later CLI
issue accepts stable provider-readiness facts.

Use Apify/MCP or another approved structured collection path only when:

- the operator chooses Level 4 or Level 5 depth;
- the operator has access or the source is public;
- the operator accepts the source, terms, cost, and reliability tradeoffs;
- terms, legal, and access boundaries are clear;
- the decision justifies structured collection;
- the output will be synthesized, not committed as a raw dump.

For gated or private communities, require access, permission, terms/legal
review where needed, and operator judgment. If that is unclear, stop and ask.

Never imply Main Branch can scrape private DMs, private analytics, protected
accounts, gated communities without permission, or provider systems without
accepted support and smoke evidence.

Levels 0-3 require no Apify. Level 4 may use Apify/MCP when access and
permission are clear. Level 5 may use Apify/MCP as one rail among multiple
source files, caveats, synthesis, and durable promotion decisions.

If agents need deterministic CLI facts later, open a follow-up for Apify/MCP
research-provider readiness. Candidate facts include MCP configured, token
present, allowed actor list, last smoke result, approved source types,
dataset/cache policy, and no-raw-dump policy.

## Parallel Research Files

For multi-source or parallel-agent research, each source gets its own file and
the main thread writes the synthesis.

```text
research/YYYY-MM-DD-offer-audience-youtube-customer-language.md
research/YYYY-MM-DD-offer-audience-reddit-pain-points.md
research/YYYY-MM-DD-offer-audience-competitor-positioning.md
research/YYYY-MM-DD-offer-audience-synthesis.md
```

Each source file should include:

- research question;
- source type;
- access or permission note;
- collection method;
- source quality;
- key patterns;
- counter-signals;
- caveats;
- what should and should not be promoted;
- public/private handling.

The synthesis file should include:

- strongest repeated language;
- market pains, desires, and buying triggers;
- objections and proof gaps;
- competitor/category positioning;
- source quality and confidence;
- recommended durable updates;
- whether the stop condition was met.

## Graduation Rules

Research does not automatically overwrite core truth.

- `research/` preserves evidence, caveats, source quality, and open questions.
- `core/` preserves accepted operating truth.
- `core/proof/` preserves approved proof, typicality, caveats, permission, and
  offer linkage.
- `core/content-strategy.md`, `core/marketing/...`, and `core/people/...`
  preserve accepted content strategy and voice constraints.
- `pushes/` and `playbooks/` preserve bounded execution plans and approval
  records.
- `decisions/` explain why a meaningful change was accepted.
- `log/` preserves field results and lessons from shipped work.

When the research suggests a meaningful business change, recommend a decision
or operator review before codifying.

## Influence And Taste

When the operator likes a style, thinker, creator, or playbook, capture the
operator-approved principle rather than copying the source.

Good durable notes:

- what the operator likes;
- what not to copy;
- what principle transfers;
- voice/style constraints;
- attribution when useful;
- whether this becomes a reusable playbook candidate.

Do not copy protected material wholesale, present a person's style as universal
truth, or flatten the operator's voice into generic internet marketing.

## Stop Rules

Stop researching and synthesize when:

- repeated language patterns are clear enough to update audience, offer,
  objections, or proof angles;
- the next business move is obvious and more research would delay shipping;
- sources are low-quality, repetitive, or no longer changing the answer;
- the operator needs field evidence, not more desk research;
- the source is gated/private and access, permission, or terms are unclear;
- the decision requires launching a small push/test rather than more analysis;
- the research would require raw copyrighted dumps, private customer data,
  account exports, session cookies, or unsupported provider access.

If the stop rule is "field evidence needed," route to a small push, page/ad
test, sales-call plan, or outcome log instead of more research.
