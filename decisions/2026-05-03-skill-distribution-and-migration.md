---
type: decision
date: 2026-05-03
status: accepted
topic: Skill distribution and runtime migration model
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/236
  - https://github.com/dmthepm/mainbranch/issues/234
  - https://github.com/dmthepm/mainbranch/issues/237
  - https://github.com/dmthepm/mainbranch/issues/238
participants: [Devon, Codex]
tags: [v0-2, skills, runtime-adapters, claude-code, migration, decision]
---

# Skill Distribution and Migration Model

## Decision

**Architecture at a Glance**

- **Portable Core**: Workflows defined as `SKILL.md` files. Cross-runtime
  portability via the emerging open Skills standard is a roadmap target,
  not a guarantee, until verified per #238.
- **Primary Distribution (Claude Code)**: Official plugin package via
  Anthropic marketplace — namespaced, discoverable, versioned.
- **Short-Term Bridge**: Project-local symlinks plus
  `additionalDirectories` with mandatory shadow detection and
  noob-safe migration.
- **Orchestration Layer**: `mb` CLI as the user-facing entry point and
  runtime-agnostic orchestrator.
- **Quality Layer**: `mb-` vendor prefix plus automated lint plus
  explicit collision and shadow protection.

Main Branch should ship the **migration and shadow-detection repair path first**,
keep the current project-local Claude Code wiring as the short-term supported
adapter, and design an official Claude Code plugin package as the likely durable
distribution target.

The current `additionalDirectories` plus project-local bridge links are not a
dead end. Claude Code officially loads skills from added directories, and
project-local `.claude/skills/` folders are a documented discovery source. But
global `~/.claude/skills/<name>` entries take precedence over project skills, so
old global Main Branch symlinks can silently shadow the active business repo.
That is a migration problem before it is an architecture problem.

Do not return to global skill symlinks. Do not copy bundled skills into business
repos as the primary update model. Do not claim Codex, Cursor, OpenClaw, Hermes,
Paperclip-adjacent orchestration, or local runtime support until each has an
adapter and smoke evidence.

The plugin path is load-bearing for one reason in particular: **bundled
Main Branch skill names are generic and almost guaranteed to collide with
other authors' skills**. Plugin namespacing
(`<plugin-name>:<skill-name>`) is the only documented mechanism that
escapes Claude Code's personal-overrides-project precedence; it protects
Main Branch users from third-party skill authors and protects third-party
authors from Main Branch. See "Bundled Skill Name Collision Surface"
below.

## Recommendation

1. **v0.2 immediate:** implement stale global Claude Code skill detection and a
   noob-safe migration command. `mb doctor`, `mb start`, and `mb onboard` should
   warn or block before a stale global `/mb-start` can win silently. **In
   parallel, decide whether to rename bundled skills to a `mb-` prefix
   before the plugin spike lands.** Compound Engineering already enforces
   this pattern in CI for an existing public Claude Code plugin
   (`ce-debug`, `ce-plan`, `ce-setup`); the prefix is a cheap, reversible
   collision-shrinker independent of the plugin migration. See
   "Bundled Skill Renaming" below.
2. **v0.2 short term:** keep `mb skill link --repo .` as the Claude Code repair
   primitive. It should continue to write `.claude/settings.local.json` with the
   active engine root and create gitignored local bridge links.
3. **v0.2/v0.3 design target:** prototype a Claude Code plugin or marketplace
   package for Main Branch skills. Adopt it only after it preserves beginner
   `/mb-start` ergonomics, supports local or project scope cleanly, updates through
   a documented path, and passes runtime smoke from a fresh business repo plus a
   migrated old-user repo. The plugin spike must explicitly answer the
   bundled-skill-name collision question: do users invoke `/mb:start` or do we
   prove a plain-`/mb-start` alias works under the plugin namespace? Lock that
   answer before promoting plugin packaging to default.
4. **Runtime-general future:** define runtime adapters as separate tested
   contracts. The portable workflow source can stay runtime-neutral, but each
   runtime needs its own discovery, install, update, and smoke contract.

## Evidence

### Bundled Skill Name Collision Surface

The bundled Main Branch skills today live in `.claude/skills/` and ship in
the wheel at `mb/_engine/.claude/skills/`. The current names are:

```
ads     end     help    organic pull    setup   site
skill-brief-draft       skill-concept   skill-review
start   think   vsl     wiki
```

Most of these are aggressively generic English verbs and nouns. They are
almost certain to be claimed by other skill authors over time, and several
already conflict with extremely common patterns:

