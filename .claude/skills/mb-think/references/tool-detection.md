# Tool Detection (CLI Facts First, Runtime Probes Second)

Provider readiness belongs to `mb status --json --peek`, `mb connect plan`, and
`mb connect doctor --json`. Use those facts before probing local runtime tools
for providers that `mb` owns. Apify research is MCP-first for now, so treat it
as an agent-side tool surface unless a later CLI contract exposes stable Apify
readiness facts. The checks below are for runtime-local capabilities that `mb`
cannot inspect directly inside the current Claude Code session.

---

## Status Values

| Value | Meaning | Action |
|-------|---------|--------|
| `true` | Runtime tool verified in this session/config | Use tool, skip runtime probe |
| `false` | Runtime tool known unavailable | Skip runtime probe unless the user selected this path |
| `null` | Unknown | Run runtime probe only when needed |
| (missing) | Never checked | Run runtime probe only when needed |

## Staleness Check

Do not routinely re-probe stale provider entries here. If provider readiness is
stale or degraded, use `mb connect doctor --json`. Runtime-local entries can be
rechecked when a selected workflow needs that tool.

---

## Detection Flow

On first `/mb-think` invocation each session:

```
1. Read `mb status --json --peek`.
2. Run `mb connect doctor --json` if a selected provider is degraded/missing.
3. If the selected research path needs a runtime-local tool, check only that
   tool.
4. Cache session knowledge and update local runtime notes only for the tool you
   actually touched.
5. Report once (experience-appropriate).
```

For full self-healing contract (stale semantics, status-change messaging, and true-tool degradation handling), see [tool-status-self-healing.md](tool-status-self-healing.md).

---

## Detection Methods

**Apify:** Treat Apify as MCP-first agent-side research enrichment. When the
selected path needs Level 4/5 structured collection, check if `mcp__apify__*`
tools exist in session, then verify source access, permission, terms/cost,
actor shape, and no-raw-dump handling before use. Do not require or imply
`mb connect apify` until a later CLI issue accepts provider-readiness facts.

**Gemini:**
```bash
[ -f "$HOME/.config/vip/env.sh" ] && source "$HOME/.config/vip/env.sh"
[ -n "$GOOGLE_API_KEY" ] && echo "GEMINI=true"
```

**Grok:** Requires BOTH env var AND Python SDK:
```bash
[ -f "$HOME/.config/vip/env.sh" ] && source "$HOME/.config/vip/env.sh"
[ -n "$XAI_API_KEY" ] && python3 -c "import xai_sdk" 2>/dev/null && echo "GROK=true"
```

**whisper:** Check MCP tools (`mcp__whisper__*`) OR CLI (multiple implementations exist):
```bash
which mlx_whisper >/dev/null 2>&1 && echo "WHISPER=mlx_whisper"
which whisper-cli >/dev/null 2>&1 && echo "WHISPER=whisper-cli"
pip3 list 2>/dev/null | grep -i "mlx-whisper" && echo "WHISPER=mlx_whisper"
```

**Save which binary was found** in config `tools.whisper.notes` (e.g., `"mlx_whisper verified"`). Different variants use different command syntax — the notes field tells future sessions which command to use. See [local-transcription.md](local-transcription.md) for variant-specific commands.

**Nano Banana** (image generation): Available when Gemini is configured (uses GOOGLE_API_KEY). Detect alongside Gemini.

**Meta Ads account access:** Use `mb connect doctor --json` for provider
readiness first. The official path is the Meta Ads CLI (`meta-ads` package,
`meta` binary). Treat live account context as available only when `mb` reports
Meta as `ready`.
```bash
# Future detection once mb reports Meta ready:
# which meta
# meta --version
# meta auth status
# meta -o json ads campaign list
# meta -o json ads insights get --fields spend,impressions,clicks,ctr,cpc
```
Lazy runtime detection only -- triggered when topic is ads-related, not on every
`/mb-think` invocation. See `/mb-ads` SKILL.md for the account-context flow.

**Document tools:**
```bash
which markitdown >/dev/null 2>&1 && echo "MARKITDOWN=true"
which pandoc >/dev/null 2>&1 && echo "PANDOC=true"
which marker_single >/dev/null 2>&1 && echo "MARKER=true"
```

**Manual probe script:** `scripts/detect-tools.sh` provides a standalone CLI check for all tools. Useful for debugging outside a Claude session.

---

## Config Update (REQUIRED)

After a runtime-local detection that is not already represented by `mb`,
optionally update local runtime notes:

```yaml
tools:
  gemini:
    status: true              # ← detection result
    notes: "GOOGLE_API_KEY verified"
    last_checked: 2026-03-02  # ← today's date
  whisper:
    status: true
    notes: "mlx_whisper verified"
    last_checked: 2026-03-02
```

Do not store secrets in repo files. Provider setup and repair language still
comes from `mb connect`.

---

## Reporting by Experience

| Experience | Format |
|------------|--------|
| `beginner` | "Research ready. I'll help with tool setup when you need it." |
| `intermediate` | "Tools: Apify ✓, Gemini ✓, Grok ✗, whisper ✗" |
| `advanced` | Silent unless changes from last session |

---

## Intent-Based Tool Surfacing

When the user's intent matches an unavailable tool, surface the option once per session per tool (track in session state), always offer a working fallback, and never block research. Messages and fallback quality: [tool-surfacing.md](tool-surfacing.md).
