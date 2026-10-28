---
type: decision
date: 2026-05-08
status: accepted
topic: Business repo topology map
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/406
linked_decisions:
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-06-business-repo-folder-model-reference-deprecation.md
  - decisions/2026-05-06-push-primitive-and-operator-vocabulary.md
  - decisions/2026-05-05-operator-loops-taxonomy.md
tags: [v0-3, topology, dashboard, graph, status, state-model]
---

# Business Repo Topology Map

## Decision

Main Branch should model a business as a **hub business repo plus linked
operating boundaries**. The hub remains the durable business brain. Child repos
exist when a site, offer, product, client, finance, legal, ops, experiment, or
archive surface has its own lifecycle, provider boundary, access boundary, or
execution history.

The topology map is a Sense-loop primitive: it helps an operator and agent see
what exists, what each repo is for, what is stale, and where to work next. It
does not replace GitHub, git history, provider permissions, or the files inside
each repo.

This decision is documentation-only. It defines the product and data model that
future `mb status`, `mb graph`, `mb doctor`, generated instructions, and
dashboard work should implement.

## Topology Layers

| Layer | Owns | Does not own |
| --- | --- | --- |
| Hub business repo | Business-visible topology, strategy, decisions, bets, pushes, logs, safe summaries, and links to child repos | Secrets, raw finance/legal/customer data, provider authority, dashboard cache |
| Child repo | Execution history and local truth for its role: site, product, offer, client, finance, legal, ops, sidecar, experiment, or archive | Company-wide strategy unless it is itself the hub |
| GitHub metadata | Discoverability hints: repo name, description, topics, visibility, issues, PRs, permissions, archive state | Full business meaning, sensitive context, or access decisions beyond GitHub's own permissions |
| Local workspace state | Operator grouping, recent repos, local paths, caches, dashboard indexes, credentials, private operator preferences | Canonical business truth or team-visible policy |
| Provider systems | Actual spending, publishing, billing, deployment, analytics, email, bank, legal, and customer permissions | Main Branch repo access or business topology truth |
| Engine/package | Reusable skills, reusable playbook blueprints, templates, and public operating recipes | A specific business's canonical memory or provider account state |

`mb` may read all of these layers, but the public topology record belongs in
the hub business repo when it is safe for that repo's audience. Private or
personal grouping stays local.

## Repo Roles

Use stable role slugs for machine-readable metadata and business-readable labels
in operator copy.

| Role slug | Business label | Use when |
| --- | --- | --- |
| `business` | Business hub | The repo owns company-level memory: `core/`, research, decisions, bets, pushes, logs, and safe summaries. |
| `site` | Site repo | The repo deploys a website, lander, minisite, docs site, or public bet feed. |
| `offer` | Offer repo | A durable offer or productized service has its own tasks, pushes, provider refs, or operating history. |
| `product` | Product repo | A software product, tool, template, course, or product surface needs its own lifecycle. |
| `client` | Client repo | Fulfillment context or deliverables have a separate confidentiality or access boundary. |
| `finance` | Finance repo | Ledgers, bookkeeping exports, tax docs, payroll, or sensitive P&L sources require private access. |
| `legal` | Legal repo | Contracts, disputes, entity docs, or legal reviews require private access. |
| `ops` | Ops repo | Infrastructure, runbooks, internal routines, or provider setup has a separate authority boundary. |
| `integration_sidecar` | Integration sidecar | A helper repo/tool produces structured provider, analytics, enrichment, deployment data, raw provider caches, metrics databases, connector glue, or large exports. |
| `experiment` | Experiment repo | Work is exploratory and may graduate, pause, or die without becoming core truth. |
| `archive` | Archive repo | Inert imports, retired projects, or historical material are kept for reference only. |

Roles describe the repo's job. Lifecycle describes whether the repo is active.
Do not use `archive` as a lifecycle status for an active repo; use the
`archive` role only when the repo itself is cold storage.

## Relationship Types

Repo topology should name relationships separately from roles. Roles answer
"what kind of repo is this?" Relationships answer "how does it relate to the
hub and to business primitives?"

