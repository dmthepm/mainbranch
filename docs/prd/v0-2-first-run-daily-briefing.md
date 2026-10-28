---
title: "PRD: v0.2 First-Run + Daily Briefing"
status: shipped
date: 2026-05-02
release: v0.2.0
linked_decision: decisions/2026-05-02-github-native-business-os.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/173
  - https://github.com/dmthepm/mainbranch/issues/184
  - https://github.com/dmthepm/mainbranch/issues/185
  - https://github.com/dmthepm/mainbranch/issues/186
  - https://github.com/dmthepm/mainbranch/issues/174
related_prds:
  - docs/prd/v0-2-agent-workflow-and-evals.md
---

# PRD: v0.2 First-Run + Daily Briefing

## Summary

Main Branch v0.2.0 proved the new product shape without building a dashboard
first.

The release made `mb` feel like the front door to a GitHub-native business
operating system:

1. bare `mb` gives a polished interactive launch screen;
2. `mb onboard` guides humans through setup or repo connection;
3. `mb status` gives a cheap daily business/repo briefing;
4. `mb start` makes the handoff to Claude Code explicit and repairable;
5. `mb update` keeps the install and bundled workflows current.

This release did not add full integrations, a live dashboard, autonomous agents,
or multi-runtime execution. It turned the first-run and daily-run loops into a
coherent terminal product.

## Problem

Before this release, the CLI worked, but it assumed the user already understood
the system.

Current behavior:

- `mb init` scaffolded a repo but did not teach or adapt.
- Bare `mb` behaved like a traditional command reference.
- The handoff to Claude Code was mostly copy/paste guidance.
- `/mb-start` carried the daily entry surface, but `mb` did not give a
  pre-runtime status view.
- GitHub was present, but not yet reframed as the business team layer.

This is enough for technical early adopters. It is not enough for the operator
who needs to be taught why git, GitHub, Claude Code, and local files matter.

## Goals

- Make first-run feel intentional, educational, and safe.
- Respect both beginners and power users.
- Preserve scriptability and boring CLI behavior where required.
- Establish `mb status` as the reusable daily briefing primitive.
- Make the Claude Code handoff explicit, diagnosable, and repairable.
- Create terminal output that feels like a product, not a scaffolding script.
- Keep all business state in the repo.

## Non-Goals

- No dashboard/server process in v0.2.0.
- No background daemon.
- No model invocation inside `mb`.
- No full multi-runtime adapter execution.
- No Google/Meta/Postiz/Cloudflare analytics sync yet.
- No secrets/credentials system beyond what is already required for current
  doctor checks.
- No database/index beyond cheap reads from git, filesystem, and GitHub CLI.

## Target Users

### Beginner

They have little or no terminal/GitHub experience. They need confidence, plain
language, and the "why" behind the stack.

Success for this user: they can install, create a repo, understand that GitHub
is where the business work lives, and start Claude Code without feeling lost.

### Intermediate

They have GitHub or terminal exposure but do not yet think of GitHub as a
business operating layer.

Success for this user: they can connect or create a repo, understand the file
taxonomy, and know when to use `mb` vs Claude Code.

### Power User

They already live in git, GitHub, and terminal tools.

Success for this user: they can skip education, inspect raw commands, connect an
existing repo, and see useful status/JSON surfaces quickly.

## User Experience Principles

- Teach the model, not only the mechanics.
- Let users skip explanations.
- Use business language by default, raw GitHub language when useful.
- Make the terminal warmer without turning it into a toy.
- Keep failure messages repair-oriented.
- Never hide where data lives.
- Never put secrets in repo files.

## Product Scope

### 1. Bare `mb` Launch Screen

Linked issue: #184

When a user runs `mb` with no arguments in an interactive terminal, show a
polished launch screen.

Required routes:

- "New here?" -> `mb onboard`
- "Daily work" -> `mb status`
- "Open agent runtime" -> `mb start`
- "Fix/check setup" -> `mb doctor`
- "Power user commands" -> normal command reference

TTY rules:

- Interactive TTY: show launch screen.
- Non-TTY: keep deterministic help/exit behavior.
- `mb --help`: always show plain command reference.
- Tests must cover TTY vs non-TTY behavior.

Tone:

- Light trail/retro flavor is allowed.
- No giant ASCII wall by default.
- Must be fast to render.
- Must not require reading a long story before using the tool.

Acceptance:

- Bare `mb` in a normal terminal shows the launch screen.
- `mb --help` stays plain.
- Piped/non-interactive invocation does not hang or prompt.
- Launch screen links to real commands that exist or clearly say "coming next"
  only inside this release branch before implementation lands.

### 2. `mb onboard`

Linked issue: #185

`mb onboard` is the human setup flow. `mb init` remains the quiet, scriptable
primitive.

Required capabilities:

