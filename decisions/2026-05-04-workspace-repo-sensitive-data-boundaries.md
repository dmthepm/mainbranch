---
type: decision
date: 2026-05-04
status: accepted
topic: Workspace, repo, and sensitive-data boundaries
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/274
  - https://github.com/dmthepm/mainbranch/issues/275
  - https://github.com/dmthepm/mainbranch/issues/120
  - https://github.com/dmthepm/mainbranch/issues/128
participants: [Devon, Codex]
tags: [v0-3, state-model, workspace, dashboard, privacy, markdown]
---

# Workspace, Repo, and Sensitive-Data Boundaries

## Decision

Main Branch should model business state through three explicit boundaries:

1. A **business repo** is the default durable brain for one coherent business
   context.
2. A **workspace** is an operator-chosen grouping of one or more business repos
   and local-only operational state.
3. A **private operator dashboard** is a local or self-hosted control surface
   over repos, GitHub, indexes, sidecars, credentials, and provider data. It is
   not canonical memory.

The default remains simple: one business repo per business, with canonical
truth in git. Main Branch should add workspace and dashboard concepts only to
make multi-repo, team, finance, legal, and provider boundaries explicit. It
must not make editable repo files the authority for access control, admin
rights, spending authority, legal authority, or provider permissions.

## Boundary Map

| Surface | Owns | Does not own |
|---|---|---|
| Business repo | Reference files, research, decisions, campaigns, bets, team-visible logs, durable summaries, proposals | Secrets, raw customer/member exports, broad ledgers, provider tokens, admin authority |
| Workspace | Local grouping of repos, recent repo list, dashboard instance metadata, local indexes, cache locations, operator preferences | Canonical business truth, team-visible policy, provider permissions |
| Repo dashboard | Read/write view for one repo through `mb`, GitHub, and files | Cross-repo authority, private finance/legal access, hosted auth |
| Workspace dashboard | Aggregated view across selected repos and GitHub contexts | Source of truth, replacement for git history, override for repo permissions |
| Private operator dashboard | Local or self-hosted view that may show private metrics, P&L, legal checklists, and personal notes | Public team memory, admin authority, account mutation without explicit operator action |
| Provider account | Spending, publishing, emailing, billing, customer data, and platform permissions | Main Branch repo permissions or frontmatter claims |

Dashboards are views and control surfaces. They may write proposed changes back
to repos, create GitHub issues, or call `mb` commands, but the durable record is
still the repo, GitHub, provider account, or git history that actually changed.

## Repo Model

Use one business repo when:

- the offer, audience, voice, proof, team, and access boundary are shared;
- multiple offers operate under the same brand or company brain;
- the same teammates should generally see the same operating memory;
- finance/legal details can stay summarized or excluded.

Use multiple business repos when:

- businesses have different legal entities, teams, brands, audiences, or
  provider accounts;
- one repo would force teammates to see finance, legal, customer, member, or
  partner data they should not see;
- a graduated offer becomes large enough to need its own site, tasks,
  campaigns, fulfillment, or provider accounts;
- private personal exploration should not become team-visible memory.

Use a hub repo when a team needs shared cross-repo coordination:

- company-level decisions;
- team daily logs;
- shared operating principles;
- cross-offer priorities;
- links to product or offer repos.

Use graduated offer or product repos when an offer becomes its own operating
surface. Keep the parent company repo as the hub and link to the child repo
from decisions, roadmap notes, and team daily logs. Do not solve this by adding
more folder aliases inside one repo.

Path configuration is narrower than workspace modeling. A future path-config
feature may let one repo rename canonical folders, but it must not decide which
repos exist, which teammates can see them, or where sensitive data belongs.

## Team Daily Logs

The phrase is **team daily log**, not chat. A team daily log is a durable work
record, not an opaque message database.

Default placement:

- single-repo team: `log/YYYY-MM-DD.md` in the business repo;
- multi-repo team: `log/YYYY-MM-DD.md` in the hub repo, with repo-relative or
  GitHub links to offer/product repos;
- repo-specific daily details: `log/YYYY-MM-DD.md` in the repo where the work
  happened, linked from the hub log when useful;
- private operator notes: a private repo or local operator state, not the
  team-visible business repo.

Team daily logs may mention finance, legal, provider, or customer matters only
at the level appropriate for the repo audience. A log can say "May close
blocked on bank reconciliation" without committing transaction rows, statements,
customer names, or legal advice.

## Finance, Legal, and `mb books`

`mb books` must not quietly turn a shared business repo into a finance database.
Bookkeeping is a Ship loop, but its data boundary is stricter than normal
campaign or decision work.

Safe for a team-visible business repo:

- high-level finance decisions;
- sanitized P&L summaries approved for that team;
- chart-of-accounts templates;
- bookkeeping workflow docs;
- non-secret provider identifiers needed for repair;
- links to private finance repos or provider dashboards when the audience is
  authorized to know they exist.

Not safe by default for a team-visible business repo:

- raw ledger rows;
- bank, credit-card, payroll, tax, legal, invoice, or statement exports;
- account numbers;
- customer/member payment records;
- legal advice, contracts, disputes, or entity documents;
- anything that would be harmful if every repo collaborator, fork, checkout,
  backup, or future agent could read it.

For solo operators, real ledger files may live in a private business repo only
after an explicit operator decision. For teams, real finance/legal records
should usually live in a private finance/legal repo, a provider account, or
local encrypted storage with narrow access. `mb books` should read those sources
through explicit paths, sidecar contracts, or provider exports, then write only
approved summaries back to team-visible repos.

Future dashboard P&L views must inherit this boundary. A dashboard may show P&L
only when the current local operator or hosting environment already has access
to the private finance source. A repo file saying `role: admin` or
`can_view_finance: true` is not enough.

## Editable Files Are Not Admin Authority

Business repos are editable by collaborators and agents. That is a feature for
business memory and proposals, but it makes repo files unsuitable as the final
authority for privileged actions.

Main Branch must not trust tracked markdown, frontmatter, `.mb/` files, or
workspace config as the sole proof that someone can:

- spend money;
- publish or deploy;
- email customers;
- access finance or legal records;
- change provider credentials;
- change teammate roles;
- approve invoices, payroll, taxes, or contracts;
- override safety gates.

Authority must come from the system that enforces it:

- GitHub permissions for repo read/write/admin rights;
- provider permissions for ads, billing, email, banking, analytics, and deploys;
- local OS user/session and secret-store access for private operator state;
- explicit human approval at the command or workflow boundary;
- future hosted access control only after a separate accepted decision.

Repo files can declare intent, desired roles, policy, or proposals. They can
help a dashboard render controls. They cannot bypass the actual permission
check before a privileged action runs.

## GitHub, Self-Hosted Git, and Backups

GitHub private repos are the default durable home because they give Main
Branch portable git history, issues, pull requests, permissions, and a familiar
team layer. That default is not a promise that all data belongs on GitHub.

Use self-hosted git, Forgejo, encrypted local storage, or provider-native
systems when legal, finance, privacy, jurisdiction, customer, or company policy
requires a narrower boundary. Main Branch should preserve portability by using
plain git, markdown, JSON contracts, and explicit local state paths. GitHub is a
strong default collaboration layer, not the only possible place to keep private
records.

## Markdown and Link Compatibility

Business repos should stay pleasant in GitHub, local editors, and Obsidian.
The durable conventions live in
[docs/markdown-link-conventions.md](../docs/markdown-link-conventions.md).

The short version:

- frontmatter links use repo-relative paths with `.md` extensions;
- body links prefer standard Markdown links when GitHub clickability matters;
- Obsidian wikilinks are allowed for graph navigation when targets resolve
  uniquely;
- filenames should be lowercase, hyphenated, and stable;
- entity tags use the existing graph style such as `#company/example-co`;
- `mb validate --cross-refs` should warn on broken frontmatter links and broken
  or ambiguous wikilinks.

## Implementation Guidance

Future dashboard work should:

- start as local-first and optional;
- read through `mb status --json`, `mb graph --json`, `mb connect status
  --json`, GitHub, and repo files;
- keep local indexes and caches rebuildable;
- store credentials outside tracked repos;
- show which repo, workspace, provider, and operator boundary each fact came
  from;
- refuse privileged actions unless the enforcing system grants permission.

Future `mb books` work should:

- accept that bookkeeping can read private finance sources without committing
  them to a team repo;
- keep real ledgers and statement exports out of public examples and fixtures;
- warn before writing finance/legal data into a repo with collaborators;
- produce approved summaries separately from raw ledgers;
- support provider inputs such as bank exports without making any one bank a
  hard dependency;
- coordinate with sidecar/provider contracts for private account data.

Future path-config work should:

- stay limited to folder-name/path overrides inside one repo;
- avoid implying that a renamed folder changes access boundaries;
- leave workspace grouping, multi-repo strategy, and sensitive-data placement
  to this decision.

## Validation Contract

For this decision slice:

- Level 0 docs/decision review is required for public/private boundary,
  frontmatter, and links.
- `scripts/check.sh` must pass before pushing.
- Focused `mb validate` tests are required only for the wikilink validation
  change.
- Package/install, fixture repo, and runtime smoke are not required because
  this does not change packaging, repo scaffolding, first-run behavior, or
  runtime discovery.

## Consequences

- Future dashboard, bookkeeping, legal, team-log, and multi-repo work has one
  public boundary decision to cite.
- Main Branch can add dashboards without making them canonical memory.
- `mb books` can become important without turning shared repos into finance
  databases.
- Path-config stays a local layout feature, not a workspace or permissions
  model.
- Markdown remains useful in GitHub and Obsidian without adding an Obsidian
  dependency.

## Review Trigger

Revisit this decision before Main Branch ships any of these:

- hosted dashboard accounts;
- team roles inside a Main Branch service;
- `mb books` writing ledger data;
- dashboard P&L or legal views;
- background sync across multiple repos;
- a workspace config file that claims to grant permissions;
- provider mutations initiated from dashboard controls.
