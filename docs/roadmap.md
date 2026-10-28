# Roadmap

This roadmap is direction, not a promise. GitHub issues and release notes are
the detailed execution record. This file explains the product shape so users,
contributors, and agents understand where Main Branch is going. The current
direction anchor is
[Repo-owned operating memory](../decisions/2026-05-15-repo-owned-operating-memory.md).

Main Branch is not only a marketing-growth context folder. Growth is the first
high-value wedge because ads, pages, content, and launches expose the memory
problem quickly. The broader product is durable operating memory for
AI-assisted businesses: meetings, fulfillment, bookkeeping summaries, provider
safe account refs, decisions, bets, pushes, logs, and lessons in repos the team
owns.

## Shipped Foundation

Main Branch already ships:

- public PyPI package and MIT-licensed engine;
- `mb onboard`, `mb init`, `mb status`, `mb start`, `mb update`, `mb doctor`,
  `mb graph`, `mb validate`, `mb migrate`, `mb connect` (including `mb connect
  exec`, which runs a command with a credential the agent does not retrieve),
  `mb fleet` (read-only status of every site across your hubs), `mb feedback`
  (local friction log with a weekly rollup), and skill management commands;
- `mb doctor repair --plan` / `--apply` and migration drift detection across
  `mb validate` and `mb doctor` for stale generated guidance, legacy
  active-write folders, stale Claude settings, wrong push/playbook paths, and
  legacy bet campaign links;
- Claude Code skill wiring with `mb-` prefixed bundled skills;
- Codex global `mb-*` skills for the supported daily loop, rendered from shared
  workflow sources where supported and grounded in deterministic `mb` facts;
- beginner setup, migration, repair, and update paths;
- local-first provider metadata and secret-safe connection checks;
- graph, status, and topology primitives (including repo-topology facts in
  `mb status --json`, `mb graph --json`, and `mb doctor repair --plan --json`)
  for future dashboard and agent workflows;
- MoneyPath readiness and proof-quality facts in `mb status --json --peek`, so
  daily status can show whether customer progress, offer, proof, CTA, channel,
  push, playbook, page, and outcome feedback are legible and connected without
  turning CLI output into strategic judgment;
- the first business-file contract system, with a public contract map and an
  enforced offer contract that routes missing offer shape to `mb-think`;
- content strategy health facts for simple and layered strategy files, channel
  and account layers, freshness, indexing, and disconnected marketing context;
- compact books readiness in `mb status --json --peek` and `mb start --json`,
  plus `mb books check`, `mb books status`, and `mb books doctor --plan` for
  privacy-bounded setup checks without reading ledgers or exposing private
  vault paths;
- the first hledger-backed sample monthly books report through
  `mb books report monthly --sample --month YYYY-MM`, using packaged fake data
  so operators can see the report shape without exposing real books;
- Meta Ads read-only readiness through `mb connect meta` /
  `mb connect test meta --json`, plus compact `mb ads meta summary --json`
  account context after the operator has configured the official Meta Ads CLI
  path;
- privacy-safe GitHub issue drafting and submission (`mb issue draft`,
  `mb issue open`) for user friction;
- push, reusable playbook, and per-push run-record vocabulary for coordinated
  business work;
- `bets/` and `/mb-bet` as the first Reflect primitive;
- `mb checkpoint` as the first hidden GitOps save layer for long agent runs;
- canonical shared workflow sources for daily start/status, setup,
  maintenance/repair, think, closeout/checkpoint, bet, ads, organic, and site
  routes;
- checked Claude and Codex shell snapshots over those shared sources, with
  read-only Codex boundaries where output or provider workflows are not yet
  full runtime support;
- the first reusable Google Ads Search launch playbook source packaged with the
  engine, with planning support kept separate from provider mutation, uploads,
  publishing, spend, account changes, and customer contact;
- materialized release-simulation fixtures and the package-visible release
  evidence ladder (PR smoke, pre-release candidate, release acceptance);
- release and local-state boundary hardening for package publishing and
  provider metadata paths;
- public contribution, support, security, compatibility, and agent guidance;
- accepted workspace/repo/sensitive-data boundary guidance and
  GitHub/Obsidian-compatible markdown/link conventions for future dashboard,
  team daily log, bookkeeping, and multi-repo work;
