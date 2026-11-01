# Tool Surfacing in /mb-think

How to help users discover research tools without blocking them.

---

## Core Principles

1. **Never block** — Always have a fallback that works
2. **Surface value** — Explain what the tool provides, not just that it's missing
3. **Once per session** — Don't nag about the same tool repeatedly
4. **Intent-triggered** — Surface tools when user's task would benefit

---

## Tool Inventory

| Tool | Purpose | Importance | Detection | Setup Time | Cost |
|------|---------|------------|-----------|------------|------|
| **Apify** | YouTube transcripts, Instagram mining, web scraping | Critical | `mcp__apify__*` tools exist | 5 min | ~$0.005/video |
| **Gemini** | Deep research (Flash + Deep Research Agent) | Important | `$GOOGLE_API_KEY` exists | 3 min | Free tier / $2-5 |
| **Grok** | X/Twitter real-time sentiment | Enhancing | `$XAI_API_KEY` + `xai_sdk` package | 5 min | ~$0.02-0.30/query |
| **whisper** | Local video/audio transcription | Enabling | `mcp__whisper__*` OR `which mlx_whisper` OR `which whisper-cli` | 2 min | Free (local) |
| **Meta ad account context** | Live Meta account access once the official CLI path is wired | Enhancing | `mb connect doctor --json` reports ready, then `meta auth status` succeeds | Pending | Normal Meta ads spend |
| **markitdown** | PDF/DOCX/PPTX conversion | Convenience | `which markitdown` | 1 min | Free |
| **pandoc** | High-quality DOCX conversion | Convenience | `which pandoc` | 1 min | Free |
| **marker** | Complex/scanned PDF OCR | Convenience | `which marker_single` | 5 min | Free |
| **Nano Banana** | Image generation via Gemini | Adjacent | `$GOOGLE_API_KEY` + `google-genai` package | 2 min | Uses Gemini credits |

---

## Intent-to-Tool Mapping

See [research-routing-quick-ref.md](research-routing-quick-ref.md) for the intent, tool and fallback table.

---

## Surfacing Messages

### Apify Missing (YouTube)

> "YouTube transcript mining needs Apify MCP.
>
> 1. Set up now (5 min) — enables YouTube + Instagram mining
> 2. I'll show you how to copy the transcript manually
> 3. Skip this video"

### Apify Missing (Instagram)

> "Instagram mining needs Apify MCP.
>
> 1. Set up now (5 min) — also enables YouTube transcripts
> 2. Research via manual screenshots (more effort)
> 3. Skip Instagram research"

### Grok Missing (X/Twitter)

> "X/Twitter sentiment research gives you real-time data with actual post citations.
>
> 1. Use web search instead (works for most cases, not real-time)
> 2. Set up Grok (5 min, requires $5 credit purchase)
> 3. Skip X research"

### Gemini Missing (Deep Research)

> "Deep research synthesizes 80+ sources automatically with Gemini.
>
> 1. Set up Gemini (3 min, free tier available)
> 2. I'll run multiple web searches and synthesize manually
> 3. Keep it simple with basic web search"

### whisper Missing (Local Files)

> "Local transcription needs whisper (runs entirely on your machine).
>
> 1. Set up whisper (10 min via Homebrew)
> 2. Upload to a transcription service, paste the result
> 3. Skip this recording"

### Ad Account Missing

> "Pulling ad account data needs live Meta ad account context.
>
> 1. Run `mb connect plan`
> 2. Check Ads Manager manually and paste metrics
> 3. Skip account data, work from reference files only"

### markitdown Missing (Documents)

> "Document conversion is best with markitdown.
>
> 1. Install now: `pip install 'markitdown[all]'`
> 2. I'll try the Read tool (has size limits)
> 3. Skip this document"

---

## Session State Tracking

Track which tools have been offered setup this session:

```
Session state:
  tools_offered_setup: [grok, whisper]
```

**Rules:**
- If tool was offered once → don't re-offer
- Use fallback silently on subsequent requests
- Exception: if user explicitly asks to set up a tool, always help

---

## Post-Research Hints

After completing research with a fallback, optionally mention the upgrade:

> "Research complete using web search. For future reference: Grok gives real-time X sentiment with citations. Setup takes 5 min if you want it."

**Rules:**
- Only hint once per tool per session
- Don't hint if user explicitly declined setup
- Keep it brief (1-2 sentences)

---

## Fallback Quality Reference

| Missing Tool | Fallback | Quality Gap |
|--------------|----------|-------------|
| Apify (YouTube) | Manual transcript paste | Same data, more user effort |
| Apify (Instagram) | Manual screenshots | Much harder, partial data |
| Grok | WebSearch site:x.com | Not real-time, no structure |
| Gemini Deep | Multi-query WebSearch | Slower, less comprehensive |
| Gemini Flash | WebSearch | Good enough for quick queries |
| whisper | External transcription | Same quality, extra step |
| Meta ad account context | Manual Ads Manager + paste | Same data, much more user effort, no automation |
| markitdown | Read tool | Size limits, token cost |

---

## Setup Guide Locations

| Tool | Guide Path |
|------|------------|
| Apify | `.claude/skills/mb-organic/references/apify-setup.md` |
| Grok | `.claude/skills/mb-think/references/grok-setup.md` |
| Gemini | `.claude/skills/mb-think/references/gemini-setup.md` |
| whisper | `.claude/skills/mb-think/references/local-transcription.md` |
| Meta ad account context | Official Meta Ads CLI path through `mb connect meta`; use only after `mb` reports Meta as `ready`. See `.claude/skills/mb-ads/references/meta-ads-integration.md` |
| markitdown | `pip install 'markitdown[all]'` (no guide needed) |
| pandoc | `brew install pandoc` or OS package manager |
| marker | `pip install marker-pdf` (may need system deps) |

---

## Progressive Disclosure

1. **Session start** (via /mb-start): `beginner` "Research ready. I'll help with additional tools when you need them."; `intermediate` "Research: Apify ✓, Gemini ✓, Grok ✗ (web fallback available)"; `advanced` silent unless tools changed.
2. **Intent match:** surface the specific tool using the messages above.
3. **Post-research:** mention the upgrade once, after a fallback.
4. **Never** advertise tools the user never tried to use.

---

## Never Block Pattern

Research must always proceed. If all options fail:

> "I couldn't find a way to [do X]. Let's continue with what we have.
>
> 1. Provide the data manually
> 2. Skip this part of the research
> 3. Set up [tool] for next time"

---

## Example

Missing tool, first request: state the value, give the numbered options (set up / fallback / skip), proceed with the pick and note the limitation in the research file. Second request in the same session: use the fallback silently, no re-offer.

---

## See Also

- [research-routing-quick-ref.md](research-routing-quick-ref.md) — Research routing
- [grok-setup.md](grok-setup.md) — Grok setup guide
- [gemini-setup.md](gemini-setup.md) — Gemini setup guide
- [local-transcription.md](local-transcription.md) — whisper setup and usage
