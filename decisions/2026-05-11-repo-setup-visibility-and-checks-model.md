---
type: decision
date: 2026-05-11
status: accepted
topic: Repo setup, visibility, and checks model
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/477
linked_decisions:
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-08-business-repo-topology-map.md
  - decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md
linked_docs:
  - docs/dependency-choices.md
  - docs/repo-visibility-rubric.md
  - docs/checks-and-review-model.md
tags: [setup, visibility, checks, github, cloudflare, topology]
---

# Repo Setup, Visibility, And Checks Model

## Decision

Main Branch recommends one clean default path for hosting and deploying a
business and its site, and writes that path into setup, site, and dependency
docs.

- **GitHub** is the repo, history, collaboration, pull-request, and checks
  rail.
- **Cloudflare** is the site, DNS, and deploy rail.
- **`mb`** owns setup guidance, checks, repair, status facts, and the
  plain-language translation of git and provider state into business language.
- **Obsidian and dashboards** display state; they do not own enforcement.

Two rules follow from this:

> **Public output does not require public source.**

A Cloudflare-deployed public site can ship from a private GitHub repo. The
default for business and site repos is private.

> **Local git shape, setup stage, and remote permission role are separate axes.**

`git.workflow_mode` from `mb status` describes the local checkout of an
existing repo. It does not describe whether the operator has push access,
whether the GitHub organization is paid, or whether `.git`/`origin` has been
initialized yet. Setup guidance and publish guidance must keep these axes
separate.

GitHub Pages is **not** part of normal Main Branch setup or site guidance.
Self-hosted Git, other Git hosts, and other deploy platforms may be possible,
but Main Branch does not maintain fallback instructions for them unless a
later decision adopts them.

This decision finishes the setup-and-checks half of the boundary that
`decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md`
deferred under "Out of Scope (Belongs to Other Decisions)".

## Why

Setup, site, dependency, topology, provider, migration, and GitOps work each
described a piece of the same product stance in different files. New users
saw GitHub Pages framed as a fallback in one place, public site repos
defaulted to `gh repo create --public` in another, and GitHub orgs were
sometimes implied to cost money.

This decision pins one stance so `/mb-setup`, `/mb-site`, docs, and future CLI
planning agree:

- one repo rail (GitHub) for source/history/collaboration/PRs/checks;
- one site rail (Cloudflare) for site/DNS/deploy;
- private-by-default repos with an explicit visibility prompt for site repos;
- checks layered locally first, with GitHub Actions and branch protection as
  optional reinforcement;
- topology fields preserved as separate concerns.

## Repo Visibility Rubric

The full plain-language rubric lives in
[`docs/repo-visibility-rubric.md`](../docs/repo-visibility-rubric.md). The
short form is:

- **Business and data repos are private by default.** They hold offer
  experiments, client work, drafts, strategy, screenshots, data, reports, and
  internal notes. A public business repo is the exception, not the default.
- **Site repos ask one question:** "Should the source files and full change
  history be public?" If unsure, the answer is private.
  - **Private:** the deployed site is still public on Cloudflare; the working
    files, drafts, copy iterations, and revision history stay private.
  - **Public:** the source is intentionally public — open-source tools,
    templates, demos, public docs, or build-in-public artifacts.
- **Data/source-record repos are private.** Raw exports, customer rows,
  provider caches, and internal memory belong in private repos regardless of
  whether the consuming site is public.
- **What "private business information" covers:** anything that would create
  risk, confusion, embarrassment, competitive disadvantage, client trust
  issues, or operational noise if a stranger saw it.

`/mb-setup` and `/mb-site` should ask the visibility question once, default
to private, and not ask the operator to choose a hosting or deploy platform
during the normal flow.

## Repo Home Rubric

Where the repo lives is a separate axis from visibility. Main Branch supports
the following defaults:

| Home | When to use | Notes |
|---|---|---|
| Local-only (no remote) | The operator is exploring or has no GitHub account yet. | Acceptable as a starting state. `mb status` should still work; publish-class guidance must not assume a remote. |
| Personal GitHub repo | A solo operator with a personal GitHub account. | Default when the operator already uses GitHub for code. |
| Free GitHub organization | A solo operator or small team that wants a brand-level namespace. | GitHub organizations are free; paid plans exist for advanced team controls, support, or higher private-repo collaboration limits, but **org does not imply paid**. |
| Paid GitHub org / Team | Advanced team controls (required reviewers, fine-grained access, audit log, etc.). | Optional. Main Branch does not require it. |
| Self-hosted Git (Forgejo, Gitea, etc.) | Operator chooses to run their own forge. | Possible but not maintained as a Main Branch rail today. |

Setup guidance should default to "personal GitHub or free GitHub organization"
and must not imply a paywall.

## Site And Hosting Rails

Cloudflare is the adopted deploy/DNS/site rail for Main Branch:

- a Cloudflare Pages project deploys from the linked GitHub repo;
- DNS, custom-domain attach, and site/CDN behavior live with Cloudflare;
- `mb connect cloudflare`, `mb site check`, and `/mb-site` carry the readiness
  and repair contract for this rail.