| Relationship | Use when |
| --- | --- |
| `hub_for` | A business repo is the strategic and operating hub for child repos. |
| `child_of` | A repo belongs under a hub business repo. |
| `execution_vehicle_for` | A child repo ships work for an offer, push, product, client, or site but is not the strategic source of truth. |
| `graduated_from` | A bet, offer candidate, push, or experiment became a durable repo boundary. |
| `supersedes` | A repo replaces an older repo, offer folder, push, or experiment. |
| `archived_from` | A repo preserves historical material that should remain inspectable but inactive. |
| `source_for` | A repo is the source repo for a deployed website, docs site, product, or sidecar. |
| `reports_to` | A restricted finance/legal/ops repo reports approved summaries back to a hub. |
| `uses_provider` | A repo is linked to safe provider handles such as Cloudflare project names, GitHub repos, or non-secret account IDs. |

These relationship names are target vocabulary for future graph/status JSON.
Until code lands, topology notes may use them in prose and frontmatter examples,
but consumers should not assume they are validated.

## Lifecycle

Repo topology lifecycle should use a small, business-readable set:

| Lifecycle | Meaning |
| --- | --- |
| `proposed` | The boundary is being considered but should not be treated as live. |
| `active` | The repo is currently used for real work. |
| `paused` | The repo may resume, but it is not today's operating surface. |
| `superseded` | A newer repo, offer, decision, or push replaced it. Keep the relationship visible. |
| `archived` | Historical record only. Work should not continue there without a revival decision. |

`graduated` is a transition, not a steady state. A bet may graduate into an
offer, a push, or a child repo; the new surface usually becomes `active`, while
the old bet stays closed with a verdict and links forward.

Topology lifecycle is separate from existing primitive statuses. It must not
rewrite bet statuses, push statuses, decision statuses, or offer statuses. A
future implementation may add repo inventory lifecycle validation without
changing the current meanings of `status:` on `bets/`, `pushes/`,
`decisions/`, or `core/offers/`.

## Where Metadata Lives

### Hub Business Repo

The hub repo should eventually carry a topology record under:

```text
core/operations/repo-topology.md
```

That file is durable business truth. It should be safe for everyone with access
to the hub repo and should contain only safe handles:

- stable topology slug;
- display name;
- role slug;
- lifecycle;
- GitHub owner/repo or provider-neutral remote URL when safe to share;
- visibility class (`public`, `team_private`, `restricted`, or `local_only`);
- safe purpose statement;
- linked offers, bets, pushes, decisions, or logs;
- child-to-parent relationship;
- high-level provider readiness summary or links to safe provider refs;
- private-boundary note such as "finance details live in restricted repo."

Example target shape:

```yaml
---
type: repo_topology
status: active
schema: mb.repo_topology.v0
home: github:example-co/example
business_display_name: "Example Business"
repos:
  - slug: example
    display_name: "Example Business"
    role: business
    lifecycle: active
    github_owner: example-co
    repo_name: example
    remote: github:example-co/example
    visibility: team_private
    purpose: "Company-level strategy, decisions, bets, pushes, and logs."
  - slug: workshop-site
    display_name: "Workshop site"
    role: site
    lifecycle: active
    relationship: execution_vehicle_for
    parent: example
    github_owner: example-co
    repo_name: workshop-site
    remote: github:example-co/workshop-site
    visibility: public
    domain: workshop.example.com
    linked_offers:
      - core/offers/workshop/offer.md
    linked_pushes:
      - pushes/2026-05-20-workshop-launch/push.md
  - slug: finance
    display_name: "Finance source"
    role: finance
    lifecycle: active
    visibility: restricted
    relationship: reports_to
    parent: example
    purpose: "Private bookkeeping source; hub stores approved summaries only."
---
```

The schema above is the intended contract, not current CLI validation. Until a
validator lands, agents may write a prose topology note in the same file, but
they should keep the frontmatter shape stable when they use it.

### Child Repos

Child repos should identify their parent boundary without becoming the parent
truth. Existing site repos already use `.mainbranch/source.json` to point back
to the business repo. New child repos should use the role-neutral
`.mainbranch/repo.json` descriptor documented in
[docs/child-repo-descriptors.md](../docs/child-repo-descriptors.md) rather
than overloading site-specific source metadata.

Repo-local descriptors may include:

- parent hub repo;
- role;
- linked offer, push, bet, or decision;
- local schema version;
- safe provider handles;
- exact command for returning to the hub.

They must not contain secrets, private local absolute paths, or permission
claims that bypass GitHub or provider authority.

The child descriptor is a signpost from the child repo back to the hub topology
map. The hub registry in `core/operations/repo-topology.md` remains the durable
business map when the two disagree.

### GitHub Metadata

GitHub topics and descriptions are useful for discovery, not business truth.

Allowed:

