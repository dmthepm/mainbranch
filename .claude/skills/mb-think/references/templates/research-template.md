# Research Template

Copy this template when creating research files.

---

## Filename Convention

```
research/YYYY-MM-DD-topic-[source].md
```

**Source suffixes:**
- `-gemini.md` — Gemini deep research
- `-gpt.md` — ChatGPT research
- `-claude-code.md` — Claude Code session (this tool)
- `-claude-web.md` — Claude.ai web interface
- `-x-social.md` — X/Twitter social research (Grok MCP)
- `-yt-mining.md` — YouTube transcript mining (Apify)
- `-ig-mining.md` — Instagram mining (Apify or manual)
- `-customer-mining.md` — Customer calls, surveys, support, onboarding, cancellation language
- `-review-mining.md` — Public reviews and rating-backed customer language
- `-winning-ad-research.md` — Competitor gap maps, ad/script teardown, winning blueprint research
- `-content-comment-mining.md` — TikTok, YouTube, Instagram, or X comment language mining
- `-local-mining.md` — Local video/audio transcription
- `-voice-mining.md` — Voice memo transcription
- `-competitor-mining.md` — Competitor site mining
- `-internal-mining.md` — Internal data (emails, DMs, reviews)
- `-audit.md` — Site or system audit
- (no suffix) — General or mixed sources

---

## Template

```markdown
---
type: research
date: YYYY-MM-DD
source: claude-code
source_url:                    # Optional: Gemini/GPT share link for provenance
model: opus-4.5
status: draft
brief_format: standard         # Use grok-8 for the 8-category researched brief
research_depth: 1              # 0-5; see research-depth-ladder.md
linked_decisions: []
linked_pushes: []
---

# [Topic] Research

## Related links

[Leave empty until `linked_decisions` or `linked_pushes` has evidence-backed
targets, then mirror those frontmatter links with Markdown relative links.
Use docs/business-connections.md when deciding whether a connection should be
a typed frontmatter link, inline link, entity tag, data reference, or no link.]

## Question

[1-3 sentences: What you're trying to learn. Be specific.]

---

## Methodology

[2-4 sentences: How you approached this research. What tools, what context provided, what attachments. Not the full prompt — just enough to reproduce or audit.]

---

## Research Depth

```text
current_depth:
recommended_depth:
reason:
useful_sources:
optional_tools:
fallback:
stop_condition:
durable_targets:
```

Explain why this depth was enough, or what would justify escalation. If using
Apify/MCP or another structured collection path, include access, permission,
terms, source-quality, and no-raw-dump notes.

---

## Sources Checked

| Source | What We Found |
|--------|---------------|
| [Source 1] | [Brief summary] |
| [Source 2] | [Brief summary] |
| [Source 3] | [Brief summary] |

---

## Source Excerpts Used

Keep excerpts short and only include what supports the analysis. Do not paste
full prompt libraries, full articles, raw comment dumps, private customer data,
or long tweet threads into committed research files.

| Source | Concise Excerpt | Why It Matters |
|--------|-----------------|----------------|
| [Source 1] | "[Short excerpt]" | [Evidence role] |

---

## Raw Findings

Real material belongs in the hub; keep large customer datasets out. See `/mb-setup` `references/where-data-lives.md`.

### [Finding Area 1]

[Detailed notes, quotes, data]

### [Finding Area 2]

[Detailed notes, quotes, data]

### [Finding Area 3]

[Detailed notes, quotes, data]

---

## Synthesis (REQUIRED)

### One-Sentence Summary (20 words max)

[Force yourself to distill the core insight]

### Key Findings (5-10 bullets, 15 words each)

1. [Finding 1]
2. [Finding 2]
3. [Finding 3]
4. [Finding 4]
5. [Finding 5]

### Implications for Reference Files

| File | Potential Update |
|------|------------------|
| `core/offer.md` | [What might change] |
| `core/audience.md` | [What might change] |
| `core/proof/angles/` | [What might change] |
| `core/proof/typicality.md` | [Aggregate outcome/average-case context] |
| `core/content-strategy.md` / `core/marketing/...` / `core/people/...` | [Hooks, frameworks, platform strategy, or layer links] |

### Open Questions

- [What we still don't know]
- [What needs follow-up research]

### Promotion Review

| Candidate Durable Target | Promote? | Reason / Caveat |
|---|---|---|
| `core/offer.md` | yes/no | [What should change, or why not yet] |
| `core/audience.md` | yes/no | [What should change, or why not yet] |
| `core/proof/` | yes/no | [Permission, typicality, outcome, or caveat note] |
| `core/content-strategy.md` / `core/marketing/...` / `core/people/...` | yes/no | [Strategy or voice implication] |
| `decisions/` | yes/no | [Decision needed before changing core truth] |

---

## Citations

- [Source 1 with link if available]
- [Source 2]
- [Source 3]
```