GitHub is the source/history/PR/checks rail. It is not the site host in normal
Main Branch flows.

GitHub Pages is not presented as a fallback. The product reasons:

- normal Main Branch users do not need a second site rail;
- GitHub Pages couples visibility and hosting in ways the visibility rubric
  explicitly separates;
- maintaining a fallback set of instructions would dilute the one clean path.

If an operator deliberately chooses GitHub Pages, that is their call. Main
Branch should not document it as a recommended path or as a fallback when
Cloudflare is unavailable.

## Checks And Review Model

The full plain-language model lives in
[`docs/checks-and-review-model.md`](../docs/checks-and-review-model.md). The
short form is:

- **`mb` defines and runs business-repo checks locally.** The same rules that
  produce `mb doctor`, `mb validate`, and `mb status` findings should be the
  rules that any later automation runs.
- **Agents use `mb` output to explain, fix, or ask for judgment.** They route
  on the `audience` field (`mechanical`, `operator_decision`, `informational`)
  from
  [`decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md`](2026-05-11-operator-facing-gitops-and-migration-planning.md).
- **GitHub Actions can run the same checks** after commits or on pull requests
  when a repo uses GitHub. The action shells `mb` rather than re-implementing
  rules. Actions are optional for solo users and recommended for team/org
  repos.
- **GitHub branch protection is optional** for solo users and recommended for
  team/org repos. Branch protection is enforcement, not a check engine.
- **Dashboards, Obsidian, and any future viewer display check state.** They do
  not own the rules.

Checks group in plain language by audience and depth:

- **mechanical** — safe shape, link, and schema checks. Safe to auto-repair.
- **operator decision** — needs human or business judgment.
- **informational** — useful context, not a blocker.
- **provider readiness** — depends on external accounts and credentials.

These groupings reuse the `audience` taxonomy from the operator-facing
GitOps decision; this decision does not invent new safety semantics.

## Topology And Permissions

Topology records (`.mainbranch/repo.json` child descriptors today, and a
planned `mb topology` surface plus future publish/setup planning) should
keep the following fields separable:

- **business repo** versus **site repo** versus **data/source-record repo**
  versus **child repo** role;
- **owner** — display name plus GitHub owner/repo identity;
- **visibility** — `private` or `public`, plus a freeform `safe_purpose`
  string;
- **deploy rail** — `cloudflare-pages`, `cloudflare-static`, or `none`;
- **collaboration mode** — `solo`, `personal`, `org`, or `team`.

Today the descriptor in
[`docs/child-repo-descriptors.md`](../docs/child-repo-descriptors.md) covers
parent/role/linked fields. Adding visibility and deploy-rail facts is a
follow-up topology slice; this decision names the fields so the future slice
does not have to redesign them.

`mb publish --plan` (deferred in the GitOps decision) will later read
`actor_role` and `publish_path` as separate axes from `workflow_mode`. Setup
and topology should preserve the distinction so a contributor without push
access does not get the same publish plan as the repo owner.

## Out Of Scope (Belongs To Other Decisions And Issues)

- Implementing scheduled data sync (MAIN-315).
- Implementing provider sync.
- Implementing a hosted dashboard.
- Documenting GitHub Pages as a fallback.
- Broad stale-doc cleanup (MAIN-318).
- Adding new CLI commands. This decision is docs and skill prose only.

## Consequences

- `/mb-setup` asks one visibility question for site repos and defaults to
  private. It does not ask the operator to choose a hosting or deploy
  platform during the normal flow.
- `/mb-site` defaults `gh repo create` to `--private` and surfaces the
  visibility prompt before creating a public site repo.
- `docs/dependency-choices.md` keeps Cloudflare as adopted and does not list
  GitHub Pages as a fallback. The "public output does not require public
  source" rule is repeated where setup advice appears.
- `mb-wiki/references/hosting-recommendation.md` reframes GitHub Pages as a
  niche option rather than a fallback host.
- Topology and publish work can rely on the distinct axes named here.
- Future checks automation (GitHub Actions, branch protection, dashboard
  reads) cites this decision rather than redesigning the layering.

## Review Trigger

Revisit if:

- a third deploy rail is adopted (for example, Vercel becomes a tested rail
  via a separate decision);
- GitHub orgs change their free/paid boundaries in a way that affects setup
  defaults;
- a new visibility class is required (for example, "internal" for a future
  team plan);
- dashboards earn enforcement responsibility that this decision currently
  declines to give them.

## Related links

- [Repo visibility rubric](../docs/repo-visibility-rubric.md)
- [Checks and review model](../docs/checks-and-review-model.md)
- [Operator-facing GitOps and migration planning](2026-05-11-operator-facing-gitops-and-migration-planning.md)
- [Business repo topology map](2026-05-08-business-repo-topology-map.md)
- [Workspace, repo, and sensitive-data boundaries](2026-05-04-workspace-repo-sensitive-data-boundaries.md)
- [GitHub-native business OS](2026-05-02-github-native-business-os.md)
