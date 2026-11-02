# Engine Path Resolution

Standard resolver for locating the Main Branch package or source checkout from a Claude Code session running inside a business repo. Used by `/mb-start`, `/mb-update`, `/mb-setup`, `/mb-help` troubleshooting, and any reference file that needs to read installed Main Branch files.

**Single source of truth.** Other reference files MUST link here rather than inline the snippet — the resolver semantics (and the order of fallbacks) need to stay in lockstep across the engine, and inline copies drift.

---

## Resolution order

1. **`.claude/settings.local.json` → `permissions.additionalDirectories`** (preferred). The directory passed to Claude Code via `additionalDirectories` is the default loading mechanism for Main Branch in Phase 2. No external config needed; pure filesystem.
2. **`~/.config/vip/local.yaml` → `vip_path`** (fallback). For users who haven't yet migrated to `additionalDirectories`, or whose `settings.local.json` is missing / malformed.

The first valid path that contains `.claude/skills/mb-start/SKILL.md` wins.

---

## The standard bash + python3 snippet

```bash
# Standard engine resolution (settings.local.json first; no extra deps)
ENGINE_PATH=$(python3 -c "
import json, os
try:
    with open('.claude/settings.local.json') as f:
        dirs = json.load(f).get('permissions', {}).get('additionalDirectories', [])
    for d in dirs:
        if os.path.isfile(os.path.join(d, '.claude/skills/mb-start/SKILL.md')):
            print(d); break
except: print('')
" 2>/dev/null)

# Fallback: check ~/.config/vip/local.yaml (needs PyYAML)
if [ -z "$ENGINE_PATH" ] || [ ! -f "$ENGINE_PATH/.claude/skills/mb-start/SKILL.md" ]; then
  ENGINE_PATH=$(python3 -c "
import os
try:
    import yaml
    with open(os.path.expanduser('~/.config/vip/local.yaml')) as f:
        print(yaml.safe_load(f).get('vip_path', ''))
except: print('')
" 2>/dev/null)
fi
```

After this block, `$ENGINE_PATH` is either a valid Main Branch package or
source-checkout path, or empty.

**Always validate before use:**

```bash
[ -n "$ENGINE_PATH" ] && [ -f "$ENGINE_PATH/.claude/skills/mb-start/SKILL.md" ] && \
  <command using $ENGINE_PATH>
```

---

## Why two fallbacks (not one)

- **`additionalDirectories`** is the default mechanism — it requires zero extra config, works without PyYAML, and gives the harness explicit knowledge of the engine path. It also works cleanly in workspace-isolated environments.
- **`~/.config/vip/local.yaml`** is the legacy mechanism that pre-dates `additionalDirectories`. We keep it as a fallback so existing users don't break on engine upgrades; it also serves users whose `settings.local.json` got reset by a tool like Claude Desktop's permission wipe.

The order matters: `settings.local.json` is harness-authoritative, `local.yaml` is best-guess. If both exist and disagree, the harness path wins because that's the path Claude Code is actually authorised to read.

---

## Failure modes and recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| `$ENGINE_PATH` is empty | Neither fallback resolved | Run `mb skill link --repo .`, then restart Claude. Use `~/.config/vip/local.yaml` only as a legacy fallback. |
| `$ENGINE_PATH` set but `.claude/skills/mb-start/SKILL.md` missing | Stale config pointing at a deleted / renamed checkout | Run `mb skill link --repo .`; it rewrites `.claude/settings.local.json` to the active Main Branch path and removes stale Main Branch paths. |
| `python3` not found | Minimal environment | Document as a setup prerequisite (every Main Branch user needs python3 in `$PATH`). |
| `yaml` import fails (fallback path only) | PyYAML not installed | The fallback is best-effort. Surface the underlying message and fall through to "no engine found" recovery. |
| Resolved path readable but `git pull` fails | Auth / network / locked-file | Run `mb update --check --repo .` and show the update-failure warning (network, auth, locked file). |

---

## When to inline vs. when to link

**Inline is correct only when:** the snippet needs a small modification for the local context (e.g., looking up a different skill's SKILL.md as the canary file, or following a different fallback chain).

**Link is correct when:** the snippet would be a verbatim copy. In that case, point at this file and let the caller's bash sub-shell run the snippet.

A reference file that inlines the resolver and *also* customises it should comment the customisation explicitly so it doesn't drift back into the standard version on a future refactor.

---

## Callers that link to this file

- `mb-setup/references/cwd-detection.md`

If you add a new caller, link here. Do not copy the snippet inline.
