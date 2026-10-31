# Roadmap

Main Branch's current focus is the daily owner loop: read business facts,
choose a next move, produce approved work, and save the lesson. This roadmap
describes direction, not a release promise or a list of active tasks.

Use [the changelog](../CHANGELOG.md) for release history and
[GitHub issues](https://github.com/dmthepm/mainbranch/issues) for current work.
Verify an issue's state before treating it as an implementation commitment.
The [repo-owned operating memory decision](../decisions/2026-05-15-repo-owned-operating-memory.md)
explains the broader product direction.

## Current foundation

The CLI checks folder shape, reports status, validates business files, maps
relationships, checks provider readiness, repairs wiring, updates installs,
and saves checkpoints. Onboarding creates a business folder separate from
the engine.

Skills read those facts and help owners research, compare choices, draft work,
and review outcomes. Claude Code supports the bundled workflows within their
provider and approval limits. Codex supports the daily loop; bet, ads, organic,
site, and books remain read-only planning. See
[compatibility](compatibility.md#workflow-coverage-today) for exact scope.

Some available commands need setup or business-specific implementation:

| Capability | Current boundary |
| --- | --- |
| Local dashboard | `mb dashboard build` and `open` provide a read-only HTML view, not a hosted service or background agent. |
| Google data | `mb google` reads Search Console and GA4 after setup. Broader Workspace source ingestion remains planned. |
| Bookkeeping | Readiness checks and fake-data sample reporting do not establish a complete private-ledger close workflow. |
| Meta Ads | Read-only readiness and account summaries after setup do not authorize campaign changes or spend. |
| Monitoring and automation starters | Generated scripts and plans still need business-specific implementation and verification. Command availability is not evidence of an operating service. |

## Improve the daily loop

The next improvements should make normal work clearer without requiring the
owner to manage git details:

- Start from consistent facts about health, recent work, readiness, and gaps.
- Turn a messy request into a concrete proposal with sources and uncertainty.
- Explain repair findings and preview changes before applying them.
- Save meaningful progress with readable messages and a clear backup boundary.
- Use previous decisions and outcomes when recommending the next action.
- Turn repeated friction into public-safe issue drafts for review.

The success measure is a coherent owner task, not the number of commands or
skills added. [A working day](working-day.md) illustrates the intended sequence.

## Extend views over business memory

Future dashboard and multi-repo work should help owners see linked businesses,
sites, offers, tasks, proposals, bets, and outcomes. Views should expose source
freshness, missing facts, and access boundaries.

Planned directions include team logs assembled from durable work, clearer
multi-repo inventory, and optional provider summaries. Any future write path
needs a narrow contract and explicit authority. A dashboard database must not
replace the business repo.

## Deepen production workflows

Research, paid creative, organic content, pages, and coordinated pushes already
provide workflow starting points. Future work should connect them to measurable
outcomes and reusable [playbooks](playbooks.md).

Broader provider mutation, automatic social posting, bookkeeping imports and
reconciliation, and production-workflow parity in Codex require separate
implementation and evidence. An approval request alone does not establish
support for an untested provider action.

## Broaden runtime support when proven

Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, and local runtimes
remain compatibility targets. Each needs discovery rules, install and update
behavior, state boundaries, and fresh-repo smoke evidence before a support claim.

External callers can invoke deterministic `mb` commands against an explicit
business folder. That does not establish support for the caller's agent workflow.

## Boundaries that remain

- Business truth stays in files and saved history owned by the user.
- Secrets and raw sensitive records stay outside tracked business memory.
- `mb` remains deterministic. Model invocation and ongoing execution belong
  to the runtime or caller.
- Publishing, spend, customer contact, and account changes need explicit
  authority and tested support.
- Connections stay optional and tied to a useful owner task.

Read [ethos](ethos.md) for the product contract and
[operator loops](operator-loops.md) for the operating method.
