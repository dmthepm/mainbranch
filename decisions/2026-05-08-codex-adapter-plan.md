---
type: decision
date: 2026-05-08
status: accepted
topic: Codex adapter plan without duplicating the skill system
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-03-skill-distribution-and-migration.md
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/401
participants: [Devon, Codex]
tags: [runtime-adapters, codex, skills, cli, decision-needed]
---

# Codex Adapter Plan

> Status note: Stage 1 shipped as the first Codex adapter. Fresh business repos
> include `AGENTS.md`, and `mb doctor`, `mb status`, and `mb start` expose Codex
> readiness. This decision remains the staging plan; current public support
> wording lives in
> [docs/compatibility.md](../docs/compatibility.md).
>
> Status note, MAIN-434 / #709: the proven Codex path is generated Main Branch
> guidance delivered by the global Codex plugin and grounded in deterministic
> `mb` facts. `/mb-*` remains a desired future command surface. See
> [docs/compatibility.md](../docs/compatibility.md) for current claims and
> [Codex Slash-Command Bridge](2026-05-23-codex-slash-command-bridge.md) for the
> command-bridge decision.

## Decision

Main Branch should pursue Codex support in stages, but the next release train
should only implement an **experimental CLI-first Codex adapter** if it
implements anything at all. Do not claim Codex workflow parity yet.

The adapter should preserve the existing boundary:

- `mb` remains the deterministic control plane for repo shape, status,
  validation, graph facts, provider readiness, repair, update, and checkpoint
  planning.
- Runtime instructions and skills remain the judgment layer. They route the
  operator, synthesize business context, ask before writes, and translate
  technical facts back into business language.
- Codex support is not a single yes/no claim. It has at least three levels:
  CLI-callable compatibility, experimental runtime workflow support, and
  supported parity.

The canonical workflow-source strategy should be **one workflow corpus with
runtime-neutral core instructions plus generated runtime discovery**, not one
hand-maintained Claude tree and a second hand-maintained Codex tree. Main
Branch's current bundled skills already use `SKILL.md` with `references/`,
`scripts/`, and frontmatter, but they live under `.claude/skills` and still
carry Claude-specific assumptions. Stage 2 should prove whether that tree can
remain the canonical source or whether the durable source should move to a
runtime-neutral `skills/` corpus that generates Claude and Codex adapters.
Codex supports a compatible `SKILL.md` directory shape, but compatible format
does not mean identical runtime behavior.

## Facts At Decision Time

Main Branch facts:

- Claude Code is the only supported runtime today.
- Codex CLI has a first adapter for power users. Fresh business repos include
  generated `AGENTS.md`; `mb doctor`, `mb status`, and `mb start` expose Codex
  readiness; no installed command or workflow parity was claimed at the time.
- `mb start --json`, `mb status --json`, generated business `CLAUDE.md`, and
  generated business `AGENTS.md` are the current runtime handoff surfaces.
- Claude Code discovery depends on project-local `.claude/skills/mb-*` bridge
  links. `.claude/settings.local.json` grants engine file access but does not
  by itself prove slash-command discovery.
- There is no Codex skill-link command or broad Codex workflow parity in this
  repository today.

Codex facts from official docs:

- Codex CLI runs locally from the terminal and can inspect a repository, edit
  files, and run commands in the selected directory.
- Codex reads `AGENTS.md` before work. It layers global guidance from
  `$CODEX_HOME`, then project guidance from the repository root down to the
  current working directory, with nearer files appearing later in the combined
  prompt.
- Codex does not treat generated business `CLAUDE.md` as a first-class
  instruction file unless a user has configured fallback filenames locally. A
  reliable Main Branch Codex path needs generated `AGENTS.md` or an equivalent
  Codex-native instruction surface.
- Codex supports `codex -C <dir>` / `codex exec -C <dir>` for working-directory
  selection and `--add-dir` for additional writable roots.
- Codex exposes `codex exec` for non-interactive runs, with JSONL output and
  output-file options that can support smoke tests.
- Codex supports Agent Skills: a skill is a directory with `SKILL.md` plus
  optional `scripts/`, `references/`, `assets/`, and `agents/`.