- `mainbranch`;
- role-like topics such as `mb-role-site` or `mb-role-product` when the repo is
  public or team-visible and the label is safe;
- short descriptions that say what the repo does in public-safe terms.

Avoid:

- customer names, partner strategy, sensitive offer tests, account identifiers,
  finance/legal status, or private launch plans in public descriptions/topics;
- treating a topic as the only source of the topology relationship.

### Local Workspace State

Local workspace state may group repos across businesses, LLCs, teams, and
operator-only projects. It is the right home for:

- recent repo lists;
- local absolute paths;
- dashboard instance metadata;
- local caches and indexes;
- personal workspace grouping;
- credentials and secret-store references.

It is not a durable team topology record unless a future decision explicitly
adds a committed workspace file. A local dashboard may use it to decide what to
show, but it should identify which facts came from local state versus repo truth.

## Naming Conventions

Naming should make the default path obvious for normal users while staying
boring enough for GitHub, local folders, and dashboards.

### GitHub Owner

Use a GitHub organization when the business has a company, team, public brand,
or multiple repos. Use the personal GitHub account when the operator is solo and
not ready to manage an organization.

| Situation | Recommended owner |
| --- | --- |
| Solo operator without a GitHub org | Personal GitHub account, e.g. `alex` |
| Solo operator with several business experiments | Personal account is acceptable; create an org when access boundaries or collaborators appear |
| Small company or team | Company org, e.g. `example-co` |
| Agency with client work | Agency org for agency-owned work; client org or restricted agency-private repos for client-owned work |
| Public OSS plus private company ops | Public OSS may live in the company org; private operations stay in separate private repos under the same org or a restricted org |

GitHub owner is not the business display name. A dashboard should show both:
`Example Business` as the display name and `example-co/example-business` as the
technical handle.

### Hub Repo Name

The company hub repo should use the durable business slug:

```text
<github-owner>/<business-slug>
```

Prefer `example-co/example` over vague names like `main`, `hub`, `brain`, or
`ops`. If the business slug and org slug are identical enough that repetition
feels awkward, keep the repo clear anyway; `example-co/example` is more durable
than `example-co/main` because it still reads correctly beside site, finance,
product, and OSS repos.

When the operator has no org, use the personal account with the same repo-name
rule:

```text
<personal-github>/<business-slug>
```

Do not use old private or invite-gated product names in public repo names.

### Child Repo Names

| Repo role | Naming convention | Example |
| --- | --- | --- |
| Business hub | `<business-slug>` | `example` |
| Main website | `<business-slug>-site` or `<business-slug>-web` | `example-site` |
| Offer website | `<offer-slug>-site` | `workshop-site` |
| Graduated offer/product | `<offer-or-product-slug>` when brand-distinct; otherwise `<business-slug>-<offer-slug>` | `workshop` or `example-workshop` |
| Finance/legal/admin | `<business-slug>-admin` when one restricted repo is enough; split to `<business-slug>-finance` and `<business-slug>-legal` when access differs | `example-admin` |
| Ops | `<business-slug>-ops` | `example-ops` |
| Client/fulfillment | `<client-or-project-slug>-delivery` when safe; use a neutral project slug when the client name is sensitive | `acme-delivery` |
| Integration sidecar | `<business-or-tool-slug>-<provider-or-job>` | `example-analytics` |
| Experiment | `<experiment-slug>-experiment` | `pricing-test-experiment` |
| Archive | `<old-slug>-archive` | `old-site-archive` |
| Public OSS/tooling | Package/tool name, not the private company hub name | `widget-cli` |

Use lowercase, hyphenated slugs. Avoid customer names, legal/entity details,
sensitive strategy, or private launch language in public repo names.

### Local Folder Names

For a small number of repos, local folders may mirror GitHub handles directly:

```text
~/Documents/GitHub/<github-owner>/<repo-name>
```

or another operator-chosen root with the same owner/repo nesting:

```text
~/src/<github-owner>/<repo-name>
```

For operators with many repos, keep the owner folder and add stable grouping
folders under it. The group folder may change as the topology gets clearer; the
repo folder should still mirror the GitHub repo name:

```text
~/Documents/GitHub/<github-owner>/
  hubs/<business-repo>
  products/<product-or-offer-repo>
  sites/<site-repo>
  private/<finance-legal-or-admin-repo>
  clients/<client-delivery-repo>
  sidecars/<integration-sidecar-repo>
  experiments/<experiment-repo>
  archive/<archive-repo>
```

