# Repo Visibility Rubric

Main Branch keeps the user's business in a git repo. That repo can live
locally, on a personal GitHub account, in a free GitHub organization, or in a
paid GitHub team or organization. None of those choices change whether the
repo's source files and full change history are visible to the public.

This rubric exists so `/mb-setup`, `/mb-site`, and any future tooling ask the
right question once and stop assuming.

The product stance is in
[`decisions/2026-05-11-repo-setup-visibility-and-checks-model.md`](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md).

## The Core Rule

> Public output does not require public source.

A public website on Cloudflare can ship from a private GitHub repo. The
working files, drafts, copy iterations, and revision history can stay private
even when the deployed site is fully public.

A second rule keeps the words honest:

> Local git shape, setup stage, and remote permission role are separate axes.

A repo can be local-only, personal, in a free organization, or in a paid
team. Workflow mode (`solo-on-main`, `branch`, `worktree`, `detached`)
describes how the operator is working in the checkout. Visibility describes
whether strangers can read the source. Permission describes whether the
current operator can push. These do not interlock.

## What "Public Repo" And "Private Repo" Actually Mean

A **public repo** means:

- the source files are visible to anyone with the URL;
- the commit history is visible, including the messages and diffs;
- pull request and issue threads are visible by default;
- a stranger can clone the repo and read everything in it.

A **private repo** means:

- only invited collaborators can read the source or history;
- the deployed site, the public README, public docs, or public release
  artifacts can still be fully public — those are separate publication
  channels.

A private repo is **not** a secret repo. It is a working space with normal
access controls.

## What Private Business Information Covers

Treat the following as private by default unless there is a specific reason
to publish:

- offer experiments that have not shipped;
- client work and client identifiers;
- draft sites, draft copy, and copy iterations;
- strategy, plans, and operating notes;
- screenshots of dashboards, inboxes, or accounts;
- raw provider exports, customer rows, and analytics dumps;
- reports and internal write-ups;
- bets, decisions, research, and pushes while they are in progress;
- anything that would create risk, confusion, embarrassment, competitive
  disadvantage, client trust issues, or operational noise if a stranger
  saw it.

When the operator is unsure, the answer is private.

## Where data lives

1. Code repos (app, site, tools): product code only. Never customer data, customers' customers' data, photos or videos. Tests, fixtures and screenshots use invented values in the real case's shape.
2. The business repo (the Main Branch hub): the team's private memory, team and agents only. Real material belongs there (recordings, P&L, reviews, real examples). No large customer datasets, because hub commits are never deleted.
3. The tracker: media and screen recordings on the issue they explain.
4. Production: customers' customers' data and sensitive categories (health, date of birth, ID photos, signatures, bank details), encrypted.
5. Direction rule for agents: real data flows up into the hub and the tracker, never down into a code repo. Going down, it becomes an invented example of the same shape.

The hub templates carry this rule into new and updated business repos.

## Defaults By Repo Role

| Repo role | Visibility default | Why |
|---|---|---|
| Business repo | **Private** | Holds offers, strategy, decisions, drafts, and operating history. Public business repos are the exception. |
| Site repo | **Private** | Ships a public site via Cloudflare without exposing copy iterations, working drafts, or revision history. |
| Data/source-record repo | **Private** | Raw exports, customer rows, provider caches, and internal memory belong here. Never public. |
| Open-source tool, template, demo, or public doc repo | **Public** | The source itself is the product. |

## The One Question To Ask For Site Repos

`/mb-site` and `/mb-setup` should ask exactly one question before creating a
site repo:

> Should the source files and full change history be public?

Default to **private**. If the operator says yes, they want public source,
proceed with a public repo. Otherwise create the repo private and let
Cloudflare deploy the public site from the private repo. Do not ask the
operator to choose a hosting or deploy platform during the normal flow;
Cloudflare is the adopted rail.

If the operator answers "I want the deployed site to be public," that is
not the same answer. Re-read this question with them. Public deploy is a
Cloudflare concern; public source is a GitHub concern.

## When Public Source Is The Right Call

Public source is appropriate when the source itself is intentionally public:

- open-source tools, libraries, and CLI projects;
- public templates and starters;
- public docs sites whose content lives in the repo;
- demos and reference implementations;
- build-in-public projects where the operator deliberately shares iteration.

In every other case, default to private and revisit if the operator's
strategy changes.

## What Visibility Does Not Decide

Visibility does not decide:

- **Where the repo lives.** Local-only, personal GitHub, free org, paid
  org, or self-hosted Git are separate choices. See the repo home rubric in
  the [setup-and-checks decision](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md).
- **Whether GitHub costs money.** GitHub organizations are free. Paid plans
  exist for advanced team controls, support, or higher private-repo
  collaboration limits, but a private repo on a free personal account or a
  free organization is fine.
- **Whether the deployed site is public.** That is a Cloudflare deploy
  question.
- **Whether the operator has push access.** That is a permission question
  handled by publish planning.

## Pairing Private Source With A Public Site

The normal Main Branch site loop is:

1. Operator creates or selects a private GitHub repo for the site.
2. `/mb-site` writes the site files (or generates a minisite) into that
   private repo.
3. `mb connect cloudflare` and `mb site check` confirm Cloudflare readiness.
4. Cloudflare Pages deploys from the private GitHub repo to the public
   domain.
5. The deployed URL is public; the source repo and its commit history stay
   private.

This is normal. It is the default.

## Related links

- [Setup, visibility, and checks model decision](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md)
- [Checks and review model](checks-and-review-model.md)
- [Dependency choices](dependency-choices.md)
- [Child repo descriptors](child-repo-descriptors.md)
- [Workspace, repo, and sensitive-data boundaries](../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md)
