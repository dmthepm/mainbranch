# Provider And MCP Pre-Flight Check

Verify provider readiness and required runtime tools before routing to skills
that need them.

---

## Why This Matters

Provider metadata belongs to the business repo through `.mb/connect.yaml`, while
secrets and MCP installs live on the user's machine. When someone clones their
business repo on a new machine, provider metadata may be visible but local
secrets and MCP tools may still be missing.

Start with deterministic CLI facts:

```bash
mb status --json --peek
mb connect plan
mb connect doctor --json
```

Use the CLI's `state`, `summary`, `next_command`, and `repair_command` before
probing runtime tools manually.

---

## Check Flow

### 1. Read provider readiness from mb

Use `mb status --json --peek` for the daily route. If the operator asks which
account to connect or a selected workflow needs outside access, run:

```bash
mb connect plan
mb connect doctor --json
```

Required provider choices for the setup/provider loop:

| Provider | Business job | Check |
|---|---|---|
| GitHub | durable work threads, proposals, reviews, shipped history | `mb connect doctor --json` |
| Cloudflare | sites, DNS, Pages, Workers | `mb connect doctor --json` |
| Google / Workspace | Drive, Docs, Sheets, Slides | `mb connect doctor --json` |
| Meta Ads | ready only after `mb connect test meta` passes official CLI read-only smoke | `mb connect doctor --json` |
| Apify | scraping, YouTube, Instagram, research sidecars | `mb connect doctor --json` |

Only continue to MCP/tool presence checks when the selected skill needs runtime
tools that `mb connect` cannot inspect directly.

### 2. Treat legacy MCP config as audit input only

Older repos may have `mcps.*` under `.vip/config.yaml`. Do not treat that file
as current shared team settings. If it exists, `mb doctor repair --plan --json`
classifies the keys as provider-readiness hints without printing raw values.
Use `mb connect plan`, `mb connect doctor --json`, and generated repo
instructions for current provider readiness.

### 3. Check if MCP tools are available

Look for tool presence:
- `mcp__apify__*` tools → Apify loaded (handles web scraping + YouTube transcripts)
- `mcp__whisper__*` tools → whisper-mcp loaded (local video/audio transcription)

### 4. Prompt if missing

If routing to a skill that needs a missing runtime tool after `mb connect`
facts have been read:

> "This action needs Apify research access. `mb connect plan` says Apify is [state].
>
> 1. Set up now — `[exact command from mb]`
> 2. Skip for now — YouTube and Instagram mining will be limited"

If user picks 1 → Show setup guide path, walk through it.

---

## When to Check

- **Always** when routing to skill that needs MCPs
- **Don't block** on optional MCPs — mention limitations
- **Remember** result for session (don't re-check)

---

## Research Tools Check

These runtime tools enhance `/mb-think` after provider readiness is known. They
are optional and should not replace `mb connect` facts:

| Tool | Check Method | If Missing |
|------|--------------|------------|
| **Apify** | `mcp__apify__search-actors` tool exists | Offer setup (important - enables YouTube + Instagram mining) |
| **Grok** | `mb connect status xai --json` shows a stored key OR `mcp__xai__*` exists | Note, don't block (fallback: WebSearch site:x.com) |
| **Gemini** | `mb connect status google-ai --json` shows a stored key | Note, don't block (fallback: multi-source WebSearch) |
| **whisper** | `mcp__whisper__*` OR `which mlx_whisper` OR `which whisper-cli` | Offer CLI fallback or manual transcription |

### Detection Order

Run only when the selected `/mb-think` path needs that runtime tool:

```bash
# 1. Apify - check for MCP tools (most important)
# If mcp__apify__* tools exist → Apify loaded

# 2. Gemini - stored key
mb connect status google-ai --json

# 3. Grok - stored key or MCP
mb connect status xai --json
# OR check for mcp__xai__* tools

# 4. whisper - MCP or CLI (check mlx_whisper first, then whisper-cli)
which mlx_whisper >/dev/null 2>&1 && echo "mlx_whisper available"
which whisper-cli >/dev/null 2>&1 && echo "whisper-cli available"
# OR check for mcp__whisper__* tools
```

### Reporting

**Good (all tools):**
> "Research tools ready: Apify, Gemini, Grok, whisper"

**Partial (common case):**
> "Research tools: Apify ready. Gemini/Grok not configured (web search fallback available)."

**Missing Apify (important):**
> "Apify MCP not detected. YouTube and Instagram mining won't work.
> Set up now? (5 min one-time) Or skip for this session."

### Progressive Disclosure

- Report availability once at session start
- Don't nag about missing optional tools
- Only offer setup when user tries to use missing capability
- Always provide fallback path
- Use `mb connect plan` / `mb connect doctor --json` for provider setup and
  repair language before any runtime-specific checks.

---

## Config vs Installation

| What | Where | Portable? |
|------|-------|-----------|
| "What this business needs" | `mb connect` provider metadata, generated repo instructions, and durable operations notes | Yes, when non-secret and intentionally committed |
| "What this machine has" | `~/.claude.json` | No (local) |

Current provider metadata documents requirements. Installation state is Claude
Code's domain. See [config-system.md](config-system.md) for legacy config
cleanup guidance.
