# Research Architecture for /mb-think Skill

**Purpose:** Define how /mb-think routes research tasks to appropriate tools based on user intent and available capabilities.

---

## Design Philosophy

**Progressive enhancement, not hard requirements.**

- /mb-think works with ZERO external tools (codebase-only research)
- Adding API keys unlocks new capabilities
- Skills auto-detect what's available and route accordingly
- Users never blocked — always graceful fallback
- Apify is MCP-first research-provider enrichment for now, not automatically an
  `mb connect` provider.

---

## Available Research Tools

### Core (Always Available)

| Tool | What | Use For |
|------|------|---------|
| **Codebase search** | Grep, Read | Existing reference/research/decisions |
| **Web search** | WebSearch | General queries, articles, documentation |
| **Web fetch** | WebFetch | Specific URLs, competitor sites |
| **User input** | Direct paste | Voice memos, DMs, emails, screenshots |

### Enhanced (MCP-Based)

| Tool | MCP | What | Use For |
|------|-----|------|---------|
| **YouTube transcripts** | Apify | Extract video transcripts | Mining expert content, competitors, frameworks |
| **Instagram mining** | Apify | Scrape posts, stories, profiles | Competitor content, audience research |
| **X/Twitter sentiment** | xAI Grok | Real-time social search | Sentiment, trends, social proof |
| **Deep research (Tier 1)** | Gemini Flash API | Quick queries, fact-checking | Standard research |
| **Deep research (Tier 2)** | Gemini Interactions API | Multi-step agentic synthesis | Complex research requiring multi-source synthesis |
| **Local transcription** | whisper-mcp | Transcribe audio/video files | User's own recordings, voice memos |

---

## Detection Logic

### 1. Check Available Tools (Once per Session)

On first `/mb-think` invocation or when routing to research:

```bash
# Check for MCP tools
# Store results in session memory to avoid re-checking

APIFY_AVAILABLE=false
GROK_AVAILABLE=false  # Note: Requires Python SDK, not just API key
GEMINI_AVAILABLE=false
WHISPER_AVAILABLE=false

# Detection via tool presence
if mcp__apify__* tools exist → APIFY_AVAILABLE=true
if xai_sdk Python package installed AND XAI_API_KEY exists → GROK_AVAILABLE=true
  # Important: REST API alone is NOT sufficient for X search
  # Must have xai_sdk package for gRPC-based X search tools
if GOOGLE_API_KEY env exists → GEMINI_AVAILABLE=true
if mcp__whisper__* tools exist → WHISPER_AVAILABLE=true
```

**Store in session context:**
```
Available research capabilities:
✓ Codebase search
✓ Web search
✓ YouTube transcripts (Apify)
✓ X/Twitter sentiment (Grok)
✗ Deep research (Gemini not configured)
✓ Local transcription (whisper-mcp)
```

### 2. Route by Intent

Parse user's natural language to determine research type:

| User Says | Intent | Preferred Tool | Fallback |
|-----------|--------|----------------|----------|
| "transcribe this video", "pull down this YouTube" | YouTube mining | Apify YouTube Actor | Ask for manual transcript |
| "what are people saying about...", "sentiment on X" | Social sentiment | Grok X search | Web search for X posts |
| "research [complex topic]", "deep dive on..." | Deep research | Gemini 2.5 | Web search + synthesis |
| "transcribe this file", user shares .mp4/.m4a | Local transcription | whisper-mcp | ffmpeg + CLI fallback |
| "mine competitors", "what's [handle] posting" | Social mining | Apify Instagram Actor | Manual scraping guidance |
| "keyword gate", "kill or build this offer", "search demand" | Keyword gate | Search/SERP sidecar or planner CSV | Web search + operator exports |
| "research [specific question]" | General research | Codebase → Web → Ask user | Always works |

### Format Selection

The routing table chooses source tools. Output format is a separate decision.
When the operator says "researched brief", "site brief", "launch brief", or
passes `--brief-format=grok-8`, gather with the appropriate source route above,
then write the synthesis using
[grok-8-brief-format.md](grok-8-brief-format.md). If the broad format is not
needed, use the standard research template.

### 3. Progressive Disclosure

Research tools are surfaced based on user need, not dumped upfront.

**Disclosure Levels:**

| Level | When | What |
|-------|------|------|
| 1. Session start | /mb-start greeting | Brief status (experience-appropriate) |
| 2. Intent match | User task benefits from tool | Surface specific tool + options |
| 3. Post-research | After using fallback | Mention upgrade path briefly |
| 4. Never | User never tried to use | Don't advertise unsolicited |

