# Nano Banana Setup (Image Generation)

Google's Gemini-powered image generation for creating ad visuals and content images directly from Claude Code.

---

## What It Does

Nano Banana generates images from text prompts with Google's Gemini models, so `/mb-ads`, `/mb-organic` and `/mb-think` can produce actual image creatives instead of only text prompts. Without it, skills output text image prompts you paste into another image tool.

---

## Prerequisites

- Google AI Studio API key (same as Gemini research — `GOOGLE_API_KEY`)
- If you already set up Gemini for `/mb-think`, you're halfway done

---

## Setup (2 minutes)

### 1. Get API Key (skip if you have GOOGLE_API_KEY)

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click "Create API Key"
3. Copy the key

### 2. Add to Environment

Add to `~/.config/vip/env.sh` (created during `/mb-setup` — see Step 4a in `mb-setup/SKILL.md` for full env setup):

```bash
export GOOGLE_API_KEY="your-api-key-here"
```

If you don't have `env.sh` yet, run `/mb-setup` first or create it manually:

```bash
mkdir -p ~/.config/vip
chmod 700 ~/.config/vip
$EDITOR ~/.config/vip/env.sh
```

Add the `export GOOGLE_API_KEY="..."` line in the editor. Do not paste API keys
into chat, screenshots, or terminal output.

### 3. Add MCP Server

```bash
claude mcp add nano-banana --scope user -- npx nano-banana-mcp
```

### 4. Verify

Restart Claude Code (`/exit` then `claude`), then check:

```bash
/mcp
```

You should see `nano-banana` listed with available tools.

---

## MCP Servers

Recommended: `nano-banana-mcp` (ConechoAI, simple and reliable). Alternatives: `nanobanana-mcp-server` (Python, `uvx nanobanana-mcp-server@latest`) and `nanobanana-mcp` (YCSE, most feature-rich, session consistency and style persistence).

---

## Pricing

Uses Google AI Studio credits (same as Gemini research):

**The ONLY model to use (copy-paste exactly):**

```
gemini-3-pro-image-preview
```

| Model | SDK String | Cost | Quality |
|-------|-----------|------|---------|
| Nano Banana Pro | `gemini-3-pro-image-preview` | ~$0.13/image | **Use this for everything.** 4K, accurate text rendering |

**NEVER use Flash models for image generation.** Quality is not ad-grade. Not even for testing — a test with the wrong model tells you nothing useful.

**NEVER use:** `gemini-2.0-flash-preview-image-generation`, `gemini-2.5-flash-image`, or any other model name. They will either 404 or produce unusable output.

**Imagen 4** (standalone text-to-image, no conversational editing):

| Model | Cost | Quality |
|-------|------|---------|
| Imagen 4 Fast | ~$0.02/image | Quick generation |
| Imagen 4 Standard | ~$0.04/image | Balanced |
| Imagen 4 Ultra | ~$0.06/image | Highest fidelity |

Free tier includes limited image generation. Paid credits scale to hundreds of images.

---

## Troubleshooting

**"MCP not found"** — Run `claude mcp add` command again. Make sure npx is available (`which npx`).

**"Invalid API key"** — Check presence without printing the value: `test -n "$GOOGLE_API_KEY" && echo "GOOGLE_API_KEY is set" || echo "GOOGLE_API_KEY is not set"`. Verify at [aistudio.google.com](https://aistudio.google.com).

**"Rate limited"** — Free tier has limits. Wait or upgrade to paid credits.

**Images have watermark** — All Nano Banana outputs include SynthID watermark (Google requirement). This is normal and expected.

---

## See Also

- `mb-think/references/gemini-setup.md` — Gemini research setup (same GOOGLE_API_KEY)
- `mb-start/references/config-system.md` — Full config file layout (local.yaml, env.sh, config.yaml)

## Resources

- Google AI Studio: https://aistudio.google.com/apikey
- Gemini Image Gen Docs: https://ai.google.dev/gemini-api/docs/image-generation
- ConechoAI MCP: https://github.com/ConechoAI/Nano-Banana-MCP
