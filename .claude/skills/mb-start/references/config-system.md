# Legacy Config Cleanup

Main Branch now treats `.vip/*.yaml` as legacy cleanup/audit input. Runtime
skills should prefer CWD-first repo detection, `mb status --json --peek`,
`mb connect`, `mb onboard`, and current repo files over `.vip` YAML.

---

## File Locations

| File | Location | Purpose | Git-tracked? |
|------|----------|---------|--------------|
| `settings.local.json` | `[repo]/.claude/` | Grants Claude Code file access to the active Main Branch package or source checkout | No (auto git-ignored by Claude Code) |
| `local.yaml` | `~/.config/vip/` | Legacy machine-local fallback for user identity, engine path, and default repo | No |
| `env.sh` | `~/.config/vip/` | Legacy API-key file from older setups; no longer created | No |
| `config.yaml` | `[repo]/.vip/` | Legacy mixed repo config that must be audited before reuse | Maybe old repos tracked it |

**Key split:**
- **Settings** = "Where is Main Branch?" (per-repo, per-machine — `.claude/settings.local.json`)
- **Local** = "Who am I? What repo do I want?" legacy fallback (per-person, per-machine)
- **Connections** = "What API keys do I have?" (`mb connect`, stored outside git)
- **Repo** = current business truth in `core/`, `research/`, `decisions/`,
  `bets/`, `pushes/`, `log/`, `documents/`, `.mb/connect.yaml`, and generated
  repo instructions. Do not use `.vip/config.yaml` as the current shared
  settings surface.

### .claude/settings.local.json (Main Branch linkage)

Created by `mb skill link` and `/mb-setup`. Tells Claude Code to load Main Branch as a read-only additional directory:

```json
{
  "permissions": {
    "additionalDirectories": ["/absolute/path/to/mainbranch"]
  }
}
```

**Auto git-ignored** by Claude Code (like `.claude/settings.local.json` is always local). Contains machine-specific absolute paths — never commit this.

### .claude/ bridge links (slash-command discovery)

`additionalDirectories` grants file access to Main Branch, but project-local
`.claude/skills/mb-*` bridge links are the supported slash-command discovery
surface. Runtime smoke on Claude Code 2.1.126 returned `Unknown command:
/mb-start` when the project-local `.claude/skills/mb-start` bridge was missing,
even though `settings.local.json` still pointed at the engine.

```
business-repo/.claude/
├── settings.local.json       # real file (auto git-ignored)
├── skills/                   # real local folder (for project custom skills)
│   ├── mb-start -> /path/to/mainbranch/.claude/skills/mb-start
│   ├── mb-ads   -> /path/to/mainbranch/.claude/skills/mb-ads
│   └── ... (only missing entries linked)
```

Created by `mb skill link` and `/mb-setup`. `/mb-start` can auto-repair missing
links. Old clone-based repos may also have `.claude/lenses/` or
`.claude/reference/` symlinks; those are legacy link dirs that `mb doctor
repair` can move to backup when they point at stale source checkouts.

**Both are needed:**
- `additionalDirectories` = file access (reading reference files across repos)
- Bridge links = slash-command discovery for Main Branch skills

---

## API Keys (`mb connect`)

API keys for optional tools are stored with `mb connect` and used through
`mb connect exec`. Setup no longer creates `~/.config/vip/env.sh` or edits your
shell profile, and never asks you to paste a key into a file or a shell line.

| Variable | Tool | Store with | How to Get |
|----------|------|------------|------------|
| `GOOGLE_API_KEY` | Gemini | `mb connect google-ai --custom --token-stdin` | https://aistudio.google.com/apikey |
| `XAI_API_KEY` | Grok | `mb connect xai --custom --token-stdin` | https://console.x.ai |
| `APIFY_TOKEN` | Apify | (Usually in MCP config) | https://console.apify.com |

Run a command that needs one with
`mb connect exec <provider> --env <NAME> -- <command>`. See
`mb-think/references/gemini-setup.md` and `mb-think/references/grok-setup.md`.