- Codex scans repository skills under `.agents/skills` from the current working
  directory up to the repository root, plus user/admin/system locations. It
  follows symlinked skill folders.
- Codex plugins bundle reusable skills, apps, and MCP servers. Repo and
  personal marketplace files can point at local or Git-backed plugin sources.
- Codex CLI, IDE extension, app, web/cloud tasks, and GitHub Action are
  different surfaces. Evidence for one surface does not prove support for all
  of them.

Local Codex capability evidence:

- Locally, `codex-cli 0.128.0` is installed and `codex --help`,
  `codex exec --help`, `codex features list`, and `codex plugin marketplace
  --help` expose the expected working-root, sandbox, approval, plugin, and
  non-interactive surfaces.

## What "Codex Support" Means

This decision used these staged terms in public docs and implementation PRs at
the time. Current support language lives in
[docs/compatibility.md](../docs/compatibility.md).

| Level | Meaning | Allowed public claim | Required evidence |
|---|---|---|---|
| CLI-callable compatibility | Codex can run packaged `mb` commands when launched in or pointed at a business repo. | "Codex can call deterministic `mb` JSON facts manually." | Existing package install plus local command evidence. This is not runtime support. |
| Stage 1 instruction-file adapter | `mb` can generate or repair Codex-facing repo instructions and handoff metadata, and Codex can ground a fresh business repo in `mb status --json --peek`. No skill parity claim. | "Stage 1 Codex adapter for power users." | Fresh `mb onboard` repo, generated `AGENTS.md`, read-only `codex exec --json --ephemeral --sandbox read-only -C "$repo"`, no tracked secret/runtime state, no business write without approval. |
| Experimental workflow adapter | Codex can discover selected Main Branch Agent Skills from one canonical source through `.agents/skills` or a Codex plugin package. | "Selected Main Branch workflows are experimental in Codex." | Stage 1 evidence plus selected skill invocation, repo-boundary checks, generated-file rules, and known gaps. |
| Supported parity | Codex covers the daily `/mb-start`-equivalent loop and selected production workflows with release-simulation evidence comparable to Claude Code. | "Codex is a supported Main Branch runtime." | Full adapter contract, install/update/repair docs, fixture repo smoke, runtime transcript review, and release gate. |

Do not describe Codex as supported because `mb` is a CLI, because Codex can read
Markdown, or because Codex and Claude both understand `SKILL.md`.

## Why Not Claim Support Immediately?

Some research points in the ecosystem are encouraging: `AGENTS.md` is a common
repo-instruction file, Agent Skills are converging around `SKILL.md`, and Codex
can discover repo skills under `.agents/skills`. That makes Main Branch
well-positioned, but it does not erase the adapter work.

Do not take the shortcut of copying or symlinking every current
`.claude/skills/mb-*` directory into `.agents/skills` and calling Codex
supported. That would fail the repo's runtime-honesty standard for four
reasons:

- many current skills still teach Claude Code slash-command discovery,
  Claude-specific restart/repair behavior, or Claude subagent patterns;
- concrete examples include generated `CLAUDE.md`, `/mb-start` invocation
  guidance, `.claude/settings.local.json`, project-local `.claude/skills`
  bridge-link repair, and Task/subagent references in lifecycle and production
  skills;
- Codex invocation syntax and user discovery are different from Claude
  slash commands;
- Codex runtime files, plugin caches, user skills, and project skills need
  their own generated-file and precedence rules;
- no fresh business repo has yet proved Codex reads Main Branch instructions,
  grounds itself in `mb status --json --peek`, preserves repo boundaries, and
  asks before writes.

Mirroring skills may become the right Stage 2 implementation detail. It is not
enough for a Stage 1 support claim.

## Staged Plan

### Stage 1: Experimental CLI-First Adapter

Goal: let a power user start Codex in a business repo and get deterministic
Main Branch facts before advice, without skill parity.

This can move quickly. The first slice is generated `AGENTS.md`,
runtime-aware handoff/readiness metadata, and a fresh-repo read-only Codex
smoke. It should not include broad skill mirroring, README support claims, or
multi-runtime parity.

