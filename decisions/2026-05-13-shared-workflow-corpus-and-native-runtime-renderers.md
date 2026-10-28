---
type: decision
date: 2026-05-13
status: accepted
topic: Shared workflow corpus and native runtime renderers
linked_decisions:
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
  - decisions/2026-05-08-codex-adapter-plan.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/451
  - https://github.com/dmthepm/mainbranch/issues/453
  - https://github.com/dmthepm/mainbranch/issues/539
  - https://github.com/dmthepm/mainbranch/issues/125
participants: [Devon, Codex]
tags: [runtime-adapters, codex, claude-code, skills, workflows, renderer]
---

# Shared Workflow Corpus And Native Runtime Renderers

Historical naming note: this decision used "workflow corpus" while the adapter
shape was being chosen. Current product language is **shared workflow source**,
with **runtime shells**, **runtime guidance**, and **runtime adapters** over
that source.

> Status note, MAIN-434 / #709: the proven Codex path is generated Main Branch
> guidance delivered by the global Codex plugin and grounded in deterministic
> `mb` facts. That support is still an adapter over shared workflow sources, not
> full Claude skill parity or broad production workflow parity. See
> [docs/compatibility.md](../docs/compatibility.md) for current claims and
> [Codex Slash-Command Bridge](2026-05-23-codex-slash-command-bridge.md) for the
> command-bridge decision.

## Decision

Main Branch should introduce a runtime-neutral workflow corpus under
`workflows/<workflow>/` and render native runtime shells from that source.

The workflow corpus becomes the durable source for portable Main Branch
workflow semantics: intent, required `mb` facts, JSON fact paths, routing rules,
write boundaries, approval gates, handoff shape, and validation expectations.
Runtime shells stay native:

- Claude Code keeps slash-command-first skills such as `/mb-start` and
  `/mb-think`.
- Codex keeps `AGENTS.md` as the always-on bootstrap surface and gains
  Codex-native workflow entrypoints only after selected workflows have renderer
  output and runtime smoke.
- Future runtimes get their own shells instead of inheriting Claude invocation
  language.

Do not keep `.claude/skills/` as the long-term canonical source for new
cross-runtime work. It remains the shipped Claude Code adapter surface while
selected workflows are migrated. Do not copy the full Claude skill tree into
`.agents/skills` by hand.

## Non-goals

This decision does not:

- implement the workflow corpus, renderer, or validator;
- port `/mb-think`, `/mb-site`, or any full production workflow to Codex;
- copy `.claude/skills` into `.agents/skills`;
- claim native Codex skills, Claude-style installed command parity, Codex Mac
  app support, Codex cloud support, or selected Codex workflow support;
- make `mb` invoke Codex, Claude, or any model;
- replace Claude Code as the supported runtime;
- build dashboard, runtime UI, provider mutation, publishing, spend, or
  customer-contact automation.

## Evidence Base

Stage 1 Codex evidence is now strong enough to design the next layer, not
strong enough to claim workflow parity.