- `start`, `end`, `setup`, `pull`, `help` are session and lifecycle words
  that any onboarding, deployment, git-helper, or chat-bookend skill would
  reasonably claim;
- `site`, `ads`, `wiki`, `vsl`, `organic` are content-domain words that
  marketing, ops, and CMS-adjacent skill authors would reasonably claim;
- `think` collides with both Claude Code's documented `<thinking>` workflow
  language and any number of reasoning or research skills already published
  in the wider ecosystem.

Per the [Claude Code skills doc][skills-docs], any user-installed
`~/.claude/skills/mb-start` (whether created by another tool, another version
of Main Branch, or hand-written) silently overrides the project-local
`.claude/skills/mb-start` we wire from the business repo. This is documented
behavior, not a bug. Issue [#234][issue-234] addresses the Main-Branch-vs-
Main-Branch shadow case, but the collision surface is broader: a user can
install any personal or project skill named `start` and lose Main Branch's
`/mb-start` without warning.

The same doc states: *"Plugin skills use a `plugin-name:skill-name`
namespace, so they cannot conflict with other levels."* That is the only
collision-proof mechanism Anthropic documents. Renaming bundled skills to
something less generic (for example `mb-start`, `mb-end`) would reduce the
collision surface inside the current symlink wiring, but it would not solve
it: any third-party personal or project skill can still choose the same name if
no namespace is enforced. Plugin packaging encodes the publisher in the
namespace by default.

This is the strongest single argument for treating the Claude Code plugin
shape as the durable destination rather than as a nice-to-have. The
migration order in this decision is still symlink-first, plugin-next,
because the issue explicitly disallows rewriting wiring in this PR — but
the destination should not drift.

[skills-docs]: https://code.claude.com/docs/en/skills
[issue-234]: https://github.com/dmthepm/mainbranch/issues/234

### Evidence From Peer Claude Code Skill Repos

A short survey of public Claude Code skill repos confirms the collision
surface is real and shows two settled responses to it:

**Compound Engineering Plugin** (Every.to, `EveryInc/compound-engineering-plugin`)
ships as a single Claude Code plugin with a marketplace. It enforces a
`ce-` prefix on every bundled skill in CI: a commit titled
*"test: enforce ce- prefix on skills and agents (#748)"* gates contributions.
The actual skills look like `ce-commit`, `ce-code-review`, `ce-debug`,
`ce-plan`, `ce-setup`, `ce-update`, `ce-work`, `ce-worktree`, with one
intentional exception (`lfg`) for the orchestrator. Install command from
their README:

```text
/plugin marketplace add EveryInc/compound-engineering-plugin
/plugin install compound-engineering
```

Multi-platform manifests live side by side at `.claude-plugin/`,
`.codex-plugin/`, `.cursor-plugin/`. Versioning is centralized in
`package.json` and propagated to all platform manifests by a release
script. This is a worked example of "plugin packaging plus prefix
discipline" co-existing in production.

**Matt Pocock's `mattpocock-skills`** is the counter-example. Skills are
named `triage`, `tdd`, `diagnose`, `setup-pre-commit`, `caveman`,
`grill-me`, `zoom-out`, `to-issues`, `to-prd`, `improve-codebase-architecture`,
`write-a-skill`. There is no prefix and no namespace. The README documents
installation through Vercel's `npx skills@latest` CLI rather than
`/plugin install`. Where that installer actually writes files is not
verified in this research pass — if it installs as a plugin under
`~/.claude/plugins/`, the plugin namespace would still protect plain
`/mb-start`; if it copies files into personal `~/.claude/skills/` or project
`.claude/skills/`, those skills would shadow plain `/mb-start` per Claude
Code's documented precedence. Either way, Matt's `setup-pre-commit` is
adjacent enough to Main Branch's `setup` in user mindshare to confuse
operators who install both, regardless of which install channel wins.

**`get-shit-done`** ships ~30 commands all scoped under a `gsd:` prefix
(`/gsd:help`, `/gsd:new-project`, `/gsd:debug`). Distribution is via
`npx get-shit-done-cc`, which writes into either project `.claude/` or
global `~/.claude/`. Their answer to collisions is one parent prefix and
verbose subcommand names.

**Daniel Miessler's PAI** (`Personal_AI_Infrastructure`) prefixes every
distribution unit with `pai-` (`pai-core-install`, `pai-hook-system`,
`pai-observability-server`). Skills inside packs use domain-specific
names (`OSINT`, `Algorithm`, `Voice`).

**Daniel Miessler's Fabric** is a different shape (prompt patterns, not
skills) but informative on overrides: bundled patterns live in
`data/patterns/<name>/`, custom user patterns live in a separate
directory, and *user patterns take precedence over bundled patterns of
the same name*. Update is manual via `fabric -U`. This is the cleanest
override-layer pattern in the survey.