Implementation shape:

- Add a generated business-repo `AGENTS.md` template or a runtime-neutral
  generated instructions template that Codex can read.
- Teach the template the same control-plane contract as generated
  `CLAUDE.md`: run `mb status --json --peek` before routing, use `mb start
  --json`, use `mb doctor repair --plan`, ask before writes, and translate
  results into business language.
- Add a runtime handoff shape for Codex in `mb start --json` or a focused
  `mb runtime codex`/`mb codex` command. Keep it deterministic; do not invoke
  a model.
- Add `mb doctor` / `mb status` readiness facts for Codex only after there is
  something real to check: executable availability, generated `AGENTS.md`
  presence, and documented repair command.
- Keep generated Codex runtime files out of tracked business truth unless they
  are durable repo instructions. Local Codex preferences, credentials, caches,
  and plugin installs stay outside the business repo or in gitignored local
  files.
- Treat generated business `AGENTS.md` as tracked durable repo instruction,
  owned by `mb init` / `mb onboard` and repairable through the relevant
  runtime-wiring repair command. Treat Codex plugin installs, `.agents/skills`
  bridge links, caches, and local runtime preferences as rebuildable runtime
  wiring unless a later adapter decision explicitly marks a file tracked.
- Keep `AGENTS.md` small enough to be always-on bootstrap guidance. It should
  teach the operator contract and the `mb` fact sources, not inline every
  Main Branch workflow. Workflow detail belongs in Agent Skills or referenced
  files loaded on demand.

Likely files:

- `mb/mb/_data/templates/AGENTS.md.tmpl` or a shared template source that can
  render both `CLAUDE.md` and `AGENTS.md`.
- `mb/mb/init.py` and `mb/tests/test_init.py` if business repo scaffolding
  writes the new instructions.
- `mb/mb/start.py`, `mb/mb/status.py`, and possibly `mb/mb/onboard.py` if the
  handoff/status envelope becomes runtime-aware.
- `docs/compatibility.md` only after the experimental adapter and smoke
  evidence exist.

Minimum smoke:

```bash
tmpdir="$(mktemp -d)"
mb onboard --yes --name "Codex Smoke Business" --path "$tmpdir/codex-business" --json
cd "$tmpdir/codex-business"
mb doctor
mb status --json --peek
mb start --json
codex exec --json --ephemeral --sandbox read-only --ask-for-approval never -C "$PWD" \
  "Start this Main Branch business day. Run only read-only mb checks and do not edit files."
git status --short
```

Pass condition:

- Codex sees the generated repo instructions.
- Codex runs or accurately uses read-only `mb` facts before advice.
- Codex identifies the business repo as the working repo, not the engine repo.
- No tracked files change during read-only smoke.
- Any write, repair, update, migration, checkpoint, provider mutation,
  publishing, spending, or customer contact path requires explicit operator
  approval.
- Optional local diagnostics may use `codex debug prompt-input` to inspect
  loaded instructions, but debug output is helper evidence, not the public smoke
  gate.

Maintenance cost: low to medium. Expect one generated template, one handoff or
runtime module, focused `init`/`start`/`status` tests, and one Codex smoke path.
The support risk is limited because there is no second skill tree yet.

Recommendation: worth pursuing as the first implementation slice after this
design is accepted.

### Stage 2: Generated Codex Workflow Entrypoints

Goal: expose selected Main Branch workflows to Codex without hand-copying every
Claude skill into a second tree.

Implementation shape:

- Treat the current `SKILL.md` layout as the near-term canonical workflow
  source because Codex supports the same Agent Skills directory structure.
- Make shared skill prose runtime-neutral where possible: say "the active
  runtime" or "this skill" when the instruction is not Claude-specific.
- Keep runtime-specific invocation syntax in thin adapter sections or generated
  wrappers:
  - Claude Code users invoke `/mb-start`.
  - Codex users may rely on implicit skill activation or explicit skill
    mention/selection through Codex's skill UI.