**Example Progression:**

```
Session start: "Research ready. Tools: Apify ✓, Gemini ✓"

User: "What are people saying on X about [topic]?"
Surface: "X sentiment is best with Grok. Use web search? Or set up?"
User: "Web search is fine"
Proceed: [does web search]
Post: "Done. FYI: Grok gives real-time sentiment if you want it later."

User: "Now research [different topic] on X"
Proceed: [uses web search without asking, already offered once]
```

**Session state:** Track `tools_offered_setup: [grok, whisper]` — don't re-offer tools already declined.

See [tool-surfacing.md](tool-surfacing.md) for full details on surfacing messages and patterns.

### 4. Fallback Patterns

**Never block research.** If preferred tool unavailable:

```
Preferred tool missing → Inform user + offer fallback
User accepts fallback → Proceed with alternative
User declines → Offer setup guide (one-time)
```

**Example:**
```
User: "What are people saying about Skool on X?"

If GROK_AVAILABLE:
  → Use grok_search_posts

If !GROK_AVAILABLE:
  → "X/Twitter sentiment research works best with Grok MCP (one-time 5-min setup).

     1. Set up Grok now (I'll guide you)
     2. Use web search instead (less real-time)
     3. Skip this research"
```

---

## Intent Detection Patterns

### YouTube Mining

**Triggers:**
- YouTube URL in message
- "transcribe this video"
- "pull down this YouTube"
- "what does [creator] say about..."
- "research this video"

**Routing:**
```
If APIFY_AVAILABLE:
  → Use starvibe/youtube-video-transcript
  → Fetch with fields: "title,channel_name,transcript_text"
  → Synthesize immediately (don't dump raw)
  → Save to: research/YYYY-MM-DD-topic-yt-mining.md

If !APIFY_AVAILABLE:
  → "YouTube transcript mining needs Apify MCP. Set up now or paste transcript manually?"
```

**Cost estimate:** ~$0.005 per video (negligible)

### X/Twitter Social Research

**Triggers:**
- "what are people saying about..."
- "sentiment on X"
- "Twitter discourse about..."
- "social proof for..."
- "trending in [niche]"

**Critical:** The xAI REST API does NOT support X search (the `search` parameter is ignored, returns `num_sources_used: 0`). Live X search requires the Python SDK (`xai_sdk`) which uses gRPC and server-side tool execution. See `grok-social.md` for full details.

**Also deprecated (Feb 2026):** The SDK's `SearchParameters`/`x_source()` approach returns `UNIMPLEMENTED`. Only `tools=[x_search()]` works. When spawning subagents for X research, include the exact code recipe — see [grok-social.md](grok-social.md) subagent recipe section.

**Routing:**
```
If GROK_AVAILABLE (Python SDK with xai_sdk):
  → Use x_search() tool with grok-4 model
  → Model autonomously calls x_keyword_search, x_semantic_search, etc.
  → Save to: research/YYYY-MM-DD-topic-x-social.md

If !GROK_AVAILABLE:
  → Use WebSearch with "site:x.com [query]"
  → Note: Less structured, no sentiment analysis, not real-time
  → Save to: research/YYYY-MM-DD-topic-web.md
```

**Cost estimate:** ~$0.02-0.30 per search (varies by complexity)

### Deep Research

**Triggers:**
- "deep dive on..."
- "comprehensive research about..."
- "research everything about..."
- Complex multi-faceted questions
- Topic requiring synthesis across many sources

**Two Tiers (see gemini-deep-research.md for full details):**

| Tier | When | Tool | Time | Cost |
|------|------|------|------|------|
| **Tier 1** | Quick questions, fact-checking | Gemini Flash API | 30-60s | ~$0.01-0.05 |
| **Tier 2** | Complex multi-source synthesis | Gemini Interactions API | 5-20min | ~$2-5 |

**Routing:**
```
If GEMINI_AVAILABLE:
  If simple question:
    → Tier 1: Gemini Flash via generate_content
    → Save to: research/YYYY-MM-DD-topic-flash.md

  If complex synthesis needed:
    → Tier 2: Deep Research Agent via Interactions API
    → Agent: deep-research-pro-preview-12-2025
    → Note: Takes 5-20 minutes, runs asynchronously
    → Save to: research/YYYY-MM-DD-topic-gemini-deep.md

If !GEMINI_AVAILABLE:
  → Use WebSearch + manual synthesis
  → Multiple queries → synthesize findings
  → Save to: research/YYYY-MM-DD-topic-claude-code.md
```

