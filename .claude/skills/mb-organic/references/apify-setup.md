# Apify Setup Guide

> **Note:** Mining (competitor analysis, content extraction) is done through `/mb-think`, not `/mb-organic`. This Apify setup is used when `/mb-think` spawns mining agents for Instagram data extraction. `/mb-organic` is generation-only.

One-time 5-minute setup. After this, Apify works automatically every time you mine through `/mb-think`.

---

## Why Apify?

Instagram blocks browser automation aggressively. Without Apify:
- Slow screenshot-by-screenshot browsing
- 60-70% success rate
- Burns through your Claude usage

With Apify:
- Clean data in seconds
- 95%+ success rate
- Handles rate limits automatically

---

## Setup Steps

### 1. Create Apify Account (2 min)

Go to [apify.com](https://apify.com) → Sign up (free tier works)

### 2. Get Your API Token (1 min)

**What's a token?** It's like a password that lets Claude use your Apify account. Keep it private - anyone with your token can use your account.

1. Click **Settings** (gear icon, bottom left)
2. Click **API & Integrations** tab
3. Under "Personal API tokens" you'll see a default token already created
4. Click the **copy icon** (looks like two squares) next to the asterisks

That's your token. Don't create a new one - the default works fine.

### 3. Add MCP to Claude Code (2 min)

**Before you start:** This step requires pasting your token into the middle of a command. That's tricky if you're new to terminal! We'll build the command in pieces so you don't have to edit anything.

Open a **new terminal window** (not inside Claude Code).

---

**Copy and paste these three pieces, one at a time:**

**PIECE 1** — Copy this and paste into terminal:
```
claude mcp add apify -e APIFY_TOKEN=
```

**PIECE 2** — Paste your Apify token right after the `=` (no space!)

Your terminal should now show something like:
```
claude mcp add apify -e APIFY_TOKEN=apify_api_xxxxx
```

**PIECE 3** — This is the tricky part. Do these in order:

1. **Type a space** (just hit the spacebar once)
2. Then copy and paste this **all on one line**:

```
--scope user -- npx -y @apify/actors-mcp-server
```

**Important:** Make sure the whole thing is on ONE line before pressing Enter. Your full command should look like:

```
claude mcp add apify -e APIFY_TOKEN=apify_api_xxxxx --scope user -- npx -y @apify/actors-mcp-server
```

---

**Now press Enter.** You should see "Added stdio MCP server apify... to user config"

---

**Why `--scope user`?** Saves Apify to your global settings so it works from any directory — essential for the two-repo setup.

**Why a separate terminal?** Keeps your API token local instead of passing through chat servers.

---

## That's It

Apify is now saved to your global Claude Code settings (`~/.claude/settings.json`).

Every time you mine Instagram content through `/mb-think`, Apify will be used automatically. No re-setup needed.

---

## Verify It's Working

**Restart Claude Code** — MCPs only load at startup:

1. Type `/exit` to quit
2. Run `claude` again (or `claude --continue` to resume your conversation)
3. Type `/mcp`

You should see `apify` in the list of configured servers.

---

## First Time Using Apify

When Claude first uses Apify, you'll see a permission prompt like:

```
Do you want to proceed?
1. Yes
2. Yes, and don't ask again for apify commands
3. No
```

**Hit 2** to always approve Apify commands. Otherwise you'll have to approve every single request.

---

## Troubleshooting

**"apify not found"** — Run the `claude mcp add` command again, make sure you replaced the token.

**"Invalid token"** — Double-check your API token on apify.com → Settings → Integrations.

**"Rate limited"** — Free tier covers ~2000 posts/month. If you hit limits, upgrade to ~$5/mo.
