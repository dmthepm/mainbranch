---
type: decision
date: 2026-05-07
status: accepted
topic: Work continuity, hidden technical memory, and task model
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/371
linked_decisions:
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-05-operator-loops-taxonomy.md
  - decisions/2026-05-05-operator-readable-git-history.md
  - decisions/2026-05-06-main-branch-operating-spine.md
  - decisions/2026-05-06-push-primitive-and-operator-vocabulary.md
tags: [v0-3, task-model, github, git, start, end, graph, playbooks]
---

# Work Continuity, Hidden Technical Memory, And Task Model

## Decision

Main Branch does not have a first-class user-facing task tracker. The product
surface is **work continuity**: the operator starts from business context,
chooses or advances the next business move, ships work, and closes with durable
memory.

Normal operators should not be asked to choose a task system. They work in
business primitives:

- bets;
- pushes;
- playbooks;
- decisions;
- research;
- logs;
- outcomes;
- checkpoints.

The technical memory layer underneath is still real:

- GitHub issues are durable work threads;
- pull requests are proposals and review conversations;
- branches are isolated workspaces for proposal/review work;
- commits and `mb checkpoint` are saved business progress;
- `gh` is the deterministic GitHub connector for issues, proposals, releases,
  reviews, and auth;
- `mb status`, `mb graph`, and future dashboards translate that technical
  memory into business-readable facts.

This refines the earlier GitHub-native decision without replacing it. GitHub
remains the adopted durable coordination layer. The change is product
language and routing: issues are not the operator's default mental model.
Issues are created or suggested when work needs a durable thread.

## Why Not A Task Tracker

Flat task lists create another management surface. They drift, duplicate the
repo, hide the real business question, and invite agents to preserve chores
instead of advancing bets, pushes, decisions, and outcomes.

The daily question is not "which tasks are in the task tracker?" The daily
question is:

> What business move should we advance, what changed since last time, and what
> needs to be saved so the next session can recover?

`/mb-start` and `mb status` answer that question by regenerating the current
view from files, git history, GitHub, graph links, provider readiness, and
recent checkpoints. The derived view may include tasks, blockers, proposals,
and saved work, but the source of truth is the underlying business and
technical memory.

## Ownership Map

| Surface | Owns | Does not own |
| --- | --- | --- |
| Bet | Wager, success metric, timebox, verdict, lesson | Generic task list |
| Push | Coordinated work toward an audience, offer, promise, channel, and outcome | Every small next action |
| Playbook | Repeatable business procedure, checks, provider requirements, and expected evidence | A separate project-management system |
| Decision | Rationale, options, accepted direction, rejected alternatives, and what changes | Work-progress tracking |
| Research | Evidence, synthesis, provenance, and open questions | Permanent chore storage |
| Log | Team daily record, event memory, and handoff context | Raw chat database |
| Checkpoint / commit | Saved business progress and readable history | User-facing ceremony |
| GitHub issue | Durable work thread, blocker, request, follow-up, or reproducible friction | Default place for every task |
| Pull request | Proposal, review conversation, and mergeable change | Chat replacement |
| Linear | Visual planning, releases, and private/internal coordination | Public source of truth |
| Dashboard | View over repo, git, GitHub, graph, connectors, sidecars, and provider facts | Canonical task database |

Decision status values such as `proposed`, `accepted`, and `codified` describe
the maturity of the decision. They do not make decisions into task trackers.
Maturity tracks the rationale's confidence and adoption: `proposed` means the
direction is drafted, `accepted` means the operator has chosen it, and
`codified` means the rationale has been integrated into durable business or
engine truth. Maturity says nothing about whether downstream work is done. A
codified decision can have unfinished downstream work; an accepted decision can
already have shipped. Follow-up sections are allowed in decisions, but
follow-ups should either be codified directly, routed into a push/playbook,
saved as a checkpoint, or promoted to a GitHub issue when they need durability.

## When Work Becomes A GitHub Issue

Create or suggest a GitHub issue when the work needs a durable thread:

- it crosses sessions and would otherwise be forgotten;
- it has an owner, blocker, deadline, dependency, or discussion;
- it is public Main Branch engine work, product work, support friction, or a
  reproducible bug;
- it should connect to a branch, pull request, release, or review loop;
- it needs team visibility;
- it is not naturally owned by one bet, push, playbook, decision, or log entry;
- future status, graph, or dashboard views need to track it as open work.

Do not create issues for:

