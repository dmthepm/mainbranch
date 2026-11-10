# Gemini Setup

3-minute setup. Free tier available for quick research.

---

## Verification Status

| Tier | Status | Notes |
|------|--------|-------|
| **Tier 1** | **TESTED (January 2026, old model)** | Flash API worked via REST with `gemini-2.0-flash`, which Google shut down on 1 June 2026. Not retested. |
| **Tier 2** | **TESTED (2026-01-26, old agent)** | Deep Research worked via REST with `deep-research-pro-preview-12-2025`, which Google lists as shut down 23 October 2026. Not retested. |

Checked against Google's deprecations page on 10 November 2026: it names `gemini-3.6-flash` (listed Stable) as the replacement for `gemini-2.0-flash`, and `deep-research-preview-04-2026` (preview) for the old agent. Main Branch has not tested either: **not tested by Main Branch**. Check the page for the current model before you use one.

---

## What You Get

Two tiers of Gemini research:

**Tier 1: Quick Research (Free tier)** - CONFIRMED WORKING
- Standard API calls via `generate_content`
- 30-60 second response times
- Good for most questions
- Model: pick a current Flash model from Google's models page (see Verification Status); `gemini-2.0-flash` is shut down

**Tier 2: Deep Research (Pay-as-you-go)** - VERIFIED WORKING
- Agentic multi-step research via Interactions API (REST, no SDK needed)
- 5-10 minute typical completion time
- Searches 80-160+ sources, produces comprehensive markdown reports with citations
- Token usage: ~500K input, ~16K output per research task

Best for:
- Competitor analysis
- Industry research
- Complex questions requiring multiple sources
- Academic-style investigation
- Best practices research

---

## Cost Upfront

**Free tier available for Tier 1 research.** Google AI Studio has a generous free tier.

| Tier | Cost | What You Get |
|------|------|--------------|
| Free | $0 | 15 RPM, 1M tokens/day — quick research |
| Pay-as-you-go (quick) | ~$0.01-0.05/query | Higher limits, Flash/Pro models |
| Pay-as-you-go (deep) | ~$2-5/task | Full Deep Research Agent |

**What does that mean practically?**
- Quick research (Tier 1): ~5-10K tokens, ~100-200 queries/day free
- Deep research (Tier 2): ~250K-900K tokens, $2-5 per research task

**Bottom line:** Start free with Tier 1. Use Tier 2 Deep Research when you need comprehensive multi-source synthesis.

---

## Setup Steps

### 1. Get API Key (2 min)

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with Google account
3. Click "Create API key"
4. Copy the key

### 2. Store the Key (1 min)

From the business repo, store the key with `mb connect`. Paste it at the prompt
your terminal gives, never into chat, a file, or a shell line.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

Then run:

```bash
mb connect google-ai --custom --account "Google AI Studio"
```

Commands that need the key run through `mb connect exec`, which puts it in that
one command's environment and nowhere else:

```bash
mb connect exec google-ai --env GOOGLE_API_KEY -- <command>
```

A key an older install already placed in your shell environment keeps working;
it is not migrated.

---

## Verify It's Working

```bash
mb connect status google-ai --json
```

This confirms the key is stored without printing the value.

**In Claude Code:**

```
/mb-think deep research on a simple topic
```

If Gemini is detected, Claude will use it for complex research.

---

## That's It

Gemini Deep Research is now available in /mb-think.

---

## Troubleshooting

**"Key not found"**
- Run `mb connect status google-ai --json` from the business repo.
- If it is not stored, repeat step 2.

**"Invalid API key"**
- Verify key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- Make sure you copied the full key (no trailing spaces)

**"Quota exceeded"**
- Free tier has limits (15 requests/minute, 1M tokens/day)
- Wait a minute and retry, or upgrade at Google AI Studio

**"Model not available"**
- Gemini models may vary by region
- Check [ai.google.dev/models](https://ai.google.dev/models) for availability

**"background=true is required" (Tier 2)**
- Deep Research requires `background: true` and `store: true` in the request body
- This is expected behavior, not an error

**"Internal server error" during Deep Research**
- Occasionally occurs during long-running research tasks
- The research may have failed mid-execution
- Solution: Start a new research request (retry)
- Poll endpoint returning 500 means the interaction is no longer retrievable

**Research stuck "in_progress" for >20 minutes**
- Deep Research has a 60-minute maximum duration
- Most complete in 5-10 minutes
- If stuck, the task may have failed silently
- Start a new request with a more focused query

---

## Why Google AI Studio (Not Google Cloud)?

| Option | Complexity | Cost |
|--------|------------|------|
| **Google AI Studio** | 3 min setup, one API key | Free tier, simple billing |
| Google Cloud + Vertex AI | 30+ min setup, project config, IAM | Enterprise pricing |

**We use Google AI Studio.** It's the same Gemini models with simpler setup.

---

## See Also

- [gemini-deep-research.md](gemini-deep-research.md) — How to use Gemini for research
- [research-routing-quick-ref.md](research-routing-quick-ref.md) — Routing logic
- `mb-start/references/config-system.md` — Config file layout (legacy local.yaml, config.yaml)
- `docs/connect.md` — `mb connect` and `mb connect exec`
