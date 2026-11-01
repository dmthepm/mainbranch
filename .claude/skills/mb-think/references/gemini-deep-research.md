# Gemini Deep Research

When and how to use Gemini for comprehensive research.

---

## Verification Status

| Tier | Feature | Status | Notes |
|------|---------|--------|-------|
| **Tier 1** | Flash API (`generate_content`) | **TESTED** | Works via REST endpoint |
| **Tier 2** | Deep Research (Interactions API) | **TESTED** | Works via REST endpoint (tested 2026-01-26) |
| **Tier 3** | Manual synthesis | **ALWAYS WORKS** | WebSearch + Apify + Claude |

**Tested endpoint (Tier 1):**
```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
Header: x-goog-api-key: $GOOGLE_API_KEY
```

**Response format:** `candidates[].content.parts[].text`

**Tested endpoint (Tier 2):**
```
POST https://generativelanguage.googleapis.com/v1beta/interactions
Header: x-goog-api-key: $GOOGLE_API_KEY
```

**Tier 2 REST API verified working:**
- Agent identifier: `deep-research-pro-preview-12-2025` - CONFIRMED
- Required parameters: `background: true`, `store: true` - CONFIRMED
- Typical completion time: 5-10 minutes
- Python SDK NOT required - REST API works directly

**Known issues (from testing):**
- Occasional internal server errors during long-running research (retry recommended)
- Poll endpoint may return 500 errors if research fails mid-execution

---

## Critical Distinction: UI vs Standard API vs Interactions API

There are THREE different things, often confused:

| Feature | Gemini UI "Deep Research" | Standard API (generate_content) | Interactions API (Deep Research Agent) |
|---------|--------------------------|--------------------------------|---------------------------------------|
| What happens | Multi-step agentic workflow | Single model call | Multi-step agentic workflow |
| Time | 5-20 minutes | 30-60 seconds | 5-20 minutes |
| Searches | 80-160+ sources | None (unless grounding enabled) | 80-160+ sources |
| Output | Detailed report with citations | Standard response | Detailed report with citations |
| Cost | Included in Gemini subscription | ~$0.01-0.05 per query | ~$2-5 per task |
| API Access | No | Yes (`generate_content`) | Yes (`interactions.create`) |

**Key insight:** The UI "Deep Research" checkbox and the API Deep Research Agent are now the **same underlying technology**. As of late 2025, you can replicate the full Deep Research experience programmatically via the Interactions API.

---

## Three Research Tiers

### Tier 1: Quick Research (30-60 seconds)
**When:** Simple questions, fact-checking, quick lookups

**Use:** Standard `generate_content` API with Flash models

**Tested model:**
- `gemini-2.0-flash` — CONFIRMED WORKING

