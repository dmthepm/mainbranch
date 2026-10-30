---
title: "PRD: the operating team (role profiles, lanes, and who carries each platform duty)"
status: draft
date: 2026-10-29
release: planned (target v0.8.x, tentative)
linked_issue: https://github.com/dmthepm/mainbranch/issues/1253
related: "#1248 machine doctor (design in #1247), #1255 source health, #1242 homelab skills (unmerged), budget view (no issue yet)"
---

# PRD: the operating team

## One page (read this first)

**The idea.** Main Branch already runs the business: bets, pushes, research,
decisions, outcomes, checkpoints. This PRD adds the **team that runs it**: the
agents, what each one owns, and who keeps the machine, the usage and the data
feeds healthy. It is one design built on what exists.

**Two shapes, same records.**
- **With a platform:** a platform orchestrator (with a security role and a
  usage steward) keeps machines, tools, usage and feeds healthy for several
  businesses. Each business orchestrator runs its own standing roles.
- **Standalone:** no platform. The one business agent carries those duties
  itself, through `mb` commands and skills, and asks the owner to run any fix.

**What's new in `mb` (read-only, like every doctor):**
1. A **role profile** per standing role, committed in the business repo at
   `core/team/<role>.md`: mission in the owner's words, what it owns and
   never does, gates, skills, cadence, model, budget cap, startup reads.
2. **Lane templates**: a brief and a receipt. Every receipt ends with
   "Runbook lines this changes".
3. **`mb team check`**: finds missing charter sections, startup files that
   don't exist, skills that aren't installed, cadence that has drifted, gates
   with no owner, and platform duties with no owner. JSON and exit codes.
4. **Later (batch B):** a budget view in `mb status`. It reads usage, shows
   banked resets for information only, and **never redeems one**.

**What stays outside `mb`:** starting or restarting agents, terminals and
multiplexers, crons, sending messages to the owner, and writing usage
snapshots. `mb` reads records; it never runs the team.

**The duty map** (section 4) says, for each duty: who does it in each shape,
which `mb` command or skill carries it, and which file proves it was done.

**Decisions asked of you:** the four in "Decision asked of reviewers" below.
Nothing here is built yet; shipped pieces are marked **shipped**.

## Decision asked of reviewers

Approve this shape before any code lands:

1. **Role profiles live in the business repo** at `core/team/<role>.md`, one
   file per standing role, with the section order from section 2. Shared
   rules live once at `core/team/agent-rules.md`.
2. **The command is `mb team`**, not `mb role`, because `role` already means a
   repo's kind in topology (`mb/mb/topology.py`, #796).
3. **Lane briefs and receipts stay in local state**, not the repo. `mb` ships
   templates and validates a given file; the durable result of a lane lands
   in the repo as the record it changed (a bet, a decision, a skill edit).
4. **The duty map is data.** A business declares, in
   `core/team/duties.md`, who carries each platform duty: a named role, or
   `platform` with the platform's name. `mb team check` fails a duty with
   no carrier.

Design only. No code ships with this PRD.

Out of scope: starting agents, multiplexers (Herdr or any other), crons and
watchers, message delivery to the owner, quota collection, cross-business
messaging (the gate), and anything that changes the machine. The budget view
is sketched in section 6 for consistency and gets its own batch.

## Standing rules

