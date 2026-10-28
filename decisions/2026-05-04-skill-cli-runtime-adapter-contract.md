---
type: decision
date: 2026-05-04
status: accepted
topic: Skill-to-CLI and runtime adapter contract
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-03-skill-distribution-and-migration.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/220
  - https://github.com/dmthepm/mainbranch/issues/225
  - https://github.com/dmthepm/mainbranch/issues/238
  - https://github.com/dmthepm/mainbranch/issues/131
  - https://github.com/dmthepm/mainbranch/issues/124
  - https://github.com/dmthepm/mainbranch/issues/177
  - https://github.com/dmthepm/mainbranch/issues/127
participants: [Devon, Codex]
tags: [v0-2, cli, skills, runtime-adapters, claude-code, workflow-boundary]
---

# Skill-to-CLI and Runtime Adapter Contract

## Decision

`mb` is the deterministic control plane that skills and runtime adapters can
call before, during, and after judgment-heavy work. Skills and runtime adapters
may depend on `mb` for repo shape, validation, migration, update, status,
onboarding progress, connection metadata, graphing, and runtime wiring. They
must not reimplement those checks in prose or shell snippets when a stable
`mb` command exists.

Agent-runtime skills remain the judgment and conversation layer. They decide
what to ask, synthesize business context, write durable artifacts, and route the
operator. They may call `mb` to inspect state or perform mechanical repairs, but
they must not make `mb` responsible for model invocation, chat memory, retries,
streaming UI, or runtime-specific conversation branching.

Runtime adapters are explicit contracts, not compatibility intent. A runtime is
not supported until it has adapter code or documented wiring, command/JSON
contracts, generated-file and state rules, and smoke evidence from a fresh
business repo. Claude Code is the reference adapter today. Codex, Cursor,
OpenClaw, Hermes, Paperclip-adjacent orchestration, and local runtimes remain
roadmap targets until each clears that bar.

## Why This Exists

Main Branch now has real CLI primitives: `mb onboard`, `mb onboard status`,
`mb status`, `mb start`, `mb doctor`, `mb update`, `mb migrate`, `mb connect`,
`mb graph`, and `mb skill validate`. Skills should lean on those primitives so
future runtime adapters inherit the same deterministic surface.

The failure mode to avoid is a Claude-only product wearing runtime-agnostic
language. A second failure mode is skill prose that repeats old clone-era setup,
guesses at repo health, or preserves onboarding state only in conversation
memory. This contract keeps mechanical facts in `mb`, judgment in skills, and
compatibility claims tied to smoke evidence.

## Current Claude Code Reference Adapter

Claude Code is the only first-class runtime in v0.2.x.

The current adapter is implemented through these local surfaces:

- `mb/mb/engine.py` locates the active engine root, writes
  `.claude/settings.local.json`, creates project-local `.claude/skills/mb-*`
  bridge links, removes legacy project links, and detects personal skill
  shadows.
- `mb/mb/init.py` scaffolds business repos, writes `.gitignore`, creates
  `.mb/schema-version`, writes `CLAUDE.md`, and calls skill linking.
- `mb/mb/onboard.py` creates and inspects `.mb/onboarding.json` through
  `mb onboard`, `mb onboard plan`, and `mb onboard status`.
- `mb/mb/status.py` exposes repo, install, runtime, onboarding, integration,
  GitHub, and next-action state in a deterministic briefing.
- `mb/mb/start.py` checks repo shape, git state, update freshness, Claude Code
  presence, skill wiring, and shadow state before printing or optionally
  launching `claude`.
- `mb/mb/update.py` owns install-mode-aware engine refresh and skill relinking.
- `mb/mb/skill_validate.py` validates bundled skill frontmatter, references,
  line-count, and `mb-` prefix discipline.

The current Claude Code adapter writes these business-repo files:

| Path | Owner | Git rule | Purpose |
|---|---|---|---|
| `CLAUDE.md` | `mb init` / user | tracked | Project instructions and safe runtime context. |
| `.claude/settings.local.json` | `mb skill link` | gitignored | Local Claude Code `additionalDirectories` engine pointer. |
| `.claude/skills/mb-*` | `mb skill link` | gitignored | Project-local bridge links to bundled skills. |
| `.mb/schema-version` | `mb init` / `mb migrate` | tracked | Business-repo schema marker. |
| `.mb/onboarding.json` | `mb onboard` | gitignored | Lightweight onboarding progress and resume state. |
| `.mb/connect.yaml` | `mb connect` | tracked when present | Safe provider metadata only, never credentials. |
| `.mb/backups/` | `mb migrate` / repairs | gitignored | Local backups and repair artifacts. |

