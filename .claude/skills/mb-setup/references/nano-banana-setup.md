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

## Model and Pricing

Nano Banana is an optional image provider. `/mb-ads` defaults to the provider in its image workflow (OpenAI GPT Image 2 is the first readiness target); use Nano Banana when the operator prefers Google or wants a comparison rail.

Uses Google AI Studio credits (same as Gemini research). Do not pin an image model ID from memory: read the current Nano Banana model name and price at [ai.google.dev/gemini-api/docs/image-generation](https://ai.google.dev/gemini-api/docs/image-generation) or from the MCP server's tool list, and use the current image-generation model, not a text or "flash" research model. A test with the wrong model tells you nothing useful.

Free tier includes limited image generation; paid credits scale up.

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