Carried from the machine doctor rulings (#1247) and the owner's rulings; not
open for change here:

- **Read-only.** `mb team check` writes nothing, calls no network, never runs
  a string from a profile. Paths in a profile are read, never executed.
- **Unverifiable means `not_verified`**, never pass. A runtime `mb` can't see
  (another account's skills, a platform's tool) is `not_verified` with a
  reason, not a guess.
- **Fixes are display-only.** Output lists what to edit; it never edits.
- **Generic in the engine.** Examples are synthetic: `<biz>`, `<platform>`,
  `<owner>`. No real hosts, users, paths or businesses.
- **Never redeem.** No code path in `mb` calls a usage redeem or consume
  endpoint. A test fails if one does (section 6).
- **A role grants no authority.** A profile describes; access comes from
  the account and its tokens.

## 1. Words

| Word | Meaning |
|---|---|
| Team | The agents working one business: an orchestrator, a few standing roles, short-lived lanes. |
| Orchestrator | Owns the business outcome, the gates and every message to the owner. |
| Standing role | Owns one area for good. Passes the three-part test: recurs weekly, owns a window (a surface with one writer), needs memory across days. |
| Lane | One bounded outcome with a brief, a receipt and an independent review. Closes when judged. |
| Gate | A decision a named role must sign in writing (architecture, security, copy). Never self-served. |
| Platform | Whatever keeps the machine, tools, usage and feeds healthy for one or more businesses. A person, a homelab orchestrator, or the business agent itself. |
| Duty | A recurring job someone must carry (section 4). |

## 2. The role profile

One markdown file per standing role, `core/team/<role>.md`, committed. A
profile only in local state is a draft. Front matter holds the facts `mb`
validates; the body holds the charter in a fixed section order.

```markdown
---
schema: mainbranch.team_role
schema_version: 1
id: architect                 # lower case, stable; the agent's address
parent: orchestrator
model: opus                   # family only; the runtime picks the version
runtime: claude-code          # claude-code | codex | other
budget_cap: "stop at 85% of the weekly window"   # text, set by whoever keeps usage
gates: [architecture-review]
skills:
  - {name: mb-think, source: mainbranch}
  - {name: biz-workspace, source: platform}
startup:
  - {path: core/team/architect.md, where: repo}
  - {path: architect/checkpoint.md, where: state}
cadence:
  - {what: "daily read of open design questions", every: daily,
     evidence: {path: architect/log.md, where: state}}
public_face: "issue #<n>"     # optional
---

## Mission in the owner's words
> "<quoted>" (source: decisions/<file>.md)

## Identity
## Owns / Does not own
## Platform services
## Never
## Windows
## Skills
## What the owner sees
## Metrics
## Cadence
```

Notes:

- **Section order and names** match the biz-workspace standard, with the
  maintainer's name replaced by "the owner".
- **`where: state`** paths resolve under a state root from local config
  (`mb` config key `team.state_root`), never hardcoded. With no state root
  set, those reads are `not_verified` (`state_root_unset`).
- **Startup reads stay short**: the profile and one checkpoint. Learning 1
  (29 Oct): a pilot goes stale unless a file that a restart loads holds it.
  The profile is that file.
- **`budget_cap` is text** in v1. The usage keeper writes it; `mb` only
  checks it is present. A numeric cap waits for the budget view.
- **The orchestrator has a profile too**, plus the roles table: `mb team
  show` renders the table from the profiles (agent, model, gates, cap,
  startup), so nobody maintains it by hand. Runtime facts (pane, session id)
  stay in the orchestrator's local checkpoint.

## 3. Lanes: brief and receipt

Templates ship in `templates/team/`. Both live in local state under
`<state_root>/lanes/`. A lane's id is `<job>_<model>`, free length (learning
6: bounded id formats fail at scale).

**Brief sections:** role and model; parent; authority to read first;
outcome (checkable); never (secrets printed, pushes, sends, spend, deletions,
what waits for the owner); steps; deliverable (receipt path); the single
done-ping.

**Receipt sections:** what changed (with commit or PR); checks run with
results; quota at start and close where the brief set a cap; what was not
done (marked PARTIAL or NOT VERIFIED); open questions; and last,
**Runbook lines this changes**: each line names a skill or doc file and the
change, or says `none`.