**Important:** Tier 1 (Flash) handles 80% of research needs. Reserve Tier 2 for competitive analysis, industry research, and complex multi-source questions.

**Status:** Both Tier 1 and Tier 2 TESTED and working (verified 2026-01-26).

**Tier 2 REST API Example:**
```bash
# Start research (returns interaction ID)
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Your research question", "agent": "deep-research-pro-preview-12-2025", "background": true, "store": true}'

# Poll for completion
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions/{id}" \
  -H "x-goog-api-key: $GOOGLE_API_KEY"
```

**Known issues:** Occasional internal server errors during long-running research. If poll returns 500 after ~10min, start a new request.

### Local Transcription

**Triggers:**
- User shares local file path (.mp4, .mov, .m4a, .wav)
- "transcribe this recording"
- "process this voice memo"
- "transcribe my Loom"

**Routing:**
```
If WHISPER_AVAILABLE:
  → Use whisper-mcp transcribe_audio tool
  → Save to: research/YYYY-MM-DD-topic-local-mining.md

If !WHISPER_AVAILABLE:
  → Check for ffmpeg + whisper CLI
  → If available: Use CLI workflow (see local-transcription.md)
  → If not: "Local transcription needs whisper-mcp or CLI tools. Set up now?"
```

### Instagram Mining

**Triggers:**
- Instagram handle provided
- "mine [handle]"
- "what's [handle] posting"
- "research competitors on Instagram"

**Routing:**
```
If APIFY_AVAILABLE:
  → Use apify/instagram-profile-scraper
  → Limit posts (estimate tokens: 10 posts ≈ 3-5k tokens)
  → Ask: "Quick scan (5 posts) or deep mine (20 posts)?"
  → Save to: research/YYYY-MM-DD-topic-ig-mining.md

If !APIFY_AVAILABLE:
  → "Instagram mining needs Apify. Set up now or manual research?"
```

**Token management:** Warn if requesting >20 posts per competitor

### Codebase Research

**Triggers:**
- "what do we know about..."
- "check existing research on..."
- "have we decided..."
- Questions about internal state

**Routing:**
```
Always available (no external dependencies)

1. Search research/ for topic
2. Search decisions/ for related choices
3. Search core/ for current evergreen business state
4. Synthesize findings
5. Save to: research/YYYY-MM-DD-topic-claude-code.md
```

---

## File Naming Conventions

### Research Output Files

Format: `research/YYYY-MM-DD-topic-[source].md`

| Suffix | Source | When Used |
|--------|--------|-----------|
| `-yt-mining.md` | YouTube via Apify | Transcribed YouTube videos |
| `-x-social.md` | X/Twitter via Grok | Social sentiment research |
| `-flash.md` | Gemini Flash (Tier 1) | Quick research, fact-checking |
| `-gemini-deep.md` | Gemini Deep Research (Tier 2) | Complex multi-step research |
| `-ig-mining.md` | Instagram via Apify | Instagram content mining |
| `-local-mining.md` | Local files via whisper | User's own video/audio |
| `-voice-mining.md` | Voice memos via whisper | User's voice recordings |
| `-claude-code.md` | This Claude Code session | General research using available tools |
| `-web.md` | Web search fallback | When MCP unavailable |
| (no suffix) | Mixed or manual sources | User provided data |

**Why source suffixes:**
- Provenance tracking (know where data came from)
- Reproducibility (can re-run with same tool)
- Cost attribution (know which tools used)
- Skill routing (some skills prefer certain sources)

---

## Token Management

> **Note:** Token estimates throughout this document are approximate and may vary based on model updates and actual content. Adjust based on your usage patterns.

### Problem

Research tools return data that becomes Claude tokens. Large outputs can:
- Exceed MAX_MCP_OUTPUT_TOKENS (default 25k)
- Burn context unnecessarily
- Slow down sessions

### Solutions

#### 1. Limit at Source

| Tool | How to Limit |
|------|--------------|
| YouTube (Apify) | Use `fields` parameter: only get `transcript_text`, `title` |
| Instagram (Apify) | Limit `resultsLimit` parameter (e.g., 10 posts not 50) |
| Grok X search | Set `limit` to 20-30 posts, not default 50 |
| Gemini | Structure prompt to request concise findings |

#### 2. Estimate Before Running

Show user token estimate:

```
"Mining 20 posts from 3 competitors will be ~15-20k tokens (about 10% of our context window).

Alternatives:
- Quick scan: 5 posts each = ~5k tokens
- Deep mine: 30 posts each = ~30k tokens (will need synthesis pass)"
```

#### 3. Synthesize Immediately

**Never dump raw output into research files.**

```
Raw transcript → Extract key points → Save synthesis
Not: Raw transcript → Save everything → Try to work with it later
```

#### 4. Progressive Depth

Offer quick scan first:

```
"Let's start with a quick scan (5 posts, ~3k tokens). If you want deeper, we can mine more."
```

---

## Setup Guides

### When to Offer Setup

```
Tool missing + User wants that research type → Offer setup once per session

"This research works best with [Tool]. Not set up on this machine.

1. Set up now (5-10 min, one-time)
2. Use [Fallback] instead
3. Skip this research"
```

### Setup Guide Locations

| Tool | Guide Path |
|------|------------|
| Apify | `.claude/skills/mb-organic/references/apify-setup.md` |
| Grok | `.claude/skills/mb-think/references/grok-setup.md` |
| Gemini | `.claude/skills/mb-think/references/gemini-setup.md` |
| whisper-mcp | `.claude/skills/mb-think/references/local-transcription.md` |

---

## Research Workflow Architecture

### Standard Flow (All Research Types)

```
1. Define Question
   └─> What specifically are you trying to learn?

2. Recommend Depth
   ├─> For offer/audience/proof/CTA/content/ads/pages/positioning
   └─> Use research-depth-ladder.md to decide how much research is enough

3. Detect Intent & Route
   └─> Determine research type from user message

4. Check Capabilities
   ├─> If available: Use preferred tool
   └─> If not: Offer setup or fallback

5. Execute
   ├─> Gather data (with token limits)
   └─> Estimate cost/tokens before running

6. Synthesize (REQUIRED)
   ├─> One-sentence summary (20 words max)
   ├─> Key findings (5-10 bullets)
   └─> Implications for reference files

7. Save
   └─> research/YYYY-MM-DD-topic-[source].md

8. Checkpoint
   └─> "Ready to make a decision, or need more research?"
```

### Multi-Source Research

For complex questions requiring multiple tools:

```
1. Define question clearly
2. Identify needed sources (e.g., social + web + codebase)
3. Spawn parallel research subagents
4. Each subagent → separate research file
5. Create synthesis research file combining all
6. Save individual files + combined synthesis
```

**Example:**
```
Question: "Should we add a guarantee? What type?"

Sources:
- Codebase: Check if we've researched this before
- X/Twitter: What are people saying about guarantees in our niche?
- Competitors: What guarantees do they offer? (Instagram/web)
- Deep research: Guarantee psychology and best practices (Gemini or web)

Output:
- research/2026-01-26-guarantee-x-social.md
- research/2026-01-26-guarantee-competitors.md
- research/2026-01-26-guarantee-psychology-gemini-deep.md
- research/2026-01-26-guarantee-synthesis.md (combines all)
```

---

## Capability Matrix

What each research type can do:

| Research Type | Best For | Requires | Fallback | Cost |
|---------------|----------|----------|----------|------|
| **Codebase** | Internal state | Nothing | N/A | Free |
| **Web search** | General queries | Nothing | N/A | Free |
| **Web fetch** | Specific URLs | Nothing | N/A | Free |
| **YouTube mining** | Video content | Apify MCP | Manual transcript | ~$0.005/video |
| **X sentiment** | Real-time social | xai_sdk Python package (gRPC) | Web search X posts | ~$0.02-0.30/query |
| **Deep research (Tier 1)** | Quick queries | Gemini Flash API | Web + synthesis | ~$0.01-0.05/query |
| **Deep research (Tier 2)** | Complex synthesis | Gemini Interactions API | Tier 1 or manual | ~$2-5/task |
| **Instagram mining** | Visual platform research | Apify MCP | Manual screenshots | ~$0.40-0.50/1K results |
| **Local transcription** | User's own files | whisper-mcp | CLI fallback | Free (local) |

---

## Session Memory Pattern

Don't re-check capabilities every time. Store in session:

```
On first /mb-think:
  Check all capabilities → Store results

On subsequent /mb-think:
  Read stored capabilities → Route immediately

On new session:
  Re-check (capabilities may have changed)
```

---

## Implementation Notes

### Routing Decision Tree

