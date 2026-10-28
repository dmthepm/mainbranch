---
type: decision
date: 2026-05-23
status: accepted
topic: Codex slash-command bridge
linked_decisions:
  - decisions/2026-05-08-codex-adapter-plan.md
  - decisions/2026-05-13-shared-workflow-source-and-runtime-shells.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/709
participants: [Devon, Codex]
tags: [runtime-adapters, codex, skills, plugins]
---

# Codex Slash-Command Bridge

## Decision

Codex support stays on generated Main Branch guidance, the global Main Branch
Codex plugin, and deterministic `mb` facts.

Main Branch should not claim Codex `/mb-*` slash-command support until Codex
exposes a supported third-party command API and a fresh smoke proves the exact
surface.

## Facts

- Codex plugins package skills, apps, hooks, and MCP servers.
- Current Codex plugin manifests do not expose a supported `commands` field.
- Local throwaway plugin probes installed and enabled generated command files,
  but no machine-readable Codex surface reported those commands as available.
- Main Branch still wants `/mb-*` as a future product surface when Codex can
  support it.

## Product Language

Use this public wording:

> Codex supports the Main Branch daily owner loop through generated Codex
> guidance and deterministic `mb` facts.

Avoid calling the adapter a "Codex owner-loop skill" in public docs. A
plugin-packaged `SKILL.md` may remain an implementation detail because that is
Codex's current packaging shape.

## Consequences

- `slash_commands_ready` stays false unless a future Codex command API and smoke
  evidence prove command visibility.
- `mb workflow list --runtime codex` should describe supported workflow
  guidance, not slash-command availability.
- Compatibility docs should name the supported Codex path once and link here for
  the slash-command bridge decision.
