# Troubleshooting

Common issues and fixes for Claude Code + Main Branch.

---

## "command not found: claude"

Terminal doesn't know where Claude is installed. Add it to your PATH.

**Mac (zsh - default on modern Macs):**
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

**Linux or older Mac (bash):**
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

**Verify it worked:**
```bash
claude --version
```

---

## "Repository not found" / 404 Error

Use the public Main Branch repo:

**Fix:**
1. Open `https://github.com/dmthepm/mainbranch` in your browser
2. Confirm the URL is typed exactly in GitHub Desktop or terminal
3. Try cloning again

**Note:** The repo is public. A 404 usually means the old URL is being used or the URL was mistyped.

---

## "Can't push to Main Branch" / Permission Denied

This is expected behavior, not an error.

**Main Branch is read-only for most users.** You can install updates but cannot push changes.

Your business files go in your own business folder (created by `mb onboard` or
`/mb-setup`). That folder is where your saved work belongs.

---

## Xcode Command Line Tools Popup (Mac)

If you see a popup about downloading "developer tools" or "Xcode Command Line Tools":

1. **Click Install** - You need these for Git operations
2. **Ignore the time estimate** - It says hours but usually takes minutes
3. **Wait for completion** - Don't cancel

**If you accidentally canceled:**
```bash
xcode-select --install
```

---

## GitHub Desktop: "Repository not found"

Same as the 404 error above. Use the public repo URL:

```text
https://github.com/dmthepm/mainbranch
```

---

## Skills Not Working

If skill prompts like `/mb-start` or `/mb-ads` aren't showing in the dropdown:

**Check 0: Is the Main Branch plugin installed and enabled?**

Main Branch ships as a Claude Code plugin — this is the most common reason the
skills are missing. Install it once and enable it:

```bash
claude plugin marketplace add dmthepm/mainbranch
```

If that fails because the marketplace still points at `noontide-co/mainbranch`,
follow the move steps in `docs/migrating.md`.

The plugin works in both the Claude Desktop app and the terminal `claude` CLI,
and it survives git worktrees. (Cloud/web Claude sessions cannot load plugins —
use Desktop or the terminal.) `mb onboard` and `mb init` wire it for you, so a
freshly onboarded repo usually has it already; the manual step above is for
repos that predate plugin wiring. Skills load at startup — restart Claude Code
after enabling.

If the plugin loads but the bare `/mb-start` still doesn't resolve, try the
namespaced form `/mainbranch:mb-start` (some builds expose plugin skills under
the plugin name). Use whichever form your build shows in the slash-command list.

**Check 1: Does the local bridge exist?**
```bash
test -e .claude/skills/mb-start && echo "START_BRIDGE_OK"
```

If missing, run the noob-safe repair path from the business repo:

```bash
mb skill link --repo .
mb skill repair --repo .
mb doctor
```

If the `mb` CLI is unavailable because this is an old clone-based setup, use
`docs/migrating.md`. Current skills depend on `mb` CLI facts, so fix the
reported migration and repair errors before treating the skills as fully ready.
Do not hand-recreate the old link model in normal help.

**Check 2: Is Main Branch loaded as an additional directory?**
```bash
cat .claude/settings.local.json
```

You should see the active Main Branch package or source-checkout path listed
under `permissions.additionalDirectories`. If not, run `mb skill link --repo .`.

**Check 3: Did you start in your business repo?**

```bash
cd ~/Documents/GitHub/[your-business]
claude
/mb-start
```

**Check 4: None of the above?** Run `/mb-setup` — it creates `settings.local.json` and missing bridge links.

**After fixing:** Close and reopen Claude (`Ctrl+C`, then `claude`) for skill changes to take effect.

---

## Workspace-Isolated Tools: Skills Not Showing

Some workspace tools are isolated; Claude doesn't know where Main Branch is unless the workspace is linked.

**The fix:** Run `mb skill link --repo .` in the workspace when possible. If you need a pre-start hook, use one that creates the bridge links plus `settings.local.json` before Claude starts.

See [workspace-setup.md](workspace-setup.md) for the full script and setup walkthrough.

**Quick version:**
1. Find your Main Branch package or source-checkout path
2. Add the pre-start hook to your workspace tool if the CLI repair path is unavailable
3. The script creates symlinks + settings, then exits
4. Start the agent again — skills appear