- Detect or ask experience level:
  - terminal familiarity;
  - GitHub familiarity;
  - Claude Code installed/known;
  - existing repo vs new repo.
- Offer three paths:
  - beginner guided setup;
  - intermediate setup with shorter explanations;
  - power-user setup with advanced options and minimal copy.
- Create a new repo through `mb init` or connect an existing repo.
- Explain why GitHub is used as the team/business layer.
- Explain where business state lives.
- Wire Claude Code skills through existing skill-link code.
- Verify skill discovery and runtime readiness through doctor/status checks.
- End with exact next commands.

Suggested beginner flow:

1. Welcome/launch screen.
2. "Have you used GitHub before?"
3. "Create new business repo or connect existing?"
4. Business name and repo path.
5. Short explanation: GitHub = tasks/proposals/history, repo = business
   brain, Claude Code = first execution runtime.
6. Scaffold/connect.
7. Verify `gh`, `git`, `claude`, skill wiring.
8. Show daily ritual.

Power-user requirements:

- `--yes` or equivalent fast path for smoke tests.
- `--path`, `--name`, and existing repo options.
- No forced educational copy.

Acceptance:

- Re-running is idempotent.
- Existing initialized repo is detected and repaired, not overwritten.
- Missing `gh` or Claude Code results in clear repair instructions.
- Does not require a GitHub API write for local-only setup.
- Produces `--json` output or a clear future path for automation.

### 3. `mb status`

Linked issue: #173

`mb status` is the first daily briefing primitive. It should be cheap, local
first, and useful before any dashboard exists.

Required sections:

- Repo:
  - path;
  - whether it looks like a Main Branch repo;
  - git branch and dirty/clean state;
  - install mode and Main Branch version.
- Runtime:
  - Claude Code found/missing;
  - skill wiring found/missing;
  - suggested repair command.
- Brain:
  - counts for core, research, decisions, pushes, legacy campaigns, log, and documents;
  - recent research;
  - recent decisions;
  - stale proposed/running decisions if detectable.
- GitHub, when `gh` is authenticated:
  - assigned open issues;
  - review requests or mentions if available cheaply;
  - recent merged PRs;
  - blocked/stale labels where present.
- Next actions:
  - one to five deterministic suggestions based on checks.

Output modes:

- human terminal summary by default;
- `--json` with stable top-level sections;
- degraded mode when `gh`, network, or git data is unavailable.

Acceptance:

- Runs in under a few seconds on a normal repo.
- Does not invoke a model.
- Does not modify repo files.
- Does not require GitHub auth to be useful.
- `/mb-start` can later call or mimic its data model.

### 4. `mb start`

Linked issue: #186

`mb start` is the runtime handoff helper.

Required behavior:

- Resolve target repo:
  - current directory if it is a Main Branch repo;
  - `--repo <path>` override;
  - future recent-repos support can come later.
- Run the handoff-relevant subset of `mb status` or `mb doctor`.
- Verify Claude Code is installed.
- Verify skill wiring.
- Print the exact command:

```bash
cd <repo>
claude
# then run /mb-start
```

Optional behavior:

- `--launch` may run `claude` directly if safe.
- `--json` emits command, repo path, runtime, and readiness.

Acceptance:

- Does not invoke a model itself.
- Handles missing Claude Code with install guidance.
- Handles missing skill wiring with `mb skill link --repo <path>`.
- Safe to run repeatedly.

### 5. `mb update`

Linked issue: #174

`mb update` owns the install-mode-aware refresh mechanism that `/mb-update`
calls and explains for normal Claude Code users.

Required behavior:

- Detect install mode:
  - pipx/PyPI;
  - editable/source clone;
  - unknown.
- For pipx installs, run the package refresh behind `mb update`; do not make
  normal users choose package-manager commands.
- For clone/source mode, recommend or run `git pull --ff-only`.
- Repair skill links after update when needed.
- Print what changed or where to read changelog when available.

Acceptance:

- Safe dry-run mode.
- Clear output for pipx vs clone mode.
- Does not corrupt editable installs.

## Data and State

The shipped v0.2.0 scope used only:

- repo files;
- git metadata;
- existing `.claude/` skill wiring;
- existing local config if present;
- GitHub CLI reads where authenticated.

Do not add a database in v0.2.0. Do not add background sync. Do not add a
dashboard server.

## CLI/API Requirements

Every new command should support:

- human terminal output;
- clear exit codes;
- no hangs in non-interactive mode;
- testable functions below the Typer command layer;
- JSON output where another skill/runtime/dashboard will likely consume it.

Suggested exit code conventions:

- `0`: usable / success;
- `1`: expected user-fixable issue;
- `2`: command/runtime error;
- `130`: user canceled.

## Copy and Language

Use business-first language, with raw terms in parentheses when helpful.

Examples:

- "tasks (GitHub issues)"
- "proposals/conversations (pull requests)"
- "what shipped (merged PRs)"
- "business brain (your repo)"

