# Claude Code Instructions

Read `AGENTS.md` first. It is the shared operating contract for all agents
working in this repository.

This file only adds Claude Code-specific guidance for the Main Branch engine
repo.

## Repository Role

This is the public `dmthepm/mainbranch` engine repository. It contains the
`mb` CLI, bundled agent-runtime skills, docs, fixtures, tests, and release
metadata.

It is not a user's business repo. Business data belongs in the repo created by
`mb onboard` or `mb init`, not in this engine checkout.

## Product Loop To Preserve

Main Branch's current daily loop is: open a business repo, start Claude Code,
run `/mb-start` or follow generated repo instructions, ground the agent in
`mb` facts, route business input into primitives such as bets, research,
decisions, pushes, playbooks, outcomes, and checkpoints, then close with
`/mb-end` or checkpoint guidance so the durable memory lands in git.

`mb` is the deterministic control and enforcement plane. Claude Code skills are
the judgment-heavy execution layer. Keep user-facing guidance in business
language first, and treat issues, branches, pull requests, commits, graph links,
and provider state as the technical memory layer underneath the business loop.

## How to Work Here

- Follow `AGENTS.md` for product shape, scope, public/private boundaries, branch
  discipline, validation, and PR expectations.
- Use `README.md`, `docs/`, `decisions/`, tests, and GitHub issues as durable
  context.
- Keep local scratch files out of durable product docs and commits.
- Run `scripts/check.sh` from the repo root before pushing code or docs that
  could affect packaged behavior.
- If you change first-run, skill discovery, `mb init`, `mb onboard`,
  `mb start`, `mb status`, `mb update`, or bundled skills, add the relevant
  fixture/package/runtime smoke evidence described in `AGENTS.md`.

## Engine vs Business Repo

When a user is operating Main Branch, they should be in their business repo:

```bash
cd path/to/my-business
mb status
mb start --launch
```

When contributing to the engine, work in this repository and keep changes
scoped to the assigned issue or PR.

## Skills

Bundled Claude Code skills live in `.claude/skills/`. If you edit a skill:

- read the skill's `SKILL.md` before changing it;
- keep `SKILL.md` under the repo's line-count gate;
- update tests, fixtures, or docs when behavior changes;
- do not write outputs into this engine repo unless the test/fixture explicitly
  requires it;
- avoid private member data, private launch strategy, or machine-specific paths
  in examples.

Claude Code is the first-class slash-skill runtime today. Codex CLI is
first-class for the proven daily loop through generated `AGENTS.md`, global Main
Branch skills installed once per user, deterministic `mb` facts, and workflow
inventory. That is global-skill support, not Codex slash-command support, full
Claude skill parity, or full production workflow parity. Business repos should
not carry repo-local Codex plugin or skill copies unless a future issue proves
that fallback is required. Other runtimes are roadmap targets until an adapter
and smoke evidence exist, so do not overclaim compatibility in docs.