- [MAIN-279 / #405](https://github.com/dmthepm/mainbranch/issues/405)
  shipped the experimental Codex CLI-first adapter: generated business-repo
  `AGENTS.md`, Codex readiness facts, and `mb doctor repair` coverage.
- [MAIN-304 / #453](https://github.com/dmthepm/mainbranch/issues/453)
  dogfooded `mainbranch 0.3.19` and recorded that Codex can be grounded by
  generated `AGENTS.md` plus deterministic `mb` facts.
- The dogfood report
  [`docs/reports/2026-05-12-codex-stage1-dogfood.md`](../docs/reports/2026-05-12-codex-stage1-dogfood.md)
  records the current boundary: Codex used `mb` facts and did not silently
  mutate repos, but it did not prove native Codex skills, Claude-style
  installed command parity, Mac app support, cloud support, or selected
  production workflow ports.
- [MAIN-349 / #539](https://github.com/dmthepm/mainbranch/issues/539)
  proved the Claude Code side of the same handoff shape: `/mb-start`
  path-to-money prompts should start from `money_path` facts, carry the
  MoneyPath snapshot into `/mb-think`, and use runtime evidence before
  treating that as shipped behavior.

That makes a renderer decision the right next step. Another `AGENTS.md` patch
would harden Stage 1 but would not solve drift between Claude and Codex
workflow semantics.

## What A Workflow Is

A Main Branch workflow is the portable contract for an operator job, separate
from the runtime UI that invokes it.

Each workflow source should declare:

- `name`, `description`, and operator loops (`sense`, `decide`, `ship`,
  `reflect`);
- supported support levels by runtime;
- trigger phrases and intent boundaries;
- required `mb` commands, such as `mb status --json --peek`, `mb start --json`,
  `mb doctor repair --plan`, `mb connect status --json`, or
  `mb checkpoint --plan --json`;
- required JSON fact paths, such as `money_path`,
  `money_path.objects.proof.quality`, `content_strategy`, `ranked_actions`,
  `runtime`, `checkpoint`, and provider readiness;
- routing rules, including when to continue in the current workflow and when to
  hand off to another workflow;
- read boundaries: which business files may be read and which deterministic
  facts must be checked first;
- write boundaries: which paths may be changed and which operations need
  explicit approval;
- approval gates for update, repair, migration, checkpoint creation,
  publishing, provider mutation, spending, customer contact, and destructive
  file operations;
- handoff format: how the runtime should explain status, choices, next actions,
  and evidence in business language;
- validation commands and runtime smoke expectations;
- runtime-specific notes for invocation syntax, discovery, mode guidance,
  restart/reload behavior, and unsupported parity claims.

The workflow source should not encode runtime-only UI assumptions such as
Claude slash-command syntax, Codex mode labels, plugin installation steps, or
runtime-specific subagent mechanics except in renderer-specific sections.

## Source Shape

Use a small directory per workflow:

```text
workflows/
  mb-start-money-path/
    workflow.md
    references/
      money-path-routing.md
    tests/
      fixtures/
```

`workflow.md` should be Markdown with frontmatter. The first implementation
slice can keep the schema intentionally narrow:

```yaml
---
name: mb-start-money-path
title: Start To MoneyPath Think Handoff
loops: [sense, decide, ship]
runtime_support:
  claude_code: supported_shell
  codex_cli: experimental_shell
  future: planned
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - content_strategy
  - ranked_actions
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---
```

Keep the first schema documentable and testable before making it clever. If a
field does not drive rendering, linting, or smoke expectations, leave it out.

## Native Runtime Shells

### Claude Code

Claude Code remains the supported runtime today.

Rendered Claude shells should produce or update:

- `.claude/skills/<workflow>/SKILL.md` when the workflow has a Claude skill;
- selected `references/`, `scripts/`, and `assets/` that are actually used by
  that skill;
- generated adapter notes for slash-command invocation, Claude restart/repair,
  and project-local `.claude/skills` bridge behavior.

Existing `.claude/skills` stay authoritative for workflows that have not been
migrated. During migration, generated output should be snapshot-tested against
the current Claude skill behavior before replacing hand-maintained prose.

### Codex CLI

Codex support remains experimental and CLI-first.

`AGENTS.md` should stay an always-on bootstrap file, not a full workflow manual.
It should:

- tell Codex to start from deterministic `mb` facts;
- explain support boundaries and approval gates;
- point to generated Codex workflow entrypoints only after those entrypoints
  exist and have smoke evidence.

Status note: MAIN-387 chose the compact generated Codex workflow index
referenced from `AGENTS.md` for the first lifecycle discovery slice. That index
routes start, status, and thinking/codification requests through deterministic
`mb` facts and keeps `.agents/skills`, plugin packaging, provider mutation,
publishing, spend, domains, and customer contact out of the current support
claim.

Rendered Codex shells may produce:

- repo-local `.agents/skills/<workflow>/SKILL.md` bridge links for selected
  workflows;
- a Codex plugin package only when plugin distribution is the real tested
  install/update surface;
- a compact generated Codex workflow index referenced by `AGENTS.md` when
  selected workflows exist.

Do not pretend Claude Code slash commands work in Codex. Codex workflow shells
should use Codex-native skill activation, instruction files, and mode guidance.
Mode guidance may mention Suggest, Auto Edit, or Full Auto only as runtime UX
advice; approval gates still come from the workflow source.

### Future Runtimes

Future runtime shells should be additive render targets over the same workflow
source. Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, local model
runtimes, and dashboard views remain roadmap targets until each has adapter
code, generated-file rules, and smoke evidence.

Do not use "runtime agnostic" as a user-facing support claim. Use it only to
describe the internal workflow source.

## Renderer Ownership

`mb` owns rendering, validation, and repair of generated runtime files. It must
not invoke Codex, Claude, or any model.

Implementation should add a small renderer module rather than mixing template
logic into individual commands. Likely surfaces:

- `mb workflow validate` or an extension of `mb skill validate` for workflow
  schema, links, line counts, and runtime-output drift;
- generator functions that render Claude and Codex shells from
  `workflows/<workflow>/`;
- snapshot tests for rendered outputs;
- `mb doctor repair --plan` entries only after a generated file becomes a real
  business-repo runtime surface.

Generated-file ownership must be explicit before a renderer writes into a
business repo:

| Path | Owner | Git rule | Purpose |
| --- | --- | --- | --- |
| `AGENTS.md` | `mb init` / `mb doctor repair` / user | tracked | Codex bootstrap instructions |
| `CLAUDE.md` | `mb init` / user | tracked | Claude project instructions |
| `.claude/skills/mb-*` | `mb skill link` | gitignored | Claude project-local bridge links |
| `.agents/skills/mb-*` | future Codex renderer/repair | gitignored unless a later decision says otherwise | Codex project-local workflow bridge links |
| `.codex-plugin/plugin.json` | future plugin package | tracked in plugin package, not generated into every business repo by default | Codex plugin metadata |

## First Workflow Family

The first workflow family to port/render should be:

**Daily start -> MoneyPath `/mb-think` handoff.**

This family covers the job where the operator asks what to do next, the runtime
grounds itself in `mb status --json --peek`, uses `money_path` and
`money_path.objects.proof.quality`, checks `content_strategy` before raw
markdown where relevant, and hands off to the thinking/codification workflow
only when writing business truth is the right next move.

Why this comes first:

- it uses the exact Stage 1 Codex evidence surface: `AGENTS.md`,
  `mb status --json --peek`, `mb start --json`, and `mb doctor repair --plan`;
- it matches MAIN-349's Claude-side evidence that path-to-money prompts should
  route through MoneyPath facts before `/mb-think` reads supporting files;
- it is the daily owner loop, not a niche production workflow;
- it exercises Sense -> Decide -> Ship without needing provider mutation;
- it tests read/write boundaries clearly: read facts first, ask before codify
  writes or checkpoints;
- it catches the current Codex ceiling: Codex can ground in facts, but it does
  not yet have native Main Branch workflow entrypoints.

Do not start with the whole `/mb-think` or `/mb-site` skill. Start with the
handoff lane: status facts, MoneyPath routing, proof-quality language,
content-strategy facts, approval gates, and a Codex-native route into a
selected thinking/codification action.

## Staged Implementation Plan

### Stage A: Workflow Corpus Prototype

Add one workflow source:

- `workflows/mb-start-money-path/workflow.md`;
- one or two focused references if the shared section would otherwise become
  too long;
- a schema validator and snapshot fixture.

Keep existing Claude and Codex runtime behavior unchanged in this slice unless
the generated output is opt-in test output only.

Validation:

- workflow schema test;
- link/reference test;
- public/private boundary review;
- snapshot of generated Claude and Codex shell text in test fixtures.

### Stage B: Claude Shell Parity

Render a Claude Code shell for the selected family and compare it against the
current `/mb-start` and `/mb-think` handoff language.

Validation:

- generated-file snapshot test;
- drift test that required `mb` commands and JSON facts appear in the Claude
  shell;
- `mb skill validate --all --json`;
- Claude Code runtime smoke only when the rendered output replaces shipped
  skill prose or discovery.

### Stage C: Codex Native Shell

Render a Codex-native shell for the same family.

The first Codex output should be either a repo-local `.agents/skills` bridge
for the selected workflow or a generated Codex workflow index referenced from
`AGENTS.md`. Choose one default in the implementation PR based on the current
Codex CLI surface. Do not introduce plugin packaging unless the branch tests
plugin installation, update, and discovery.

Validation:

- generated-file snapshot test;
- drift test against the shared workflow source;
- fresh `mb onboard` fixture;
- read-only `codex exec --json --ephemeral --sandbox read-only -C <repo>`
  smoke proving Codex reads bootstrap instructions and uses required `mb`
  facts;
- interactive Codex CLI or app smoke when the claim depends on skill selection,
  plugin installation, or runtime UI discovery;
- clean `git status --short` for read-only starts.

### Stage D: Selected Workflow Port

Only after Stage C, use [#125](https://github.com/dmthepm/mainbranch/issues/125)
for selected workflow ports such as fuller `/mb-think` or `/mb-site`.

Validation must name the exact workflows and runtimes that passed smoke. Docs
may say "selected Main Branch workflows are experimental in Codex" only for
those workflows.

MAIN-125 should stay parked until the shared workflow prototype proves that one
workflow family can render or route cleanly through the shared source, Claude
shell, and Codex shell without semantic drift.

## Drift And Test Rules

Future implementation PRs should make drift mechanically visible.

Minimum gates:

- source schema validation for every `workflows/<workflow>/workflow.md`;
- generated-output snapshots for each runtime shell;
- parity assertions that required `mb` commands and JSON fact paths in the
  source appear in every rendered shell that claims support;
- file-ownership tests for tracked vs. gitignored generated files;
- no private local path, token, account id, customer/member data, or raw
  business data in generated instructions;
- runtime smoke evidence when rendered files affect discovery, invocation, or
  workflow behavior.

Mechanical tests do not prove LLM-facing workflow behavior. Runtime smoke is
required before support language changes.

## Support Language

At decision time, use these claims until future evidence changes them:

- Claude Code: supported runtime for current slash-command skills.
- Codex CLI: Stage 1 instruction-file adapter grounded by generated `AGENTS.md`
  and deterministic `mb` facts; no installed plugin command surface had shipped
  yet.
- Codex selected workflows: not shipped yet.
- Future runtimes: compatibility targets only.

After the first rendered Codex workflow passes smoke, the narrow allowed claim
is:

> Selected Main Branch workflows are experimental in Codex.

Name the workflow. Do not imply all Claude Code skills work in Codex.

## Rejected Options

- **Keep only `AGENTS.md`.** Good for Stage 1 bootstrap, insufficient for
  selected workflow parity and drift detection.
- **Keep `.claude/skills` canonical forever.** Fast locally, but it bakes
  Claude invocation, bridge-link, and slash-command assumptions into the shared
  source.
- **Copy `.claude/skills` into `.agents/skills`.** Creates a second
  hand-maintained tree and overclaims runtime behavior.
- **Build a model-running workflow launcher in `mb`.** Violates the
  CLI/runtime boundary. `mb` should render, validate, and expose deterministic
  facts; runtimes own conversation.
- **Start with `/mb-site`.** Valuable later, but it carries more provider,
  artifact, child-repo, and publishing complexity than the first renderer
  needs.
- **Use shared references plus thin entrypoints only.** Useful as a transition
  tactic, but insufficient as the durable source because references alone do
  not encode required `mb` commands, JSON fact paths, approval gates,
  generated-file ownership, support levels, or drift tests.

## Follow-Up Issue

Open the next implementation issue as:

**Create shared workflow corpus prototype for daily start -> MoneyPath think
handoff.**

Suggested scope:

- add `workflows/mb-start-money-path/workflow.md`;
- add a workflow schema validator;
- add generated Claude and Codex shell snapshots;
- prove required `mb` commands and JSON fact paths cannot drift across
  supported shells;
- keep runtime behavior unchanged unless the branch also includes the required
  smoke evidence.

Likely files:

- `workflows/mb-start-money-path/workflow.md`;
- optional `workflows/mb-start-money-path/references/money-path-routing.md`;
- renderer or validator code under `mb/mb/`;
- tests under `mb/tests/` for schema validation, renderer snapshots, and drift
  assertions;
- snapshot fixtures for Claude and Codex shell output;
- generated Claude shell output only when the branch is ready to replace
  hand-maintained `/mb-start` or `/mb-think` handoff prose;
- generated Codex shell or workflow index only when the branch includes the
  required Codex smoke evidence;
- generated `AGENTS.md` updates only if the Codex shell exists and needs an
  index from the bootstrap file.

Acceptance criteria:

- The workflow source declares intent/triggers, required `mb` commands, JSON
  facts, routing rules, read/write boundaries, approval gates, handoff format,
  validation commands, and runtime-specific notes.
- Tests fail when a supported runtime shell omits a required command or JSON
  fact from the workflow source.
- Generated Claude and Codex shell snapshots are committed as test fixtures.
- Existing Claude Code behavior remains unchanged unless the PR includes
  Claude skill validation and appropriate runtime smoke.
- Codex behavior remains experimental; any generated Codex shell is covered by
  fresh fixture repo smoke and read-only `codex exec` evidence before docs
  mention selected workflow support.
- No private paths, credentials, account data, customer/member data, or raw
  business data appear in workflow sources or generated outputs.

Use `Refs #451` for setup-only slices. Use `Closes #451` only for the PR that
lands this decision and the staged implementation plan.