**Also available (check current pricing at [ai.google.dev/pricing](https://ai.google.dev/pricing)):**
- `gemini-2.0-flash-exp` — Experimental, may have different behavior
- `gemini-1.5-flash` — Older but stable
- `gemini-1.5-pro` — More capable, higher cost

**Options:**
- Optional: Enable Google Search grounding for current info
- Typical query cost: ~$0.005-0.02

**Note:** This is NOT "Deep Research" — it's a standard model call.

### Tier 2: Deep Research (5-20 minutes)
**When:** Complex questions requiring multi-source synthesis

**Status:** TESTED AND WORKING (verified 2026-01-26)

**Use:** Deep Research Agent via Interactions API
- Agent: `deep-research-pro-preview-12-2025` (verified working)
- Powered by: Gemini Pro model (most capable)
- Autonomous: plans, searches 80-160+ queries, reads, synthesizes, iterates
- Produces detailed reports with citations

**Observed performance (from testing):**
- Typical completion: 5-10 minutes
- Token usage example: ~500K input, ~16K output, ~8K thought tokens
- Output: Comprehensive markdown report with source annotations

**Cost breakdown (estimated from actual usage):**
- Standard task: ~$2-3 (80 searches, 250K tokens)
- Complex task: ~$3-5 (160 searches, 900K tokens)

### Tier 3: Manual Deep Dive (Variable)
**When:** Specific sources needed, API unavailable, or cost-sensitive

**Use:** WebSearch + Apify + manual synthesis by Claude
- Full control over sources
- Can combine with transcripts, PDFs, specific URLs
- Requires more orchestration

---

## Interactions API: Deep Research

### REST API (No SDK Required)

**Verified working as of 2026-01-26.** You can use the REST API directly without any SDK.

**Start Deep Research:**
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Your research question here",
    "agent": "deep-research-pro-preview-12-2025",
    "background": true,
    "store": true
  }'
```

**Response:**
```json
{
  "agent": "deep-research-pro-preview-12-2025",
  "created": "2026-01-26T21:35:02Z",
  "id": "v1_xxxxx",
  "status": "in_progress"
}
```

**Poll for completion:**
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions/{interaction_id}" \
  -H "x-goog-api-key: $GOOGLE_API_KEY"
```

**When complete**, the response includes:
- `status: "completed"`
- `outputs[].text` — The full research report in markdown
- `outputs[].annotations[]` — Source citations with URLs
- `usage` — Token counts

### SDK Requirements (Alternative)

```bash
# Python — use google-genai (NOT google-generativeai)
pip install google-genai>=1.55.0

# JavaScript
npm install @google/genai>=1.33.0
```

Requires `GOOGLE_API_KEY` from Google AI Studio.

### API Endpoint

```
POST https://generativelanguage.googleapis.com/v1beta/interactions
```

### Basic Usage (Python)

```python
import time
from google import genai

client = genai.Client()

# Start Deep Research (runs asynchronously)
interaction = client.interactions.create(
    input="Research the competitive landscape for AI-powered research tools.",
    agent='deep-research-pro-preview-12-2025',
    background=True,  # Required for Deep Research
    store=True        # Required when using background=True
)

print(f"Research started: {interaction.id}")

# Poll for results (typically 5-20 minutes)
while True:
    interaction = client.interactions.get(interaction.id)
    if interaction.status == "completed":
        print(interaction.outputs[-1].text)
        break
    elif interaction.status == "failed":
        print(f"Research failed: {interaction.error}")
        break
    time.sleep(30)  # Check every 30 seconds
```

### With Streaming (Real-time Progress)

```python
interaction = client.interactions.create(
    input="Research topic...",
    agent='deep-research-pro-preview-12-2025',
    background=True,
    stream=True,
    agent_config={"thinking_summaries": "auto"}  # Shows reasoning progress
)

for update in interaction:
    if update.thinking_summary:
        print(f"Thinking: {update.thinking_summary}")
```

### Follow-up Questions

```python
# Initial research
first = client.interactions.create(
    input="Research AI research tools",
    agent='deep-research-pro-preview-12-2025',
    background=True, store=True
)
# ... wait for completion ...

# Follow-up (uses previous context)
followup = client.interactions.create(
    input="Now compare the top 3 in terms of pricing",
    previous_interaction_id=first.id,  # Links to previous research
    model='gemini-3-pro-preview'        # Can use model for quick follow-ups
)
```

### Key Parameters

| Parameter | Value | Required | Notes |
|-----------|-------|----------|-------|
| `agent` | `deep-research-pro-preview-12-2025` | Yes | For Deep Research agent |
| `background` | `True` | Yes | Research runs asynchronously |
| `store` | `True` | Yes (with background) | Enables result storage |
| `stream` | `True` | No | Real-time progress updates |
| `agent_config.thinking_summaries` | `"auto"` | No | Show intermediate reasoning |
| `previous_interaction_id` | ID string | No | For follow-up questions |

### Current Limitations (Preview)

- Maximum 60-minute research duration (most complete in 5-20 min)
- No custom function calling tools
- No MCP server integration
- No structured output schemas
- No audio inputs
- Beta API — schemas may change
- Data retention: 55 days (paid), 1 day (free tier)

---

## When to Use What

| Scenario | Tier | Tool |
|----------|------|------|
| Quick fact check | 1 | WebSearch or Flash |
| "What's the best X?" | 1-2 | Depends on depth needed |
| Competitive analysis | 2 | Deep Research Agent |
| Industry trends | 2 | Deep Research Agent |
| Academic-style investigation | 2 | Deep Research Agent |
| Specific URL content | 3 | Apify RAG Browser |
| YouTube transcripts | 3 | Apify + synthesis |
| Social media sentiment | 3 | Grok or X mining |

---

## Cost Comparison (January 2026 Pricing)

### Tier 1: Standard API Calls

| Model | Input (per 1M) | Output (per 1M) | Typical Query | Use Case |
|-------|----------------|-----------------|---------------|----------|
| Gemini 3 Flash | $0.50 | $3.00 | ~$0.01 | Fast, most tasks |
| Gemini 2.5 Flash | $0.30 | $2.50 | ~$0.005 | Budget-conscious |
| Gemini 3 Pro | $2.00 (<=200K), $4.00 (>200K) | $12.00 (<=200K), $18.00 (>200K) | ~$0.05 | Complex reasoning |
| Gemini 2.5 Pro | $1.25 (<=200K), $2.50 (>200K) | $10.00 (<=200K), $15.00 (>200K) | ~$0.04 | Mid-tier option |

**Batch pricing:** 50% discount on all models.
**Context caching:** Reduces repeat content cost by up to 90%.

### Tier 2: Deep Research Agent

| Task Complexity | Searches | Input Tokens | Output Tokens | Est. Cost |
|-----------------|----------|--------------|---------------|-----------|
| Standard | ~80 | ~250K (50-70% cached) | ~60K | $2-3 |
| Complex | ~160 | ~900K (50-70% cached) | ~80K | $3-5 |

**All Deep Research charged at Gemini 3 Pro rates.** Caching significantly reduces costs for repeated content.

### Tier 3: Manual Synthesis

Variable — typically $0.20-1.00 depending on:
- Number of WebSearch calls
- Apify scraping costs
- Claude synthesis tokens

### Cost Optimization Tips

1. **Use Tier 1 for 80% of queries** — Flash handles most questions well
2. **Reserve Tier 2 for complex synthesis** — competitive analysis, industry research
3. **Enable caching** for repeated prompts/system instructions
4. **Batch processing** for non-urgent workloads (50% discount)

---

## Workflow from /mb-think

### For Tier 1 (Quick)

```
1. Detect simple research question
2. Use WebSearch or Flash with grounding
3. Synthesize response
4. Save to: research/YYYY-MM-DD-topic-web.md or -flash.md
```

### For Tier 2 (Deep Research Agent)

```
1. Detect complex research need
2. Check: Is GOOGLE_API_KEY set?
   ├─> If no: "Deep research requires Gemini. Set up now (3 min)?"
   └─> If yes: Continue
3. Start Deep Research via Interactions API
4. Notify user: "Research started. This takes 5-20 minutes."
5. Poll for completion (or use streaming for updates)
6. Extract findings, don't dump raw
7. Save to: research/YYYY-MM-DD-topic-gemini-deep.md
8. Checkpoint: "Ready to decide, or need more research?"
```

### Important: Async Handling

Deep Research takes 5-20 minutes. Options:
1. **Wait:** Poll in background, update user on progress
2. **Continue:** Let user do other work, notify when complete
3. **Stream:** Show reasoning progress in real-time

---

## Output Format

Save to: `research/YYYY-MM-DD-topic-[source].md`

Source suffixes:
- `-flash.md` — Tier 1, quick research
- `-gemini-deep.md` — Tier 2, Deep Research Agent
- `-web.md` — Tier 3, WebSearch synthesis
- `-claude-code.md` — Tier 3, manual synthesis

**Template:**

```markdown
---
type: research
date: YYYY-MM-DD
source: gemini-deep | gemini-flash | web | claude-code
model: gemini-3-pro | gemini-3-flash | gemini-2.5-flash
tier: 1 | 2 | 3
duration: 30s | 12min  # Actual time taken
status: complete
topics: [topic1, topic2]
linked_decisions: []
---

# [Topic] — Deep Research

## One-Sentence Summary
[20 words max — the key insight]

## Research Question
[What were we trying to learn?]

## Key Findings

### Finding 1: [Title]
[2-3 sentences explaining this finding]

### Finding 2: [Title]
[2-3 sentences]

[Continue as needed, typically 5-10 findings]

## Synthesis
[1-2 paragraphs connecting the findings into a coherent picture]

## Implications for Reference Files
- **offer.md:** [How this affects our offer]
- **audience.md:** [What we learned about our audience]
- **voice.md:** [Tone/messaging implications]
- **angles/:** [New angles or refinements]

## Open Questions
- [What follow-up research is needed?]
- [What remains uncertain?]

## Sources
- [Key sources cited in research]
```

---

## Can We Replicate UI Deep Research via API?

**Yes, fully.** The Interactions API with `deep-research-pro-preview-12-2025` agent provides the **exact same technology** that powers the UI "Deep Research" checkbox.

| Capability | UI | API |
|------------|-----|-----|
| Multi-step planning | Yes | Yes |
| 80-160+ web searches | Yes | Yes |
| Autonomous iteration | Yes | Yes |
| Cited reports | Yes | Yes |
| Progress visibility | Yes | Yes (with streaming) |
| Follow-up questions | Yes | Yes (previous_interaction_id) |
| File/document analysis | Yes | Yes (File Search tool) |

**What's different:**
- API requires polling/streaming (not instant UI updates)
- API charges per-token (UI included in subscription)
- API is in preview (may have schema changes)
- API allows programmatic integration

**Practical recommendation:**
- **Tier 1 (Flash)** handles 80% of research needs — fast and cheap
- **Tier 2 (Deep Research Agent)** for comprehensive multi-source synthesis — use sparingly
- **Tier 3 (Manual)** when you need specific source control or cost sensitivity

---

## Fallback Options

If Deep Research API unavailable or too expensive:

1. **WebSearch multi-query:** Run 5-10 targeted searches, synthesize manually
2. **Apify RAG Browser:** Good middle ground, scrapes and processes pages
3. **Flash with grounding:** Enable Google Search, get decent synthesis
4. **Manual orchestration:** Combine multiple tools, Claude synthesizes

Don't block research just because Deep Research isn't available — adapt and continue.

---

## Quick Reference

| Question | Answer |
|----------|--------|
| Is Deep Research available via API? | **Yes**, via Interactions API |
| Agent identifier | `deep-research-pro-preview-12-2025` |
| Underlying model | Gemini 3 Pro |
| SDK version (Python) | `google-genai>=1.55.0` |
| SDK version (JS) | `@google/genai>=1.33.0` |
| API endpoint | `POST /v1beta/interactions` |
| Typical time | 5-20 minutes |
| Max time | 60 minutes |
| Cost per task | $2-5 (based on Gemini 3 Pro rates) |
| Can I replicate UI experience? | **Yes**, same underlying technology |
| Status | Preview/Beta (schemas may change) |

---

## Benchmarks (Deep Research Agent)

| Benchmark | Score | Notes |
|-----------|-------|-------|
| Humanity's Last Exam (HLE) | 46.4% | Full set |
| DeepSearchQA | 66.1% | Multi-step info seeking |
| BrowseComp | 59.2% | Web navigation |

---

## API Comparison: What's Available

| API | Access Deep Research? | Best For |
|-----|----------------------|----------|
| `generate_content` | No | Quick queries, standard tasks |
| `interactions.create` (model) | No | Stateful conversations, tool use |
| `interactions.create` (agent) | **Yes** | Deep Research, agentic workflows |

The Interactions API is the new unified interface. It supports both models and agents through the same endpoint — just specify `model=` or `agent=`.

---

## See Also

- [gemini-setup.md](gemini-setup.md) — Setup guide
- [research-routing-quick-ref.md](research-routing-quick-ref.md) — Routing logic
- [research-routing-quick-ref.md](research-routing-quick-ref.md) — Quick decision tree

---

## Changelog

- **2026-01-26:** Major update — documented Interactions API, corrected pricing, added three-tier architecture
- **2025-12:** Initial version (incorrectly described Flash as Deep Research)