Owner nesting prevents ambiguity when one machine has repos from multiple
businesses, clients, personal accounts, and OSS orgs. Grouping folders prevent a
large owner namespace from becoming a flat pile. If an operator uses a flat
clone folder, the local folder may include the owner for clarity:

```text
<github-owner>--<repo-name>
```

Do not commit local absolute paths to the topology registry. `mb status` and a
dashboard may display a local path from local workspace state, but the durable
repo record should store GitHub handles, safe display names, and business
relationships.

Repos and folders will sometimes move or rename. Main Branch should treat the
GitHub owner/repo handle as the durable technical handle and the local path as a
repairable checkout location. Future doctor/status repair should help reconnect
a moved checkout, a renamed repo, or a repo moved between local grouping folders
without treating the old local path as canonical truth.

### What Status And Dashboards Should Display

When topology facts exist, `mb status` and dashboards should show these fields
as distinct facts instead of collapsing them into one name:

| Fact | Example | Source |
| --- | --- | --- |
| Business display name | `Example Business` | Hub topology or `mb` onboarding state |
| GitHub owner | `example-co` | Git remote/GitHub metadata/topology |
| Repo name | `example-site` | Git remote/GitHub metadata/topology |
| Local folder | `~/Documents/GitHub/example-co/example-site` | Local workspace state only |
| Repo role | `site` | Hub topology or child descriptor |
| Parent hub | `example-co/example` | Hub topology or child descriptor |
| Website/domain | `example.com` | Safe topology metadata, site records, or provider refs |
| Privacy boundary | `public`, `team_private`, `restricted`, `local_only` | Hub topology |
| Relationship | `execution_vehicle_for core/offers/workshop/offer.md` | Hub topology and graph links |

This distinction matters because the same word can be a brand, GitHub org, repo
name, local folder, website, offer, or product. The topology map should make the
relationships explicit instead of forcing the operator to infer them from names.

## Business Primitive Routing

Topology should not blur existing primitives:

| Question | Home |
| --- | --- |
| "What are we trying to learn?" | `bets/YYYY-MM-DD-slug.md` |
| "What do we sell repeatedly?" | `core/offer.md` or `core/offers/<slug>/offer.md` |
| "What coordinated work is shipping?" | `pushes/YYYY-MM-DD-slug/push.md` |
| "Which reusable recipe should we run?" | Engine/package playbook blueprint, such as a future `.claude/playbooks/<playbook>/` |
| "What happened in this run?" | `pushes/<push>/playbooks/<playbook>.md` |
| "What did we decide?" | `decisions/YYYY-MM-DD-slug.md` |
| "What did we learn or observe?" | `research/`, `log/`, or `documents/` depending on shape |
| "Where does this repo fit?" | `core/operations/repo-topology.md` in the hub, plus a child repo descriptor when needed |
| "Where is sensitive source data?" | Private repo/provider/local source, with only approved summaries linked back |

A live idea can be both a bet and an offer candidate. Keep the bet as the
time-boxed wager with criteria and verdict. Create or update the offer only
when the operator decides the thing is durable enough to sell repeatedly.
Successful bets may graduate into offers, pushes, playbooks, decisions, or
child repos; unsuccessful bets close with a lesson and should not disappear.
Dead, paused, placeholder, superseded, or graduated offer records should be
labeled and linked before anyone considers deleting or renaming them.

Reusable playbooks and push playbook run records are different boundaries. A
reusable playbook is public engine/package capability: an opinionated operating
recipe that many businesses can run. A push playbook is a business repo record:
the approvals, provider boundary, checks, manual steps, evidence, and review
criteria for this specific run. The hub repo should own the run record and
outcome links; the engine/package should own the reusable recipe; sidecar repos
or provider systems may own raw metrics, caches, connector code, and exports.

## Slug Rubric

Slugs are part of the topology because they are how operators and agents
recognize the same thing across files, GitHub, and dashboards.

| Surface | Slug rule |
| --- | --- |
| Offer slug | Stable, undated noun for the thing sold: `workshop`, `local-visibility`, `membership`. Do not rename just because positioning changes. |
| Bet filename | Dated wager: `bets/2026-05-08-local-visibility-test.md`. The date preserves the point-in-time hypothesis. |
| Push folder | Dated execution push: `pushes/2026-05-20-workshop-launch/push.md`. The slug names the action, not the whole business. |
| Child repo name | Stable operating boundary: `workshop-site`, `local-visibility`, `example-finance`. Avoid dates unless the repo is intentionally event-specific. |
| Archive/experiment repo | Preserve the historical slug unless a decision explains the rename. Dead, placeholder, paused, superseded, or graduated work should be labeled before it is deleted. |