## Grok-8 Researched Brief Variant

Use this variant when the operator passes `--brief-format=grok-8`, asks for a
researched brief, or needs the research to feed `/mb-ads`, `/mb-site`, organic
content, or a push playbook. See
[../grok-8-brief-format.md](../grok-8-brief-format.md) for the full guidance.

Add this frontmatter:

```yaml
brief_format: grok-8
linked_pushes: []
```

After `## Source Excerpts Used`, add:

```markdown
## Grok-8 Researched Brief

### 1. Business And Offering Deep Dive

### 2. ICP And Deep Audience Insights

### 3. Customer Journey And Story Mapping

### 4. Competitive And Market Landscape

### 5. Brand Archetype And Story Discovery

### 6. Technical, Functional, And Experience Requirements

### 7. Content And Asset Audit

### 8. Success Metrics And Constraints
```

After `### Implications for Reference Files`, add:

```markdown
### Downstream Handoff

| Next Surface | Ready Input | Missing Or Risky |
|---|---|---|
| `/mb-ads` | [Angles, objections, proof, audience language] | [Unknowns] |
| `/mb-site` | [Offer, audience, story, requirements, assets, metrics] | [Unknowns] |
| Push playbook | [Trigger, resource, approval gate, provider boundary] | [Unsupported/manual pieces] |
| Reference files | [Specific files to update] | [What not to codify yet] |
```

---

## Status Values

| Status | Meaning |
|--------|---------|
| `draft` | Research in progress, not yet synthesized |
| `complete` | Synthesis done, ready to inform decisions |
| `codified` | Findings have been applied to reference files |
| `superseded` | Newer research replaces this |

---

## Linking to Decisions

When a decision uses this research, update the frontmatter:

```yaml
linked_decisions:
  - decisions/2026-01-17-pricing-strategy.md
  - decisions/2026-01-18-guarantee-policy.md
```

This creates a bidirectional link (research links forward to decisions, decisions link back to research).

---

## Quality Checklist

Before marking research as `complete`:

- [ ] Question is specific and answerable
- [ ] At least 3 sources checked
- [ ] Raw findings are detailed
- [ ] Synthesis section is complete
- [ ] One-sentence summary exists and is under 20 words
- [ ] Key findings are 5-10 bullets, each under 15 words
- [ ] Implications for reference files are explicit
- [ ] Open questions documented
- [ ] Citations included

---

## Example: Completed Research

```markdown
---
type: research
date: 2026-01-17
source: claude-code
model: opus-4.5
status: complete
brief_format: standard
linked_decisions: []
linked_pushes: []
---

# Pricing Tier Strategy Research

## Question

What pricing tier structure should we use for the community membership?

**Why this matters:** Currently one tier at $97/month. Considering adding free tier or premium tier. Need data to decide.

---

## Sources Checked

| Source | What We Found |
|--------|---------------|
| Competitor analysis (5 communities) | $47-197/month range, most have 2-3 tiers |
| Skool pricing norms | Free tier common for lead gen, paid starts at $47-97 |
| Past member feedback | 3 members mentioned wanting "advanced" content |
| Industry benchmarks (SaaS pricing research) | 3 tiers is optimal, middle tier gets 60% of signups |

---

## Raw Findings

### Competitor Pricing

- Community A: Free / $67/month / $197/month
- Community B: $97/month only (premium positioning)
- Community C: Free / $47/month (high volume)
- Community D: $147/month / $297/month (ultra-premium)
- Community E: Free / $97/month / $497/year

### Member Feedback

[Detailed quotes and feedback...]

### Industry Data

[Pricing psychology research, conversion data...]

---

## Synthesis

### One-Sentence Summary (20 words max)

Three-tier pricing with free/paid/premium maximizes reach while creating natural upgrade paths for committed members.

### Key Findings

1. Two-tier (free/paid) is minimum viable for lead generation
2. Three-tier captures both budget-conscious and power users
3. Middle tier gets 60%+ of signups in most communities
4. Annual pricing increases retention 30-40% vs monthly
5. Premium tier should be 2-3x base price, not 1.5x
6. Free tier converts 5-15% to paid within 60 days
7. "Investment" framing outperforms "deal" framing for our audience

### Implications for Reference Files

| File | Potential Update |
|------|------------------|
| `core/offer.md` | Add tier descriptions, pricing logic |
| `core/audience.md` | Segment by tier (free seeker vs committed buyer) |
| `core/proof/angles/value.md` | Update ROI math for each tier |

### Open Questions

- What should the free tier include to create desire for paid?
- Should premium be monthly or annual-only?
- How do we position the upgrade without devaluing free?

---

## Citations

- [Competitor A sales page URL]
- [Pricing research article URL]
- Member feedback: Slack #feedback channel, Jan 2026
```
