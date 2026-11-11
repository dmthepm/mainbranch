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

## Tool Credentials

Setup does not create a shell-wide key file or edit shell startup files.
Optional tools get their credentials through `mb connect`. Run
`mb connect plan` to see what is ready and what is missing, and add a
credential only when the operator wants that tool. Agents use credentials
through `mb connect exec` and never read or print the value.

Someone who already keeps their own environment file does not need to change
anything. Do not create, source, move or delete it.

**Progressive disclosure:** Don't raise tool setup with beginners until a task
needs it.

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

`mb init` writes `.gitignore`. Do not write it from the shell. If the repo has
none, show the user this template and let them create the file:

```gitignore
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

# Main Branch local Claude wiring
.claude/worktrees/
.claude/skills/mb-*
```

**Main Branch bridge link entries** in a repo that already had a `.gitignore`:

`mb skill link --repo "$REPO_PATH"` adds these lines when missing, under the
header `# Main Branch local Claude wiring`, and refuses a `.gitignore` that is a
symlink. Without the CLI, do not write `.gitignore` from the shell: show the
user these three lines and let them add any that are missing.

```gitignore
# Main Branch local Claude wiring
.claude/settings.local.json
.claude/worktrees/
.claude/skills/mb-*
```

The `mb-` skill prefix is reserved for Main Branch. Name owner skills without
`mb-` so git includes them. `mb doctor` warns about ignored owner folders using
that prefix; rename those folders without `mb-`.

**Why `.claude/settings.local.json` is git-ignored:** Claude Code auto-ignores this file, but we add it explicitly for safety. It contains machine-specific absolute paths to Main Branch (`additionalDirectories`) that differ per computer.

**Why `.claude/skills/mb-*` (not `.claude/skills/`):** Users have custom skills (deck, pr-review, etc.) that ARE tracked in git. Ignoring the whole folder would hide those. Every Main Branch skill is named `mb-*`, so one line covers them, and a release that adds a skill adds no line. The line also ignores anything else named `mb-*` there, so the `mb-` prefix is reserved for Main Branch skills; files already tracked stay tracked. Older repos may keep per-skill lines such as `.claude/skills/start`; link never removes lines, so delete one by hand if you want to reuse that name for your own skill. Old clone-based `.claude/lenses/` and `.claude/reference/` dirs are legacy link dirs; repair them with `mb doctor repair` instead of teaching them as current setup.

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