If two possible names compete, prefer the name that best matches the durable
operating boundary. Keep aliases or historical names in the topology note rather
than renaming files or repos silently.

## Examples

These examples are intentionally generic. They show naming shape and boundaries,
not private operator history.

### Solo Operator Without A GitHub Organization

```text
github.com/alex/clearer-offers          # role: business
github.com/alex/clearer-offers-site     # role: site
```

Local folders:

```text
~/Documents/GitHub/alex/clearer-offers
~/Documents/GitHub/alex/clearer-offers-site
```

The hub repo stores `core/`, bets, pushes, decisions, logs, and the topology
note. The site repo has a child descriptor pointing back to the hub. If finance
is private and simple, it may remain outside GitHub with only approved summaries
in the hub.

### Small Company With One Org

```text
github.com/example-co/example           # role: business
github.com/example-co/example-site      # role: site
github.com/example-co/example-admin     # role: finance/legal, restricted
```

The hub repo is the company brain. The site repo deploys the public website.
The restricted admin repo holds private finance/legal source material and
reports approved summaries back to the hub. The topology record may mention the
admin repo exists only if that is safe for the hub repo's audience.

### Public OSS Project Plus Private Company Operations

```text
github.com/example-co/example           # role: business, private/team
github.com/example-co/example-cli       # role: product or integration_sidecar, public OSS
github.com/example-co/example-site      # role: site, public deployable surface
github.com/example-co/example-admin     # role: finance/legal, restricted
```

The public OSS repo should use the package or tool name. It is not automatically
the company hub. Product strategy, company decisions, private pushes, and
finance/legal summaries stay in the hub or restricted repos as appropriate.

### Agency And Client Fulfillment

```text
github.com/agency-co/agency             # role: business
github.com/agency-co/agency-site        # role: site
github.com/agency-co/client-alpha-delivery  # role: client, restricted
```

Client repos should not expose parent-company finance, unrelated client
context, private strategy, or cross-client notes. The agency hub can link to the
client repo as a fulfillment boundary and keep only approved summaries or
status notes visible to the agency team.

### Graduated Offer Or Product

```text
github.com/example-co/example           # role: business
github.com/example-co/local-visibility  # role: offer or product
github.com/example-co/local-visibility-site # role: site
```

The idea starts as a bet in `bets/YYYY-MM-DD-local-visibility-test.md`. If the
operator decides it is durable, the hub gets or updates
`core/offers/local-visibility/offer.md`. If execution needs its own lifecycle,
issues, PRs, provider accounts, or deploy history, it graduates into a child
repo. The old bet remains closed with links to the offer, repo, push, outcome,
or decision that explains the graduation.

### Provider Sidecar And Playbook Run

```text
github.com/example-co/example           # role: business
github.com/example-co/example-site      # role: site
github.com/example-co/example-ads-data  # role: integration_sidecar, restricted
```

The business repo stores the offer, bet, push, playbook run record, approval
notes, public-safe provider refs, and outcome summary. The reusable playbook
blueprint lives in the engine/package. The sidecar repo or provider system may
store daily metrics, account caches, connector glue, large exports, or raw
provider data under the appropriate access boundary. Public examples use
placeholders and sanitized fixtures.

## Private Finance And Legal Representation

Finance and legal repos may be important topology nodes, but they are sensitive
by default.

Safe in the hub repo:

- role (`finance` or `legal`);
- lifecycle;
- visibility class (`restricted` or `local_only`);
- approved summary of what the repo is for;
- link to an approved finance/legal decision or operating policy;
- high-level status such as "monthly close pending" if safe for the hub's
  audience.

Not safe by default:

- raw ledger paths, bank exports, payroll, tax, contracts, legal advice,
  disputes, customer/member records, account numbers, provider tokens, or
  exact private local paths;
- frontmatter claiming that a user can view finance or legal data. Permission
  comes from GitHub, provider systems, local OS access, or future hosted auth,
  not from editable repo files.

Future dashboards may show finance or legal status only when the current
operator already has access to the private source. The dashboard should label
that boundary instead of copying raw sensitive data into the hub.

## Surface Behavior Before A Dashboard

### `mb status`

`mb status` should eventually expose a compact `topology` section:

- current repo role;
- parent hub if known;
- linked child repo count by role;
- stale or missing topology descriptors;
- private-boundary warnings without leaking sensitive details;
- ranked action when topology confusion blocks work.