- quick one-session work;
- raw thought dumps before they are shaped;
- sensitive private context;
- ordinary decision rationale;
- checklist steps inside an active push or playbook;
- work already represented clearly by a bet, push, decision, or checkpoint.

Some durable items are facts about an external commitment rather than plans
against a bet: a promised reply, renewal, meeting follow-up, compliance date,
or provider deadline. These still need durable memory. The safe home depends on
the privacy boundary: a GitHub issue, log entry, private repo note, provider
record, or approved summary. Keep this surface narrow and operator-driven; it
is not where ordinary work lands.

Skills should prefer issue drafts or explicit suggestions over public issue
creation. Public issue creation is a shared-memory action, not a hidden
background side effect.

## `gh` CLI And GitHub Facts

`gh` is an adopted core operational dependency because it is inspectable,
scriptable, exit-coded, and already maps to the GitHub primitives Main Branch
uses: issues, pull requests, reviews, releases, auth, and public coordination.

`mb` and skills should use `gh` for deterministic GitHub facts and mutations
when the GitHub layer is needed. The operator-facing language should translate:

- issue -> task, blocker, request, or follow-up;
- pull request -> proposal or review;
- merge -> shipped proposal;
- review request or mention -> needs attention;
- release -> available update or shipped version.

Contributor docs may use GitHub terms directly. Beginner and operator-facing
copy should speak business first. The system can show technical details behind
an inspectable "show details" path, but the default sentence should be about
work, not GitHub mechanics.

## Recent Commits And Checkpoints

Recent commits are not developer trivia. They are the saved timeline of the
business. `mb status`, `/mb-start`, `/mb-end`, and future dashboards should use
recent checkpoint and commit facts to answer:

- what changed since last time;
- what work was saved;
- which bet, push, decision, research note, log, or issue a change connects to;
- whether there is unsaved work that should be checkpointed before continuing;
- whether a future session can recover the current state.

The accepted operator-readable git history contract remains the source for
commit language. Main Branch should keep improving the journal/status layer so
agents do not need to run ad hoc `git log` probes unless status facts are
unavailable.

## `/mb-start`

`/mb-start` is the daily regeneration ritual. It should make the current day
visible from deterministic facts before giving advice.

It should:

- run `mb status --json --peek` once the business repo is known;
- read update, doctor, runtime, skill-wiring, provider, graph, GitHub, journal,
  checkpoint, and ranked-action facts from that report;
- use `gh`-backed GitHub facts through `mb status` when available;
- inspect recent saved work and unsaved work through the status/checkpoint
  contract;
- route thought dumps into business primitives by proposing placement before
  executing: candidate bets, decisions, research notes, push entries, log
  items, playbook runs, or issue drafts. The operator confirms or redirects;
  the dump is not silently filed;
- propose the next one to three moves, not a comprehensive task list;
- suggest issue creation only when work needs a durable thread;
- speak in operator language by default.

The next one to three moves should be at **push or scope altitude**, not atomic
task altitude. A move is the next meaningful slice of business work, such as
"advance the launch push," "decide the audience tightening question," or "ship
the VSL draft for review." Atomic execution belongs inside the session, not in
the regenerated view.

`/mb-start` may proactively update the **Main Branch tool** when the update path
is deterministic, safe, and already supported by `mb update`. The operator
surface should say plainly that Main Branch updated itself or that an update
needs attention. It should not force the operator to reason about package
managers, branches, or install modes unless the update fails or asks for help.
Operators should be able to turn automatic Main Branch tool updates off when
they need Main Branch to stay on a specific version.

`/mb-start` may also help the business repo start from the latest saved
work, but the operator-facing language should not say "behind remote,"
"fast-forward," or similar git plumbing. It should say "I brought in the latest
saved work" when the sync is clean, or "there is saved work from another
workspace to review before we start" when it needs attention. Automatic
business-repo sync is acceptable only when `mb` can prove it is clean,
conflict-free, and will not overwrite unsaved local work. If there is unsaved
work, a divergent history, a merge conflict, or uncertainty about the safe path,
`/mb-start` should pause and explain the business meaning before changing the
repo.

`/mb-start` should not silently perform actions that change canonical business
memory in a way that is not proven safe, public/shared coordination state,
provider accounts, or customer-facing surfaces. When the right next action
changes those surfaces, it should present the business meaning and the exact
command or approval gate.

## `/mb-end`

`/mb-end` is the closure and reflection ritual. It should reconcile the session
without turning into tomorrow's task manager.

It should:

