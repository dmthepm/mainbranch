---
type: decision
date: 2026-05-13
status: accepted
topic: Shared workflow source and runtime shells
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
  - decisions/2026-05-08-codex-adapter-plan.md
  - decisions/2026-05-13-shared-workflow-corpus-and-native-runtime-renderers.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/583
  - https://github.com/dmthepm/mainbranch/issues/451
  - https://github.com/dmthepm/mainbranch/issues/453
  - https://github.com/dmthepm/mainbranch/issues/125
participants: [Devon, Codex]
tags: [runtime-adapters, codex, claude-code, workflows, shared-workflow-source]
---

# Shared Workflow Source And Runtime Shells

> Status note, MAIN-434 / #709: the proven Codex path is generated Main Branch
> guidance delivered by the global Codex plugin and grounded in deterministic
> `mb` facts. The generated `AGENTS.md` sections remain runtime shells over
> shared workflow sources. See [docs/compatibility.md](../docs/compatibility.md)
> for current support claims and
> [Codex Slash-Command Bridge](2026-05-23-codex-slash-command-bridge.md) for the
> command-bridge decision.

## Decision

Main Branch workflow semantics belong in a shared workflow source under
`workflows/<workflow>/workflow.md`.

Runtime-specific files are shells or guidance over that source. They should
explain discovery, invocation, runtime limits, and support level for one
runtime. They should not become a second copy of the workflow.

For the current adapter path:

- `workflows/<workflow>/workflow.md` is the canonical source for durable
  workflow semantics.
- `.claude/skills/` remains the first-class Claude Code UX for shipped slash
  skills.
- Codex uses `AGENTS.md` and generated or referenced runtime guidance as the
  entrypoint.
- `mb` CLI JSON remains the deterministic fact layer.
- Runtime smoke decides what support language is allowed.

Do not make `.claude/skills/<workflow>` or `.agents/skills/<workflow>` the
canonical workflow source for Main Branch workflows.

## Why This Exists

The first Codex adapter slice proved that Codex can be grounded by generated
`AGENTS.md` and deterministic `mb` facts, but it did not prove Claude-style
installed command support or selected workflow support.

The first shared source prototype proved that a portable workflow file can
declare intent, required `mb` commands, JSON fact paths, routing rules,
boundaries, approval gates, handoff shape, runtime notes, and validation.

The next risk is choosing the wrong permanent source. Putting workflow truth in
runtime-specific skill folders would make the directory layout feel native for
one runtime while making drift more likely across runtimes. The workflow source
needs to be above runtime packaging.

## Source Ownership

Shared workflow source owns durable semantics:

- intent and trigger boundaries;
- required `mb` commands;
- required JSON fact paths;
- repo files to read;
- research-depth or routing rules;
- public/private boundaries;
- approval gates;
- durable promotion and codification rules;
- output or handoff shape;
- validation expectations;
- support evidence required before runtime claims.

Runtime shells own presentation and discovery:

- how this runtime discovers the workflow;
- how a user asks for the workflow in that runtime;
- runtime-specific warnings;
- slash-command availability or non-availability;
- support level and smoke requirement;
- concise guidance that points back to shared semantics instead of duplicating
  them.

`mb` owns deterministic facts and validation. It may render, validate, and
repair runtime files. It must not invoke a model or run the conversation.

## Codex Boundary At Decision Time

Codex is CLI/instruction-file-first in the current Main Branch support model.
Fresh business repos include `AGENTS.md`; `mb status`, `mb start`, and
`mb doctor repair` expose Codex readiness. At the time, that did not prove an
installed plugin command surface.

Codex guidance should say how to treat a natural request as a Main Branch
workflow, starting from read-only `mb` facts. It should not tell users to run
Claude Code slash commands.

The narrow support claim after a successful `/mb-think` read-only smoke is:

> Codex has experimental `/mb-think` workflow guidance through shared workflow
> source.

Do not claim:

- Codex supports all Main Branch skills.
- Codex has full Claude-style `/mb-think` skill parity.
- Claude Code skills work in Codex.

## `.agents/skills` Boundary

Codex skills and `.agents/skills` may become useful later, but they are not the
canonical source for MAIN-368.

Do not use this branch to:

- create `.agents/skills`;
- symlink Claude skills into another tree;
- copy `.claude/skills/mb-think`;
- make `.agents/skills` the distribution layer;
- create a generic runtime framework;
- port every skill.

If a later issue decides Main Branch needs a Codex skill distribution layer, it
should explicitly cover `.agents/skills`, plugin packaging, symlinks vs copies
vs generated files, PyPI package behavior, generated business repos,
Windows/WSL behavior, and runtime smoke evidence.

## What MAIN-368 Should Prove

MAIN-368 should prove:

- a shared workflow source can represent `/mb-think`;
- Codex can follow the workflow through Codex-native guidance;
- Claude Code behavior is preserved unless explicitly replaced and smoked;
- drift tests catch missing commands, facts, gates, and support boundaries;
- support language stays honest.

Tests should catch:

- missing `mb status --json --peek`;
- missing `mb start --json` when declared;
- missing research-depth ladder;
- missing approval gates;
- missing public/private boundaries;
- Codex guidance saying "Run `/mb-think`";
- Codex guidance claiming Claude skill parity;
- runtime shells accumulating full workflow logic instead of staying concise;
- stale product naming in touched files.

## Consequences

This keeps Main Branch from becoming a pile of runtime-specific prompt copies.
It also keeps Codex support honest: Codex can get native guidance without
pretending it has the same slash-command UX as Claude Code.

The tradeoff is that a workflow source and renderer layer must be maintained.
That cost is acceptable because it gives the project mechanical drift tests and
a clear future adapter path.

## What Changes

`workflows/mb-think/workflow.md` becomes the canonical shared source for the
portable `/mb-think` workflow semantics. Renderer snapshot tests should cover
both Claude and Codex shells. Public docs should use current naming:

- shared workflow source;
- runtime shell;
- runtime guidance;
- runtime adapter.

Future `.agents/skills` or Codex plugin distribution work needs its own issue
and decision if it becomes the right adapter surface.