`mb team check --brief PATH` and `--receipt PATH` validate one file's
sections. A receipt without the runbook section fails. The owning role
applies the runbook lines before closing the lane; `mb` doesn't check that
(it can't see intent), so it stays a judging step.

## 4. The duty map

Status: **shipped** (in `mb` today), **designed** (an approved or draft
PRD), **proposed** (this PRD), **platform tool** (exists outside `mb`, not
generic yet), **unverified** (no working proof yet).

| Duty | With a platform | Standalone | Carried by | Evidence |
|---|---|---|---|---|
| Business outcome: bets, pushes, decisions, outcomes | Business orchestrator | Business agent | `mb-bet`, `mb-think`, `mb status` (**shipped**) | `bets/`, `pushes/`, `decisions/`, `log/` in the repo |
| Research | A lane or research role | Business agent | `mb-think` (**shipped**) | `research/*.md` |
| Goals and weekly numbers | Orchestrator reads; roles fill | Business agent | No contract yet. Bet `metric`/`target` (**shipped**); a goals file contract (**proposed**, follow-up) | `core/team/goals.md` (proposed) |
| Durable memory | Each role | Business agent | `mb checkpoint`, `/mb-end` (**shipped**) | Git commits |
| Team records and cold starts | Orchestrator | Business agent (one profile, itself) | `mb team` (**proposed**) | `core/team/*.md`; `mb team check` exit 0 |
| Gates | The owning role; orchestrator routes | Owner, or the agent with an independent review lane | `mb team check` `team.gates.owner` (**proposed**) | Verdict file naming the head SHA |
| Lanes | The owning role | Business agent | Templates + `mb team check --receipt` (**proposed**) | Receipt with runbook lines |
| Usage and caps | Platform usage steward writes snapshots; roles read | Business agent reads its runtime's own usage screen | Budget view (**proposed**, batch B); snapshot writer is a **platform tool** | Quota snapshot; standalone is **unverified** (no snapshot writer) |
| Machine health | Platform orchestrator + platform security | Business agent runs doctor; owner runs fixes | `mb machine doctor` (**designed**, #1247) | Doctor JSON, exit 0 |
| Source health (feeds still flowing) | Platform collectors write records; platform alerts | The business's scheduled sync writes records | `mb` reader (**designed** in an interface draft for #1255) | Status record per source |
| Updates | Platform updates shared tools, then each business runs `mb update` | Business agent runs `mb update --check` at start | `mb update`, `/mb-start` (**shipped**) | `mb update --check` JSON |
| Security checks and CVE watch | Platform security; a CVE export | Business agent runs a weekly security check | Homelab skills (#1242, **unmerged**); CVE export (**platform tool**) | Review file; export rows |
| Credentials | Platform holds machine and tool credentials; business holds provider credentials | Business agent, owner signs in | `mb connect` (**shipped**) | `mb connect list` |
| Several businesses at a glance | Platform | n/a | `mb fleet checkin` (**shipped**) | Fleet JSON |
| Briefing the owner | Orchestrator only, through the platform's channel | The session itself, and `/mb-end` | Outside `mb` (delivery); `/mb-end` (**shipped**) | Platform message log; standalone: the checkpoint commit |
| Backups | Platform | Owner, checked by doctor | `mb machine doctor` `backups.*` (**designed**) | Doctor JSON |

`core/team/duties.md` holds this table for one business, with the carrier
column filled: a role id, or `platform: <name>`. Rules for `mb team check`:

- A duty with no carrier fails (`team.duty.owner`).
- A carrier that names a role with no profile fails.
- `platform: <name>` passes as `not_verified` (`outside_repo`): the repo
  can't see the platform. That is the honest answer, and it doesn't block
  exit 0 for duties the business doesn't own (see exit codes).

**Worked example (placeholder form of a real pilot).** Platform:
`<platform>-orchestrator`, `<platform>-security`, `token-steward`.
Business `<biz>`: `<biz>-orchestrator` with standing roles `product`,
`architect` (design, gate: architecture), `security` (gate: security
verdict naming the head SHA). Usage, machine, source health, CVE watch and
shared-tool updates: `platform: <platform>`. Bets, research, lanes, gates,
`mb update` in the repo: business roles. In the standalone shape the same
`duties.md` names `orchestrator` on every row and drops the fleet row.

What the pilot proved so far: charters, startup files, the roles table,
lane briefs and receipts with runbook lines, gate verdict files, and a
usage snapshot read before each batch, all by hand. Not yet proved: any of
it validated by `mb`, a standalone business carrying the platform duties,
and source health end to end.

## 5. `mb team`

```
mb team show [<role>] [--json]   # roles table, or one role's startup reads
mb team check [<role>] [--brief PATH | --receipt PATH] [--json]
```

### Checks

| Id | Fails when | Not verified when |
|---|---|---|
| `team.profile.schema` | Front matter missing, unknown `schema_version`, bad types | n/a (unreadable is fail, `unreadable_file`) |
| `team.charter.sections` | A required section is missing or out of order | n/a |
| `team.charter.mission-source` | Mission has no quote, or its source path doesn't exist in the repo | n/a |
| `team.startup.exists` | A `repo` startup path doesn't exist | A `state` path with no state root, or outside it |
| `team.skills.installed` | A `mainbranch` skill isn't in the repo's bundled set | A `platform` or `other` skill: `outside_mb` unless found in a known skill dir for the runtime |
| `team.cadence.drift` | Evidence is older than its cadence plus grace (daily: 36 h; weekly: 9 days) | Evidence path unreadable or in state with no root |
| `team.gates.owner` | A gate named in `duties.md` or a profile has no single owning role, or two | n/a |
| `team.duty.owner` | A duty has no carrier, or names a missing role | Carrier is `platform: <name>` |
| `team.cap.present` | A standing role has no `budget_cap` | n/a |
| `team.size` | More than the configured number of standing roles (default 4 plus the orchestrator) | n/a; this one is `warn` |
| `team.receipt.runbook` | `--receipt` file has no "Runbook lines this changes" section | n/a |

Cadence evidence uses the file's own time where it can (the newest dated
line in a log, the git commit time for a repo file), not the file's mtime.
Learning 6: a stateless reader needs since-fields in the record.

### Output and exit codes

The shared JSON envelope (`docs/json-output-contract.md`) plus
`schema: "mb.team.check"`, `schema_version`, `safe_to_share: true` (profiles
are repo content; no state file contents are echoed), `summary{counts}` and
`checks[]` with `id`, `role`, `status`, `reason`, `fix` (display-only text).

States and exit precedence match the machine doctor: `2` > `1` > `3` > `0`.

| Code | Meaning |
|---|---|
| 2 | Usage error, or no `core/team/` directory. No verdict. |
| 1 | At least one fail. |
| 3 | No fail, but a business-owned check is `not_verified`. |
| 0 | Every business-owned check passed. `platform`-carried duties may be `not_verified`; they are counted and listed, never shown as passed. |

`mb status` gets one line from this (`team: 4 roles, 1 issue`) once it
ships; `/mb-start` routes a failing team check to the orchestrator's first
action.

## 6. Budget view (batch B, sketched so A doesn't contradict it)

- **Input:** usage snapshots in a directory named in local config
  (`team.usage_dir`), never a hardcoded path. Files `claude.json` and
  `codex.json`, `schema_version` 1. An unknown version is refused and shown
  as `not_verified` (`schema_unknown`).
- **Stale:** a snapshot older than 1 hour, or any reading older than 3
  hours, is unknown. Unknown is never "available".
- **Shown:** per account, used %, window end, session %, age of the reading;
  each role's `budget_cap` next to it.
- **Banked resets:** count and expiry, for information only. An expiring
  reset is never a reason to redeem.
- **Never redeem.** `mb` has no code path that calls a redeem or consume
  endpoint. A static test scans the package and fails on any such call.
- **The one suggestion:** only when a weekly window reads 100% used, `mb`
  shows a question for the owner ("Use one banked reset now?"). It never
  acts on the answer.
- **Standalone:** no snapshot writer exists, so the view shows `unknown`
  and points at the runtime's own usage screen. A writer for standalone
  owners is a follow-up, not v1.

## 7. Learnings folded in (29 Oct)

1. Role cards held in a file a restart loads: the profile (section 2).
2. Quota snapshot, reading ages, never redeem until zero: section 6.
3. Security patches skipping the minimum release age, and 4. a daily
   toolbox existence check: not this PRD; they belong to the machine skill's
   maintenance notes.
5. Cutover gaps on a new host: the machine doctor's new-host checks
   (#1248), not here.
6. Bounded ids fail at scale: lane ids are free length. Stateless readers
   need since-fields: cadence evidence reads in-record times. One row per
   key: `duties.md` allows one carrier per duty.

## 8. Validation plan for the code batch

- Fixture business repos: a full team, a standalone agent, a profile
  missing each section, a state root unset, a stale cadence, an orphan gate,
  a `platform` carrier.
- Exit-code tests for each precedence case.
- Static tests: no subprocess and no network in `mb team`; no redeem or
  consume call anywhere in the package.
- Templates round-trip: a filled brief and receipt pass `mb team check`.
- Runtime smoke: `mb team show` and `mb team check --json` in a fixture
  business repo from an installed wheel, per `AGENTS.md`.
- A real run on the pilot business's repo, with its result in the receipt.

## Open questions

1. `core/team/` or `core/operations/team/`? `core/operations/` already holds
   loop state. Recommendation: `core/team/`, shorter and owner-readable.
2. Should `goals.md` get its contract in this batch, or its own issue?
   Recommendation: its own issue; this PRD only references it.
3. Is the default size limit (4 standing roles) right for a standalone
   business, which may want 0? Recommendation: 0 is valid; the limit is an
   upper bound only.
4. Skill discovery for Codex global skills: which directory is
   authoritative? Until answered, Codex skills report `not_verified`.

Next: security and parent review of this draft; then a code batch for
`mb team` (A) with fixtures; then the budget view (B) after the usage
schema is confirmed final.