- Add adapter metadata where it earns its keep, such as:
  - `loops`
  - `requires_mb_commands`
  - `writes_business_files`
  - `provider_mutation`
  - `publishing_or_spend`
  - `runtime_notes`
- Generate or link Codex discovery from the canonical source:
  - repo-local `.agents/skills/mb-*` bridge links for business repos, or
  - a Codex plugin package with `.codex-plugin/plugin.json` and marketplace
    metadata, or
  - both, with one clear default.
- Start with lifecycle skills such as `mb-start`, `mb-status`, `mb-help`,
  `mb-update`, and `mb-setup`. Defer production workflows such as `mb-site`,
  `mb-ads`, `mb-organic`, `mb-vsl`, and `mb-end` until their runtime-specific
  subagent, provider, and checkpoint assumptions are audited.
- Extend `mb skill validate` so the canonical skill source can be checked for
  portable Agent Skills rules as well as Claude-specific rules.
- Preserve Claude Code support. Codex changes must not break `.claude/skills`
  bridge links or the Claude invocation contract.

Likely files:

- `.claude/skills/mb-*/SKILL.md` and references as the current source to
  normalize.
- A future source or generator if the project moves canonical skills out of
  `.claude/skills`.
- `mb/mb/engine.py` or a new runtime adapter module for Codex skill linking.
- `mb/mb/skill_validate.py` for portable skill metadata and runtime-specific
  lint gates.
- Packaging metadata such as `.codex-plugin/plugin.json` and
  `.agents/plugins/marketplace.json` if plugin distribution is chosen.

Maintenance cost: medium. Expect runtime-neutral skill cleanup, generator or
plugin packaging code, portable-skill validation, selected lifecycle skill
smokes, stale-install diagnostics, and docs for generated files. The support
risk is hidden Claude-specific language inside a shared skill.

Recommendation: defer broad workflow linking until Stage 1 passes and one
small lifecycle skill, probably `mb-start`/`mb-status`, has been made
runtime-neutral enough to test in Codex.

### Stage 3: Parity And Runtime Simulation Gate

Goal: make Codex a supported runtime for the daily owner loop and selected
production workflows.

Implementation shape:

- Extend the Claude Code dogfood harness pattern with a Codex lane.
- Add Codex simulation prompts for:
  - fresh first day;
  - messy thought dump;
  - ask-before-writing decision;
  - writing skill without silent saves;
  - checkpoint discipline;
  - broken Codex wiring/repair;
  - private-data refusal;
  - legacy repo drift.
- Use `codex exec` for repeatable proxy evidence where possible.
- Use an interactive Codex CLI or app smoke when the claim depends on runtime
  UI discovery, skill selection, plugin installation, or human invocation.
- Document known differences from Claude Code instead of hiding them behind a
  generic "runtime support" label.

Maintenance cost: high. Every supported workflow now needs release-simulation
coverage in at least two runtimes, transcript review, docs/support copy,
adapter-specific repair paths, and explicit handling for Codex features that do
not map to Claude Code one-for-one.

Recommendation: do not attempt Stage 3 until Stage 1 is boring and Stage 2 has
proved at least one lifecycle workflow in Codex.

## Canonical Source Strategy

Do not maintain two divergent copies of every skill.

Preferred path:

1. Use the current `.claude/skills/mb-*` directories as the near-term workflow
   corpus only while Stage 2 proves whether they can be made runtime-neutral
   enough.
2. If Stage 2 shows the Claude path is too load-bearing, move the canonical
   corpus to a runtime-neutral `skills/mb-*` tree and generate both
   `.claude/skills` and Codex discovery from it.
3. Normalize skill prose so shared instructions are runtime-neutral.
4. Isolate runtime-specific invocation details into small adapter sections or
   generated wrappers.
5. Generate runtime discovery:
   - Claude Code: existing `.claude/skills/mb-*` bridge links.
   - Codex: future `.agents/skills/mb-*` bridge links and/or Codex plugin
     package.

Rejected paths:

- Hand-copying `.claude/skills` into `.agents/skills`.
- Rewriting all workflows as Codex-specific prompts.
- Making `mb` invoke Codex, Claude, or any model directly.
- Claiming parity from a symlink alone.

