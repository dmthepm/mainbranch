# Grok/xAI Setup Guide

Setup guide for real-time X/Twitter data using xAI's Grok API.

---

## Auto-Detection

Start with `mb status --json --peek` and `mb connect doctor --json` for
provider readiness. Treat any old `.vip/config.yaml` tool status as a legacy
snapshot, not current truth.

### Claude Code Env Var Caveat

Claude Code sessions may not inherit env vars from your shell profile (`~/.zshrc`, `~/.bashrc`). Do not rely on one. Store the key with `mb connect` (step 3) and run Grok commands through `mb connect exec`, which gives the key to that one command.

See `mb-start/references/config-system.md` for legacy config cleanup guidance.

---

## CRITICAL: REST API vs Python SDK

**The xAI REST API supports live X search through the Responses API.** The Python SDK is optional.

| API | Chat Works | X Search Works |
|-----|------------|----------------|
| REST `POST https://api.x.ai/v1/responses` with `"tools": [{"type": "x_search"}]` | YES | YES |
| Python SDK (`xai_sdk`) | YES | YES |
| REST `api.x.ai/v1/chat/completions` with `search: true` (legacy Live Search) | YES | NO: `num_sources_used: 0` |

The legacy `search: true` failure is the removed Live Search feature, not a limit of REST. Use `/v1/responses`.

**Checked against xAI's X Search docs on 10 November 2026** (docs.x.ai/developers/tools/x-search). Their examples use `grok-4.7`. Main Branch has not tested REST `x_search` or any model: **not tested by Main Branch**. Older notes here (January 2026) said server-side tools need the grok-4 family and that grok-3 returns `INVALID_ARGUMENT`; treat that as history and check xAI's models page for the current name.

---

## Two Setup Options

| Option | Live X Search | Setup Time | Best For |
|--------|---------------|------------|----------|
| **Python SDK** (recommended) | YES | 5 min | Real X sentiment research |
| **MCP wrapper** (community) | MAYBE* | 10 min | If SDK doesn't work |

*MCP wrappers use REST API, which may not return live X data. Test before relying on it.

---

## Cost Upfront

**This is NOT free.** xAI requires credits before API use.

| Item | Cost |
|------|------|
| Minimum purchase | $5 |
| New user bonus | $25 free credits |
| Data sharing bonus | +$150/mo free credits |

**X Search is billed on top of tokens** (xAI docs, checked 10 November 2026):
- $5 per 1,000 posts fetched
- $10 per 1,000 user profiles fetched
- plus token costs at the model's current rates (see xAI's pricing page; the old Grok-4 figure of ~$3 input and ~$15 output per million tokens is January 2026 history)

A search's cost depends on how many posts and profiles it fetches, so do not promise a number of searches from a $5 balance. Start small, then read the usage in your xAI console.

---

## Why X Search via Grok?

Web search gives you articles and blogs. Grok with X search gives you what people are actually saying RIGHT NOW on X/Twitter.

**Use cases:**
- "What are people saying about [topic]?"
- "What's the sentiment around [brand/product]?"
- "What's trending in [industry]?"
- Social proof research — find real opinions to inform messaging

**Without X search:** Manual X browsing, no sentiment analysis, no structured data
**With X search:** Search, analyze, get trends with citations to actual posts

---

## Option 1: Python SDK (Recommended)

The official xAI Python SDK supports live X search via gRPC.

### 1. Get xAI API Key (2 min)

