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

| User Intent | Trigger Phrases | Primary Tool | Fallback |
|-------------|-----------------|--------------|----------|
| YouTube research | YouTube URL, "transcribe video", "what does [creator] say" | Apify | Manual transcript paste |
| X/Twitter sentiment | "what are people saying", "sentiment on X", "Twitter discourse" | Grok | WebSearch site:x.com |
| Deep web research | "deep research", "comprehensive analysis", "research everything" | Gemini | Multi-source WebSearch |
| Local transcription | Local file path (.mp4, .m4a), "transcribe my recording" | whisper | External service + paste |
| Instagram mining | Instagram handle, "mine [handle]", "competitor posts" | Apify | Manual screenshots |
| Ad account research | "ad performance", "what's working", "CPA", "ROAS", "check my ads" | Verified Meta ad account context | Manual Ads Manager + paste |
| Document conversion | PDF/DOCX path, "ingest this document", "convert this" | markitdown | Read tool (limited) |
| General research | Default, "research [topic]", "what do we know" | WebSearch + codebase | Always available |

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

## Progressive Disclosure Levels

### Level 1: Session Start (via /mb-start)

Brief mention based on experience:

| Experience | Message |
|------------|---------|
| `beginner` | "Research ready. I'll help with additional tools when you need them." |
| `intermediate` | "Research: Apify ✓, Gemini ✓, Grok ✗ (web fallback available)" |
| `advanced` | No message unless tools changed since last session |

### Level 2: Intent Match (during /mb-think)

Surface specific tool when user's task would benefit. See surfacing messages above.

### Level 3: Post-Research Hint

After using a fallback, briefly mention what the tool would provide. Once per session.

### Level 4: Never Surface

Don't mention tools user never tried to use. No unsolicited tool advertisements.

---

## Never Block Pattern

Research must always proceed. If all options fail:

> "I couldn't find a way to [do X]. Let's continue with what we have.
>
> 1. Provide the data manually
> 2. Skip this part of the research
> 3. Set up [tool] for next time"

---

## Example Flows

### User wants YouTube research, Apify missing

```
User: "Research what Alex Hormozi says about pricing"

Claude: "I'd transcribe some Hormozi videos, but YouTube mining needs Apify MCP.

Options:
1. Set up Apify (5 min, one-time)
2. Share a video URL and I'll guide you to copy the transcript manually
3. Research pricing without YouTube"

User: "2"

Claude: "Got it. Share the YouTube URL and I'll tell you how to copy the transcript."
```

### User wants X research, Grok missing (first time)

```
User: "What are people saying about Skool on X?"

Claude: "X sentiment research works best with Grok — you get real-time data with actual post citations.

Options:
1. Use web search instead (good for most cases)
2. Set up Grok (5 min, requires $5 credit)
3. Skip X research"

User: "1"

Claude: [proceeds with web search, notes limitation in research file]
```

### User wants X research, Grok missing (second time same session)

```
User: "Now check what people say about memberships on X"

Claude: "Searching X via web..."
[proceeds with fallback silently, no re-offer]
```

---

## See Also

- [research-routing-quick-ref.md](research-routing-quick-ref.md) — Research routing
- [grok-setup.md](grok-setup.md) — Grok setup guide
- [gemini-setup.md](gemini-setup.md) — Gemini setup guide
- [local-transcription.md](local-transcription.md) — whisper setup and usage