The settled industry answer for *cross-author collision* is some
combination of:

- a plugin/package namespace (`mb:start`, `compound-engineering:debug`);
- and/or a vendor prefix on every bundled name (`ce-debug`, `pai-core`,
  `gsd:help`).

The plugin namespace alone is not enough when users install through
non-marketplace channels (the Matt Pocock case). The vendor prefix alone
is not enough when third-party authors ship the same prefix or pick the
same name. The strongest production example in this survey
(Compound Engineering) does both.

This evidence does not change the recommendation's sequence — symlinks
now, plugin destination next — but it does change the prefix question
from "maybe later" to "decide before v0.2.5 plugin spike lands." See
"Bundled Skill Renaming" below.

### Bundled Skill Renaming

Renaming the bundled skills to a `mb-` prefix (`mb-start`, `mb-end`,
`mb-setup`, `mb-pull`, `mb-help`, `mb-site`, `mb-ads`, `mb-wiki`,
`mb-think`, `mb-organic`, `mb-vsl`, plus `mb-skill-brief-draft`,
`mb-skill-concept`, `mb-skill-review`) is a small, reversible change
that closes the collision surface even before plugin packaging lands.
The cost is one round of user-visible slash command churn (`/start`
becomes `/mb-start`). Plugin packaging would force the same churn
later (`/mb:start`), so the marginal cost of doing it now is small.

### Daily-Use UX Cost

The product reason this question is hard: Main Branch's promise to
non-technical operators is "open Claude Code, type `/start`, you're
running." Renaming bundled skills, or moving to plugin namespacing,
changes the daily ritual. That cost is real and should not be hand-waved.

What changes and what does not:

- **The `mb` CLI itself is unaffected.** `mb start`, `mb status`,
  `mb doctor`, `mb update`, `mb onboard` — every command at the terminal
  prompt — keeps the names it has today. The renaming question only
  touches in-Claude-Code slash commands.
- **The slash-command surface picks up extra characters.** `/start`
  becomes either `/mb-start` (prefix, with or without plugin packaging)
  or `/mb:start` (plugin namespace). Three to four extra keystrokes per
  invocation.
- **Claude Code slash autocomplete is the real mitigation.** A user who
  types `/m` and the bundled skills are the only `mb-`-prefixed entries
  on their machine generally sees the right command surface immediately.
  Worst case: type `/mb` and tab. The "hard to remember" hit lands
  mostly on first-time users who don't yet know to type the prefix at
  all — which is exactly where onboarding copy can do the work.
- **Plugin packaging would force the same churn later.** If we keep
  `/start` now and migrate to plugin packaging in v0.2.5, operators have
  to relearn the slash command then. Doing the rename once, in concert
  with plugin packaging, is one disruption rather than two.

What is honestly unknown:

