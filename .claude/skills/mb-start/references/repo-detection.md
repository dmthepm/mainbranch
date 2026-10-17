# Repo Detection (Step 2)

CWD-first detection of the business repo. The user starts Claude in their
business repo — check current `core/` first, then old repo migration
fingerprints, before falling back to old local config.

---

## CWD Detection (Primary — Fast Path)

```
1. Check CWD for business repo fingerprint:
   test -d "core"
   ├── YES → This IS the business repo. Use CWD. Skip to config loading.
   └── NO → Continue to step 2.

2. Check CWD for old Main Branch repo fingerprints:
   test -d "reference/core" / "reference/offers" / "reference/domain"
   ├── YES → This is an old Main Branch repo. Use CWD as migration input.
   │          Run mb status --json --peek and mb doctor repair --plan.
   │          Do not call old paths current. Do not write to them.
   └── NO → Continue to step 3.

3. Check CWD for Main Branch source-checkout fingerprint (old workflow):
   test -f ".claude/skills/mb-start/SKILL.md"
   ├── YES → User is in a Main Branch source checkout (old workflow). Trigger migration guidance.
   └── NO → Continue to step 4.

4. Fall back to legacy machine-local config:
   Read ~/.config/vip/local.yaml → default_repo + recent_repos
   ├── Found valid repo(s)? → Present options (see below)
   └── Nothing valid? → Discovery or /mb-setup
```

### Migration Guidance (Step 2 - User Is in Main Branch Source)

> "It looks like you're running Claude inside the Main Branch source folder. The recommended workflow is now to run Claude from your business folder instead.
>
> 1. **Quick switch:** Close this session, `cd [their-repo-path]` then `claude` then `/mb-start`
> 2. **Need setup help?** `/mb-setup` will configure everything
> 3. **Continue here anyway** (some features may need manual paths)"
>
> If `~/.config/vip/local.yaml` has `default_repo`, show that path in option 1.

---

## Config Loading

Once business repo is identified (from CWD or legacy config), load current
facts through `mb`:

```
1. Run mb status --json --peek
   ├── OK? → Use status facts for readiness, drift, providers, onboarding, and routing
   └── Fails? → Use mb doctor repair --plan --json for repair guidance

2. If legacy .vip YAML exists
   ├── Run mb doctor repair --plan --json to audit key families
   └── Do not treat .vip/config.yaml as current team settings

3. If CWD was selected because old reference paths exist without core/
   ├── Keep CWD as the migration input for mb status/doctor
   ├── Tell the operator to follow the repair/migration plan
   └── Do not write new business truth into reference/*
```

---

## Multi-Repo Selection (When CWD Is NOT a Business Repo)

If CWD detection fails (step 4 above), present options from legacy local
config:

**Validate EVERY path before showing it to the user.** Never present a dead
path as an option. For each path in `default_repo` and `recent_repos`, check
`test -d "[path]/core"`. If invalid, check for old `reference/core`,
`reference/offers`, or `reference/domain`; if present, describe the path as an
old Main Branch repo that needs the repair/migration plan before use. Hide
other invalid paths for this session and explain that the old local fallback
may be stale. Do not rewrite legacy config during repo detection. See
[config-system.md](config-system.md) for fallback rules.

**ALWAYS present numbered options** — even with ONE repo found:

> "I found this business repo:
>
> 1. [repo-name]
> 2. Another one (tell me the path)
> 3. Create new (`/mb-setup`)
> 4. I'm confused (`/mb-help`)
>
> Which one? (hit a number)"

**MULTIPLE found:** List all, then options 2-4 above.

**NONE found:** Ask user for path, or route to `/mb-setup`.

### Discovery Algorithm (When No Config)

Use fallbacks in order:

1. **Scan additionalDirectories** for paths containing current `core/`
2. **Use bash to find repos** (if step 1 fails)
   ```bash
   find ~/Documents/GitHub -maxdepth 3 -type d \( -name "reference" -o -name "core" \) -print 2>/dev/null
   ```
3. **Ask the user** (if nothing found)

**Verify with Read, not Glob:** Use `Read` on `[path]/core/soul.md` to confirm it's a current business repo. `soul.md` belongs in `core/` for current repos. If only old `reference/core`, `reference/offers`, or `reference/domain` exists, treat the folder as migration input and run the repair plan before any normal workflow.

**Skip the Main Branch source checkout** - any path containing `.claude/skills/mb-start/SKILL.md` is not the operator's business folder.

---

## When CWD IS the Business Repo (Happy Path)

No repo selection needed. Confirm briefly and move on:

> "Working in **[repo-name]**."

---

## Required Repo Variable

After repo detection/selection, set one repo variable and use it everywhere:

```bash
REPO_PATH="[absolute-path-to-selected-business-repo]"
```

**Rule:** All business-folder operations must target `REPO_PATH` (not implicit CWD). This is critical when `/mb-start` is invoked from a Main Branch source checkout and the selected business folder is elsewhere.

Legacy `~/.config/vip/local.yaml` may name a default or recent repo. Treat it
as a fallback suggestion only, not the current writable repo registry. If the
operator chooses a different repo, keep that choice session-scoped unless a
current `mb` command exposes an explicit persistence path.

If user name or experience is missing, ask only when needed for the current
answer. Do not write the answer into legacy YAML.

Do not create or update `[repo]/.vip/config.yaml` during repo detection. Older
repos may have it; audit it with `mb doctor repair --plan --json`.

---

## Verify Main Branch Is Loaded (Config + Skill Bridge Links)

After detecting the business repo, confirm Main Branch is accessible and `/mb-start` bridge exists in the selected repo (`REPO_PATH`):

```bash
# 1. Resolve engine path from selected repo's settings.local.json
ENGINE_PATH=$(test -f "$REPO_PATH/.claude/settings.local.json" && REPO_PATH="$REPO_PATH" python3 -c "
import json, os
with open(os.path.join(os.environ['REPO_PATH'], '.claude/settings.local.json')) as f:
    dirs = json.load(f).get('permissions', {}).get('additionalDirectories', [])
for d in dirs:
    if os.path.isfile(os.path.join(d, '.claude/skills/mb-start/SKILL.md')):
        print(d); break
" 2>/dev/null)

# 2. Check /mb-start bridge exists in selected repo
test -e "$REPO_PATH/.claude/skills/mb-start" && echo "START_BRIDGE_OK"
```

**If `additionalDirectories` missing:** run `mb skill link --repo "$REPO_PATH"`, then restart Claude.

**If bridge links missing** (but `additionalDirectories` exists): run the standard repair from [auto-heal.md](auto-heal.md), targeting `REPO_PATH`.

Before the repair command succeeds, describe the bridge repair as a proposed step. After it succeeds, name the command that ran, say the missing bridge links in **[repo-name]** were repaired, and ask the operator to restart Claude Code from that repo and try `/mb-start`.

**If `/mb-start` was invoked from a Main Branch source checkout:** always run this verification block for the selected `REPO_PATH` before routing. This is the migration safety net for existing users.

**Why both are needed:**
- `additionalDirectories` = file access (read reference files, compliance docs)
- Bridge links = slash-command discovery for Main Branch skills
