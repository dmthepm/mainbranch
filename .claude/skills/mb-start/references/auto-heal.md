# Auto-Heal: Bridge Link Recovery

When a user launches Claude in their business repo and skills aren't showing, this file provides the self-repair logic. It's readable via `additionalDirectories` file access even when skills aren't discoverable.

---

## When This Runs

This runs in two places:

1. **Bootstrap path:** a user or support agent can read this when `/mb-start` is missing.
2. **Main `/mb-start` path:** when `/mb-start` is invoked from Main Branch, it resolves a selected business repo and runs this repair against that repo.

---

## Step 0: Set target repo

Always target the business repo explicitly:

```bash
REPO_PATH="[absolute-path-to-business-repo]"
test -d "$REPO_PATH" || echo "BAD_REPO_PATH"
```

If running directly inside the business repo, set:

```bash
REPO_PATH="$PWD"
```

---

## Step 1: Find engine path

If the `mb` CLI exists, prefer the packaged repair path. It handles pipx
installs and clone-based installs, writes `settings.local.json`, creates
bridge links, and updates `.gitignore`:

```bash
if command -v mb >/dev/null 2>&1; then
  mb skill link --repo "$REPO_PATH"
fi
```

Then verify Step 3. If it passes, skip the manual symlink loop below.

```bash
ENGINE_PATH=$(REPO_PATH="$REPO_PATH" python3 -c "
import json, os
with open(os.path.join(os.environ['REPO_PATH'], '.claude/settings.local.json')) as f:
    dirs = json.load(f).get('permissions', {}).get('additionalDirectories', [])
for d in dirs:
    if os.path.isfile(os.path.join(d, '.claude/skills/mb-start/SKILL.md')):
        print(d); break
" 2>/dev/null)
echo "ENGINE_PATH=$ENGINE_PATH"
```

If empty: `settings.local.json` is missing or doesn't point to Main Branch. Tell the user to run `mb skill link --repo "$REPO_PATH"` if the CLI is installed, or manually create `REPO_PATH/.claude/settings.local.json`:

```json
{
  "permissions": {
    "additionalDirectories": ["/absolute/path/to/mainbranch"]
  }
}
```

---

## Step 2: Create skill bridge links

```bash
mkdir -p "$REPO_PATH/.claude/skills"

# Per-skill symlinks (preserves local custom skills)
for d in "$ENGINE_PATH"/.claude/skills/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  [ -e "$REPO_PATH/.claude/skills/$n" ] || ln -s "$d" "$REPO_PATH/.claude/skills/$n"
done
```

---

## Step 2.5: Update .gitignore

Main Branch machine-local files and skill bridge links must not be committed.
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

**Why `.claude/skills/mb-*` (not `.claude/skills/`):** Users have custom skills (deck, pr-review, etc.) that ARE tracked. Ignoring the whole folder would hide those. Every Main Branch skill is named `mb-*`, so one line covers them, and a release that adds a skill adds no line. The line also ignores anything else named `mb-*` there, so the `mb-` prefix is reserved for Main Branch skills; files already tracked stay tracked. Older repos may keep per-skill lines such as `.claude/skills/start`; link never removes lines, so delete one by hand if you want to reuse that name for your own skill.

**Idempotent:** link adds only missing lines and never removes any, so
existing `.gitignore` lines are not duplicated.

---

## Step 3: Verify

```bash
test -e "$REPO_PATH/.claude/skills/mb-start" && echo "HEAL_OK" || echo "HEAL_FAILED"
```

---

## Step 4: Tell the user

If HEAL_OK:
> "I've set up the skill bridge links. **Please restart Claude** (Ctrl+C, then `claude`) — skills like `/mb-start` will appear in the dropdown on next launch."

If HEAL_FAILED:
> "Auto-repair failed. Run `/mb-update` or `mb update --repo .` first, then try
> `mb skill link --repo .` again. If `mb update` is unavailable because this is
> an old `0.1.x` install, bootstrap once with `pipx upgrade mainbranch`. If you
> cloned the engine, check that the path in `.claude/settings.local.json` is
> correct."

---

## Why this is needed

`additionalDirectories` in `settings.local.json` grants file access to Main Branch but does not reliably trigger slash-command discovery in Claude Code. Runtime smoke on Claude Code 2.1.126 returned `Unknown command: /mb-start` after the project-local `.claude/skills/mb-start` bridge was removed while `additionalDirectories` still pointed at the engine. Bridge links (symlinks from `.claude/skills/[name]` to Main Branch skill directories) make Claude discover skills as if they're local.

---

## What the links look like

```
business-repo/.claude/
├── settings.local.json                              # Real file (used by Claude Code)
├── skills/                                          # Real directory
│   ├── mb-start -> /path/to/mainbranch/.claude/skills/mb-start  # Symlink (bridge)
│   ├── mb-ads -> /path/to/mainbranch/.claude/skills/mb-ads      # Symlink (bridge)
│   ├── my-local-skill/                              # Real dir (preserved)
│   └── ...
├── lenses/                                          # Real directory
│   ├── ftc-compliance.md -> /path/to/mainbranch/... # Symlink (bridge)
│   └── ...
└── reference/                                       # Real directory
    ├── compliance -> /path/to/mainbranch/...        # Symlink (bridge)
    └── ...
```

Local custom skills are never overwritten — the `[ -e ] || ln -s` guard skips anything that already exists.