**Older installs:** an existing `~/.config/vip/env.sh` is left alone and keeps
working for shells that source it. It is not migrated; do not add to it.

---

## Legacy Machine-Local Fallback

```bash
cat ~/.config/vip/local.yaml 2>/dev/null
```

```yaml
# Legacy fallback only. Current repo truth comes from CWD, mb JSON, repo files,
# .claude/settings.local.json, .mb/ state, and provider metadata.
vip_path: /absolute/path/to/mainbranch  # legacy key name; points at Main Branch
default_repo: /absolute/path/to/my-business
recent_repos:
  - /absolute/path/to/my-business
  - /absolute/path/to/client-project

# Optional user hints from old local setup
user:
  name: "Your Name"
  experience: advanced  # beginner | intermediate | advanced

# Optional media fallback from old local setup
media:
  root: /absolute/path/to/Main Branch
  # images: /absolute/path/to/ad-images
  # videos: /absolute/path/to/ad-videos

# Optional concept fallback from old local setup
default_concepts: 2

# Optional changelog seen-state fallback from old local setup
last_seen_version: "0.1.0"
```

**CRITICAL: Always use absolute paths, never `~`.** The Glob and Read tools do
not expand `~`, causing silent failures (0 results when files exist). If legacy
fallback values contain `~`, treat them as stale and ask for the path again.

**Media paths** are machine-specific (contain usernames, sync folder
locations). Skills may read legacy `media.{type}` or `media.root/{type}/` as
fallback, but new choices stay session-scoped unless a current `mb` settings
surface owns the write.

---

## Legacy Business Repo Config Audit

```bash
mb doctor repair --plan --json
```

Older repos may have `[repo]/.vip/config.yaml` with mixed key families:
business facts, MCP requirements, tool snapshots, infrastructure refs, content
defaults, skill defaults, client repo pointers, and old reference-structure
notes.

Do not load it as current truth. The doctor repair plan classifies keys without
printing raw values so private paths, provider notes, client context, and
credentials are not copied into chat or durable files. Move only still-current,
non-private facts into the appropriate current surface after operator review.

---

## Migration from Old Settings

Existing users may have `~/.claude/settings.json` with `business_repo_path`.

**Detection:**
```bash
cat ~/.claude/settings.json 2>/dev/null | grep business_repo_path
```

**If found:**
1. Extract the path
2. Treat it as a fallback suggestion for this session.
3. Do not migrate it into `~/.config/vip/local.yaml`; that file is legacy local
   fallback state, not the current repo registry.

---

## Missing Legacy Config

If repo has `core/` but no `.vip/config.yaml`:

Do not create it. Use `mb status --json --peek`, `mb onboard status --json`,
`mb connect plan`, and current repo files instead.

---

## Migration Table

| Scenario | Behavior |
|----------|----------|
| New user, no repo | Route to `/mb-setup` |
| Existing user, no config | Discovery works, offer upgrade |
| Existing user, accepts | Fast path going forward |
| Existing user, declines | Works exactly as before |

---

## When Skills Read Config

| Skill | Reads | Purpose |
|-------|-------|---------|
| `/mb-start` | legacy local.yaml only when CWD/config discovery fails | Find default/recent repos as fallback |
| `/mb-start` | `mb status --json --peek`, `mb connect`, `mb onboard` | Check readiness, repairs, onboarding, provider state |
| `/mb-help` | legacy local.yaml only as optional fallback | Adjust verbosity based on experience |
| `/mb-ads`, `/mb-think` | current settings when available; legacy `media.*` read-only fallback | Resolve where non-markdown outputs go |

---

## When Skills Write Config