**After fixing:** Skills only load at startup. If you added bridge links mid-session, you need to restart Claude.

---

## "Cannot edit files outside allowed directories"

This is common in sandboxed workspace tools. It means Claude can only edit files inside the current workspace folder.

**What this means in plain English:** Claude is working in one folder "bubble" and can't directly write to files outside that bubble with the normal write tool.

**Important context:** In a regular terminal Claude session (not workspace-isolated by an IDE or agent tool), Claude will often prompt for permission and continue. This error is most common in stricter workspace-isolated environments.

**Fix options:**
1. **Best:** Start Claude in the repo you want to edit (or switch workspace to that repo)
2. **Fallback:** Use terminal commands to write files in the target path

**Recommended for beginners:** Use option 1 whenever possible. It's easier to review and less error-prone.

**If you're in a workspace tool:** open a workspace rooted at the target repo, then re-run `/mb-setup` or `/mb-start`.

---

## Context Feels "Off" or Claude Forgot Things

Claude's context decays as conversations get longer. The CLAUDE.md instructions fade.

**Fix:** Run a slash command to reload fresh instructions.

Good commands for refreshing context:
- `/mb-start` - Reloads and routes
- `/mb-think` - For research/decisions
- `/mb-help` - For questions

---

## Turn Friction Into a GitHub Issue

If a Main Branch command, skill, setup step, or doc gap is reproducibly confusing
after the repair path above, help the operator create a privacy-safe public issue
draft. Do not submit it for them.

**Bug:**
```bash
mb issue draft bug --command "mb doctor" --what-happened "..." --expected "..."
```

**Feature gap:**
```bash
mb issue draft feature --problem "..." --proposal "..."
```

**Question:**
```bash
mb issue draft question --question "..." --context "..." --tried "..."
```

Drafts go under `.mb/issue-drafts/` and are gitignored. Tell the operator to
review the draft for private business data, customer/member details, secrets,
account IDs, screenshots, and local-only paths before running:

```bash
mb issue open .mb/issue-drafts/[draft].md --yes
```

Use this only for Main Branch product friction that belongs in the public issue
tracker. Operator-specific business strategy belongs in the community or their
private repo, not public GitHub.

---

## MCP Not Working (Apify, etc.)

### "apify not found" in /mcp

MCP wasn't installed correctly. Re-run the setup:

```bash
claude mcp add apify -e APIFY_TOKEN=your_token_here --scope user -- npx -y @apify/actors-mcp-server
```

**Important:** Use `--scope user` so it's saved globally.

### "Invalid token" errors

Check your token at apify.com → Settings → API & Integrations. Copy the default token (don't create a new one).

### MCP installed but not showing

MCPs only load at startup. Restart Claude:

```bash
/exit
claude --continue
```

Then type `/mcp` to verify it appears.

### Permission prompts every time

When Claude first uses an MCP, hit `2` to "always allow" instead of `1` for one-time.

---

## Resuming a Session

If you closed Terminal or need to pick up where you left off:

```bash
claude --continue
```

This resumes your previous conversation with full context.

---

## Business Repo Not Loading Automatically

If `/mb-start` doesn't load your business repo:

```bash
mb start --json
mb doctor repair --repo /path/to/your/repo --plan --json
```

**Common fixes:**

| Problem | Solution |
|---------|----------|
| Current folder is not the business folder | `cd` into the business folder and restart Claude |
| Skill links are stale | Run `/mb-update` or `mb update --repo .`, then restart Claude |
| Folder was moved | Run `mb start --json`; if it cannot find the folder, choose the correct path in `/mb-start` |
| `.vip/config.yaml` exists | Audit it with `mb doctor repair --plan --json`; do not treat it as current team settings |

**Migration from old system:**
Use `docs/migrating.md` for clone-era installs, old repo layouts, or stale
`~/.claude/settings.json` paths. Keep troubleshooting focused on the current
business-folder flow.

---

## Git Conflicts in an Old Engine Clone

Most users should update through `/mb-update` or `mb update`. Raw package or
source-checkout repair belongs in `docs/migrating.md`.

From the business repo, prefer:

```bash
mb update --repo .
mb skill link --repo .
mb doctor
```
