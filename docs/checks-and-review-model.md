# Checks And Review Model

Main Branch keeps the daily loop honest by running checks against a business
repo. This doc explains how local `mb` checks, agent review, GitHub Actions,
GitHub branch protection, and dashboards fit together so that one set of rules
runs in every place.

The product stance is in
[`decisions/2026-05-11-repo-setup-visibility-and-checks-model.md`](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md).
The classification taxonomy this doc uses is locked in
[`decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md`](../decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md).

## One Rule Engine, Many Surfaces

`mb` is the rule engine. Every other surface reads its output:

- **`mb` defines and runs business-repo checks locally.** `mb doctor`,
  `mb validate`, and `mb status` produce structured findings with an
  `audience` and `operator_summary`.
- **Agents use `mb` output to explain, fix, or ask for judgment.** Skills
  route on `audience` and render `operator_summary`. They do not re-derive
  rules from filenames or paths.
- **GitHub Actions can run the same checks** after commits and on pull
  requests. The action shells `mb` rather than re-implementing rules.
- **GitHub branch protection is enforcement, not a check engine.** It can
  require that the action passes; it does not decide what the rules say.
- **Dashboards, Obsidian, and any future viewer display state.** They do
  not own rules and they do not own enforcement.

If a check disagrees between surfaces, the local `mb` answer is the contract.
Other surfaces should be updated to read `mb`, not patched to encode a
different rule.

## Audience Groups

Every finding carries an `audience` field. Skills and agents route on this
field:

- **`mechanical`** — Safe shape, link, and schema checks with a deterministic
  correct fix. Main Branch can repair these without judgment.
- **`operator_decision`** — Needs human or business judgment. Content
  changes, destructive moves, frontmatter that depends on operator intent.
- **`informational`** — Useful context, not a blocker.

A fourth category is product-shaped rather than safety-shaped:

- **provider readiness** — Depends on external accounts and credentials.
  Surfaced through `mb connect doctor` and the connection-status outputs.
  Provider readiness is informational from `mb`'s point of view (it cannot
  fix a provider account); it becomes a blocker only when the operator
  attempts a workflow that requires the provider.

`mb` does not invent a fifth category. New finding types pick one of the four.

## Where Each Surface Runs

### Local `mb`

The default surface. Runs from inside a business repo without any external
account:

```bash
mb doctor
mb validate
mb status
mb status --json --peek
```

These commands work offline. They cover repo shape, schema, link mirrors,
migration drift, status facts, and ranked next actions.

`mb doctor repair --plan` plans `mechanical` repairs without applying them.
`mb doctor repair --apply` applies them once the plan has been reviewed.
`operator_decision` items are never auto-applied.

### Agent Review

Skills run inside Claude Code (or another runtime) and read `mb` output.
They:

- present `operator_summary` lines in business language;
- group findings by `audience` so the operator sees `mechanical` items as
  "safe to apply", `operator_decision` items as "needs a call", and
  `informational` items as context;
- show `mb doctor repair --plan` for `mechanical` items, then offer
  `mb doctor repair --apply`;
- never silently mutate the repo on `operator_decision` items.

Agents are the user-facing translator. They are not a second rule engine.

### GitHub Actions

When the business repo is hosted on GitHub, the same checks can run on
commits and pull requests:

- the action checks out the repo;
- installs `mb` (from PyPI or a pinned commit);
- runs `mb validate --json` and `mb status --json`;
- fails the check if any finding has a severity the operator chose to gate
  on.

The action is optional for solo users and recommended for team and
organization repos. The action surface is documented separately when a
shipped workflow is added; this doc only names the contract.

### GitHub Branch Protection

Branch protection enforces what merges. It is optional for solo users and
recommended for team and organization repos. Typical settings:

- require the `mb` action to pass before merge;
- require pull request review for team repos;
- restrict who can push to the default branch on team repos.

Solo operators on `solo-on-main` workflows usually skip branch protection.
That is fine. Branch protection is enforcement; the engine is still `mb`.

### Dashboards, Obsidian, And Future Viewers

These display state. They read `mb status`, validation reports, and graph
data. They:

- show open findings grouped by audience;
- link to the underlying files;
- surface stale data;
- never run their own rules or claim authority to repair.

A future hosted dashboard inherits the same contract: read `mb`, do not own
the rules.

## Check Groupings In Plain Language

When presenting findings to the operator, group by audience first and depth
second:

- **mechanical** — "Safe to apply. Want me to fix it?"
- **operator decision** — "Needs a call. Here is what the file currently
  says and what `mb` expects."
- **informational** — "Heads up. No action required."
- **provider readiness** — "External account state. Here is the readiness
  state and the next command."

Skills should not invent severity words like "warning" or "error" when an
audience word fits. Reserve severity terminology for the underlying CLI
output where it already exists.

## How New Checks Land

When a new check is added:

1. The rule lives in `mb` and ships in a `mb` release.
2. The finding carries `audience` and `operator_summary` from day one.
3. Tests cover the finding shape (existence, audience, summary).
4. Skills that need to route on the check read the new finding type; they
   do not hardcode strings from the prose summary.
5. The GitHub Action, when present, picks up the new finding automatically
   because it shells `mb`.
6. Dashboards pick up the new finding automatically because they read `mb`.

A check is not "shipped" until `mb` knows about it. A check that only exists
in a skill or in an action is a workaround, not a check.

## What This Doc Does Not Cover

- **The contract for `mb publish --plan`'s `actor_role` and `publish_path`**
  is defined in
  [`decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md`](../decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md).
- **The exact GitHub Action workflow file** lives with the shipped workflow,
  not here. This doc names the contract; the workflow ships with its own
  validation evidence.
- **Hosted dashboard state model** is out of scope until a dashboard surface
  is accepted. See
  [`decisions/2026-05-15-repo-owned-operating-memory.md`](../decisions/2026-05-15-repo-owned-operating-memory.md).

## Related links

- [Setup, visibility, and checks model decision](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md)
- [Operator-facing GitOps and migration planning](../decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md)
- [Repo visibility rubric](repo-visibility-rubric.md)
- [Dependency choices](dependency-choices.md)