If plugin packaging becomes the Stage 2 default, prefer the pattern used by
mature cross-runtime plugin packages: one shared `skills/` directory, thin
runtime manifests such as `.codex-plugin/plugin.json` and
`.claude-plugin/plugin.json`, root marketplace metadata for local discovery,
and tooling that syncs version/metadata across manifests. Avoid a model where
`.claude/skills`, `.agents/skills`, `.cursor/skills`, and plugin copies are
hand-maintained separately.

## What Stays In `mb`

These must remain CLI/JSON contracts, not prompt-only checks:

- repo shape and schema markers;
- migration and repair plans;
- status, drift, onboarding, recent activity, GitHub task/proposal signals,
  bets, pushes, provider readiness, and ranked actions;
- graph and cross-reference validation;
- update freshness and install-mode-aware repair;
- runtime wiring inspection;
- checkpoint planning and validation;
- provider readiness and safe connection metadata.

If a Codex skill needs stable machine-readable data that `mb` does not expose,
the follow-up should add the deterministic CLI/JSON contract first.

## Product Claims

Allowed now:

- "Main Branch's `mb` CLI is runtime-agnostic and can be called by automation
  or future runtime adapters."
- "Codex is a compatibility target."
- "Codex can manually call deterministic `mb` commands when pointed at a
  business repo, but there is no supported Main Branch Codex adapter yet."

Allowed after Stage 1 smoke:

- "Main Branch has an experimental Codex CLI-first adapter for power users."
- "Codex can start from generated repo instructions and read `mb` JSON facts."

Allowed after Stage 2 smoke:

- "Selected Main Branch Agent Skills are experimental in Codex."
- Name the exact workflows that passed smoke. Do not imply full parity.

Allowed after Stage 3:

- "Codex is a supported Main Branch runtime" only for the workflows and
  platforms covered by the adapter contract and release evidence.

Never claim:

- "Codex support" without naming the support level.
- "All Claude skills work in Codex" without per-workflow evidence.
- "Runtime agnostic" as a user-support claim.

## Comparable Project Lessons

Primary-source-backed lessons:

- Codex, OpenHands, Cursor/Cline-style tools, and similar repo agents all make
  repo instruction files useful. Lesson: generate `AGENTS.md` for Codex.
  Non-claim: `AGENTS.md` does not prove workflow support.
- Codex skills, Claude Code skills, OpenHands skills, and the Agent Skills
  ecosystem use a compatible `SKILL.md` shape. Lesson: one workflow source is
  plausible. Non-claim: runtime invocation, permissions, and subagent behavior
  are not identical.
- Continue, Cursor/Cline-style rules, Roo modes, Goose subagents, and Claude
  plugins separate rules, skills, workflows, hooks, tools, and permissions.
  Lesson: keep always-on repo guidance separate from invoked workflows and
  deterministic `mb` commands. Non-claim: Main Branch should not adopt any one
  runtime's mode system as its core abstraction.
- Cross-runtime plugin repos with `.codex-plugin`, `.claude-plugin`, and
  `.agents/plugins/marketplace.json` show the useful packaging pattern: shared
  `skills/`, thin runtime manifests, and metadata/version sync. Non-claim:
  plugin install by itself does not prove Main Branch workflow parity.
- Broader multi-runtime packages that copy skills into many runtime-specific
  folders expose the risk: sync scripts, path patches, stale caches, symlink
  variance, and feature matrices where hooks, agents, slash commands, and
  auto-start differ. Lesson: generate and validate adapter outputs if copying
  is unavoidable.

Pattern observations from local/public package inspection:

- Some cross-runtime plugin packages keep one shared `skills/` directory and
  add thin `.codex-plugin`, `.claude-plugin`, and marketplace manifests. This
  is the cleanest Stage 2 packaging model if Main Branch wants plugin
  distribution.
- Some broader multi-runtime packages copy skills into runtime-specific
  folders and patch path text during sync. This can move quickly, but it
  creates exactly the drift risk MAIN-276 is meant to avoid.

## Source Review

Primary/runtime sources used:

- [Codex CLI](https://developers.openai.com/codex/cli)
- [Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md)
- [Codex Agent Skills](https://developers.openai.com/codex/skills)
- [Codex Plugins](https://developers.openai.com/codex/plugins)
- [Codex plugin build docs](https://developers.openai.com/codex/plugins/build)
- [Codex CLI slash commands](https://developers.openai.com/codex/cli/slash-commands)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Agent Skills overview](https://agentskills.io/)
- [OpenHands Agent Skills and Context](https://docs.openhands.dev/sdk/guides/skill)
- [OpenHands Plugins](https://docs.openhands.dev/sdk/guides/plugins)
- [Continue Agent Mode](https://docs.continue.dev/features/agent/how-it-works)
- [Aider conventions](https://aider.chat/docs/usage/conventions.html)

Local evidence:

- `codex --version` returned `codex-cli 0.128.0`.
- `codex --help` exposed `-C/--cd`, `--add-dir`, sandbox modes, approval
  policies, web search, MCP, plugins, and non-interactive subcommands.
- `codex exec --help` exposed `--ephemeral`, `--ignore-user-config`,
  `--ignore-rules`, `--json`, and `--output-last-message`.
- `codex features list` showed skills/plugins/subagents-related features in
  the installed CLI.
- Local repository inspection confirmed no current Codex adapter files or
  generated business `AGENTS.md` exist in Main Branch.

Additional research considered but not adopted as claims:

- "Mirror all skills and call Codex supported" is too aggressive without smoke
  evidence and runtime-language cleanup.
- "Codex, Cursor, and any Agent Skills-compatible runtime are supported via
  shared skills" is a future target, not a current public claim.
- "Use Codex `/goal` to implement complete support in one run" may be useful
  for a future implementation workspace, but it should not change the public
  support level or skip adapter evidence. Treat `/goal` as a contributor
  productivity path, not a product claim.
- `codex exec --json --ephemeral --sandbox read-only -C "$repo"` is the durable
  proxy evidence for Stage 1. `codex debug prompt-input` remains useful local
  diagnostic evidence, but interactive runtime discovery or plugin installation
  still needs interactive evidence when the support claim depends on it.

## Acceptance Checklist

- Distinguishes CLI-callable compatibility from runtime workflow support:
  covered in "What Codex Support Means."
- Explains how to avoid divergent skill copies: one workflow corpus with
  runtime-neutral core instructions plus generated runtime discovery, with
  hand-copying rejected.
- Names the minimum viable Codex smoke: Stage 1 fresh-repo smoke commands and
  pass conditions.
- Includes maintenance-cost estimates: each stage names implementation,
  evidence, and support burden.
- Recommends the first implementation slice: Stage 1 generated `AGENTS.md`,
  runtime-aware handoff/readiness, and read-only Codex smoke.
- Preserves the public/private boundary: no local-only paths, private repos,
  customer/member data, credentials, or unsupported runtime claims belong in
  committed docs.

## Follow-Up Issues To Open

1. **Implement experimental Codex CLI-first adapter.**
   - Generate business-repo `AGENTS.md` or shared runtime instructions.
   - Add Codex handoff metadata and readiness checks.
   - Add smoke evidence using read-only
     `codex exec --json --ephemeral --sandbox read-only -C "$repo"`.

2. **Make lifecycle skills runtime-neutral enough for Codex discovery.**
   - Start with `mb-start` and `mb-status`.
   - Keep Claude invocation syntax in adapter sections.
   - Extend `mb skill validate` for portable Agent Skills metadata.

3. **Prototype Codex skill/plugin distribution.**
   - Compare repo-local `.agents/skills` bridge links with `.codex-plugin`
     packaging.
   - Document generated files, gitignore rules, install/update/repair paths,
     and conflict handling.

4. **Add Codex runtime smoke harness.**
   - Reuse the Claude dogfood fixture shape.
   - Use `codex exec` for proxy runs.
   - Define when interactive Codex CLI/app evidence is required.

5. **Update compatibility docs only after evidence exists.**
   - Promote Codex from roadmap to experimental only for the exact support
     level proven by the implementation PR.