Claude Code behavior is grounded in the official runtime docs:

- [Claude Code skills](https://code.claude.com/docs/en/skills) describe
  personal, project, and plugin skill locations; precedence; plugin
  namespacing; and discovery from added directories.
- [Claude Code plugins](https://code.claude.com/docs/en/plugins) describe
  `.claude-plugin/plugin.json`, plugin skill directories, and namespaced skill
  invocation.

Per those docs, personal skills override project skills with the same name, and
plugin skills use a namespace such as `/plugin-name:skill-name`. That is why the
current adapter must keep shadow detection and why the durable Claude Code
distribution target is namespaced plugin packaging rather than global symlinks.

## Skill-to-CLI Boundary

Skills must call or trust `mb` for deterministic state:

- repo shape and schema: `mb doctor`, `mb validate`, `mb migrate`;
- daily readiness and GitHub/task context: `mb status --json`;
- runtime handoff readiness: `mb start --json`;
- engine freshness and relinking: `mb update --json`;
- onboarding progress: `mb onboard status --json`;
- onboarding plan updates: `mb onboard plan ... --json`;
- provider metadata and repair hints: `mb connect status --json`,
  `mb connect doctor --json`;
- graph/index context: `mb graph --json`;
- bundled skill integrity: `mb skill validate --all --json`;
- skill discovery repair: `mb skill repair --repo .` and
  `mb skill link --repo .`.

Skills own judgment-heavy work:

- deciding which missing input to ask for first;
- interpreting business context, voice, proof, and constraints;
- writing research, decisions, campaign artifacts, scripts, sites, reviews, and
  session summaries;
- choosing whether to route to another skill or keep working in the current
  skill;
- explaining tradeoffs to the operator in the active runtime conversation;
- asking for human approval before spending money, publishing, or mutating
  external accounts.

Skills must not:

- silently copy old clone-era setup instructions when a current `mb` command
  exists;
- store resume-critical setup progress only in chat memory;
- ask users to commit secrets, raw exports, full finances, or credentials;
- rely on sibling-skill relative paths or absolute local paths;
- claim a non-Claude runtime works because the skill prose looks portable;
- shell out to model providers through `mb`.

## Lifecycle Skill Audit

Lifecycle skills are the session and setup surface. They should be thin over
`mb` for mechanical facts and thick on conversation, routing, and explanation.

| Skill | CLI contract it should rely on | Skill-owned judgment |
|---|---|---|
| `/mb-start` | `mb update --json`, `mb onboard status --json`, `mb status --json`, `mb start --json`, `mb connect status --json` | repo selection prompts, readiness interpretation, intent routing, and bounded onboarding collection |
| `/mb-setup` | `mb onboard`, `mb onboard plan`, `mb onboard status`, `mb skill link`, `mb doctor` | teaching the repo model and collecting only setup inputs the CLI cannot infer |
| `/mb-update` | `mb update --repo . --json` | summarizing the latest changelog and telling the user when to restart the runtime |
| `/mb-pull` | legacy alias to `/mb-update` | compatibility copy only |
| `/mb-end` | `mb status --json`, git status/log commands until a first-class end-session CLI contract exists | summary, crystallize questions, commit narration, and session closure |
| `/mb-help` | `mb doctor --json`, `mb status --json`, `mb educational <topic>` | diagnosing confusion and choosing the most useful next action |

Lifecycle skills should prioritize resumability. `/mb-start` and `/mb-setup`
must use `mb onboard status --json` when onboarding may be incomplete. The
progress file is operational state, not business truth; accepted business truth
still belongs in `core/`, `research/`, `decisions/`, `bets/`, `pushes/`, `log/`,
or `documents/`. Legacy `campaigns/` records remain compatibility reads, not
the current write target for coordinated work.

## Production Skill Audit

Production skills generate or review business work. They should call `mb` for
preflight state and then operate against repo files.

| Skill | CLI contract it should rely on | Skill-owned judgment |
|---|---|---|
| `/mb-think` | `mb status --json`, `mb graph --json`, `mb validate --json`, tool/provider status from `mb connect` when relevant | research routing, synthesis, decision framing, and codification |
| `/mb-ads` | `mb status --json`, `mb connect status --json` for ad/provider readiness, `mb validate --json` for repo sanity | copy generation, compliance review, substantiation, and creative critique |
| `/mb-vsl` | `mb status --json`, `mb graph --json` | script strategy, offer/audience interpretation, and voice matching |
| `/mb-organic` | `mb status --json`, `mb connect status --json` for social/research providers when relevant | platform judgment, content mining, and output adaptation |
| `/mb-site` | `mb status --json`, `mb connect status --json`, `mb validate --json` | brief generation, design/generation flow, deployment gates, and review loops |
| `/mb-wiki` | `mb status --json`, `mb graph --json`, `mb validate --json` | note creation, knowledge structure, and publishing choices |
| `mb-skill-*` helper skills | `mb skill validate --all --json` for structural checks | drafting and reviewing skill content or site concepts |

When a production skill needs stable machine-readable data that `mb` does not
yet expose, the follow-up is to add or document the CLI/JSON contract first.
Do not bury the deterministic check in a skill-only shell snippet unless it is
clearly experimental and the skill says so.

## Runtime Adapter Contract

Each runtime adapter must document and implement the following before moving
out of roadmap status.

### 1. Discovery

The adapter must define:

- how `mb` detects the runtime executable, plugin, project config, or local
  endpoint;
- how `mb doctor`, `mb status`, and `mb start --json` report found/missing,
  version when cheaply available, and repair commands;
- how the runtime discovers workflow files;
- how skill/command names are invoked by a human inside that runtime;
- how conflicts, shadowing, or stale global installs are detected.

### 2. Install and Update

The adapter must define:

- the supported install modes;
- the command users run to install or update the runtime-side package;
- whether `mb update` can refresh the adapter deterministically;
- whether a runtime restart or reload is required after relinking;
- the fallback when the runtime is missing or authenticated state cannot be
  verified.

### 3. State and Generated Files

The adapter must list every file it creates or expects, including:

- repo-relative path;
- owner (`mb`, runtime, user, or skill);
- tracked vs gitignored rule;
- whether it may contain secrets or raw business data;
- repair or regeneration command.

Runtime-local preferences and credentials must stay outside the business repo
or in gitignored local files. Canonical business truth stays in tracked business
files. Rebuildable indexes, local caches, runtime wiring, and progress records
need explicit repair paths.

### 4. Runtime-Aware CLI Hooks

The adapter must expose enough state for:

- `mb doctor` to explain what is broken and which command repairs it;
- `mb status --json` to include runtime readiness and next actions;
- `mb start --json` to include handoff command metadata and whether execution
  was attempted;
- skill-fronting `mb` commands to emit runtime-aware hints without invoking a
  model.

### 5. Smoke Evidence

The minimum smoke for a new supported runtime is:

1. install or enable the adapter from a clean environment;
2. create a fresh business repo with `mb onboard --yes`;
3. run `mb doctor`, `mb status --json`, and `mb start --json`;
4. launch the runtime from the business repo;
5. verify the runtime discovers the Main Branch entry skill/workflow;
6. invoke the entry workflow and prove it reads the business repo, not the
   engine repo;
7. verify generated local/runtime files obey the documented gitignore and
   secret rules;
8. record exact commands, versions, and limitations in the PR.

If authentication or UI constraints block the runtime launch, the PR must say
that explicitly. CLI tests alone do not prove runtime support.

## Support Levels

Use these terms in public docs and PRs:

| Level | Meaning | Release gate |
|---|---|---|
| Supported | Expected to work for users. Regressions block release. | Adapter contract plus fresh-repo runtime smoke. |
| Experimental | May work for power users. Breakage is tracked but not a launch blocker. | Documented adapter shape plus at least one local/manual smoke with known gaps. |
| Roadmap | Product target only. No user support claim. | No adapter or insufficient smoke evidence. |

Claude Code is supported today. Windows is experimental as an OS surface.
Codex, Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, and local
runtimes are roadmap runtime surfaces until their adapters prove otherwise.

## Runtime-Aware Invocation Hints

Skill-fronting `mb` commands may print clearer runtime-aware handoff hints. They
must remain deterministic. They may not invoke a model or assume Claude Code is
the only possible runtime.

Future `--json` envelopes for commands such as `mb think <topic>` should follow
this shape:

```json
{
  "ok": true,
  "command": "mb think",
  "workflow": {
    "name": "think",
    "skill": "mb-think",
    "arguments": ["pricing research"]
  },
  "runtime": {
    "target": "claude-code",
    "support": "supported",
    "configured": true,
    "executable": "claude"
  },
  "invocation": {
    "kind": "skill",
    "cwd": "/path/to/business-repo",
    "launch_command": ["claude"],
    "follow_up": "/mb-think pricing research",
    "prompt": "",
    "execution_attempted": false
  },
  "checks": [],
  "next_actions": [
    "cd /path/to/business-repo",
    "claude",
    "/mb-think pricing research"
  ]
}
```

`execution_attempted` must be false unless the command has an explicit launch
flag and the runtime process was actually started. If no runtime is configured,
the command should degrade to plain hints and mark the runtime as unconfigured.

`mb start --json` is the current Claude Code handoff envelope and is
grandfathered with its existing `command` object and `launch.attempted` fields.
New hint commands should use the fields above. If `mb start` ever migrates to
the shared hint envelope, that must be a compatibility-managed CLI contract
change with tests, changelog notes, and a transition path for existing
consumers.

## Workflow Launcher and Playbook Gate

A workflow launcher can stay in `mb` only if it is deterministic across at
least two runtime adapters. It may:

- list available workflows;
- print the runtime-specific command or prompt to run;
- validate repo/runtime readiness before handoff;
- emit JSON metadata for dashboards or scripts;
- track deterministic progress for `mb`-owned subprocesses.

It must not:

- call a model;
- own conversation state;
- retry model outputs;
- stream chat UI;
- branch on runtime-specific model behavior inside `mb`;
- hide human approval gates for spend, publishing, or external mutations.

If a playbook progress surface requires model invocation, chat memory, retries,
or streaming UI, it belongs in the runtime skill layer. `mb` should document the
per-runtime one-liners and expose machine-readable status that the runtime can
consume. The playbook UX wrapper from #127 is allowed only behind this gate: a
single progress surface is fine when it reports deterministic phases and
runtime handoff metadata, not when it turns `mb` into the agent runtime.

## Onboarding Resume Contract

Multi-session onboarding state belongs to `mb`, not to a chat transcript.

`mb onboard status --json` is the resume contract for lifecycle skills and
future adapters. Skills should use:

- `summary.status`;
- `summary.next_recommended_action`;
- `summary.missing_inputs`;
- `checklist[].status`;
- `checklist[].missing_inputs`;
- `profile.team_size`;
- `boundaries.collect_now`;
- `boundaries.defer_until_needed`.

Skills may update the plan with `mb onboard plan ... --json` when the user gives
bounded setup answers. They must write accepted business truth to normal tracked
business files. `.mb/onboarding.json` remains lightweight operational progress
and is gitignored.

## Validation Contract

For this contract itself, Level 0 docs/decision validation is enough: links
resolve, local paths are current, no stale runtime claims, and no private local
details are committed.

Future changes use the ladder:

- CLI JSON or behavior changes require focused tests for command output and
  exit codes.
- Package, bundled-data, skill-discovery, update, or install changes require
  wheel/install smoke.
- First-run, repo-shape, `mb onboard`, `mb status`, `mb start`, or migration
  changes require fixture business-repo smoke.
- Skill prose or discovery changes require `mb skill validate --all` and a
  runtime/manual note.
- New runtime support requires the adapter smoke evidence above.

## Consequences

- Skill refactors should remove prose-only checks once an `mb` JSON contract
  exists.
- `mb think` and future skill-fronting commands should gain JSON handoff
  envelopes before they become automation surfaces.
- Non-Claude runtime issues should start from adapter specs and smoke plans, not
  README compatibility copy.
- The Claude Code plugin path remains the durable target because namespacing is
  the documented conflict escape.
- Workflow launcher work should close or move back into skills if it cannot
  stay deterministic across runtimes.

## Review Trigger

Revisit this contract when either of these becomes true:

- a second runtime adapter reaches experimental status; or
- more than one workflow needs a deterministic progress surface that cannot be
  expressed as status, handoff hints, and runtime-owned conversation.
