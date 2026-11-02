# Repo Scaffolding Reference

Detailed instructions for creating the business repo's configuration files, environment setup, and gitignore.

## Machine-Local Config Safety (`~/.config/vip/local.yaml`)

When updating `local.yaml`, always use **read → merge → write**:
- Read existing file first
- Preserve unknown keys
- Add/refresh only the keys needed (`vip_path`, `recent_repos`, optional `default_repo`, `user.*`)
- Ask before changing `default_repo` if one already exists

**Never overwrite the whole file with:**
```bash
cat > ~/.config/vip/local.yaml
```

That can silently delete user settings.

## API Key Environment (Progressive Setup)

Create the env.sh template for optional research tools. This lives outside git repos for security.

```bash
mkdir -p ~/.config/vip
cat > ~/.config/vip/env.sh << 'EOF'
# Main Branch API Keys
# This file is sourced by your shell. Keep it outside git repos.

# === OPTIONAL RESEARCH TOOLS ===
# These unlock additional capabilities. Add as needed.

# Gemini - Deep web research + Nano Banana image generation (free tier available)
# Get from: https://aistudio.google.com/apikey
# export GOOGLE_API_KEY=""

# xAI/Grok - X/Twitter sentiment analysis
# Get from: https://console.x.ai
# export XAI_API_KEY=""
EOF
```

Add source line to shell config (detects zsh vs bash):

```bash
# Detect shell and add source line
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ]; then
  grep -q 'source.*vip/env.sh' ~/.zshrc 2>/dev/null || \
    echo '[ -f "$HOME/.config/vip/env.sh" ] && source "$HOME/.config/vip/env.sh"' >> ~/.zshrc
else
  grep -q 'source.*vip/env.sh' ~/.bashrc 2>/dev/null || \
    echo '[ -f "$HOME/.config/vip/env.sh" ] && source "$HOME/.config/vip/env.sh"' >> ~/.bashrc
fi
```

**Explain to user:**
> "Created `~/.config/vip/env.sh` for API keys. It's outside git repos (security) and sourced on shell startup.
>
> You don't need keys now -- Apify handles most research. Add Gemini/Grok later if you want deep research capabilities."

**Progressive disclosure:** Don't overwhelm beginners with API setup. The env.sh exists but stays empty until they need it.

## Legacy .vip Config

Do not create `.vip/config.yaml` for new repos. Older repos may already have it
with mixed business facts, MCP requirements, tool snapshots, infrastructure
refs, content defaults, skill defaults, private paths, or client context.

Audit old files with:

```bash
mb doctor repair --plan --json
```

Move only still-current, non-private facts into current surfaces such as
`core/`, `core/operations/`, generated repo instructions, or provider metadata
managed through `mb connect`. Keep credentials and machine-specific paths local.

## Create .gitignore

```bash
cat > .gitignore << 'EOF'
# Secrets
.env
*.env.local

# Machine-local settings (absolute paths, not shared)
.claude/settings.local.json

# Session state (not shared between machines)
.vip/local.yaml

# OS
.DS_Store

# Editor
.vscode/
.idea/
EOF
```

**Then add Main Branch bridge link entries** (dynamic, based on which engine skills exist):

```bash
GITIGNORE="$REPO_PATH/.gitignore"

ensure_gitignore_entry() {
  entry="$1"
  grep -qxF "$entry" "$GITIGNORE" 2>/dev/null || echo "$entry" >> "$GITIGNORE"
}

if ! grep -q "MAIN BRANCH MACHINE-LOCAL" "$GITIGNORE" 2>/dev/null; then
  cat >> "$GITIGNORE" << 'GITIGNORE_BLOCK'

# === MAIN BRANCH MACHINE-LOCAL (do not commit) ===
GITIGNORE_BLOCK
fi

ensure_gitignore_entry ".claude/settings.local.json"
ensure_gitignore_entry ".claude/worktrees/"

# Add each Main Branch skill symlink individually (preserves custom skill tracking)
for d in "$ENGINE_PATH"/.claude/skills/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  ensure_gitignore_entry ".claude/skills/$n"
done
```

**Why `.claude/settings.local.json` is git-ignored:** Claude Code auto-ignores this file, but we add it explicitly for safety. It contains machine-specific absolute paths to Main Branch (`additionalDirectories`) that differ per computer.

**Why per-skill entries (not `.claude/skills/`):** Users have custom skills (deck, pr-review, etc.) that ARE tracked in git. Ignoring the whole folder would hide those. We only ignore the Main Branch-linked symlinks. Old clone-based `.claude/lenses/` and `.claude/reference/` dirs are legacy link dirs; repair them with `mb doctor repair` instead of teaching them as current setup.

**Why legacy `.vip/local.yaml` is git-ignored:** Older repos may have stored
session state like `current_offer` there. Treat it as audit input, not durable
business truth, and do not write it as the active-offer mechanism. Older
`.vip/config.yaml` files may have been tracked as shared settings; audit them
with `mb doctor repair --plan --json` before reusing any values.

---

## Folder Structure

Full structure (single-offer):
```
{business-name}/
├── CLAUDE.md              # Always loaded - business brain
├── README.md              # Human-readable overview
├── .env                   # Secrets (gitignored)
├── .gitignore             # Include .env
│
├── core/                  # Evergreen business brain
│   ├── soul.md            # Why you exist
│   ├── offer.md           # What you sell / brand thesis
│   ├── audience.md        # Who buys
│   ├── voice.md           # How you sound
│   ├── content-strategy.md # Business-level content strategy and layer index
│   ├── marketing/          # Optional distribution, channel, account layers
│   ├── people/             # Optional founder/person voice source material
│   ├── proof/
│   │   ├── testimonials.md
│   │   └── angles/        # Proven messaging entry points
│   ├── brand/             # Visual identity and brand systems
│   ├── operations/        # Business-type specific operating context
│   ├── finance/           # Ledger and tax artifacts
│   └── offers/            # Per-offer specifics when multi-offer
│
├── research/              # Dated investigations
│   └── YYYY-MM-DD-topic-[source].md
│
├── decisions/             # Dated choices with rationale
│   └── YYYY-MM-DD-topic.md
│
├── bets/                  # Operating bets with target, deadline, and result
│   └── YYYY-MM-DD-topic.md
│
├── log/                   # Running activity log
│
└── pushes/                # Coordinated pushes and their artifacts
    └── YYYY-MM-DD-push-name/
```

Full structure (multi-offer — adds offer folders and `product-ladder.md`):
```
{business-name}/
├── ...                    # Same as above, plus:
├── core/
│   ├── product-ladder.md  # How offers relate
│   └── offers/            # Offer-specific overrides
│       ├── community/
│       │   └── offer.md   # Offer-specific details
│       └── course/
│           └── offer.md
```
