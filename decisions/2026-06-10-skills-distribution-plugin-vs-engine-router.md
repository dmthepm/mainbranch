---
type: decision
date: 2026-06-10
status: proposed
topic: Skills distribution — native Claude Code plugin vs the engine router
linked_decisions:
  - decisions/2026-05-03-skill-distribution-and-migration.md
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
  - decisions/2026-05-13-shared-workflow-source-and-runtime-shells.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/236
  - https://github.com/dmthepm/mainbranch/issues/237
participants: [Devon, Claude]
tags: [skills, runtime-adapters, claude-code, plugins, distribution, worktrees]
---

# Skills Distribution: Native Claude Code Plugin vs the Engine Router

## Decision (Proposed)

Make the Claude Code plugin the primary distribution rail for bundled Main
Branch skills, installed and repaired through `mb`. Keep the engine router —
`mb skill link` symlinks plus `additionalDirectories` — as the repair fallback
during migration and for environments where plugins do not apply.

This finishes the direction the
[skill distribution decision](2026-05-03-skill-distribution-and-migration.md)
already accepted: symlinks short term, plugin destination next. The manifest
already ships — `.claude-plugin/plugin.json` is versioned with every release
and packaged into the wheel at `mb/_engine/.claude-plugin/` — so the remaining
work is wiring, smoke evidence, and migration, not invention.

The CLI contract does not change. `pipx install mainbranch`, `mb onboard`,
`mb update`, `mb doctor`, and `mb skill link` keep their names and exit codes.
What changes is what those commands wire underneath.

## Why Now: Skills Disappear In Claude Code Worktrees

The operator-reported failure — "my skills seem to disappear from the worktree
all the time in Claude Code" — is the router's design working as designed,
against a runtime feature it was never designed for.

The chain, with evidence:

1. `/mb-start` discovery requires the project-local bridge links.
   `additionalDirectories` alone is not enough; runtime smoke recorded
   `Unknown command: /mb-start` when the links were missing
   ([claude-code-invocation-contract.md](../docs/claude-code-invocation-contract.md),
   "Supported Path" and "Repair Contract" sections).
2. The router writes those links as machine-local, gitignored state.
   `link_skills()` (`mb/mb/engine.py:681`) creates `.claude/skills/<name>`
   symlinks and appends them to `.gitignore` under the
   `# Main Branch local Claude wiring` header (`mb/mb/engine.py:55`), alongside
   `.claude/settings.local.json` and `.claude/worktrees/`.
3. Claude Code runs sessions in git worktrees under `.claude/worktrees/`.
   Git materializes only tracked files in a new worktree. Gitignored wiring
   does not exist there: no skill links, no local settings.
4. Result: every fresh worktree session starts with an empty
   `.claude/skills/`, and skill discovery silently drops. Verified live on
   2026-06-10 in an operating business repo: the repo root holds 16 engine
   symlinks; its active Claude Code worktree holds an empty `.claude/skills/`.
5. The engine already knows. `mb doctor repair --apply --only claude` restores
   "start wiring … from this repo or worktree" (`mb/mb/doctor.py:2175-2191`,
   test at `mb/tests/test_doctor.py:355`). But that repair is manual and
   per-worktree. The operator experiences the steady state, which is: gone.

Root cause in one sentence: the router distributes skills as per-repo
untracked filesystem state, and Claude Code creates fresh per-session
checkouts that only carry tracked state.

### A second defect found while reproducing