1. Go to [console.x.ai](https://console.x.ai)
2. Sign up or log in (requires X account)
3. **Purchase credits first** — Click "Buy some credits" → minimum $5
4. Then go to "API Keys" in sidebar → Create API key
5. Copy the key

### 2. Install SDK (1 min)

```bash
pip install xai-sdk
```

### 3. Store the Key (1 min)

From the business repo, store the key with `mb connect`. Paste it at the prompt
your terminal gives, never into chat, a file, or a shell line.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

Then run:

```bash
mb connect xai --custom --account "xAI"
```

Run anything that needs it through `mb connect exec`:

```bash
mb connect exec xai --env XAI_API_KEY -- python3 test_grok.py
```

### 4. Test X Search

Create a test script `test_grok.py`:

```python
from xai_sdk import Client
from xai_sdk.tools import x_search
from xai_sdk.chat import user

client = Client()

chat = client.chat.create(
    model="grok-4",  # tested January 2026; xAI docs now show grok-4.7 (untested here)
    tools=[x_search()],
)

chat.append(user("What are people saying about AI coding assistants on X today?"))

response = chat.sample()
print(response.content)
```

Run it:

```bash
mb connect exec xai --env XAI_API_KEY -- python3 test_grok.py
```

If you see actual X posts with handles and timestamps, X search is working.

**Note:** The SDK API changed in v1.6+. The old async `add_user_turn()` pattern no longer works. Use the sync `append(user(...))` + `sample()` pattern shown above.

### Available Sub-Tools & Search Parameters

See [grok-social.md](grok-social.md) for the full list of sub-tools (`x_user_search`, `x_keyword_search`, etc.) and search parameter details.

---

## Option 2: MCP Wrapper (Fallback)

A community MCP server that wraps the Grok REST API. **Warning:** May not support live X search since REST API has limitations.

### 1. Get xAI API Key

Same as Option 1 above.

### 2. Clone the MCP Server

Open a **new terminal window** (not inside Claude Code):

```bash
cd ~/
git clone https://github.com/mzkrasner/grok-x-insights-mcp.git
cd grok-x-insights-mcp
npm install
npm run build
```

### 3. Store the Key

Store it with `mb connect` as in Option 1, step 3. Do not write it into a `.env`
file.

### 4. Add to Claude Code

The server reads `GROK_API_KEY`, so start it through `mb connect exec`. The key
belongs to one business repo, so register the server from that repo with
`--scope project`. `mb connect exec` finds the key from the working directory
Claude Code launches the server in, and only inside the business repo that holds
the `xai` connection; started from anywhere else it fails with "unknown provider
'xai'". Launch Claude Code from the business repo:

```bash
cd path/to/my-business
claude mcp add grok-x-insights --scope project -- mb connect exec xai --env GROK_API_KEY -- node ~/grok-x-insights-mcp/dist/index.js
```

### 5. Verify

Restart Claude Code (`/exit` then `claude`), then `/mcp` to see if it loaded.

### MCP Tools Available

| Tool | Purpose |
|------|---------|
| `grok_search_posts` | Search and analyze X posts |
| `grok_analyze_topic` | Deep analysis with aspects |
| `grok_get_trends` | Trending topics |
| `grok_chat` | General chat |

**Test if X search actually works:** Check responses for `num_sources_used > 0`. If it's 0, the MCP is using REST API and X search isn't working.

---

## Fallback: WebSearch

When neither SDK nor MCP work:

```
WebSearch: "[topic] site:x.com"
```

**Limitations:**
- Not real-time (only indexed pages)
- No sentiment analysis
- No structured data

Still useful for finding popular/viral posts that have been indexed.

---

## Troubleshooting

**SDK: "ModuleNotFoundError: xai_sdk"** — Run `pip install xai-sdk`

**SDK: "Invalid API key"** — Check it is stored without printing the value:
`mb connect status xai --json`,
then verify at [console.x.ai](https://console.x.ai)

**SDK: "num_sources_used: 0"** — You're using REST API, not SDK. Make sure you're using `x_search()` tool.

**SDK: "the model grok-3 is not supported when using server-side tools"** — In Jan 2026 this meant grok-3 had lost server-side tools. Use a model from xAI's X Search docs (see the dated note near the top).

**SDK: "AttributeError: 'Chat' object has no attribute 'add_user_turn'"** — Old SDK API. Update to v1.6+: use `chat.append(user(...))` then `chat.sample()` instead of async `add_user_turn()`.

**MCP: "grok-x-insights not found"** — Run `npm run build` and check the path.

**MCP: No X data returned** — The MCP may be using REST API. Try the Python SDK instead.

**Rate limited** — Check credit balance at console.x.ai.

---

## Resources

- **xAI Docs:** https://docs.x.ai/docs/guides/tools/search-tools
- **Python SDK:** https://github.com/xai-org/xai-sdk-python
- **Usage patterns:** See [grok-social.md](grok-social.md)
