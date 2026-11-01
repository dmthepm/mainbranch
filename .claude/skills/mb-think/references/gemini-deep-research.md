# Gemini Deep Research

When and how to use Gemini for comprehensive research. Setup: [gemini-setup.md](gemini-setup.md). Routing: [research-routing-quick-ref.md](research-routing-quick-ref.md).

---

## Three Tiers

| Tier | Use | Tool | Time | Cost |
|------|-----|------|------|------|
| **1 Quick** | Simple questions, fact-checking | `generate_content` with `gemini-2.0-flash` (tested; optional Google Search grounding) | 30-60s | ~$0.005-0.05 |
| **2 Deep** | Competitive analysis, industry research, multi-source synthesis | Deep Research Agent via Interactions API, agent `deep-research-pro-preview-12-2025` (tested 2026-01-26) | 5-20 min (max 60) | ~$2-5 (about 80 searches/250K tokens standard, 160 searches/900K complex; Gemini 3 Pro rates, caching cuts repeats) |
| **3 Manual** | Specific sources, API unavailable, cost-sensitive | WebSearch + Apify + Claude synthesis | variable | ~$0.20-1.00 |

Tier 1 handles about 80% of needs; reserve Tier 2. Tier 1 is a standard model call, not "Deep Research". Check current prices at ai.google.dev/pricing. Batch is 50% off; context caching cuts repeat content up to 90%.

The Gemini UI "Deep Research" checkbox and the Tier 2 agent are the same technology. The UI is included in a Gemini subscription; the API is per-token and has no UI access. `generate_content` cannot reach Deep Research; `interactions.create(agent=...)` can.

| Scenario | Tier |
|----------|------|
| Quick fact check | 1 (WebSearch or Flash) |
| Competitive analysis, industry trends, academic-style investigation | 2 |
| Specific URL content, YouTube transcripts, social sentiment | 3 (Apify, Grok) |

---

## Tier 1 (REST)

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
Header: x-goog-api-key: $GOOGLE_API_KEY
```

Response text: `candidates[].content.parts[].text`.

## Tier 2 (REST, no SDK required)

Start:

```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Your research question here", "agent": "deep-research-pro-preview-12-2025", "background": true, "store": true}'
```

Returns `{"id": "v1_xxxxx", "status": "in_progress", ...}`. Poll:

```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions/{interaction_id}" \
  -H "x-goog-api-key: $GOOGLE_API_KEY"
```

When `status` is `completed`: `outputs[].text` is the markdown report, `outputs[].annotations[]` the source URLs, `usage` the token counts. Poll about every 30s; stop on `failed`.

Parameters: `agent` (required), `background: true` (required), `store: true` (required with background), `stream: true` (progress), `agent_config.thinking_summaries: "auto"`, `previous_interaction_id` (follow-up questions; can pass `model='gemini-3-pro-preview'` for quick follow-ups).

SDK alternative: Python `pip install "google-genai>=1.55.0"` (not `google-generativeai`), JS `npm install "@google/genai>=1.33.0"`; `client.interactions.create(...)` / `client.interactions.get(id)`.

Known issues and limits (preview API, schemas may change): occasional 500s on long runs (if a poll returns 500 after ~10 min, start a new request); no custom function tools, MCP, structured output schemas or audio input; data retained 55 days (paid) or 1 day (free).

---

## Workflow from /mb-think

**Tier 1:** detect a simple question; use WebSearch or Flash; synthesize; save to `research/YYYY-MM-DD-topic-flash.md` (or `-web.md`).

**Tier 2:**
1. Detect a complex research need.
2. If `GOOGLE_API_KEY` is not set: "Deep research requires Gemini. Set up now (3 min)?"
3. Start the Interactions request and tell the user: "Research started. This takes 5-20 minutes."
4. Poll (or stream), letting the user keep working; notify on completion.
5. Extract findings; don't dump raw output.
6. Save to `research/YYYY-MM-DD-topic-gemini-deep.md`.
7. Checkpoint: "Ready to decide, or need more research?"

## Output Format

Use [templates/research-template.md](templates/research-template.md) with frontmatter `source: gemini-deep | gemini-flash | web | claude-code`, `model`, `tier: 1 | 2 | 3`, `duration`. Suffixes: `-flash.md`, `-gemini-deep.md`, `-web.md`, `-claude-code.md`. Required sections: one-sentence summary (20 words), research question, key findings (5-10), synthesis, implications for reference files, open questions, sources.

## Fallbacks

If Deep Research is unavailable or too expensive: run 5-10 targeted WebSearch queries and synthesize, use Apify RAG Browser, Flash with grounding, or combine tools manually. Don't block research.