`tests/test_engine.py::test_link_skills_removes_legacy_project_symlink` fails
on a clean `main` checkout (documented as pre-existing in #809/#810). The test
is right and the engine was wrong: `bundled_skills()` returned every directory
under the engine root's `.claude/skills/`, with no check that the directory is
a skill. A source checkout's engine root is a live working tree, and the
May 2026 `mb-` rename left residue directories (`start/`, `setup/`, `think/`)
holding only `.DS_Store` — invisible to `git status`, but real to
`link_skills()`. The function removed the legacy `start` project symlink and
then immediately re-created it from the residue. Fixed in this branch:
`bundled_skills()` now requires `SKILL.md` (`mb/mb/engine.py:100`), with
regression tests in `mb/tests/test_engine.py`.

The two defects share one shape: the router trusts live filesystem state —
the engine working tree on one side, per-repo untracked links on the other —
and live filesystem state drifts.

## Current State: The Four Layers

| Layer | What it is today | Anchors |
| --- | --- | --- |
| CLI | Deterministic control plane: onboard, init, status, start, doctor, update, validate, graph, connect, checkpoint, skill management. JSON contracts per [json-output-contract.md](../docs/json-output-contract.md). | `mb/mb/cli.py`, [AGENTS.md](../AGENTS.md) |
| Skills | Bundled Claude Code skills in `.claude/skills/mb-*`, shipped in the wheel at `mb/_engine/.claude/skills/`, routed into business repos by `link_skills()` symlinks + `.claude/settings.local.json` `additionalDirectories` + gitignore block. Shadow detection guards personal-skill precedence (`inspect_personal_skill_conflicts`, `mb/mb/engine.py:603`). Validation: frontmatter (`name`, `description`, `loops`), `mb-` prefix, 500-line gate (`mb/mb/skill_validate.py:18`). | `mb/mb/engine.py`, `mb/mb/skill_validate.py` |
| Playbooks | Engine-packaged recipes under `playbooks/<name>/playbook.md` with Claude shells under `.claude/playbooks/<name>/SKILL.md`; shells are read as files through engine access, not slash-discovered. Shared workflow sources under `workflows/` are the runtime-agnostic contract per the [shared workflow decision](2026-05-13-shared-workflow-source-and-runtime-shells.md). | `playbooks/`, `.claude/playbooks/`, `workflows/` |
| Repos/git | Business repo as the durable brain; hydration via `mb init`/`mb onboard` (`mb/mb/init.py`, `templates/`); checkpoints as hidden GitOps; GitHub issues/PRs as work threads; `.claude/worktrees/` gitignored. | [system-architecture.md](../docs/system-architecture.md) |

## Exemplar Patterns (Local Survey, 2026-06-10)

Five public skill-shipping repos, read from local checkouts:

| Repo | Distribution shape | What makes it durable |
| --- | --- | --- |
| `pbakaus/impeccable` | Marketplace repo: root `marketplace.json` + plugin payload at `./plugin` (`plugin.json`, `skills/`). Also commits `.claude/skills/impeccable` for direct project use, and generates per-harness dirs (`.codex`, `.cursor`, `.gemini`, …) from one source via transformer scripts. `HARNESSES.md` is a verified capability matrix. | Plugin installs to user scope; committed project skills are tracked files, so worktrees carry them. One source, many rendered adapters. |
| `mvanhorn/last30days-skill` | Single skill; `plugin.json` + `marketplace.json` at root (`source: "./"`); hooks dir. README leads with `/plugin marketplace add` + `/plugin install` "(auto-updates via marketplace)"; cross-agent via `npx skills add … -g`. | Marketplace is the update channel. No per-repo state to lose. |
| `EveryInc/compound-engineering-plugin` | Marketplace repo with `plugins/compound-engineering/` payload; ~40 skills, all `ce-` prefixed, prefix enforced in CI; version centralized and propagated to manifests by release script. | Namespace + prefix together; user-scope plugin cache; versioned updates. |
| `coreyhaines31/marketingskills` (Corey Haines) | Plain committed `skills/` + `plugin.json` (`skills: ./skills`) + `marketplace.json`. Installed via `npx skills add` (writes `.agents/skills/`, symlinks `.claude/skills/`), plugin marketplace, or SkillKit. `skills-lock.json` hashes for drift. | Skills are tracked content wherever they land; lockfile makes staleness detectable rather than silent. |
| `JuliusBrussee/caveman` | Plugin with hooks (`SessionStart`, `UserPromptSubmit`) using `${CLAUDE_PLUGIN_ROOT}`; one installer script that detects every agent on the machine and runs each agent's native path (plugin / extension / rule file / `npx skills add`). | Native rail per runtime, one installer UX on top — structurally `mb onboard`'s job. |

The pattern across all five: nobody distributes skills as per-repo untracked
symlinks. Skills are either (a) a versioned plugin installed at user scope, or
(b) tracked files committed where the runtime reads them. Both survive
worktrees, fresh clones, and new sessions, because both live where the runtime
actually looks — not in machine-local state a checkout has to regenerate.

What the router gains over the exemplars today: deterministic repair
(`mb doctor` can prove and fix wiring), one update channel (`pipx upgrade`
moves CLI and skills together), and no trust prompt at first run. What it
loses: worktree durability, collision protection (personal skills still
shadow project links; the namespace is the only documented escape), Windows
reliability, and staleness honesty (a copied fallback or leftover dir is
indistinguishable from truth — see the second defect above).

## Recommendation

Adopt the plugin rail. The operator's instinct is right, and the 2026-05-03
decision already named the destination; the worktree failure converts "likely
durable target" into "the current adapter fails the daily loop on a supported
runtime surface."

Keep `mb` as the only install surface the operator sees, per the strategic
posture already accepted: `mb onboard` writes the marketplace and plugin
enablement so the user never learns the word marketplace. The router does not
die; it narrows to (a) the repair/fallback path while migration is staged,
(b) clone-mode engine development, and (c) the pattern Codex global skills
already follow on their separate rail.

## Staged Migration Path

The CLI contract — command names, flags, exit codes, JSON envelopes — holds at
every stage.

- **Stage 0 (this branch).** Fix `bundled_skills()` residue trust. No user
  behavior change. Done.
- **Stage 1 — re-smoke the plugin.** #237 closed; re-verify against current
  Claude Code per the
  [runtime dogfood runbook](../docs/claude-code-runtime-dogfood.md): install
  from the shipped manifest, confirm whether invocation is `/mb-start` or
  `/mainbranch:mb-start`, confirm plugin-cache behavior for `references/`,
  scripts, and — critically — the engine surfaces skills read outside their
  own directories (see register, item 3). Record transcript evidence.
- **Stage 2 — parallel rail.** `mb onboard`/`mb init` gain an opt-in flag that
  writes plugin wiring (project-scope `.claude/settings.json`, tracked) while
  still writing symlinks. `link_status()` (`mb/mb/engine.py:757`) learns a
  plugin-aware definition of "wired" so `mb doctor`/`mb status`/`mb start`
  facts stay honest on both rails.
- **Stage 3 — default flip.** New repos default to plugin wiring. `mb update`
  adds a version handshake (CLI `__version__` vs installed plugin version) and
  a refresh path. `mb doctor repair` migrates symlink repos: remove the
  gitignore wiring block, drop the links, write plugin settings — plan first,
  apply on approval, consistent with the noob-safe migration rules in the
  2026-05-03 decision.
- **Stage 4 — retire symlink writes.** Keep detection and repair for old
  repos. Update [claude-code-invocation-contract.md](../docs/claude-code-invocation-contract.md),
  README, compatibility, and beginner docs in the same release.

The kill criteria from the 2026-05-03 decision stand unchanged: fresh-onboard
smoke, migrated-old-repo smoke, update freshness, beginner invocation
ergonomics, and doctor-repairable plugin state, or the flip does not ship.

## What Might Break — Register

1. **Skills routing (invocation names).** If plugin skills resolve only as
   `/mainbranch:mb-start`, every doc, generated `CLAUDE.md`, onboarding copy,
   and cross-skill route in SKILL.md prose that says `/mb-start` is stale at
   once. `mb skill validate` already parses slash routes
   (`mb/mb/skill_validate.py:368`) and can gate the rename mechanically.
   Stage 1 smoke answers which form is canonical before anything renames.
2. **Skills routing (shadow detection).** `inspect_personal_skill_conflicts`
   assumes project links are the active surface. Under the plugin, personal
   skills no longer shadow (namespace), but stale *project* links left behind
   become the new shadow risk — the detector inverts rather than retires.
3. **Engine surfaces outside skill directories.** `mb-ads` reads
   `.claude/lenses/` and `.claude/reference/compliance/` from the engine root
   (`.claude/skills/mb-ads/references/review-workflow.md`, "Context Files").
   That works today only because `additionalDirectories` grants engine file
   access. The plugin cache ships `skills: ./.claude/skills/` only — under a
   plugin-only install, lens review breaks silently. Resolution options:
   ship lenses inside the plugin payload and reference them through
   `${CLAUDE_PLUGIN_ROOT}` (the caveman pattern), or fold them into the
   skill's own `references/`. This is also a self-containment violation under
   the existing skill maintenance rules in [AGENTS.md](../AGENTS.md), so it
   needs fixing regardless of distribution rail.
4. **`mb update` flows.** Today `pipx upgrade` moves CLI and skills together
   and `mb update` relinks (`mb/mb/update.py:199,482`). Under the plugin,
   Claude Code owns the skill copy; CLI and plugin versions can skew. The
   Stage 3 handshake must make skew a visible `mb status`/`mb doctor` fact
   with an exact repair command, or stale-skill bugs become unreproducible.
5. **Skill line gates and validation.** `scripts/check.sh` and
   `mb skill validate` read the repo/engine root and keep working unchanged.
   New gap: nothing validates the *installed plugin cache*. Release discipline
   already bumps `.claude-plugin/plugin.json` per
   [release-agent-contract.md](../docs/release-agent-contract.md); add a
   release check that the published plugin payload matches the wheel payload.
6. **Business-repo hydration.** `mb init`/`mb onboard` call `link_skills()`
   (`mb/mb/init.py:143,235`, `mb/mb/onboard.py:1200`). Existing repos carry
   the gitignore wiring block as legacy state to clean. Fixture-repo and
   release-simulation tiers assume symlink wiring and need a plugin-path
   variant before the default flips.
7. **Playbooks and workflows that assume engine paths.** `.claude/playbooks/`
   shells and `workflows/` sources ride the wheel and are read through engine
   file access, not the plugin. Either they ship in the plugin payload too, or
   `additionalDirectories` survives the migration for file access only — in
   which case the settings write stays, and only slash discovery moves to the
   plugin. Decide this explicitly at Stage 1; do not let it happen by drift.
8. **Codex and shared workflow renderers.** Codex's global-skill rail is
   untouched, but drift checks that compare Claude shells under
   `.claude/skills/` to shared sources must keep pointing at the repo source,
   not at any plugin cache.
9. **Worktrees, still.** Plugin enablement written to *tracked*
   `.claude/settings.json` survives worktrees; anything left in
   `settings.local.json` does not. If file access via `additionalDirectories`
   survives for playbooks (item 7), worktree sessions still lose it — the
   doctor worktree repair stays load-bearing until that is resolved.

## Leveled-Up Model Opportunities

Parts of the system were shaped when agent runtimes and models needed more
scaffolding. Worth a deliberate keep/relax pass; verdicts proposed here, each
its own follow-up issue if accepted.

| Constraint | Built because | Verdict |
| --- | --- | --- |
| Router indirection (symlinks + settings + gitignore triple) | Plugins didn't exist; determinism had to be hand-built | **Replace** with the plugin rail (this decision). |
| Deterministic JSON fact contracts (`mb status --json` et al.) | Agents invented repo state | **Keep.** This is the product moat, not a model crutch. Stronger models make the facts more leveraged, not less needed. |
| 500-line SKILL.md gate | Context windows were tight; prose sprawled | **Keep the gate, relax the fear.** Progressive disclosure through `references/` works well with current models; the gate is now a discipline tool against context cost, and #809 shows it shaping work (rewriting in place to stay at exactly 500). |
| Legacy-name routing tables (`LEGACY_SKILL_NAMES`, `_KNOWN_UNPREFIXED_SKILL_ROUTES`, `RETIRED_PROJECT_SKILL_LINK_NAMES` in `mb/mb/engine.py:34-53`) | Pre-rename users needed soft landings | **Relax on a clock.** Plugin migration (Stage 3) is the natural sunset for most of this surface; carrying three name generations forever is drift fuel. |
| Step-by-step shell snippets inside skill prose | Models lost track of multi-step CLI sequences | **Relax selectively.** Keep exact commands for operator handoff and repair; trim agent-facing duplication where a JSON fact contract already exists (the skill-to-CLI contract already says this — enforce it during skill edits). |
| Shadow detection and backup machinery | Documented precedence made personal skills silently win | **Keep until Stage 4**, then narrow to stale-project-link detection (register, item 2). |
| Personal/legacy skill backups before any move | Beginner trust | **Keep.** Reversibility is product character, not model compensation. |
| `mb educational` layer | Operators (not models) need teaching | **Keep.** It was never a model crutch; do not confuse the two audiences when trimming. |

## Consequences

- The disappearing-skills complaint gets a structural fix, not another repair
  command.
- `bundled_skills()` is residue-proof as of this branch, which also protects
  locally built wheels from packaging rename leftovers.
- Item 3 of the register (lenses outside the skill directory) is real
  self-containment debt and should be fixed before or with Stage 1.
- `mb` remains the only surface an operator has to learn.

## Next Action

Review this proposal. If accepted, open the Stage 1 re-smoke issue with the
register's items 1, 3, and 7 as explicit questions the smoke must answer.