```python
def route_research(user_message, available_tools):
    """Route research request to appropriate tool."""

    # Check for explicit URLs/files first
    if contains_youtube_url(user_message):
        return route_youtube(available_tools)

    if contains_local_file(user_message):
        return route_local_transcription(available_tools)

    # Check for social research triggers
    if contains_social_trigger(user_message):
        if "x" in message or "twitter" in message:
            return route_x_social(available_tools)
        if "instagram" in message or contains_ig_handle(message):
            return route_instagram(available_tools)

    # Check for complexity
    if is_complex_research(user_message):
        return route_deep_research(available_tools)

    # Default: general research (always works)
    return route_general_research()
```

### Tool Priority

When multiple tools could work:

1. **Most specific** tool for the job (e.g., YouTube actor for YouTube URLs)
2. **Highest fidelity** when tie (e.g., Grok > web search for X sentiment)
3. **Lowest friction** when equivalent (e.g., codebase before web if answer might be there)

---

## Error Handling

### MCP Tool Failures

```
Tool exists but fails → Don't retry with same tool
  ├─> Check for known issues (no credits, rate limit)
  ├─> Explain to user what went wrong
  └─> Offer fallback or skip

Never: Keep retrying same tool hoping for different result
```

### Partial Results

```
Tool returns partial results → Accept and synthesize what we got
  ├─> Note limitation in research file
  └─> Document what's missing in "Open Questions"
```

### No Results

```
Tool returns zero results → Inform user, ask to refine query
  ├─> Suggest more specific query
  └─> Offer alternative source
```

---

## Content Mining: What AI Can and Cannot Do

> "AI can show WHAT worked. Human must judge WHY." — Koston Williams

When mining competitor content (YouTube, Instagram, TikTok), understand the division of labor:

### AI CAN:
- **Collect** — Scrape posts, pull transcripts, gather metrics
- **Identify** — Surface patterns, hooks, formats, engagement rates
- **Display** — Show you the data in structured form

### AI CANNOT:
- **Explain** — Tell you WHY something actually worked
- **Judge** — Know if a framework transfers to YOUR niche
- **Feel** — Sense the emotional resonance that makes content connect
- **Decide** — Choose which frameworks fit YOUR energy and personality

### YOUR JOB (Framework Transfer):

Extract three dimensions from mined content:

| Dimension | What AI Shows You | What YOU Determine |
|-----------|-------------------|-------------------|
| **Visual** | Format, production style, patterns | Does this fit MY setup/skills? |
| **Audible** | Energy, pacing, delivery | Can I match this energy authentically? |
| **Emotional** | Primary emotion triggered | Does this align with MY audience's identity? |

**The skill is framework transfer.** A competitor's content worked for THEM — their audience, their personality, their offer. Your job is to see the framework beneath the content, judge whether it transfers to your context, and adapt it to your voice.

### The Path (Do Not Skip Steps)

```
Mining → Framework Extraction (human) → Reference Update → THEN Content Generation
```

Don't go straight from mining to scripts. Extract what you learned, codify it into reference files, then generate from enriched reference. This is why the goal of all research is reference files.

---

## Quality Gates

Before marking research as complete:

- [ ] Synthesis section exists
- [ ] One-sentence summary under 20 words
- [ ] 5-10 key findings, each under 15 words
- [ ] Implications for reference files documented
- [ ] Source attributed correctly (suffix + citations)
- [ ] Token usage reasonable (< 25k for output)
- [ ] File saved to correct location with correct naming

---

## Future Enhancements

Potential additions (not implemented yet):

- **Reddit sentiment** — Similar to X/Twitter research
- **LinkedIn research** — Professional sentiment, thought leadership
- **Email mining** — Extract insights from user's own emails (privacy-sensitive)
- **Podcast transcription** — Similar to YouTube but audio-only RSS feeds
- **PDF research** — Extract from research papers, ebooks
- **Competitor ad mining** — Facebook Ad Library scraping via Apify

**How to add new research types:**

1. Add detection pattern to intent routing
2. Create tool-specific guide in `references/`
3. Add fallback pattern
4. Update this architecture doc
5. Add suffix to file naming conventions

---

## See Also

- `tool-surfacing.md` — Progressive disclosure and surfacing patterns
- `research-phase.md` — Detailed research workflow
- `gemini-setup.md` — Gemini API setup guide
- `gemini-deep-research.md` — Deep research workflow with Gemini
- `grok-setup.md` — Grok MCP setup guide
- `grok-social.md` — X/Twitter research specifics
- `local-transcription.md` — Local audio/video workflow
- `research-template.md` — File template for research output