| Trigger | What's Written | Where |
|---------|----------------|-------|
| `/mb-setup` first run | Current repo files, `.claude/settings.local.json`, skill links, `.mb/` state | Business repo |
| User selects repo in `/mb-start` | Session-scoped selection unless a current `mb` command exposes persistence | n/a |
| User says "I'm advanced" | Use for the current answer unless a current `mb` command exposes persistence | n/a |
| User says "save as default" | Prefer current skill/workflow inputs; do not write `.vip/config.yaml` | n/a (no write) |
| User connects infrastructure | Provider metadata through `mb connect`; secrets stay local | `.mb/connect.yaml` and local secret stores |
| User configures media path | Session-scoped path unless a current `mb` command exposes persistence | n/a |

**Rule:** Never write legacy config as part of normal startup. Legacy files are
read-only fallback and audit input unless an explicit migration/repair command
owns the write.

### Legacy Config Safety

Do not update `~/.config/vip/local.yaml` from `/mb-start` routing. If a future
repair command must touch it, that command should:

1. Read the existing file first.
2. Merge changes into existing keys rather than replacing the whole file.
3. Preserve unknown keys for forward compatibility.
4. Ask before changing defaults that affect future sessions.
5. Show the planned write before applying it.

**Never use full-file overwrite commands like:**
```bash
cat > ~/.config/vip/local.yaml
```

That pattern can silently delete fields (like `user.*`, `vip_path`, or future keys).

---

## Fallback Chain

Config is always optional. Skills work without it.

```
1. If CWD has current `core/`, use CWD and current repo facts.
2. If CWD has old `reference/core`, `reference/offers`, or `reference/domain`
   without `core/`, run `mb status --json --peek` and `mb doctor repair --plan`
   from that CWD before saved config or discovery. Treat old paths as
   migration input only.
3. Try legacy local.yaml only when CWD and current settings do not identify a
   current repo or old repo migration input.
4. Use `mb status --json --peek`, `mb connect`, and repo files for current facts
5. Path invalid? → attempt session-only recovery, then rediscover
6. Parse error? → warn, then rediscover
```

**Principle:** Config is a speed optimization, not a requirement.

---

## Config Hygiene (Stale Path Handling)

Users rename folders, move repos, or clone to new locations. Config paths go stale. `/mb-start` must handle this gracefully — a normie user won't know to say "fix my config."

### Validation Rule

**Before presenting ANY repo as a numbered option, verify the path exists:**

```bash
if test -d "[path]/core"; then
  echo "current"
elif test -d "[path]/reference/core" || test -d "[path]/reference/offers" || test -d "[path]/reference/domain"; then
  echo "old-repo-needs-repair"
else
  echo "invalid"
fi
```

Never show a dead path. Never load a dead path and show "0/18 EMPTY" for a repo that simply moved.

### Recovery Algorithm

When a config path is invalid:

1. **Check parent directory** — if the parent exists, the folder was likely renamed
2. **Scan siblings** — look for current `core/` in adjacent folders
3. **If match found** — tell the user: "Looks like **[old-name]** moved to
   **[new-name]**. I'll use that for this session."
4. **If no match** — silently drop the stale entry from the list

### Stale Entry Handling

After validation, hide stale paths from the option list for this session. Do
not write the cleaned list back to legacy `local.yaml` from `/mb-start`.

### Common Scenarios

| What Happened | What User Sees | What /mb-start Does |
|---------------|---------------|-------------------|
| Folder renamed | Nothing broken | Detects new name, uses it for this session, presents correct option |
| Folder deleted | Fewer options | Prunes dead entry, shows only valid repos |
| Folder moved to new parent | "Switch to different repo" | Can't auto-detect across parents — user provides new path for this session |
| Clone to new machine | Empty config | Normal discovery flow — no stale paths to worry about |

---

## User Must Always Have Choice

**Even with valid saved config, `/mb-start` must list ALL validated repos from `recent_repos`:**

> "Found your repos:
>
> 1. [default-repo-name] (saved default)
> 2. [other-repo-name]
> 3. Switch to different repo
>
> (hit a number)"

If only one repo: show it plus "Switch to different repo."

**After switching:** Keep the selected repo session-scoped unless a current
`mb` command exposes an explicit persistence path.

**Never auto-proceed without asking.** The saved default is a suggestion, not a lock-in.