The human output should stay business-readable: "This site repo points back to
the business hub" rather than "source descriptor detected."

### `mb graph`

`mb graph --json` should eventually include repo nodes and relationship edges:

- `owns`, `links_to`, `graduated_from`, `supersedes`, `source_for`,
  `reports_to`, and `uses_provider`;
- edges from bets to offers, pushes, push playbook run records, child repos,
  sidecars, and outcomes;
- role and lifecycle attributes on repo nodes.

Graph output remains an index over repo truth and safe metadata. It should not
fetch private child repo contents unless the operator explicitly includes them.

### Generated Instructions

Generated `CLAUDE.md` and skill instructions should tell agents:

- start in the hub business repo for strategy, bets, decisions, and routing;
- switch to a child repo when editing that child repo's code/site/product files;
- read the child repo descriptor when present;
- ask before deleting, renaming, or merging offer folders or child repos;
- keep private finance/legal source data out of shared business memory.

### Doctor And Repair

`mb doctor repair --plan` should eventually identify topology drift:

- child repo descriptor missing or pointing at a missing hub;
- hub topology record references a missing or inaccessible repo;
- role/lifecycle absent on linked repos;
- legacy site source records that need a generalized descriptor;
- private-boundary records that accidentally include unsafe details;
- offer slug and child repo name drift that needs operator review.

Repair should be preview-first. It may create missing descriptors or add safe
placeholder topology entries only after operator approval. It must not rename
repos, delete folders, or move sensitive data automatically.

### Future Dashboard Map

The dashboard should render the topology as a map over existing truth:

- hub repo in the center;
- child repos grouped by role and lifecycle;
- active bets, pushes, playbook runs, offers, decisions, issues, PRs,
  checkpoints, and provider readiness attached to the relevant boundary;
- private finance/legal nodes clearly marked as restricted without exposing raw
  data;
- local workspace grouping labeled as local state, not committed truth.

The dashboard is the map, not the source of truth.

## Implementation Follow-Ups

Open or update follow-up issues for these slices:

1. **Topology registry schema and validator.** Add `core/operations/repo-topology.md`
   validation, safe visibility classes, role/lifecycle enums, and link checks.
   Tracked in [#416](https://github.com/dmthepm/mainbranch/issues/416).
2. **General child repo descriptor.** Extend the existing site-repo
   `.mainbranch/source.json` pattern into the role-neutral
   `.mainbranch/repo.json` descriptor without breaking site workflows. Tracked
   in [#417](https://github.com/dmthepm/mainbranch/issues/417).
3. **Status and graph topology facts.** Add additive JSON sections for topology
   role, parent, child counts, stale descriptors, repo nodes, and safe edges.
   Tracked in [#418](https://github.com/dmthepm/mainbranch/issues/418).
4. **Generated instructions and skills.** Teach `/mb-start`, `/mb-help`,
   `/mb-site`, and generated business `CLAUDE.md` to use the topology model and
   avoid destructive repo/offer moves. Coordinate the offer/bet parts with
   [#411](https://github.com/dmthepm/mainbranch/issues/411).
5. **Doctor repair plan.** Add preview-first topology drift checks and unsafe
   private-metadata warnings. This is untracked as a standalone follow-up until
   the registry and descriptor contracts in #416 and #417 land.
6. **Dashboard map.** Build only after status/graph expose enough deterministic
   topology facts to keep the dashboard a view over truth. This is intentionally
   gated behind #418 rather than tracked as dashboard implementation in this
   decision.

## Review Checklist

- Every topology example is sanitized and public-safe.
- The hub repo remains canonical business memory.
- GitHub remains the durable work/proposal layer.
- Local workspace state does not become public product truth.
- Finance/legal/private repos are represented by safe handles and summaries.
- Editable repo files do not claim provider, finance, legal, or teammate
  authority.
- Implementation work remains additive until schemas and migrations ship.

## Consequences

- Main Branch has a public model for multi-repo businesses without building a
  dashboard first.
- Future dashboard work can show repo topology without inventing a dashboard
  database as source of truth.
- `mb status`, `mb graph`, doctor, generated instructions, and skills have a
  common vocabulary for repo roles and lifecycle.
- Bet, offer, push, and child-repo boundaries stay distinct, which prevents
  agents from deleting or renaming ambiguous work during migration.
- Sensitive finance/legal surfaces stay visible enough to avoid confusion while
  keeping raw private data outside shared business memory.