- **Does Claude Code support a true slash alias** that lets `/start`
  resolve to a prefixed or namespaced skill in the absence of a same-named
  shadowing skill? This research pass did not verify a documented alias
  mechanism. Treating "alias works" as an assumption would be exactly
  the kind of unverified runtime claim the OSS operating checklist warns
  against. The plugin spike (#237) should produce smoke evidence on this
  before we decide whether to keep `/start` as a courtesy.
- **Where third-party non-marketplace installers (`npx skills add`,
  similar) actually write files.** Subsequently confirmed: the dominant
  Vercel-labs `npx skills@latest` installer writes plain non-namespaced
  skills to project `./.claude/skills/<name>/SKILL.md` (default) or
  `~/.claude/skills/<name>/SKILL.md` (`-g`). See the External Research
  Findings section below for the resolved evidence.

Open questions tied to renaming:

- Which prefix? `mb-` matches the CLI binary name. `mainbranch-` is more
  discoverable but verbose. `noontide-` ties to the publisher rather than
  the product. Recommendation in this doc: `mb-`, on the same grounds
  that compound-engineering chose `ce-` over `compound-engineering-`.
- If renaming lands inside symlink wiring (v0.2.4), does it help or hurt
  the v0.2.5 plugin migration? It probably helps: the diff between a
  symlink-wired `mb-start` and a plugin-packaged `mb-start` is "the
  wrapper changed," not "every name changed."

The honest framing for the maintainer is: keeping `/mb-start` is the cheapest
choice for users who never branch out beyond Main Branch's bundled skills,
and it is also the riskiest choice for the moment a user installs anything
else. The product north star ("make this easy for new people") points at
keeping the bare command. The collision evidence ("real third-party skills
named `triage`, `setup-pre-commit`, `tdd` already exist in public skill repos")
points at the prefix. The plugin spike (#237) is the right place to
resolve the tension because it is the only way to know whether a slash
alias rescues both goals at once.

This question is in scope for follow-up work but should be answered
before the v0.2.5 plugin spike.

### Strategic Posture: Distribution Channels

The Claude Code skills ecosystem has three competing distribution
channels in active use. Main Branch should pick a posture toward each
intentionally, not by drift.

**Anthropic plugin marketplace (`/plugin marketplace add`).**
The Anthropic-blessed channel. Plugins are versioned, namespaced,
auto-cached at `~/.claude/plugins/cache/`, and discoverable through
Anthropic's plugin surfaces. This is the highest-leverage exposure
channel for new audiences who already use Claude Code and browse for
plugins. Recommendation: **target this as the durable destination.**
Main Branch should publish its plugin manifest at
`dmthepm/mainbranch` and let users install via
`/plugin marketplace add dmthepm/mainbranch`. Discoverability,
trust signal, and namespacing all come for free.

**Vercel's `npx skills@latest` CLI.** A generic agent-skills installer
that targets multiple coding agents from a git repo containing a
`.claude-plugin/plugin.json` plus a skills folder. It is one of several
third-party installers in this space; it is not Anthropic infrastructure.
Per Vercel-labs's public docs, default install writes to project
`./.claude/skills/`; `-g` writes to personal `~/.claude/skills/`. Both
land as plain non-namespaced skills that participate in Claude Code's
documented precedence, which means a `-g` install can shadow a project-
local same-named skill. Recommendation: **be compatible, do not depend on.** If Main Branch ships
a clean plugin manifest, third-party installers that read that manifest
will work as a side benefit. We do not need to add an `npx mainbranch-skills`
shim — we already have `mb`. Two installer surfaces would split the
support story for no user gain.

**`mb` itself as the install surface.** This is the channel we already
own. `pipx install mainbranch` plus `mb onboard` plus `mb update` is a
deterministic, scriptable, runtime-aware install path. It is the channel
that makes the runtime-agnostic story credible: when we add Codex or
Cursor adapters later, `mb` is what wires them. Recommendation: **keep
`mb` as the canonical entry point.** When the plugin spike (#237)
lands, `mb onboard` should write the plugin marketplace and
`enabledPlugins` into project `.claude/settings.json` automatically, so
the user still types four commands (`pipx install`, `mb onboard`, `cd`,
`mb start --launch`) and never has to know the plugin marketplace exists.
Power users can run `/plugin install mainbranch` directly from any repo
if they prefer.

**npm/Node tooling more broadly.** Main Branch is a Python project
shipped via PyPI/pipx. Adding Node/npm to the install path doubles the
user's prerequisite surface (Python *and* Node) and doubles our packaging
maintenance. Recommendation: **no Node/npm in the install path.**
Compatibility with npm-based installers (Vercel skills, npx-style
plugin marketplaces, etc.) lands through the plugin manifest, not by
shipping a Node-side installer.

**Exposure read-through.** The plugin marketplace is the strongest
discoverability bet that does not depend on the maintainer's existing
audience. Publishing under `dmthepm/mainbranch` puts Main Branch in
the same surface where new Claude Code users find compound engineering
and similar tools. Three things compound this: a clean plugin manifest,
a vendor prefix (or namespace) that does not embarrass us when listed
next to `compound-engineering` and `mattpocock-skills`, and an `mb` CLI
that auto-wires the plugin so the user sees one command, not three.
Skipping the marketplace and staying on symlinks is a real choice — it
just means accepting that exposure to Claude Code users outside the
maintainer's existing audience is harder.

**What this does not decide.** Whether the plugin invocation form is
`/start`, `/mb-start`, `/mb:start`, or some alias resolves to live runtime
behavior the v0.2.5 spike (#237) must verify. This section commits to
the channel, not the keystroke count.

### External Research Findings (May 2026 pass)

A targeted research pass with a search-heavy assistant (Grok) returned
findings on the five open questions above. The validation framing in
that output was discounted — Grok has a known tendency to validate
existing direction. The substantive primary-source claims are folded in
below; the praise was set aside.

**Confirmed:**

- **Slash aliases — none exist.** No documented user-facing alias
  mechanism in the last 6+ months. Hardcoded built-in aliases only
  (`/compact` → `/reset`/`/new`). Open feature requests (Anthropic
  GitHub issues #14576 from late 2025 and #32785 from early 2026) are
  unmerged. **Implication:** keeping `/mb-start` working as a courtesy in
  parallel with `/mb-start` or `/mb:start` is not a documented option
  today. The renaming UX cost is real.
- **`npx skills@latest` writes plain non-namespaced skills.** Default is
  project scope `./.claude/skills/<name>/SKILL.md`; `-g` writes to
  `~/.claude/skills/<name>/SKILL.md`. Both paths are exactly the
  shadow-prone surfaces Claude Code's documented precedence covers, and
  the `mattpocock-skills` install path lands in personal scope when
  invoked globally. **Implication:** the Matt Pocock collision concern
  earlier in this doc is sharpened, not softened: those installs do
  produce plain `/mb-start` invocations that shadow project-local Main
  Branch skills under Anthropic's documented precedence rule.
- **Plugin marketplace discoverability surfaces.** Primary in-app surface
  is `/plugin` → Discover tab; primary public surface is
  `https://claude.com/plugins` (tied to `anthropics/claude-plugins-official`).
  Secondary community hubs reportedly include `buildwithclaude.com`,
  `claudepluginhub.com`, and `claudemarketplaces.com`; verifying their
  reach is not load-bearing for this decision. **Implication:**
  publishing under `dmthepm/mainbranch` reaches the in-app Discover
  surface only if the marketplace is added by the user (which `mb` can
  automate). Reach into the official `claude-plugins-official` listing
  is gated by Anthropic approval.
- **Anthropic posture is pro-ecosystem for compatible tools.** Third-
  party marketplaces are explicitly first-class via
  `/plugin marketplace add`. The April 2026 access restrictions Anthropic
  shipped targeted non-official "harnesses" that bypass the Claude Code
  binary, not plugins, skills, or MCP servers. **Implication:** Main
  Branch positioned as a CLI plus a plugin/skill bundle is on the safe
  side of Anthropic's policy stance; positioning it as a Claude Code
  replacement would not be.

**Still contradictory:**

- **Slash-command resolution under plugins.** Anthropic's skills doc
  states plugin skills require `plugin-name:skill-name` invocation and
  do not fall back to non-namespaced `/mb-start`. Compound Engineering's
  README and CHANGELOG both document and use bare `/ce-debug`,
  `/ce-plan`, `/ce-strategy` (see `README.md` lines 16–75 and
  `CHANGELOG.md` in `EveryInc/compound-engineering-plugin`). The external
  research suggests this
  works because the *skill name itself* is `ce-debug`, not because of a
  namespace fallback — meaning Compound is using the plugin shape only
  as a distribution wrapper, while the actual invocation depends on the
  prefix being baked into the skill name. That interpretation is
  plausible but is not directly confirmed by Anthropic's docs. **The
  v0.2.5 plugin spike (#237) must produce smoke evidence that resolves
  this directly**: install a plugin that ships a skill named `start`,
  verify whether `/start` or only `/mb:start` works, and verify whether
  a skill named `mb-start` inside the same plugin is invoked as
  `/mb-start` or `/mb:mb-start`. Treat any other interpretation as
  unverified.

**Flagged but not load-bearing:**

- An "Open Agent Skills standard" referenced as the shared `SKILL.md` +
  YAML frontmatter format that both Anthropic's Claude Code skills doc
  and OpenAI's Codex skills doc cite as "the open agent skills standard"
  Codex / Claude Code skills build on. The standard's existence as a
  shared format is therefore first-party from at least two runtime
  vendors and is not the part flagged for verification. What remains
  unverified in this pass is (a) Linux-Foundation alignment specifically,
  (b) the exact portability guarantees the standard makes about
  cross-runtime invocation, scoping, or update behavior, and (c) which
  other runtimes (Cursor, Gemini CLI, OpenCode, Windsurf, GitHub Copilot,
  etc.) fully implement it versus loosely consume `SKILL.md` files.
  Those three sub-questions belong to the runtime-adapter contract
  (#238) and should be answered before any compatibility doc claims a
  given non-Claude runtime is portable for free.
- A reported market shift from "install everything" toward curation and
  quality filtering ("install fatigue") was mentioned in the external
  research. It is consistent with what shows up in the local peer-repo
  survey (Compound's CI prefix gate, PAI's vendor prefix, get-shit-done's
  parent prefix) but is sentiment, not evidence. It does not change the
  decision; it only sharpens the framing that a vendor-prefix lint and
  collision-aware migration are the kinds of quality signals operators
  are asking for.

**Net effect on the recommendation.** The findings tighten three things
without changing the sequence:

1. The renaming question shifts from "decide before plugin spike" to
   "decide alongside plugin spike," because the resolution behavior
   determines whether the prefix lives on the skill name (Compound
   pattern, `/mb-start`) or only in the plugin namespace (Anthropic-doc
   pattern, `/mb:start`). Both produce roughly the same UX cost. The
   spike answers which form is canonical.
2. The `mattpocock-skills` shadow case is now confirmed concrete: their
   global install does land in `~/.claude/skills/`, and Claude Code's
   precedence rule does shadow project-local same-named skills. This
   moves shadow detection from "good hygiene" to "table stakes for
   shipping the plugin path."
3. Positioning Main Branch as a CLI plus plugin/skill bundle is
   long-term stable on Anthropic's policy stance. Positioning as a
   competing harness is not. Stay in the plugin lane.

### Current Main Branch Behavior

`mb` currently packages the Claude Code skill source inside the Python package
or source checkout and wires business repos through `mb.engine`:

- `mb/mb/engine.py` locates the active engine root, preferring packaged data
  over source checkout paths.
- `_write_settings()` writes `.claude/settings.local.json` with
  `permissions.additionalDirectories` pointing at the active engine root.
- `link_skills()` creates `.claude/skills/<name>` symlinks, or copies if
  symlinks fail, and gitignores the generated local wiring.
- `link_status()` requires both the active engine root in
  `additionalDirectories` and a project-local `.claude/skills/mb-start/SKILL.md`.
- `mb start`, `mb doctor`, `mb status`, and `mb onboard` all rely on
  `link_status()` and tell users to run `mb skill link --repo .` when wiring is
  missing.

This proves the current adapter is deterministic, scriptable, and repairable,
but it does not prove Claude Code will choose the intended skill when a personal
skill with the same name exists.

### Claude Code

Claude Code documents four skill locations: enterprise, personal
`~/.claude/skills`, project `.claude/skills`, and plugin skills. It also states
the precedence problem directly: enterprise overrides personal, personal
overrides project, and plugin skills use a plugin namespace so they cannot
conflict with the other levels.

Claude Code also documents that `--add-dir` primarily grants file access, but
skills are an exception: a `.claude/skills/` directory inside an added directory
is loaded automatically. Other `.claude/` configuration from added directories
is not loaded by default.

For reusable distribution, Claude Code now has a plugin system. Plugins can
bundle skills, agents, hooks, MCP servers, LSP servers, commands, executables,
and settings. Marketplaces provide discovery and version management. Plugin
install supports user, project, and local scopes; project scope writes to
`.claude/settings.json`, while local scope writes to `.claude/settings.local.json`.
Claude Code copies installed plugin directories into a cache, so plugin files
must be self-contained or refer to paths through plugin variables.

Sources:

- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code plugin discovery and marketplaces](https://code.claude.com/docs/en/discover-plugins)
- [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code plugin reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code settings scopes](https://code.claude.com/docs/en/settings)

### Codex

Codex has converged on a similar split:

- `AGENTS.md` is the repo instruction contract. Codex builds an instruction chain
  from global and project files, with closer files overriding broader guidance.
- Agent skills are the authoring format for repeatable workflows. Codex reads
  repo skills from `.agents/skills` along the current directory to repo-root
  path, user skills from `$HOME/.agents/skills`, admin skills from
  `/etc/codex/skills`, and system skills bundled with Codex.
- Codex explicitly says direct skill folders are for local authoring and
  repo-scoped workflows; reusable distribution should use plugins.

Sources:

- [Codex AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [Codex Agent Skills](https://developers.openai.com/codex/skills)
- [Codex plugins](https://developers.openai.com/codex/plugins)

### Other OSS Agent Tooling

Other serious tools show the same pattern with different file names:

- Cursor uses versioned project rules in `.cursor/rules`, global user rules,
  and `AGENTS.md` as a simple root-level alternative. Its legacy `.cursorrules`
  file remains supported but is deprecated.
- Cline uses project `.clinerules/`, global rules, skills, workflows, hooks, and
  `.clineignore`. It also recognizes `.cursorrules`, `.windsurfrules`, and
  `AGENTS.md` for cross-tool compatibility. Its docs recommend project storage
  for codebase-specific customization and global storage for personal
  preferences.
- Aider does not have a comparable skill package system. It recommends loading a
  small `CONVENTIONS.md` via `/read` or `--read`, and can always-load read-only
  convention files through `.aider.conf.yml`.

Sources:

- [Cursor rules](https://docs.cursor.com/en/context)
- [Cline customization overview](https://docs.cline.bot/customization/overview)
- [Cline rules](https://docs.cline.bot/customization/cline-rules)
- [Aider conventions](https://aider.chat/docs/usage/conventions.html)
- [Aider config](https://aider.chat/docs/config/aider_conf.html)

## Tradeoffs

### Project-Local Symlinks

Pros:

- Deterministic for `mb`; easy to create, inspect, test, and repair.
- Keeps business repos pointing at the active installed package or source
  checkout without committing generated runtime wiring.
- Works for pipx and clone installs with one `mb skill link --repo .` command.

Cons:

- Still loses to personal/global skills with the same name.
- Symlinks can be broken by moved installs, source checkout changes, Windows
  constraints, or filesystems without symlink support.
- Bridge links are Claude Code adapter details, not a portable Main Branch
  workflow format.

### Global Symlinks

Pros:

- One setup step can affect every repo.
- Convenient for a single technical maintainer.

Cons:

- Wrong scope for a business repo product: personal/global state can override
  repo-local truth.
- Stale links survive package updates and repo moves.
- Shadow failures are silent and beginner-hostile.

Global symlinks should be treated as legacy state to detect and migrate away
from, not a supported install target.

### Copied Skill Folders

Pros:

- No symlink support required.
- Easy to inspect from the business repo.

Cons:

- Copies become stale immediately unless every update refreshes them.
- Business repos would carry generated adapter artifacts rather than business
  truth.
- It blurs user-edited skills and packaged Main Branch skills.

Copy fallback is acceptable when symlink creation fails, but copied folders
should be detected as generated adapter state and refreshed or replaced by
`mb`.

### `additionalDirectories`

Pros:

- Officially supported for loading skills from an added directory.
- Lets installed package data remain the source of truth.
- Keeps generated business-repo state small.

Cons:

- It is primarily an access mechanism, not full configuration discovery.
- It does not load other `.claude/` configuration from the engine directory.
- It does not solve personal-skill precedence by itself.

Keep it short term because it is official and already tested, but pair it with
shadow detection and plan to replace the bridge with plugin packaging if the
plugin path proves better.

### Official Plugin Packaging

Pros:

- Current Claude Code and Codex docs both identify plugins as the reusable
  distribution unit for skills.
- **Namespacing is the only documented mechanism that prevents collisions
  with personal/global skills shipped by other authors.** Given how generic
  Main Branch's bundled skill names are (`start`, `end`, `setup`, `pull`,
  `help`, etc.), this stops being a nice-to-have and becomes the
  load-bearing reason to move.
- Plugin scopes make user, project, and local installs explicit.
- Marketplaces and plugin updates provide a real distribution story.

Cons:

- Plugin install/update is a runtime-specific operation that may require Claude
  Code version checks, trust prompts, marketplace setup, and runtime smoke.
- Plugin cache semantics require the package to be self-contained.
- Main Branch must verify beginner `/mb-start` ergonomics. If namespacing changes
  invocation from `/mb-start` to a qualified plugin command, that is a product
  cost, not an implementation detail.

Plugin packaging should be the target, not an untested rewrite.

## Noob-Safe Migration

The migration must be boring, reversible, and explicit.

`mb` should detect:

- global `~/.claude/skills/<bundled-skill>` entries for every bundled Main
  Branch skill name;
- whether each entry is a symlink, directory copy, or unexpected file;
- whether a symlink resolves to the active engine root, a different Main Branch
  engine root, a missing path, or an unrelated user-created skill;
- whether project-local `.claude/settings.local.json` points at the active
  engine root;
- whether project-local `.claude/skills/mb-start/SKILL.md` exists;
- whether copied project-local generated skill folders are stale relative to the
  active bundled skill set;
- Claude Code version or feature availability when plugin migration is later
  added.

`mb` should repair:

- generated project-local bridge links through `mb skill link --repo .`;
- stale global Main Branch symlinks by moving them to a timestamped backup
  directory only after explicit confirmation or `--apply`;
- stale generated project-local copied folders by replacing them only when `mb`
  can prove they are generated Main Branch adapter state;
- missing `.claude/settings.local.json` or missing `additionalDirectories`
  entries by rewriting the local settings file;
- post-update state by running the same detection after `mb update`.

`mb` should not repair:

- unrelated user-authored `~/.claude/skills/<name>` directories automatically;
- any global skill without a backup;
- anything requiring runtime/plugin trust prompts without telling the user what
  Claude Code will ask them to trust.

Suggested command split:

- `mb doctor`: detect shadows, mark stale global `/mb-start` as a hard runtime
  handoff problem, and print exact next commands.
- `mb start`: block handoff when stale global `/mb-start` is likely to win.
- `mb onboard`: run the same preflight before declaring setup complete.
- `mb skill link --repo .`: repair project-local wiring and report global
  shadows without modifying global state.
- `mb migrate runtime --check`: dry-run migration plan for runtime adapter
  state.
- `mb migrate runtime --apply`: perform reversible moves/backups for generated
  Main Branch runtime state only.

## Runtime Adapter Contract

Main Branch should not make the Claude Code adapter shape the product shape.
Each runtime should have an adapter manifest or equivalent code contract with:

- support level: supported, experimental, or roadmap;
- discovery sources and precedence;
- install/update command;
- local vs project vs global state locations;
- generated files and gitignore rules;
- shadow or stale-state detection;
- exact launch instructions for `mb start`;
- JSON status shape for `mb doctor` and `mb status`;
- required runtime smoke.

Initial adapter claims:

- Claude Code: supported today, with current project-local wiring and future
  plugin investigation.
- Codex: roadmap until `.agents/skills`, plugins, and `AGENTS.md` behavior are
  implemented and smoked against a business repo.
- Cursor: roadmap; likely maps to `AGENTS.md` plus `.cursor/rules`, but Main
  Branch should not claim workflow parity without testing.
- OpenClaw, Hermes, Paperclip-adjacent orchestration, and local runtimes:
  roadmap only. Paperclip-like systems should consume stable repo and JSON
  contracts rather than become the CLI's runtime model.

## Kill Criteria

Kill global symlink support if any release ships a migration path that can
detect, back up, and remove stale Main Branch global skill links safely.

Kill copied project-local skill folders as a normal path if package/install
smoke proves symlinks or plugin installs work across the supported OS matrix.
Keep copy fallback only for systems where symlinks are unavailable.

Kill the current `additionalDirectories` bridge as the primary Claude Code path
only when plugin packaging proves all of this:

- fresh `mb onboard` to Claude Code `/mb-start` works;
- an old-user repo with stale global skills migrates cleanly;
- `mb update` or documented Claude plugin update keeps skills current;
- beginner-facing invocation remains acceptable;
- `mb doctor`, `mb start`, and `mb onboard` can detect and repair broken plugin
  state;
- package/install smoke and Claude Code runtime smoke are recorded.

Kill the plugin path, or defer it, if:

- plugin namespacing makes `/mb-start` confusing for beginners without a clean
  alias;
- project or local scope cannot be automated or explained safely;
- marketplace setup adds more first-run friction than the current bridge;
- plugin caching breaks skill references, helper scripts, or packaged data;
- Claude Code plugin APIs change faster than Main Branch can validate.

## Follow-Up Work

Concrete follow-ups should be separate from this decision:

1. Implement [#234](https://github.com/dmthepm/mainbranch/issues/234):
   stale global Claude Code skill shadow detection and safe
   migration.
2. Add [#237](https://github.com/dmthepm/mainbranch/issues/237): a Claude
   Code plugin packaging spike with fresh-repo and migrated-repo runtime smoke.
3. Define [#238](https://github.com/dmthepm/mainbranch/issues/238): the
   first runtime adapter contract document or JSON shape before adding Codex,
   Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, or local runtime
   behavior.
4. Implement [#240](https://github.com/dmthepm/mainbranch/issues/240):
   rename bundled skills to a `mb-` vendor prefix alongside the #237
   plugin spike. Include a slash-alias smoke if Claude Code supports it;
   otherwise document the one-time UX change. Pattern reference:
   Compound Engineering's CI-enforced `ce-` prefix.
5. Implement [#241](https://github.com/dmthepm/mainbranch/issues/241):
   add bundled-skill-name lint to `mb` so future skills cannot ship
   without the chosen prefix (mirrors Compound Engineering's "test:
   enforce ce- prefix on skills and agents" gate).
6. Update compatibility docs only after adapter smoke changes what is supported.
