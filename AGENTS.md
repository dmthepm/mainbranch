# Agent Instructions

Main Branch also carries read-only `mb-homelab-*` skills for securing the machines that run your agents; they do not touch business data. See [homelab skills](docs/homelab-skills.md).

Main Branch is public open-source infrastructure. Treat this file as the
repo-level operating contract for Codex, Claude Code, and any other agent or
human contributor working in this repository.

## Product Shape

Main Branch is a CLI plus agent-runtime skill system for running a business from
markdown files in git.

- `mb` is the deterministic, inspectable, scriptable control plane.
- Agent-runtime skills are the judgment-heavy execution layer.
- Shared workflow sources are the runtime-agnostic workflow contract; runtime
  shells and generated guidance are adapters over those sources.
- GitHub issues are tasks.
- Pull requests are proposals and review conversations.
- Git history is the evolution story.
- A user's business repo is the durable business brain.
- A user is not met with git speak but instead business speak.

Claude Code and Codex CLI are the supported agent runtimes today. Claude Code
uses project-local slash skills. Codex uses generated `AGENTS.md`, global Main
Branch skills, deterministic `mb` facts, and workflow inventory. That is
daily-loop Codex support, not full production workflow parity. Business repos
should not carry repo-local Codex plugin or skill copies unless a future issue
proves that fallback is required.
Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, and local runtimes
remain compatibility targets until tested. Do not claim support before there is
an adapter and smoke evidence for the exact surface.

The public product frame lives in `docs/ethos.md`, the operator loop taxonomy
lives in `docs/operator-loops.md`, and release direction lives in
`docs/roadmap.md`.

## Daily Operating Loop

The current product center is the daily owner loop:

1. The operator opens the business repo and starts Claude Code or Codex CLI.
2. `/mb-start`, the generated repo instructions, or global Main Branch Codex
   skills ground the agent in deterministic `mb` facts before advice.
3. The agent routes thought dumps and requests into business primitives:
   bets, goals, offers, research, decisions, pushes, playbooks, outcomes, and
   checkpoints.
4. `mb` keeps the repo healthy: repo shape, status health, graph links,
   provider readiness, runtime wiring, update/repair paths, validation, and
   guarded commits.
5. `/mb-end` and `mb checkpoint` reconcile what changed so durable business
   memory stays in git.

Normal users should not have to manage git plumbing directly. Issues, branches,
pull requests, commits, graph links, and provider state are the hidden technical
memory layer that preserves and inspects business progress. Describe those
primitives in business language first: tasks, proposals, saved checkpoints,
relationship health, provider readiness, and outcomes.

When working on this loop, check the current GitHub issues instead of copying a
stale plan into docs. Issue anchors change quickly. For daily-loop guardrail
work, verify the live issue state around generated repo guidance, migration
lint, topology/status/graph facts, child repo descriptors, reusable playbooks,
runtime dogfood, and provider readiness before treating any anchor as active.
If docs need examples, describe the topic and link the active issue only after
checking GitHub.

## Quick Start

