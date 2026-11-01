# Gemini Setup

3-minute setup. Free tier available for quick research.

---

## Verification Status

| Tier | Status | Notes |
|------|--------|-------|
| **Tier 1** | **TESTED** | Flash API works via REST endpoint |
| **Tier 2** | **TESTED** | Deep Research API works via REST (verified 2026-01-26) |

---

## What You Get

Two tiers of Gemini research:

**Tier 1: Quick Research (Free tier)** - CONFIRMED WORKING
- Standard API calls via `generate_content`
- 30-60 second response times
- Good for most questions
- Tested model: `gemini-2.0-flash`

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

### 2. Add to Environment (1 min)

Create or edit your vip env file:

```bash
mkdir -p ~/.config/vip
nano ~/.config/vip/env.sh
```

Add your key:

```bash
export GOOGLE_API_KEY="your_key_here"
```

Save (Ctrl+X, Y, Enter) and reload:

```bash
source ~/.config/vip/env.sh
```

**Optional:** Add to your shell profile for persistence:

```bash
echo 'source ~/.config/vip/env.sh' >> ~/.zshrc
```

---

## Verify It's Working

```bash
test -n "$GOOGLE_API_KEY" && echo "GOOGLE_API_KEY is set" || echo "GOOGLE_API_KEY is not set"
```

This should confirm the key is set without printing the value.

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
- Did you `source ~/.config/vip/env.sh`?
- Or restart your terminal?
- Check presence without printing the value:
  `test -n "$GOOGLE_API_KEY" && echo "GOOGLE_API_KEY is set" || echo "GOOGLE_API_KEY is not set"`

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
- `mb-start/references/config-system.md` — Full config file layout (local.yaml, env.sh, config.yaml)
- `mb-setup/SKILL.md` Step 4a — How env.sh is created during initial setup