- initial paid-traffic site readiness checks through `mb site check`.

Claude Code is the supported slash-skill runtime today. Codex CLI is supported
for daily Main Branch routes through generated `AGENTS.md`, global `mb-*` skills
under the Codex skills root, deterministic `mb` facts, and workflow inventory.
Other runtimes are compatibility targets until adapter code and smoke evidence
exist.

## Current Direction: Chat-First, CLI-Backed Daily Loop

The current product step is making the normal day feel coherent in chat while
keeping the facts deterministic underneath: open the business repo, start
Claude Code, ask `/mb-start`, let the agent run `mb` facts internally, see what
matters in plain language, repair what is stale, ship approved work, and save a
readable checkpoint before moving on.

In one pass, the loop is:

1. **Start grounded.** `/mb-start`, generated repo instructions, or `mb start`
   should make the agent read deterministic `mb` facts before making claims.
2. **Route the thought dump.** A messy operator update should become a business
   primitive: bet, research, decision, push, playbook, outcome, log entry, or
   checkpoint.
3. **Use the right layer.** Claude Code skills are the chat UX and judgment
   layer. `mb` is the fact and safety layer: repo shape, graph links, status
   health, MoneyPath, proof quality, content strategy health, books readiness,
   connected-account readiness, updates, repairs, validation, and guarded commits.
4. **Hide the plumbing, preserve the memory.** Issues, branches, pull requests,
   commits, graph links, and connected-account handles exist so the business
   can inspect what happened later. The user-facing language should stay
   business-readable.
5. **Keep approval explicit.** Writing durable files, publishing, spending,
   provider mutation, and customer contact should stay operator-approved.
6. **Close the loop.** `/mb-end` and checkpoint guidance turn the session into
   durable git-backed memory before the next day starts.

The work clusters into a few durable buckets:

- **Start and status.** `/mb-start`, `/mb-status`, and `mb status` should read
  the same facts: since-last-check changes, ranked next actions, drift,
  onboarding progress, update severity, connected-account readiness, GitHub
  tasks/proposals, MoneyPath readiness, proof quality, content strategy health,
  books readiness, and recent business activity.
- **Repair and migration.** `mb doctor`, `mb doctor repair`, `mb update`, and
  `mb migrate` should make stale installs, old repo layouts, broken skill
  wiring, ignored local state, and provider setup problems visible and
  repairable without asking a non-developer to reason through git plumbing.
- **Business-readable history.** Checkpoints should feel like saved business
  progress, not developer ceremony. The git journal should become a readable
  timeline for status, handoff, retros, and future dashboards.
- **Pushes and growth workflows.** Ads, organic content, sales videos, sites,
  research, bets, and coordinated pushes remain the strongest shipped wedge.
  `pushes/` is the official folder for coordinated work; old structural paths
  surface through migration and repair facts when present.
- **Research depth.** Offer, market, and content work should escalate source
  collection deliberately: memory first when enough, repo context next, public
  research when the answer depends on current outside facts, and deeper
  synthesis only when the decision justifies the time, tokens, and permissions.
- **Books readiness and reporting.** hledger is the accounting engine, `mb
  books` is the privacy, JSON, and workflow wrapper, and skills are the chat UX.
  Fake-data sample monthly reporting is shipped; next direction is
  private-vault reports, imports, reconciliation, or close workflows only after
  separate privacy and smoke evidence.
- **Provider rails.** Cloudflare, GitHub, Google/Workspace, Meta Ads, Apify,
  Postiz-style social scheduling, and future sidecars should enter through
  explicit, tested rails with approval gates where money, publishing, account
  mutation, or customer contact is involved. Meta Ads has read-only readiness
  and compact summary rails; broader provider mutation remains out of scope.
- **Issue and friction capture.** `mb issue` drafts privacy-safe issues and
  `mb feedback` logs friction locally, including `mb connect` refusals, with a
  weekly rollup. Next direction is turning repeated friction into issue drafts
  so real use improves the public engine.

Current public implementation anchors are GitHub issues, not promises in this
roadmap. Check live issues before using any anchor as current scope. For this
phase, the durable topic cluster is generated repo guidance, migration lint,
topology/status/graph facts, child repo descriptors, reusable playbooks,
runtime dogfood, connected-account readiness, and issue/friction capture. Link specific
issue numbers only after verifying their state on GitHub.