First-time setup is in [CONTRIBUTING.md](CONTRIBUTING.md#local-setup).

For normal repo validation:

```bash
scripts/check.sh
```

For focused CLI work:

```bash
cd mb
pytest tests/test_<area>.py -q
```

For package/install changes:

```bash
(cd mb && python3 -m build)
python3 -m venv /tmp/mainbranch-smoke
/tmp/mainbranch-smoke/bin/pip install mb/dist/*.whl
/tmp/mainbranch-smoke/bin/mb --version
/tmp/mainbranch-smoke/bin/mb skill list
```

## Repository Layout

```
.
+-- AGENTS.md          # shared instructions for repo agents
+-- CLAUDE.md          # Claude Code adapter instructions
+-- README.md          # public user-facing entrypoint
+-- CHANGELOG.md       # public release truth
+-- CONTRIBUTING.md    # contributor workflow
+-- decisions/         # dated product/architecture decisions
+-- docs/              # setup, compatibility, PRDs, checklists, migration docs
+-- mb/                # Python package, CLI, tests, bundled data
+-- .claude/skills/    # bundled Claude Code skill source
+-- templates/         # files copied into created business repos
+-- workflows/         # runtime-agnostic workflow source contracts
+-- tools/             # experimental helper tools
+-- scripts/           # repo-level validation helpers
```

## Repo Surfaces

Changes may affect one or more public surfaces:

- CLI behavior in `mb/mb/` and `mb/tests/`;
- packaged data under `mb/mb/_data/`;
- bundled skills under `.claude/skills/`;
- shared workflow sources under `workflows/` and generated runtime shells or
  fixtures derived from them;
- business-repo scaffolding under `templates/` and `mb/mb/init.py`;
- user docs in `README.md`, `docs/beginner-setup.md`, `docs/migrating.md`,
  `SUPPORT.md`, and `docs/compatibility.md`;
- contributor/agent docs in `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and
  `.github/`;
- release surfaces in `CHANGELOG.md`, GitHub Releases, PyPI metadata, and
  Linear Releases.

Do not assume a change is "just docs" when it changes instructions that agents,
skills, users, or release automation follow.

## Public / Private Boundary

This repository is public. Every committed file should be safe for a stranger to
read forever.

Public is appropriate for:

- deterministic CLI behavior;
- runtime-agnostic skill contracts;
- product decisions, PRDs, and release criteria;
- sanitized examples and fixtures;
- open-source support, security, and contribution docs.

Do not commit:

- secrets, tokens, credentials, raw account data, or customer/member data;
- private local paths, personal operating preferences, or machine-specific
  automation details;
- private community operations, launch plans, or partner/customer strategy;
- untested runtime compatibility claims.

Use OS temp for throwaway scratch repos. Use `.agent/` for repo-local,
gitignored agent logs, smoke-test evidence, and branch-local handoff notes.
Some hosted runners may provide their own ignored scratch space; public examples
in this repo use `.agent/`. Scratch space is not durable product truth. Durable
truth belongs in code, tests, docs, decisions, fixtures, or GitHub issues.

## Start Protocol

Use [`docs/agent-cold-start.md`](docs/agent-cold-start.md) for the full
cold-start sequence. The short version:

1. Read the always-read set first: this file, `README.md`, `docs/ethos.md`,
   `docs/operator-loops.md`, `docs/roadmap.md`,
   `docs/oss-operating-checklist.md`, and the current `CHANGELOG.md`
   `[Unreleased]` plus latest shipped section.
2. Read the assigned GitHub issue and all comments. Maintainer and hosted
   agents with Linear access then call Linear MCP `get_issue` for the mirrored
   Linear issue and use the returned `gitBranchName` as the branch name.
   External contributors without Linear access can use a GitHub-native branch
   name and reference the issue in the PR. GitHub is the public durable work
   thread for comments by default; Linear-only comments are for private logs or
   internal team context.
3. Write a local cold-start note for substantial branches before editing.
4. Progressively discover task-specific docs and decisions only after the work
   thread is clear: runtime docs for runtime claims, release docs for
   release-bearing work, skill docs for skill changes, PRDs/decisions for
   product choices, and post-release docs for post-release sweeps.
5. Check open PRs for overlapping files before making broad edits.

For substantial branches, write a local cold-start note before editing:

```md
# Cold Start

Issue:
Linear ID:
Release:
Priority:
Status:

## Scope

In:

Out:

## Risks

-

## Validation Plan

- Static:
- CLI:
- Package/install:
- Fixture repo:
- Runtime/manual:
```

## Work Shape

Prefer one coherent user loop per branch. Do not broaden scope silently. If you
find adjacent work, open or comment on a follow-up issue instead of burying it in
the current PR.

Name which operator loop the branch improves: Sense, Decide, Ship, or
Reflect. Use `docs/operator-loops.md` when the fit is unclear.

Good issue slices look like:

- one command surface, such as `mb status`;
- one repair loop, such as `mb update`;
- one validator, such as cross-reference validation;
- one runtime proof, such as Claude Code `/mb-start` discovery from a fresh repo.
- one product loop, such as "turn user friction into a GitHub issue draft" or
  "surface the next three actions from status signals."

Avoid tiny PRs that cost more in cold start, review, CI, and merge overhead than
they return. Large PRs are fine when they have one success metric and
concern-organized commits.

## Branches, Issues, and Releases

GitHub issues in this repo mirror to Linear. Maintainer and hosted agents with
Linear access should call Linear MCP `get_issue` for the mirrored Linear issue
and use its `gitBranchName`; this normally has the shape
`<username>/main-<number>-<full-ticket-title-lowercase-with-dashes>`. Preserve
Linear IDs in branch names, commit messages, and PR metadata so Linear Releases
can attach work correctly.

External contributors without Linear access can use a GitHub-native branch name
such as `<gh-username>/<issue-number>-<short-title>` and reference the GitHub
issue in the PR. If work truly has no issue, create the public GitHub issue
first when the work is product-facing. For non-issue maintenance, use a short
concrete branch name such as `<gh-username>/status-briefing` or
`<gh-username>/runtime-smoke`.

GitHub remains the public durable issue thread:

- use `Closes #N` only when the PR fully completes the GitHub issue;
- use `Refs #N` for partial slices or related context;
- comment on GitHub issues when scope changes, blockers appear, or a branch is
  ready for review; the GitHub comment syncs to Linear;
- use Linear-only comments only for private logs or internal context that should
  not appear on public GitHub;
- keep target release and priority visible in the local cold-start note and PR
  bodies for release-bearing work.

## Linear-Hosted Agents

When launched from Linear or assigned a Linear issue:

- treat the Linear issue as the task brief, but verify durable details in this
  repository before editing;
- use the Linear issue's `gitBranchName`;
- preserve the Linear ID in branch, commit, and PR metadata;
- map Linear status honestly: move to started/in progress only when coding or
  writing actually begins, and do not mark shipped until release verification
  proves users can install it;
- keep GitHub issue closure accurate with `Closes #N` only for fully completed
  GitHub issues;
- comment when scope changes, blockers appear, or validation cannot reach the
  required level;
- open a PR when the hosted-agent workflow expects it, but never merge it unless
  explicitly instructed.

Workspace-level Linear guidance should stay short and point agents back here.
This file is the detailed contract.

## GitHub Workflow

Prefer the GitHub CLI for GitHub truth and mutations:

```bash
gh config set pager cat
gh config set prompt disabled
```

Use `gh issue view`, `gh issue list`, `gh pr view`, `gh pr diff`,
`gh pr checks`, `gh pr create`, and `gh pr edit` when GitHub work is needed.
Do not merge a PR unless the maintainer explicitly asks for merge.

Hosted agents that are assigned an issue may open a PR when their task runner
expects it. Local branch-author agents should follow the current prompt: if it
says to stop before PR creation, push the branch and report that it is ready.

## Commit Discipline

Use concern-based commits. A reviewer should understand the branch from:

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

This repo commonly uses:

- `[add] Brief description`
- `[update] Brief description`
- `[fix] Brief description`
- `[remove] Brief description`
- `[refactor] Brief description`

Do not rewrite pushed history unless the maintainer explicitly asks.

## Validation Ladder

Use the lightest eval that proves the behavior. Do not ship first-run,
runtime-discovery, update, packaging, or skill changes on unit tests alone.

For release-bearing flows, the *how* of running these checks — picking one
runtime path, capturing stdout/stderr/exit on the first run, and not
re-running long checks to recover lost evidence — lives in
[`docs/release-agent-contract.md`](docs/release-agent-contract.md).

Level 0, docs/decision:

- frontmatter where expected;
- links resolve;
- no stale product claims;
- no private details in public docs.

Level 1, static:

```bash
scripts/check.sh
```

Run this from the repo root before pushing. It mirrors CI's package working
directory; do not substitute root-level `mypy mb` unless you also pass the right
config.

Level 2, CLI contract:

- focused Typer/CliRunner tests;
- exit codes;
- `--json` behavior where present;
- TTY vs non-TTY behavior for launch and onboarding UI;
- no hangs in scripts or CI.

Level 3, package/install smoke:

Run when packaging, entrypoints, bundled data, skill discovery, or update paths
change.

```bash
(cd mb && python3 -m build)
python3 -m venv /tmp/mainbranch-smoke
/tmp/mainbranch-smoke/bin/pip install mb/dist/*.whl
/tmp/mainbranch-smoke/bin/mb --version
/tmp/mainbranch-smoke/bin/mb skill list
```

Use `pipx install --force ...` or `pipx upgrade ...` smoke when install/update
behavior changed.

Level 4, fixture repo:

```bash
tmpdir="$(mktemp -d)"
mb onboard --yes --name "Test Business" --path "$tmpdir/test-business"
cd "$tmpdir/test-business"
mb doctor
mb status
mb start --json
mb validate
```

Level 5, runtime smoke:

- create a fresh business repo;
- launch the relevant runtime from that repo;
- verify `/mb-start` or the equivalent runtime entrypoint is discoverable;
- verify the skill reads the business repo and does not write into the engine
  repo;
- record the evidence in the PR.

For Claude Code release-bearing runtime evidence, follow the
[Claude Code runtime dogfood runbook](docs/claude-code-runtime-dogfood.md).
Use `scripts/claude-runtime-dogfood.py --install-mode editable` when you need
repeatable deterministic fixture, CLI, repo-boundary, and evidence-template
collection. Choose the PR smoke, pre-release candidate, or release acceptance
prompt tier from [docs/release-simulations.md](docs/release-simulations.md)
when release validation needs operator-moment simulations. The optional
`--run-claude-print` path is proxy evidence only; it does not replace
interactive Claude Code TUI smoke for release-bearing runtime claims. For
package-visible releases, answer the pre-simulation prompt checkpoint, run the
release candidate and release acceptance tiers before tagging whenever
feasible, and manually review transcript excerpts for whether Claude actually
used `mb` facts or only produced a permission-distorted fallback.

If a runtime cannot be launched because of auth or UI constraints, say that
explicitly and describe the closest verified fallback. Do not pretend CLI tests
cover runtime discovery.

## Skill Maintenance

Bundled skills are product code even when implemented as Markdown.

When changing `.claude/skills/<name>/`:

- keep each skill directory self-contained;
- reference `references/`, `scripts/`, and `assets/` using paths relative to the
  skill directory;
- do not reference sibling skills with `../` paths or absolute local paths;
- keep shared helper content small enough to duplicate when two skills need it;
- keep `SKILL.md` under the line-count gate and move detail into
  `references/`;
- avoid platform-specific shell interpolation in cross-runtime skill content
  unless there is a documented fallback;
- test behavior with the relevant runtime smoke when discovery or invocation
  changes.

Mechanical Python tests do not prove LLM-facing skill behavior. If the prose or
workflow changed, include a runtime/manual validation note.

### SKILL.md frontmatter — `loops:` field

Every `SKILL.md` should declare which operator loops it traverses. The
operator-loop taxonomy lives in [docs/operator-loops.md](docs/operator-loops.md):
`sense`, `decide`, `ship`, `reflect`. A skill is a journey across loops; loops
are stations the skill passes through.

```yaml
---
name: mb-bet
description: Open, update, close, list, and narrate Main Branch business bets.
loops: [decide, reflect, ship]
---
```

Rules:

- Skills can span 1+ loops. Most useful skills span 2-3 (for example,
  `/mb-think` is `[sense, decide, ship]` because it researches, decides, and
  codifies the decision into a file).
- Skill names do not have to mirror loop names. `/mb-think` is a brand-name
  multi-loop skill, not a "Think loop" claim.
- Only the four canonical loop slugs are valid (`sense`, `decide`, `ship`,
  `reflect`). Channels (Paid, Organic, Pages, Ops) are not loops and do not
  belong in this field.
- All bundled skills must declare `loops:` and `mb skill validate` enforces the
  field and canonical slugs. Runtime/status grouping does not consume the field
  for product behavior yet; as `mb status` loop grouping, the future dashboard,
  and the bets feed land, they will read it.

## State Model

- Business state stays in git.
- Local operational state stays out of git.
- Secrets stay in the OS keychain, environment, or runtime-specific secret
  stores, never in repo files or frontmatter. Agents use them through
  `mb connect exec`, never by reading or printing the value.
- Dashboard/server/process state must be explicit, local-first, optional, and
  documented before it is added.

## PR Expectations

PR bodies should give reviewers product scope and validation evidence:

- summary of the user loop or product truth changed;
- in-scope and out-of-scope bullets;
- commit list, oldest first;
- release, Linear IDs, `Closes`/`Refs`, and follow-ups;
- success metric;
- validation by ladder level;
- public/private boundary note.

Update `CHANGELOG.md` for user-visible CLI, skill, packaging, compatibility, or
workflow changes. Skip it only for invisible maintenance.

## Release Truth

Do not describe a version as shipped until the release surfaces agree:

- `CHANGELOG.md` has the version section;
- package-visible release candidates have release simulation and transcript
  review evidence before tagging whenever feasible;
- the matching `oe-vX.Y.Z` GitHub Release exists;
- PyPI shows `mainbranch X.Y.Z` when the change is package-visible;
- release notes, README copy, and roadmap language match those facts.

`CHANGELOG.md` may describe unreleased work only under `[Unreleased]`. If a
draft PR, planning doc, or local branch mentions a version that has not been
released, use "planned", "target", or "next" rather than "shipped".

## Post-Release Alignment

After a release ships, run the alignment sweep in
[`docs/post-release-alignment.md`](docs/post-release-alignment.md) before
opening the next parallel batch. That doc owns the post-release sequence,
parallel-work lane rules, AI code review ritual, local agent preferences
policy, and the current product stance checklist.

## Review Focus

When reviewing, lead with findings:

- public operating checklist in `docs/oss-operating-checklist.md`;
- public/private boundary;
- product direction;
- state model;
- runtime claims;
- CLI contract;
- validation evidence;
- issue/release fit;
- stale language;
- test quality;
- truncated files.

Verdicts should be explicit: approve, request changes, or needs discussion.

## Writing Style

Agent-facing docs (this file, `CLAUDE.md`, generated repo guidance, bundled
skill prose) and PR descriptions follow the agent writing style rubric in
[`docs/agent-writing-style.md`](docs/agent-writing-style.md): action-first,
link instead of restate, plain business language, no narration of internal
thought process. User-facing product copy stays warmer and is not bound to
the rubric verbatim.