Avoid overclaiming. v0.2.0 is still terminal-first and Claude-Code-first.

## Release Plan

Each release should be a meaningful product slice. Avoid splitting work so
finely that cold start, PR creation, review, CI, and merge overhead cost more
than the feature. Prefer one branch per coherent user loop, with multiple
concern-based commits inside the branch.

### v0.2.0

- #184 bare `mb` launch screen
- #185 `mb onboard`
- #173 `mb status`
- #186 `mb start`
- #174 `mb update`

Success criteria:

- a fresh user can install Main Branch and run bare `mb`;
- the launch screen makes the next step obvious without breaking `mb --help` or
  non-interactive scripts;
- onboarding can create or connect a business repo and explain GitHub in
  business language;
- `mb status` gives a useful daily briefing without invoking a model;
- `mb start` gets the user to Claude Code with skill discovery verified or a
  clear repair path;
- `mb update` handles pipx and clone/source installs accurately;
- the full first-run loop is proven with CLI tests, fixture repo smoke, and a
  Claude Code `/mb-start` smoke or an explicit blocker note.

### v0.2.1

- #188 GitHub activity briefing primitives
- #121 graph index + interactive view
- #122 cross-reference validation
- #187 `mb connect` foundation

Success criteria:

- `mb status` can include cheap GitHub activity when `gh` is authenticated;
- graph/index output can answer basic entity, tag, and relationship questions;
- cross-reference validation catches stale links and broken references;
- `mb connect` establishes the credential/config pattern without putting
  secrets in the repo;
- at least one real business repo can use the briefing and graph data without
  manual file spelunking.

### v0.2.2

- #177 runtime adapter contract
- #124 cross-runtime compatibility
- #131 runtime-aware invocation hints
- #130 tool tethering
- #143 similar-bets graph query

Success criteria:

- the runtime adapter contract is documented and tested against Claude Code plus
  at least one other runtime target;
- invocation hints do not hardcode Claude Code as the only path;
- tool tethering produces clear setup/repair guidance;
- similar-bets queries demonstrate that graph context improves real workflow
  selection;
- compatibility claims stay narrower than what has been tested.

### v0.3.0+

- #189 dashboard spike
- #128 `mb books`
- mb-site/mb-ads/mb-think deeper workflow surfaces
- first structured data sync

Success criteria:

- dashboard/server mode is explicit, local-first, and optional;
- local operational state has a documented home and repair story;
- one structured data sync proves the database/index pattern before
  generalizing;
- domain-specific workflow surfaces earn their scope through real usage rather
  than splitting into premature separate CLIs.

## Linear Mapping

| Issue | Priority | Status | Release |
|---|---|---|---|
| #112 Accept GitHub-native business OS direction | Urgent | Closed | v0.2 Direction |
| #183 PR: GitHub-native business OS decision | Urgent | Merged | v0.2 Direction |
| #184 TTY-aware bare `mb` launch screen | Urgent | Closed | v0.2.0 |
| #185 `mb onboard` adaptive setup flow | Urgent | Closed | v0.2.0 |
| #173 `mb status` daily briefing v0 | Urgent | Closed | v0.2.0 |
| #186 `mb start` runtime handoff helper | High | Closed | v0.2.0 |
| #174 `mb update` install-mode-aware refresh | High | Closed | v0.2.0 |
| #80 `/mb-ads` compliance gate | Urgent | To Do | v0.1.3 |
| #188 GitHub activity briefing primitives | High | To Do | v0.2.1 |
| #187 `mb connect` foundation | High | To Do | v0.2.1 |
| #121 graph index + interactive view | High | To Do | v0.2.1 |

Everything not listed above is out of scope for this v0.2.0 product slice
unless explicitly pulled forward.

## Open Questions

- Should bare `mb` route to `mb status` by default after onboarding has run?
- Should `mb onboard` create GitHub repos through `gh` or only local repos in
  v0.2.1+?
- What is the minimum useful GitHub read for `mb status` without slowing it down?
- Where should recent repo selection live: local config now or wait for v0.2.1?

## Definition of Done

v0.2.0 was done when a fresh user could:

1. install Main Branch;
2. run `mb`;
3. choose onboarding;
4. create or connect a business repo;
5. run `mb status` and understand the repo state;
6. run `mb start` and reach Claude Code with clear `/mb-start` instructions;
7. update Main Branch through `mb update`;
8. recover from common missing-tool states through clear repair guidance.

Development work for this release should follow the agent workflow and runtime
eval ladder in
[`docs/prd/v0-2-agent-workflow-and-evals.md`](v0-2-agent-workflow-and-evals.md).
In particular, CLI tests are not enough for first-run work: changes that affect
skill discovery, runtime handoff, or `/mb-start` need a Claude Code smoke or an
explicit note explaining why it could not be run.
