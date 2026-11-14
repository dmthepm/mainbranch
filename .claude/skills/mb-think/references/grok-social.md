# X/Twitter Social Research

Real-time social intelligence from X/Twitter using xAI's Grok API.

## Contents

- [CRITICAL: API Limitations](#critical-api-limitations)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [Option 1: Python SDK](#option-1-python-sdk-recommended-for-x-search)
- [Option 2: Grok X Insights MCP](#option-2-grok-x-insights-mcp-community-wrapper)
- [Option 3: WebSearch Fallback](#option-3-websearch-fallback)
- [Workflow Patterns](#workflow-patterns)
- [Output Format](#output-format)
- [Cost & Token Management](#cost--token-management)
- [Combining with Other Research](#combining-with-other-research)
- [Fallback Strategy](#fallback-strategy)
- [Technical Details](#technical-details)

---

## CRITICAL: API Limitations

**X search works over REST (`/v1/responses` with the `x_search` tool) or the Python SDK.** The old `search: true` chat-completions Live Search is what no longer works. See [grok-setup.md](grok-setup.md) for the REST vs SDK explanation, dated 10 November 2026; Main Branch has not tested REST `x_search`. The SDK recipe below is the tested route.

**DEPRECATED (Feb 2026):** The `SearchParameters` / `x_source()` API (aka "Live Search") has been removed server-side. Using `search_parameters=SearchParameters(sources=[x_source()])` returns `UNIMPLEMENTED: "Live search is deprecated"`. Use the Agent Tools API (`tools=[x_search()]`) instead — see code below.

---

## When to Use

**Trigger phrases:**
- "what are people saying about..."
- "sentiment on X about..."
- "what's trending in..."
- "social proof for..."
- "X/Twitter research on..."
- "real-time opinions about..."

**Best for:**
- Understanding current sentiment around a topic
- Finding social proof and real opinions
- Researching what your audience actually talks about
- Trend discovery in your niche
- Competitive intelligence (what are people saying about competitors?)

**Not for:**
- Historical research (use Gemini/web search)
- Deep technical research (use Gemini)
- Content that lives in articles/blogs (use web search)
- Private DMs, account analytics, protected accounts, or account-private data
- Posting, replying, liking, following, DMing, or other X account mutation
- Guaranteed full reply-tree/comment scraping for a specific post; use optional
  public X mining only as a read-only sample path when that is the actual
  question and the operator accepts the source, terms, cost, and reliability
  tradeoffs

---

## Quick Start

**Three approaches, in order of preference:**

1. **Python SDK** (full X search) → Requires `xai_sdk` package
2. **Grok X Insights MCP** (community wrapper) → See [grok-setup.md](grok-setup.md)
3. **Fallback: WebSearch** → `site:x.com [query]` (less structured)

---

## Option 1: Python SDK (Recommended for X Search)

The official xAI Python SDK uses gRPC and supports X search tools that execute server-side.

### Setup

```bash
pip install xai-sdk
```

Store the key with `mb connect` and run scripts through `mb connect exec`; see
[grok-setup.md](grok-setup.md).

### How X Search Works

X search is **tool-based**. You don't call search directly — you give the model access to search tools and it decides when to use them:

```python
from xai_sdk import Client
from xai_sdk.tools import x_search
from xai_sdk.chat import user

client = Client()

chat = client.chat.create(
    model="grok-4",  # tested January 2026; xAI docs now show grok-4.7 (untested here)
    tools=[x_search()],
)

chat.append(user("What are people saying about AI coding assistants on X?"))

response = chat.sample()
print(response.content)
```

### Available Sub-Tools

When you pass `x_search()`, the model gets access to:

| Sub-Tool | Purpose |
|----------|---------|
| `x_user_search` | Find X user accounts |
| `x_keyword_search` | Keyword-based post search |
| `x_semantic_search` | Semantic/contextual search |
| `x_thread_fetch` | Fetch full thread from a post |

### x_search() Parameters

You CAN control these directly when creating the tool:

```python
import datetime
from xai_sdk.tools import x_search

tool = x_search(
    from_date=datetime.datetime(2026, 2, 1),      # Optional: start date
    to_date=datetime.datetime(2026, 2, 15),        # Optional: end date
    allowed_x_handles=["xai", "elonmusk"],         # Optional: limit to these handles
    excluded_x_handles=["spambot"],                # Optional: exclude these handles
    enable_image_understanding=True,                # Optional: analyze images in posts
    enable_video_understanding=True,                # Optional: analyze videos in posts
)
```

**Note:** `allowed_x_handles` and `excluded_x_handles` are mutually exclusive. The model still autonomously decides WHEN to search — you control the scope/filters.

### Example with Streaming

```python
from xai_sdk import Client
from xai_sdk.tools import x_search
from xai_sdk.chat import user

def research_topic(topic: str):
    client = Client()

    chat = client.chat.create(
        model="grok-4",
        tools=[x_search()],
    )

    prompt = f"""Research what people on X are saying about: {topic}

    Provide:
    1. Overall sentiment (positive/negative/mixed)
    2. Key themes (3-5 bullet points)
    3. Notable quotes from actual posts
    4. Any controversies or debates"""

    chat.append(user(prompt))

    result = []
    for response, chunk in chat.stream():
        if chunk.content:
            result.append(chunk.content)
            print(chunk.content, end="", flush=True)

    return "".join(result)

research_topic("Skool communities")
```

### Subagent Prompt Recipe

When spawning a Claude Code subagent for Grok X research, include this exact recipe in the prompt. Subagents cannot reverse-engineer the SDK — they need the code:

```
GROK X SEARCH RECIPE — use this exact pattern, do not try alternatives:

from xai_sdk import Client
from xai_sdk.tools import x_search
from xai_sdk.chat import user

client = Client()
chat = client.chat.create(model="grok-4", tools=[x_search()])
chat.append(user("YOUR QUERY HERE"))
response = chat.sample()

response.content has the full X search results with citations

DO NOT use SearchParameters, x_source(), or the xai_sdk.search module — deprecated.
DO NOT try the REST API — it does not support X search.
DO NOT try to reverse-engineer the SDK — use exactly this pattern.
```

**Why this matters:** The SDK contains two search APIs. The deprecated one (`SearchParameters`/`x_source()`) is more discoverable via introspection. Without this recipe, agents burn all turns trying the wrong API.

---

## Option 2: Grok X Insights MCP (Community Wrapper)

A third-party MCP server that wraps Grok API. May or may not support live X search depending on implementation.

See [grok-setup.md](grok-setup.md) for setup.

### Tools (if MCP available)

| Tool | Purpose |
|------|---------|
| `grok_search_posts` | Search and analyze X posts |
| `grok_analyze_topic` | Deep analysis with aspects |
| `grok_get_trends` | Trending topics |
| `grok_chat` | General chat |

**Warning:** Test if your MCP implementation actually returns X data. Check for `num_sources_used > 0` in responses.

---

## Option 3: WebSearch Fallback

When Python SDK isn't available, use WebSearch with site restriction:

```
WebSearch: "AI coding assistants site:x.com"
```

**Limitations:**
- Not real-time (indexed pages only)
- No sentiment analysis
- No structured data
- Can't see replies/threads easily

Still useful for finding popular/viral posts that have been indexed.

For specific public X post/profile teardown, use optional public X mining only
as read-only sidecar research when configured and when the operator accepts the
source, terms, cost, and reliability tradeoffs. Then synthesize the post
mechanic and comment quality. Grok is the better path for topic-level "what are
people saying now?" research; optional public X mining is the better path for
bounded public profile/post/reply samples.

---

## Workflow Patterns

### Pattern 1: Sentiment Check (Python SDK)

User: "What are people saying about Skool?"

```python
prompt = """Search X for recent posts about Skool communities.
Analyze:
1. Overall sentiment (positive/negative/mixed)
2. Common themes in what people say
3. Include actual quotes from posts
4. Any common complaints or praises"""

# Save to: research/YYYY-MM-DD-skool-sentiment-x-social.md
```

### Pattern 2: Competitive Intelligence

User: "What do people say about [competitor] vs us?"

```python
prompt = """Research X posts comparing [our brand] vs [competitor].
Look for:
1. What people love about each
2. Common complaints about each
3. Feature comparisons people mention
4. Price/value discussions"""

# Save to: research/YYYY-MM-DD-competitive-x-social.md
```

### Pattern 3: Social Proof Mining

User: "Find social proof about [topic] for my messaging"

```python
prompt = """Find posts where people describe their experience with [topic].
I need:
1. Actual quotes I can use (with attribution)
2. The language/words real people use
3. Before/after stories
4. Common objections mentioned"""

# Save quotes and patterns to research/
# Consider codifying strong angles to core/proof/angles/
```

### Pattern 4: Fallback (WebSearch)

When Python SDK unavailable:

```
1. WebSearch: "[topic] site:x.com"
2. WebFetch on promising URLs
3. Manual synthesis of findings
4. Note: "Source: WebSearch (not real-time)"
5. Save to: research/YYYY-MM-DD-topic-web.md
```

---

## Output Format

Save X/Twitter research to: `research/YYYY-MM-DD-[topic]-x-social.md`

**Template:**

```markdown
---
type: research
date: YYYY-MM-DD
source: grok-x-social
status: complete
topics: [topic1, topic2]
linked_decisions: []
---

# [Topic] — X/Twitter Social Research

## One-Sentence Summary
[20 words max — what did you learn?]

## Query Details
- **Search:** [query used]
- **Time window:** [timeframe]
- **Posts analyzed:** [count]

## Sentiment Overview
- **Overall:** [positive/negative/neutral/mixed]
- **Distribution:** [breakdown]

## Key Themes
1. [Theme 1]
2. [Theme 2]
...

## Notable Quotes
> "[Actual quote from X post]"
> — [@handle](link)

> "[Another quote]"
> — [@handle](link)

## Implications for Reference Files
- [Which files should be updated based on this?]

## Open Questions
- [What follow-up research is needed?]

## Citations
- [Links to source posts]
```

---

## Cost & Token Management

**xAI API Pricing (as of 2026):**

| Model | Input | Output | X Search |
|-------|-------|--------|----------|
| grok-4 (January 2026 figures) | ~$3/M tokens | ~$15/M tokens | YES |
| grok-3 (January 2026 figures) | ~$3/M tokens | ~$15/M tokens | NO (server-side tools removed) |
| grok-3-fast (January 2026 figures) | ~$1/M tokens | ~$5/M tokens | NO |

xAI's docs (10 November 2026) list `grok-4.7` in current X Search examples and add $5 per 1,000 posts fetched and $10 per 1,000 profiles fetched on top of tokens. Check xAI's pricing page for current token rates.

**Old token-only estimates per X search query (January 2026; they leave out the per-post and per-profile charges above):**

| Operation | Approx Tokens | Approx Cost |
|-----------|---------------|-------------|
| Simple sentiment search | ~5-10K total | ~$0.02-0.10 |
| Deep topic analysis | ~15-20K total | ~$0.10-0.30 |
| Multi-turn conversation | ~30K+ total | ~$0.30+ |

**Cost management tips:**

1. **Be specific:** "Skool pricing complaints" vs just "Skool"
2. **Limit scope:** "last 7 days" vs "all time"
3. **Single turn:** Get what you need in one prompt
4. **Use a model xAI's X Search docs show** (`grok-4.7` on 10 November 2026; not tested by Main Branch). The old "grok-4 is the only model" claim is withdrawn.

---

## Combining with Other Research

**Grok + Gemini workflow:**

1. **Grok first:** What are people saying RIGHT NOW?
2. **Gemini second:** Deep research on the patterns you found
3. **Synthesize:** Combine real-time sentiment with structured research

**Example:**
> "Research email list transition strategies"
> 1. Grok: "What are people saying about email list rebrands?" (real sentiment)
> 2. Gemini: "Best practices for email list transitions" (structured research)
> 3. Combine into comprehensive research file

---

## Fallback Strategy

**When Python SDK isn't available:**

| Approach | Quality | Effort |
|----------|---------|--------|
| WebSearch `site:x.com` | Medium | Low |
| Manual X search + paste | High | High |
| Skip X research | N/A | None |

**WebSearch fallback example:**
```
WebSearch: "Skool community reviews site:x.com"
WebSearch: "Skool vs Circle site:x.com"
```

**Don't block research** just because live X search isn't available — adapt and continue.

---

## Technical Details

### Why Legacy `search: true` Doesn't Work for X Search

This section covers the removed Live Search parameter on chat completions only. REST with the `/v1/responses` `x_search` tool is the current route (see grok-setup.md).

The xAI REST API at `api.x.ai/v1/chat/completions` accepts a `search` parameter, but testing shows:

```json
// Request
{
  "model": "grok-3",
  "search": true,
  "messages": [{"role": "user", "content": "What are people saying about X?"}]
}

// Response shows
{
  "num_sources_used": 0,  // <-- No X data fetched
  ...
}
```

The model responds with general knowledge, not live X data.

### Why Python SDK Works

The Python SDK (`xai_sdk`) uses:
- **gRPC** (not REST) for communication
- **Server-side tool execution** — model calls search tools that run on xAI's infrastructure
- **Tool injection** — you pass `x_search()` and model autonomously decides when to search

This is fundamentally different from REST API — the search executes server-side where xAI has X data access.

### SDK Resources

- **Docs:** https://docs.x.ai/docs/guides/tools/search-tools
- **SDK Repo:** https://github.com/xai-org/xai-sdk-python
- **Install:** `pip install xai-sdk`