- inspect what changed;
- summarize saved and unsaved business work;
- reconcile decision lifecycle carefully;
- crystallize what the session meant: connect the day's work to the active
  bet, push, decision, core truth, or unresolved tension so the lesson can feed
  the next Sense pass;
- propose or save approved checkpoints through `mb checkpoint`;
- identify unresolved durable threads that may deserve attention next time.

It should not become a backlog grooming flow. If it finds unresolved work, it
can name the thread and recommend what should happen next, but the next
session's `/mb-start` is responsible for regenerating the current view.

## Automatic Action Boundary

Main Branch should be proactive. Proactive does not mean opaque.

Allowed without an operator decision when the command is already designed as a
safe read or safe self-maintenance path:

- check status, doctor, graph, update, provider readiness, GitHub activity, and
  checkpoint state;
- read recent commits, issues, proposals, releases, and provider metadata;
- update the Main Branch tool through a supported safe `mb update` path;
- bring in latest saved work for the business repo when the sync is
  proven clean, conflict-free, and safe for unsaved local work;
- repair local runtime wiring when the repair is explicitly safe,
  idempotent, and scoped to Main Branch-generated local wiring.

Requires an approval moment:

- saving a checkpoint;
- applying migrations to a business repo;
- changing business files outside a proven-safe sync or explicit checkpoint
  flow;
- creating or closing public/shared GitHub issues;
- creating branches or pull requests;
- merging proposals;
- publishing, deploying, spending money, emailing customers, changing provider
  accounts, or mutating customer/member data;
- writing raw provider exports, finance/legal data, or sensitive details into
  a repo.

When speaking to the operator, do not expose technical state as the default
sentence. Say "I saved your work," "I found saved work from another workspace,"
"Main Branch updated itself," "this needs your approval before it changes the
business," or "this provider is not ready." Command details remain available
for inspection and repair.

## Graph, Connectors, And Playbooks

The graph is not a task graph first. It is relationship memory across business
primitives and technical memory:

```text
core strategy chooses where to push
bet names what we are testing
decision records why the direction changed
research records what we learned
push coordinates the work
playbook defines the repeatable procedure and checks
provider refs point to external systems
issue tracks durable open work when needed
proposal reviews a change
checkpoint saves progress
outcome and reflection feed the next Sense pass
```

Connectors and sidecars follow the dependency choices contract. `mb` should
wrap provider paths when they improve a loop through readiness checks, safe
metadata, JSON facts, repair guidance, approval gates, or business-language
routing. Missing connectors degrade the relevant path; they do not break the
core daily loop.

Playbooks are not task trackers. A playbook is a repeatable operating procedure
with prerequisites, provider readiness, checks, expected artifacts, and outcome
evidence. A playbook run may create research, pushes, decisions, checkpoints,
provider refs, or GitHub issues, but the playbook itself is not a generic list
of tasks.

Deterministic checks may become a broader product surface, but this decision
does not settle "checks" as a standalone primitive. Here, checks mean the
provider readiness, validation, site, graph, status, and playbook evidence that
already belongs to `mb` and supported provider rails.

## Consequences

- Remove stale "pick a task tracker" guidance from bundled skills and setup
  docs.
- Stop teaching `focus.md`, `todo.md`, or `tasks/` as Main Branch primitives.
- Reframe decision-as-tracker language: decisions are rationale and direction.
- Keep `mb status` GitHub translation fields such as assigned tasks and open
  proposals, because they are useful derived views over GitHub facts.
- Teach `/mb-start` as regeneration from current facts, not backlog reading.
- Teach `/mb-end` as closure, crystallization, and checkpointing, not tomorrow
  planning.
- Keep future dashboards as views over repo, git, GitHub, graph, connectors,
  sidecars, provider facts, and checkpoints. They must not become the canonical
  task database.
- Add an explicit opt-out config for automatic Main Branch tool updates before
  making auto-update behavior the default daily-start path.
- Decide any future "checks" primitive or daily-focus regeneration UI in a
  separate issue so this decision does not smuggle in a new surface.

## Refused

- No `tasks/` directory.
- No `todo.md` or `focus.md` as a recommended Main Branch primitive.
- No decisions-as-default-task-tracker.
- No Linear/Notion as peer durable task primitives in public Main Branch docs.
- No dashboard database as canonical task truth.
- No public issue creation from private thought dumps without an operator
  approval moment.
- No agent-maintained task list as a hidden side effect. Agents should not
  write durable "what I'm tracking" lists into `.context/`, `.mb/`, or any repo
  location as a workaround for not having a task tracker.
