# System Architecture

Current architecture reference. This document covers the durable shapes:
business repo layout, primitives, schemas, artifact routing, and state
boundaries. Product principles live in [ethos.md](ethos.md). Loop taxonomy
lives in [operator-loops.md](operator-loops.md). Release direction lives in
[roadmap.md](roadmap.md). The CLI surface lives in
[the README](../README.md#for-contributors-and-power-users). For a visual
index over the system, see the
[Main Branch system map](architecture/system-map.md).

Older folder names live in [Superseded Names](#superseded-names) at the
bottom. The rest of this doc describes the current model.

## Architecture In One Sentence

Business memory lives in repos the operator owns. `mb` is the deterministic
control plane. Skills do the judgment work. Provider data, secrets, caches,
and dashboards stay outside the main business record.

```text
Main Branch engine     +     business repo            +     optional systems
mb CLI                       core/                          provider APIs
bundled skills               research/                      sidecar databases
validators                   decisions/                     local caches
templates                    bets/                          dashboard views
docs                         pushes/
                             log/
                             documents/
```

The engine doesn't know your business. The business repo does. The engine
reads it without owning it. Provider systems and dashboards are inputs or
views; they do not replace the repo.

## Business Repo Shape

```text
my-business/
├── CLAUDE.md
├── .gitignore
├── .mb/                         # explicit Main Branch state
├── .claude/                     # local runtime wiring; only worktrees/ ignored
├── core/
│   ├── soul.md
│   ├── offer.md
│   ├── audience.md
│   ├── voice.md
│   ├── vocabulary.md            # optional operator-owned display words
│   ├── content-strategy.md
│   ├── product-ladder.md
│   ├── offers/
│   ├── proof/
│   ├── brand/
│   ├── marketing/
│   │   ├── distribution-strategy.md
│   │   ├── channels/
│   │   └── accounts/
│   ├── team/
│   ├── people/
│   ├── strategy/
│   ├── operations/
│   └── finance/
├── research/
├── decisions/
├── bets/
├── pushes/                      # launches, drops, challenges, promos, nurtures, outreach, events, announcements, rounds, waves
├── log/
└── documents/
```

The main business brain is `core/`.

## Repo Topology

A company can outgrow one repo without leaving the Main Branch model. The
business repo stays the hub; specialized repos become linked operating
boundaries. The durable model lives in
[decisions/2026-05-08-business-repo-topology-map.md](../decisions/2026-05-08-business-repo-topology-map.md).
Role-neutral child repo descriptors live in
[child-repo-descriptors.md](child-repo-descriptors.md). New child repos use
`.mainbranch/repo.json` as a local signpost back to the hub; existing site
repo `.mainbranch/source.json` files remain compatibility links.

| Role | What it holds | Boundary |
| --- | --- | --- |
| `business` | Core operating memory, research, decisions, bets, pushes, logs, docs | Default team context |
| `site` | Cloudflare Pages, landing page, minisite, website, or public bet feed | Public deployable surface |
| `offer` | Graduated offer or productized service that needs its own lifecycle | Linked back to the business repo |
| `product` | Software product, tool, course, template, or product surface | Separate when execution has its own lifecycle |
| `client` | Client-specific fulfillment context and deliverables | Separate when access or confidentiality differs |
| `finance` | hledger journal, exports, tax docs, sensitive P&L sources | Private by default; share summaries intentionally |
| `legal` | Contracts, entity docs, disputes, or legal reviews | Private by default; share summaries intentionally |
| `ops` | Private infrastructure, runbooks, provider setup, or team routines | Separate when operational authority differs |
| `integration_sidecar` | Helper repo/tool for provider, analytics, enrichment, deployment data, raw caches, metrics databases, or connector glue | Optional and contract-backed |
| `experiment` | Exploratory work that may graduate, pause, or die | Not core truth until decided |
| `archive` | Inert imports, legacy projects, or cold storage | Read-only unless revived |

`mb status --json`, `mb graph --json`, and `mb doctor repair --plan --json`
expose topology facts today. A future dashboard rendering this topology in
business language is direction, not current behavior; see
[roadmap.md](roadmap.md).

## Primitive Contracts

### Business File Contracts

Business file contracts define the owner-facing shape of useful business
records: purpose, required frontmatter, required body sections, privacy
boundary, lifecycle, severity, approval rules, and the recommended `mb-*` route.
See [business-file-contracts.md](business-file-contracts.md).

These contracts sit above frontmatter schema validation. Frontmatter checks make
files machine-readable; file contracts explain whether the file has enough
business context to route work safely. Contract findings are deterministic `mb`
facts for `mb validate`, `mb status`, Claude Code, Codex, and future workflow
migrations.

### Shared Workflow Source

Portable workflow semantics live in `workflows/<workflow>/workflow.md`.
Runtime-specific files are runtime shells or runtime guidance over that source,
not the canonical truth.

Shared workflow sources now cover the daily start/status, setup,
maintenance/repair, think, closeout/checkpoint, bet, ads, organic, and site
workflows. Each source declares the workflow intent, operator loops, runtime
support level, checked runtime surfaces, required `mb` fact commands, JSON fact
paths, approval gates, public/private boundaries, routing rules, handoff shape,
and validation expectations. Claude Code remains the first-class slash-skill
runtime shell through `.claude/skills/<name>/SKILL.md`; Codex uses tracked
`AGENTS.md` plus global Main Branch `mb-*` skills under the Codex skills root,
with output and provider workflows kept at read-only planning until runtime
smoke proves write support. Neither `.claude/skills`, generated repo guidance,
nor runtime skill files are the canonical source for cross-runtime workflow
semantics.

`mb` may validate, render snapshots for tests, and repair generated runtime
guidance. It must not invoke Claude, Codex, or any model.

### `core/`

Evergreen business truth: offer, audience, soul, voice, proof, brand systems,
strategy, operations, and finance boundaries. Files do not carry dates.
Current truth, not a snapshot.

### Offers

In a single-offer repo, `core/offer.md` is the durable offer truth: promise,
pricing, mechanism, deliverables, qualification, objections, guarantee, and
delivery assumptions.

In a multi-offer repo, `core/offer.md` is the portfolio thesis. Per-offer truth
lives in `core/offers/<slug>/offer.md`; optional per-offer audience context
lives in `core/offers/<slug>/audience.md`.

A new or uncertain offer idea usually starts as a bet. Do not rename, delete,
merge, split, or move offer folders without an accepted decision, approved
migration plan, or explicit operator instruction.

### Proof

Reusable evidence that a claim is true. Company-wide proof belongs in
`core/proof/`. Offer-specific proof belongs in `core/offers/<slug>/proof/`.
Standard filenames: `testimonials.md` for individual permissioned testimonials,
`typicality.md` for average-case outcome context, and `angles/` for durable
messaging angles.

Status-detectable testimonial structure can use frontmatter or structured
entries with permission fields such as `public`, `permissioned_public`,
`approved_for_public`, or `safe_to_share`. Offer linkage is explicit when proof
lives under `core/offers/<slug>/proof/` or when a testimonial entry uses
`offer`, `linked_offer`, or `linked_offers`. Loose prose can still be useful to
the operator, but `mb status` only treats path placement and those structured
fields as offer-link signals.

Use `permissioned_public: false` for specific proof that is useful internally
but not approved for public marketing yet. `mb status --json --peek` reports
that as blocked public-marketing proof under
`money_path.objects.proof.quality.public_marketing`; skills should collect
permission before using it in public ads, pages, or claims.

Generic testimonials are still proof material. They should not be described as
specific, offer-linked, typicality-aware, or outcome-backed unless the
corresponding MoneyPath facts say so. `typicality.md` should record
average-case outcomes, caveats, common failure context, and time-to-outcome
when those facts are available.

### MoneyPath Status

MoneyPath is a read-only `mb status` view over existing primitives, not a new
business file or replacement for offer truth. It checks whether customer
progress, offer, audience, proof, product ladder, CTA, channel, active push,
playbook, page readiness, and outcome feedback are legible and connected.

The score is gated. A missing CTA path, ambiguous active offer, or missing
outcome feedback caps the overall level even when other files are rich. The CLI
reports deterministic readiness facts; skills and operators still own offer
strategy, conversion quality, and market judgment.

Future dashboards can render proof badges or gaps from
`money_path.objects.proof.quality`, such as generic proof, specific proof,
offer-linked proof, typicality-aware proof, and outcome-backed proof. Those
badges should cite the underlying facts rather than invent a separate
persuasion score.

### Content Strategy

The content operating model lives in
[`docs/content-strategy.md`](content-strategy.md). Keep
`core/content-strategy.md` as the simple business-level strategy and index.
It answers what the business wants to be known or recommended for, who the
content is for, which pillars and content jobs matter, and what not to publish.

Use advanced layers only when the operator needs them:

```text
core/marketing/distribution-strategy.md
core/marketing/channels/<channel>.md
core/marketing/accounts/<platform>-<account>.md
core/people/<person>.md
```

`core/marketing/distribution-strategy.md` coordinates blog, wiki, changelog,
email, social, communities, partners, and paid amplification. Channel files
record platform norms and update triggers. Account files record account-specific
audience, voice reference, cadence, content mix, CTA path, and allowed topics.
Person files hold founder/person voice source material, beliefs, stories, proof,
and fabrication boundaries. `core/voice.md` remains the brand voice contract.
`mb validate` enforces layered file shape, account-to-channel/person
relationships, freshness metadata for fast-changing platform layers, and
unindexed layers that are not indexed from `core/content-strategy.md`.
`mb status --json` normalizes that into `content_strategy` health facts for
`/mb-start` and future read-only dashboard views.

Specific execution still belongs in `pushes/<YYYY-MM-DD-slug>/`, and results
or lessons land in `log/`, a push review log, research, decisions, or core
updates. Do not duplicate publishable site/blog/wiki content into the business
repo's operating strategy.

### Team Members

Public-safe team context lives in `core/team/<slug>.md`. The filename stem is
the stable team member slug that other primitives can reference later, for
example a future bet `owner: maya` or `owner: core/team/maya.md`. Prefer a slug
that matches the person's primary GitHub handle when that is stable.

Team member frontmatter:

```yaml
type: team_member
slug: maya
name: Maya Chen
preferred_name: Maya
role: Growth Lead
relationship: member
github:
  - mayachen
areas:
  - paid traffic
  - launch reviews
notes: Public-safe business context only.
```

Allowed `relationship` values are `owner`, `member`, `contractor`, `advisor`,
and `external_collaborator`. Owners and members are part of the operating team.
Contractors and advisors are useful business context but may not own decisions.
External collaborators are outside the team; add them only when GitHub activity,
pushes, offers, or decisions need a business-readable name.

Do not store payroll, compensation, legal ownership percentages, home contact
details, private customer/member data, secrets, or account credentials in team
files. GitHub handles should be stored without `@`. `mb validate` checks team
frontmatter shape, handle normalization, and duplicate handles. `mb status`
exposes a `team` block so GitHub activity can say a person's business name when
the handle is known and preserve unknown handles when it is not.

### `research/`

Point-in-time findings from when the operator went looking. Research can cite
sources, but it should synthesize what matters rather than become a capture
folder.

```text
research/2026-05-06-competitor-offer-analysis.md
research/2026-05-06-customer-language-review.md
```

### `decisions/`

Choices with rationale: situation, options, accepted direction, rejected
alternatives, what changes because of it. Decisions can be proposed before
acceptance. Accepted decisions become durable truth until superseded.

### `bets/`

Time-boxed operating hypotheses: what the operator will try, why it might
work, by when, and how success or failure will be judged. A bet is usually
Decide → Ship → Reflect. It may lead to a push, an offer change, a workflow,
a content pillar, a provider setup, or a decision.

### `pushes/`

`pushes/` is the engine primitive for coordinated work. See
[decisions/2026-05-06-push-primitive-and-operator-vocabulary.md](../decisions/2026-05-06-push-primitive-and-operator-vocabulary.md):
folder `pushes/<YYYY-MM-DD-slug>/push.md`, frontmatter `type: push`, link
field `linked_pushes`, JSON keys push-shaped, and `kind:` as a bounded enum
(`launch | drop | challenge | promo | nurture | outreach | event |
announcement | round | wave`).

The operator's preferred display word for a push (e.g. *drop*, *launch*,
*challenge*) lives in `core/vocabulary.md` and never overrides `kind:` on
disk.

A push is not a generic generated-artifact bucket. A push has:

- a named goal or outcome;
- a recipient or audience (including internal stakeholders for Ops adoption);
- one or more distribution or adoption channels;
- a bounded time window or review moment;
- artifacts and actions that belong to the same push;
- links to the bets, offers, strategy, decisions, research, logs, and
  provider data that explain or measure it.

Qualifying examples: paid ad push, organic content sequence, email/newsletter
launch, site or landing-page launch, partner outreach push, product/offer
announcement, internal adoption push with a clear goal and outcome.

Non-qualifying: raw transcripts, one-off code experiments, provider exports,
loose session recovery notes, archived repo dumps, generated artifacts with
no named push.

#### Push Folder Shape

```text
pushes/
  2026-05-06-workshop-waitlist/
    push.md
    ads.md
    emails.md
    posts.md
    playbooks/
    site.md
    review-log.md
    assets/
    source/
```

`push.md` is the record. Other files are push artifacts, source notes,
operator review notes, or asset references for that same push. The folder
name uses **day** precision (`YYYY-MM-DD-slug`) to match other dated
primitives.

For larger pushes, typed subfolders are acceptable:

```text
pushes/2026-05-06-workshop-waitlist/
  push.md
  ads/
  emails/
  posts/
  playbooks/
  site/
  reviews/
  assets/
  source/
```

Do not create a push folder just because a file was generated. If the work
does not have a push goal, route it to the primitive that owns it.

#### Push Record

Recommended `push.md` frontmatter:

```yaml
---
type: push
slug: workshop-waitlist
kind: launch
status: active
health: on-track
goal:
  metric: qualified waitlist signups
  target: "40"
  by: 2026-05-20
owner: Devon
audience: founders testing Main Branch
offer: core/offers/workshop/offer.md
promise: Own the workshop launch memory in git.
channels: [paid, email, site]
started: 2026-05-06
review_on: 2026-05-20
linked_strategy:
  - core/content-strategy.md
linked_offers:
  - core/offers/workshop/offer.md
linked_bets:
  - bets/2026-05-06-workshop-waitlist.md
linked_decisions:
  - decisions/2026-05-06-workshop-price.md
linked_research: []
provider_refs:
  meta_ads:
    campaign_id: "example-placeholder"
metrics_sources:
  - ".mb/sidecars/meta-ads/workshop-waitlist.sqlite"
---
```

For a one-off push without a bet, use `linked_bets: []` and a non-empty
`no_bet_reason` in its frontmatter. `mb status` warns about live pushes with no
bet link or one-off reason. If the push has no review, start, or date field,
status uses the leading date in its slug or folder name to check staleness.

`mb validate` enforces this shape: `type: push`, bounded `kind:`, lifecycle
`status:`, separate `health:`, structured `goal: { metric, target, by }`, one
`owner`, a named `audience`, a named `offer`, and a short `promise`.

Push status maps to operator loops:

| Status | Loop meaning |
| --- | --- |
| `draft` | Decide is still forming the push. |
| `planned` | Decide is complete; Ship has not started. |
| `active` | Ship is underway. |
| `paused` | Sense or Decide must resolve a blocker. |
| `completed` | Ship is done; Reflect should evaluate it. |
| `canceled` | The push was intentionally stopped. |
| `archived` | Historical record only. |

`channels` is loose, not a hard enum. Common slugs: `paid`, `organic`,
`email`, `site`, `community`, `partner`, `outreach`, `internal`.

#### Playbooks

Two layers:

- A **reusable playbook** is an engine-packaged operating recipe under
  `playbooks/<name>/playbook.md`. Public, sanitized, opinionated, runnable by
  many businesses. Runtime shells such as
  `.claude/playbooks/<name>/SKILL.md` adapt that source for a specific runtime.
- A **push playbook** is a per-run business repo record under
  `pushes/<push>/playbooks/<playbook>.md`.

A push playbook is a plan, approval record, setup recipe, and outcome hook.
It is not proof that Main Branch can mutate a provider account. `provider`
records where execution would happen; `provider_boundary` records whether
execution is manual, external, candidate, or backed by an accepted adapter.
Provider ids are lowercase hyphenated slugs (e.g. `manual`, `meta-ads`,
`postiz`, `x-api`).

Required v1 playbook frontmatter:

```yaml
---
type: playbook
status: draft
push: ../push.md
platform: instagram
provider: manual
provider_boundary: plan-only
trigger:
  kind: comment_keyword
  keyword: TEMPLATE
resource:
  kind: url
  value: https://example.com/resource
copy:
  public_cta: Comment TEMPLATE for the resource.
  reply: Thanks. The resource is linked in the post.
approval:
  required: true
  status: needed
  approved_by:
  approved_at:
state:
  provider_refs: []
  activated_at:
  retired_at:
validation:
  dry_run: not-run
  smoke_evidence: []
  notes: Draft only; no provider mutation.
linked_outcomes: []
---
```

Valid playbook statuses: `draft`, `planned`, `approved`, `active`, `paused`,
`completed`, `canceled`, `retired`. Valid provider boundaries: `plan-only`,
`external-manual`, `candidate-adapter`, `accepted-adapter`. Until a separate
provider issue accepts an adapter with approval gates, docs, tests, and smoke
evidence, `mb validate` rejects `accepted-adapter` claims.

Playbook frontmatter must not contain tokens, API keys, private account
exports, raw DMs, customer records, cookies, or session secrets. Safe
provider state means stable public-safe ids, timestamps, validation notes,
links to repo outcome/log files, and smoke evidence references.

### `log/`

What happened: daily records, session summaries, recovery notes, operator
handoffs, non-decision work records. Use `log/` when the durable value is
chronology and recovery rather than a research finding, decision, bet, or
push artifact.

### `documents/`

Supporting material durable enough to keep but not itself core truth,
research, decision, bet, push, or log entry.

```text
documents/transcripts/   # raw or lightly cleaned source transcripts
documents/prototypes/    # throwaway code, HTML, images, scripts, or demos
documents/archive/       # inert legacy imports or reference dumps
```

Use separate repos when a prototype, site, app, offer, finance surface, or
archive graduates into its own operating boundary.

## Artifact Routing

| Artifact | Official home |
| --- | --- |
| Paid ad batch tied to a named push | `pushes/<push>/ads/...` |
| Organic sequence tied to a named push | `pushes/<push>/posts/...` |
| Email or newsletter launch sequence | `pushes/<push>/emails/...` |
| Resource delivery, provider setup, or automation approval plan tied to a push | `pushes/<push>/playbooks/...` |
| Landing-page launch record | `pushes/<push>/site.md` or child site repo |
| Push review notes | `pushes/<push>/review-log.md` or `reviews/` |
| Raw transcript or source capture | `documents/transcripts/...` |
| Meeting summary or operator handoff | `log/YYYY-MM-DD.md` or `documents/meetings/...` |
| Synthesized findings from source material | `research/YYYY-MM-DD-slug.md` |
| Throwaway code, HTML, script, or image experiment | `documents/prototypes/...` |
| Operational site, app, or offer repo | separate child repo with links back |
| Fulfillment SOP, delivery note, or internal ops guide | `core/operations/...`, `documents/...`, or a client repo |
| Finance source ledger | private finance repo or local sidecar; only safe summaries link back |
| Session recovery or daily work record | `log/YYYY-MM-DD.md` |
| Accepted architecture or product choice | `decisions/YYYY-MM-DD-slug.md` |
| Engine coordination or review | GitHub issue or pull request |
| Inert legacy import | `documents/archive/...` or separate archive repo |
| Local cruft | ignored or deleted, not migrated |

Ambiguous artifacts get routed by the operator through migration or doctor
repair. No silent bulk moves.

## Relationship Model

```text
strategy decides where we should push
bet defines what we are trying to learn
offer defines what we are selling
push coordinates the work
provider data records what happened
research / decision / log captures what we learned or changed
```

- Strategy lives in `core/content-strategy.md`, `core/marketing/...`, or
  `core/strategy/...`.
- Offers live in `core/offer.md` and `core/offers/<slug>/offer.md`.
- Bets live in `bets/...` and can link to one or more pushes.
- Pushes link back to bets, offers, decisions, research, and strategy.
- Provider refs identify external provider campaign/account objects without
  copying raw provider data into the business repo.
- Metrics sources point to provider APIs, local sidecars, `.mb/` caches, or
  exported files under a boundary the operator chose.
- Reflection lands in a bet verdict, research note, decision update, push
  review log, or `log/` entry.

## State Boundaries

Business state:

- `core/`
- `research/`
- `decisions/`
- `bets/`
- `pushes/`
- `log/`
- `documents/`
- git history
- GitHub issues and pull requests

Local operational state:

- `.mb/` caches, indexes, schema markers, repair backups, local connection
  metadata;
- `.claude/settings.local.json` and runtime wiring;
- runtime-specific local files;
- OS keychain, environment variables, 1Password, or other secret stores.

External or optional state:

- provider APIs;
- local SQLite sidecars;
- private analytics or finance repos;
- exported CSVs in private storage;
- future dashboard indexes (direction, not shipped).

Secrets, bearer tokens, OAuth refresh tokens, service-account JSON, customer
exports, raw member data, and sensitive finance/legal data do not belong in
public examples or committed business repo files.

## Provider, Sidecar, and Dashboard Boundary

Provider systems record live operational facts. Sidecars can enrich Main
Branch with structured data. A future local dashboard could render repo and
provider truth without owning it. None of these replace the main business record.

Main Branch does not claim blanket provider mutation. A provider rail can mutate
external systems only when that exact workflow has preview behavior, operator
approval, readiness checks, tests, and smoke evidence. Until then, playbooks are
plans and approvals, not execution. See [roadmap.md](roadmap.md) and
[dependency-choices.md](dependency-choices.md) for direction.

Correct pattern:

```text
pushes/2026-05-06-workshop-waitlist/push.md
  provider_refs.meta_ads.campaign_id -> provider object
  metrics_sources[] -> sidecar/cache/private analytics source

mb status / future dashboard
  reads push.md, graph, git, GitHub, and provider-safe summaries
```

Incorrect pattern:

```text
push.md becomes a raw ads database
dashboard database becomes the only place push truth exists
.mb/cache is treated as business memory
chat transcript is treated as the decision record
```

## `mb` and Skills

`mb` is the deterministic control plane: repo scaffolding, validation,
graph, status, doctor/repair, connect, update, migrate, skill management,
and checkpoint. The full surface lives in
[the README](../README.md#for-contributors-and-power-users).

Skills own judgment-heavy work: synthesis, writing, review, routing. They call
`mb` for facts. Claude Code is the supported slash-skill runtime today. Codex
CLI is supported for daily Main Branch routes through generated repo guidance,
global `mb-*` skills under the Codex skills root, and deterministic `mb` facts.
Other runtimes are compatibility targets until adapter code and smoke evidence
exist. See [compatibility.md](compatibility.md).

Curated rails — GitHub, Cloudflare, Google/Workspace, official ads paths,
Postiz, hledger, transcription helpers — earn their place by improving a loop
and by failing in ways `mb` can explain. See
[ethos.md](ethos.md#8-curated-rails-beat-saas-sprawl) and
[dependency-choices.md](dependency-choices.md).

## Validation and Migration

The validation ladder is in [AGENTS.md](../AGENTS.md). Release evidence
ladder is in [release-simulations.md](release-simulations.md). The short
rule: prove the surface you changed.

Migration preserves user-authored content and distinguishes compatibility
bridges from split truth.

## Superseded Names

This section is the only place older folder names belong. Treat the rest of
the doc as describing the current model.

Older repos and historical decisions used:

| Old | Current |
| --- | --- |
| `campaigns/<slug>/campaign.md` (`type: campaign`, `linked_campaigns`) | `pushes/<YYYY-MM-DD-slug>/push.md` (`type: push`, `linked_pushes`) |
| business-repo `reference/` folder | `core/` (per [decisions/2026-05-06-business-repo-folder-model-reference-deprecation.md](../decisions/2026-05-06-business-repo-folder-model-reference-deprecation.md)) |
| `domain/` | `core/` |
| `.vip/local.yaml` / `.vip/config.yaml` | `.mb/` plus runtime-specific local files; legacy YAML is audit-only |
| `outputs/` | `pushes/<push>/...` for coordinated work; `documents/` for supporting material |

Compatibility behavior:

- `campaigns/<slug>/campaign.md` records still read. `mb validate`,
  `mb graph`, and `mb status` index them identically to `pushes/`;
  `type: campaign` is a recognized alias on read; new writes go to
  `pushes/`. Migration policy is in
  [decisions/2026-05-06-push-primitive-and-operator-vocabulary.md](../decisions/2026-05-06-push-primitive-and-operator-vocabulary.md)
  and the relationship model is unchanged from
  [decisions/2026-05-06-campaign-primitive-and-architecture-model.md](../decisions/2026-05-06-campaign-primitive-and-architecture-model.md).
- Existing site repo `.mainbranch/source.json` files remain compatibility
  links; new child repos use `.mainbranch/repo.json`.
- Ambiguous legacy artifacts go through operator review (`mb doctor
  repair --plan` / migration), not silent bulk moves.
