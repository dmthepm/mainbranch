---
title: Legacy business repo migration dogfood
date: 2026-05-04
linked_issue: https://github.com/dmthepm/mainbranch/issues/222
linked_linear: MAIN-193
release: v0.2.3
status: completed
tags: [migration, dogfood, onboarding, v0-2]
---

# Legacy Business Repo Migration Dogfood

## Summary

The v0.1 to v0.2 path migration worked on one real legacy business repo when
run on a disposable copy: legacy `reference/core` and `reference/offers` content
moved to `core/`, compatibility links were created, `.mb/schema_version` reached
`0.2`, and rerunning `mb migrate --check` reported no pending changes.

The path is recoverable, but it is not yet noob-safe as a single turnkey
migration. The main blockers are privacy-unsafe diff output, confusing `mb
migrate status` option behavior, stale Claude Code engine paths after skill
repair, noisy legacy frontmatter validation, and bundled skill docs that still
contain legacy setup language.

Follow-up issues:

- [#242](https://github.com/dmthepm/mainbranch/issues/242) - Make `mb
  migrate check` privacy-safe for legacy repo diffs.
- [#243](https://github.com/dmthepm/mainbranch/issues/243) - Honor or
  reject root `--repo` for `mb migrate status`.
- [#244](https://github.com/dmthepm/mainbranch/issues/244) - Clean stale
  engine paths when repairing Claude Code skill wiring.
- [#245](https://github.com/dmthepm/mainbranch/issues/245) - Skip OS
  metadata files during path migration.
- [#246](https://github.com/dmthepm/mainbranch/issues/246) - Add repair path
  for legacy frontmatter validation failures after migration.
- [#247](https://github.com/dmthepm/mainbranch/issues/247) - Remove legacy
  setup copy from bundled skills.

## Scope Tested

Tested one real legacy local business repo using a disposable copy under OS
temp. The source repo was not mutated.

Baseline shape:

- installed CLI was `mb 0.2.3` in pipx mode;
- repo had old `reference/core` and `reference/offers` layout;
- repo had no `.mb/schema_version`;
- repo had `.claude/settings.local.json` pointing at an old clone-mode engine;
- repo had project-local Claude Code skill links from the old setup flow;
- repo had a non-main branch and preexisting untracked local files.

A quick local scan also found more legacy candidates with `reference/core`,
legacy hidden engine markers, or old `.claude/settings.local.json` markers.
Those were not migrated in this issue.

## Command Evidence

Baseline read-only checks:

- `mb doctor --json` exited non-zero. It detected Claude Code, GitHub auth,
  network, current Main Branch version, and bundled skills. It warned on legacy
  layout and schema `0.1`, reported skill wiring as broken, and surfaced
  onboarding progress as `2/4` required steps complete.
- `mb migrate status --repo <repo> --json` reported current version `0.1`, latest
  `0.2`, and pending migration `001_v01_to_v02_path_config`.
- `mb migrate --repo <repo> --check` planned the expected path migration, but
  printed full file diffs with private business content. `--json` also embedded
  the full diff in `plan.diff`.

Migration apply on the disposable copy:

- `mb migrate --repo <copy> --apply --json` succeeded.
- It moved legacy core files into `core/`.
- It moved legacy offers into `core/offers/`.
- It created `reference/core` and `reference/offers` compatibility symlinks.
- It added current working folders and `.mb/schema_version`.
- It wrote a migration decision note in the business repo.
- It created a timestamped backup under `.mb/backups/`.
- It also moved an OS metadata file into `core/offers/`, which should be
  ignored in future migration behavior.

Immediate post-migration checks:

- `mb migrate status --repo <copy> --json` reported current version `0.2` with
  no pending migrations.
- `mb migrate --repo <copy> --check --json` reported `has_changes: false`.
- `mb doctor --json` still exited non-zero because skill wiring was stale.
  Layout and schema checks were green.
- `mb status --json` recognized the repo and install, but readiness was degraded
  by stale skill wiring and a dirty worktree.
- `mb start --json` returned the correct Claude Code command, but `ok: false`
  because the `/start` skill was not wired to the active engine.
- `mb validate --cross-refs --json` failed with legacy schema debt: hundreds of
  missing required frontmatter fields, legacy status values, missing
  frontmatter, and one YAML parse error. This appears to be legacy content
  schema debt rather than a failed path migration, but the current migration
  flow does not explain that distinction well.

Repair check:

- `mb skill link --repo <copy> --json` succeeded.
- After repair, `mb doctor --json` returned `ok: true` with only onboarding
  progress as a warning.
- After repair, `mb status --json` reported skill wiring healthy and readiness
  score `100`.
- After repair, `mb start --json` returned `ok: true`; the only remaining
  warning was the expected dirty migration worktree.
- The repaired settings kept the active packaged engine path and also retained
  the old clone-mode engine path. That is workable, but confusing and likely to
  create stale runtime access in old-user migrations.

## Onboarding / Session Resume

The new onboarding progress surface helped. Even with no `.mb/onboarding.json`
state file present, `mb doctor`, `mb status`, and `mb onboard status --json`
inferred enough from repo shape to resume:

- before skill repair, runtime handoff was pending and the next action was `mb
  skill link --repo .`, then `mb start --json`;
- after skill repair, runtime handoff became complete;
- the remaining required step was business profile collection;
- the next recommended agent action was concrete: ask only for business type,
  team size, current success stage, and desired outcome.

This satisfies the basic multi-session resume requirement for a migrated repo:
an agent does not need the prior transcript to see the next setup step. The
remaining gap is that legacy frontmatter validation failures and stale engine
paths still need clearer repair ownership.

## Safety Assessment

Safe enough for a technical operator on a disposable copy or clean branch:

- the path migration applied and became idempotent;
- backups were created;
- `mb skill link --repo .` repaired runtime handoff;
- `mb start --json` was ready after repair.

Not safe enough for a broad noob-user migration announcement yet:

- `mb migrate --check` can leak full private business files into pasted logs;
- one plausible `mb migrate status` command form inspects the wrong repo;
- skill repair can leave both old clone and current packaged engine paths;
- validation remains very noisy on legacy files without a separate repair story;
- bundled skills still contain stale legacy setup language.

## Public / Private Boundary

No private repo names, local absolute paths, raw business file contents,
customer/member data, credentials, or account details are included in this
report. Raw command outputs were inspected only locally, and all mutation tests
ran on a disposable copy under OS temp.