Current boundaries:

- no dashboard as source of truth;
- no broad multi-runtime support claims;
- no hosted/public/provider marketplace product;
- no automatic model invocation from `mb`;
- no provider setup that stores secrets in repo files.

## Next: Dashboard extensions, sidecars, and multi-repo views

Once the daily operating loop is boring, Main Branch should make the broader
business system easier to see without replacing the repo or deterministic CLI
facts as source of truth.

`mb dashboard build` and `mb dashboard open` already provide a local read-only
HTML view over repo facts. They do not provide a hosted service or background
agent. `mb google` provides read-only Search Console and GA4 commands after
setup; broader Workspace source ingestion remains planned.

Planned extensions:

- visual multi-repo inventory for business repos, site repos, offer repos, and
  sensitive/private repos, with explicit access boundaries;
- a dashboard map of repos, pushes, bets, commits, issues, PRs, checkpoints,
  provider-safe summaries, and sidecar summaries;
- sidecar enrichment contracts for optional tools such as public company
  context, analytics, bookkeeping, transcription, deployment helpers, and
  provider metrics;
- team daily log surfaces built from commits, checkpoints, issues, PRs, and
  explicit `log/` files instead of treating raw chat as source of truth;
- finance/legal warnings and access-boundary views that make sensitive repos
  obvious without pulling private raw data into shared business memory.

Candidate directions stay candidates until a decision, adapter, and smoke
evidence promote them. That includes dashboard write surfaces, broader provider
mutation, social scheduling rails, growth automation execution, and broader
runtime adapters beyond the supported Claude Code and Codex daily routes. Future dashboard writes should be narrow, schema-backed, and
approval-gated, not free-form chat state or a second source of truth.

Anti-scope:

- no dashboard database as the source of business memory;
- no Slack replacement claim before repo truth, GitHub activity, team logs, and
  permission boundaries are proven;
- no finance/legal raw data in shared repos by default;
- no "connect every SaaS" hub. Provider rails are curated, official where
  possible, deterministic, smoke-tested, and optional.

## Later: Bets And Pushes Become Operating Systems

The next proof point after the daily decision loop is graduating real business
bets into offers, pages, ads, fulfillment, and public Ship surfaces.

Planned scope:

- links between bets, decisions, research, pushes, and outcomes;
- public bets feed generated through site workflows;
- offer launch workflows that connect research, keyword gates, landers, ads,
  organic distribution, tracking, and `/mb-start` orchestration;
- deterministic site/CMS rails over Cloudflare Pages, DNS, GitHub, and
  operator-approved measurement checks;
- decisions on Ops surfaces (books, P&L, compliance) and fulfillment scope;
- bookkeeping/P&L primitives that respect finance-data privacy boundaries
  while still giving operators useful summaries.

## Longer Range

Longer-range work should preserve the same state model: business truth in git,
local operational state outside git, and live process state only when explicit.

Likely directions:

- deeper Codex production workflows and adapters for Cursor, OpenClaw, Hermes, Paperclip-adjacent
  orchestration, and local runtimes;
- extensions beyond the local read-only dashboard, including optional server views over repo
  truth, graph output, GitHub, and connected tools;
- structured data layer for metrics, ads, analytics, P&L, and ledgers, with
  explicit access boundaries before sensitive financial/legal data is surfaced;
- richer sidecar ecosystem behind narrow JSON contracts;
- deeper Paid, Organic, Pages, and Ops workflows under the four-pillar framing;
- optional chat or team-communication surfaces that convert important
  conversation into durable artifacts: issues, proposals, decisions, pushes,
  logs, and commits.

## Reading Order

- [ethos.md](ethos.md) for the product principles.
- [operator-loops.md](operator-loops.md) for the Sense -> Decide -> Ship ->
  Reflect loop.
- [dependency-choices.md](dependency-choices.md) for dependency, integration,
  sidecar, CLI, MCP server, and provider-adapter judgment.
- [compatibility.md](compatibility.md) for runtime support status.
- [business-file-contracts.md](business-file-contracts.md) for file-contract
  shape, guided-route findings, and covered/deferred contracts.
- [CHANGELOG.md](../CHANGELOG.md) for what actually shipped.
- [GitHub issues](https://github.com/dmthepm/mainbranch/issues) for
  durable public work threads.
