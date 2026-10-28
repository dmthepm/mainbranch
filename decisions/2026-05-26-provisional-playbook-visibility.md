---
type: decision
date: 2026-05-26
status: accepted
topic: Provisional playbook visibility
linked_decisions:
  - decisions/2026-05-07-growth-automation-playbook-addons.md
  - decisions/2026-05-13-shared-workflow-source-and-runtime-shells.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/753
  - https://github.com/dmthepm/mainbranch/issues/743
participants: [Devon, Codex]
tags: [playbooks, workflows, codex, claude-code, packaging]
---

# Provisional Playbook Visibility

## Decision

Retire `ship-bet` and `weekly-review` from bundled reusable playbook packaging.
They are not rejected product ideas; they are future workflow candidates that
need real shared workflow contracts before they become user-facing routes again.

`ship-bet` is a future composed workflow candidate. It should wait until
`mb-bet`, file-contract guided routes, and the handoffs from bet to push, site,
ads, checkpoint, and review are concrete enough to render from a shared workflow
source.

`weekly-review` is a future Reflect workflow candidate. It should wait until
status, validation, graph, file contracts, bet verdicts, push reviews, durable
updates, and checkpoint routes have a clear shared contract.

Neither surface should ship as `.claude/playbooks/<slug>/SKILL.md`, a Codex
global skill, a generated Codex route, or a default inventory row today.

## Why

Main Branch now separates four related surfaces:

- shared workflow sources under `workflows/<workflow>/workflow.md`;
- runtime shells such as Claude Code skills and Codex global skills;
- reusable playbooks under `.claude/playbooks/<slug>/`;
- per-run push playbook records under `pushes/<push>/playbooks/<playbook>.md`.

`ship-bet` and `weekly-review` were useful skeletons while the product was
finding shape, but they blurred those surfaces. They described orchestration
across skills and files rather than a reusable operating recipe with its own
references, templates, fork points, and run-record expectations.

Keeping them as internal bundled playbooks would preserve the ambiguity. Making
them first-class skills would overclaim runtime support. Removing them from
bundled playbook packaging keeps the future ideas available without making the
current product surface overclaim.

## Contrast: Google Ads Search Launch

`google-ads-search-launch` stays bundled as a draft/manual reusable playbook
because it has the shape a reusable playbook should have:

- a concrete operating recipe for one kind of paid-search proof run;
- references and field notes;
- a push playbook run-record template;
- explicit fork points and manual approval gates;
- provider, spend, and publishing boundaries;
- inventory status that marks it draft/manual and provider-gated;
- no direct Codex global skill route.

That is the comparison standard for future reusable playbooks. A playbook can
be draft/manual, but it still needs a concrete repeatable method and the run
record shape that proves what the operator chose.

## Future Source Shape

If `ship-bet` returns, start with:

```text
workflows/ship-bet/workflow.md
```

That workflow should declare required `mb` facts, write boundaries, approval
gates, output paths, and handoffs to bet, push, site, ads, end, and checkpoint
routes. It should not become a hidden orchestrator or provider automation rail.

If `weekly-review` returns, start with:

```text
workflows/weekly-review/workflow.md
```

That workflow should declare Reflect-loop inputs, status/validate/graph facts,
durable update gates, bet verdict and push review routing, checkpoint behavior,
and the owner-facing weekly review output.

Do not create `playbooks/<slug>/playbook.md` or new bundled reusable playbook
directories for these names unless a later issue decides they are true
repeatable recipes rather than composed workflows.

## Cleanup Boundary

Old generated Codex global skill directories named `ship-bet` or
`weekly-review` may still exist on user machines from earlier development
states. `mb doctor repair --apply --only codex` may remove those stale
directories only when marker checks prove Main Branch generated them.

Repair must not delete an unrelated user-created Codex skill with the same
directory name. The cleanup rule is marker-driven, not name-only.

## Out Of Scope

This decision does not implement MAIN-459 file contracts or guided routes. It
does not add new workflow sources, new Claude Code slash skills, new Codex
global skills, runtime orchestration, progress UI, provider mutation,
publishing, spend, CRM/email writes, or customer contact.

Those surfaces need separate issues, shared contracts, tests, and smoke evidence
before support language can change.
