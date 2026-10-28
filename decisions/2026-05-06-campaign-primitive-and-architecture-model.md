---
type: decision
date: 2026-05-06
status: accepted
agent_visibility: historical_context_only
topic: Campaign primitive and architecture model
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/321
  - https://github.com/dmthepm/mainbranch/issues/323
  - https://github.com/dmthepm/mainbranch/issues/324
linked_decisions:
  - decisions/2026-05-06-business-repo-folder-model-reference-deprecation.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
---

# Campaign Primitive And Architecture Model

> **⚠️ Superseded in part by
> [decisions/2026-05-06-push-primitive-and-operator-vocabulary.md](2026-05-06-push-primitive-and-operator-vocabulary.md).**
>
> **The body below is historical except where preserved by this notice.**
> The canonical engine primitive is now `push` (folder `pushes/`,
> `type: push`, `linked_pushes`). When the body says "`campaigns/` is the
> canonical home," read that as the *historical* canonical. New writes go
> to `pushes/`; `campaigns/` is a compatibility read only.
>
> What the body still gets right (preserved by the supersession note):
> - the definition of a coordinated push;
> - the relationship model (*strategy → bet → offer → push → provider
>   data → reflection*);
> - the lifecycle (`draft, planned, active, paused, completed, canceled,
>   archived`) — same lifecycle, now applied to `pushes/`;
> - the non-campaign artifact routing (where `research/`, `documents/`,
>   `log/` content goes).
>
> What is now wrong if read literally:
> - any sentence asserting that `campaigns/` is the canonical write
>   target;
> - the example `campaign.md` frontmatter as the canonical schema (it is
>   the legacy schema and stays valid on read; new writes use `push.md`);
> - the implication that `linked_campaigns` is the durable link field
>   (it is now an alias on read; `linked_pushes` is canonical).
>
> Treat the new decision as authoritative when this body and that
> decision conflict.

## Decision

`campaigns/` is the canonical business-repo home for coordinated pushes, not a
rename of legacy `outputs/`.

A campaign is a named, bounded push with a goal or outcome. It coordinates
artifacts and actions intended to move something in the world: a sale, signup,
reply, adoption behavior, launch milestone, audience response, or measured
learning event.

Campaigns can be audience-facing or internal Ops adoption work. The standard is
not "external marketing only"; the standard is a coordinated push with a
recipient group, a goal, a timeline or review moment, and an outcome to judge.

`campaigns/` must not become a generated-artifact junk drawer. If generated
work does not belong to a named push, route it to `research/`, `decisions/`,
`log/`, `documents/`, GitHub, or a separate repo.

## Definition

A campaign has:

- a specific goal or outcome;
- one or more channels or adoption surfaces;
- a recipient group or audience;
- a bounded time window or review date;
- artifacts and actions that are part of the same push;
- relationships to the business context that explains it;
- links to provider/live data where performance is measured.

Examples:

- paid acquisition push;
- organic content sequence;
- email or newsletter launch sequence;
- site or landing-page launch;
- community activation push;
- partner or outreach push;
- product, offer, waitlist, beta, or event announcement;
- internal migration or adoption push with owner, timeline, and outcome.

Non-examples:

- raw transcripts;
- one-off prompt tests;
- throwaway prototypes;
- raw provider exports;
- session recovery notes;
- PR review notes;
- archived repo dumps;
- generated files with no named goal or coordinated push.

## Relationship Model

Use this model:

```text
strategy decides where we should push
bet defines what we are trying to learn
offer defines what we are selling
campaign coordinates the push
provider data records what happened
research / decision / log captures what we learned or changed
```

Campaigns can link to:

- `core/content-strategy.md` and future `core/strategy/...` files;
- `core/offer.md` and `core/offers/...`;
- `bets/...`;
- `decisions/...`;
- `research/...`;
- `log/...`;
- provider/live data such as Meta Ads, Google Ads, email, analytics, Stripe,
  CRM, and future sidecars.

A campaign file may point to provider data. It must not become the provider
database.

Provider/live data may live in provider APIs, local SQLite sidecars, `.mb/`
caches, private analytics or finance repos, exported CSVs in private storage,
or future dashboard indexes. The campaign record stores safe references and
measurement pointers, not raw sensitive data.

## Folder Shape

Default shape:

```text
campaigns/
  2026-05-workshop-waitlist/
    campaign.md
    ads.md
    emails.md
    posts.md
    site.md
    review-log.md
    assets/
    source/
```

Large campaigns can use typed subfolders:
```text
campaigns/
  2026-05-workshop-waitlist/
    campaign.md
    ads/
    emails/
    posts/
    site/
    reviews/
    assets/
    source/
```

The campaign folder is scoped to one push. Multi-channel is acceptable when the
channels serve the same goal. If a folder starts collecting unrelated goals,
split it into separate campaigns.

## Campaign Record

Recommended `campaign.md` frontmatter:

```yaml
---
type: campaign
slug: workshop-waitlist
status: active
goal: "40 qualified waitlist signups"
channels: [paid, email, pages]
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

This is the architecture target. Current CLI validation may enforce less until
follow-up implementation lands.

Statuses should eventually normalize around:

| Status | Meaning |
| --- | --- |
| `draft` | The push is being framed. |
| `planned` | The push is decided but not live. |
| `active` | The push is shipping. |
| `paused` | A blocker or missing input needs attention. |
| `completed` | Shipping is done and reflection is due or complete. |
| `canceled` | The push was intentionally stopped. |
| `archived` | Historical record only. |

`channels` should start as a loose set with validation hints. Recognized slugs
can include `paid`, `organic`, `email`, `pages`, `community`, `partner`,
`outreach`, and `ops`. Tooling should warn on unfamiliar slugs before it fails,
because businesses will have legitimate niche channels.

## Non-Campaign Artifacts

Use these homes:

| Artifact | Home |
| --- | --- |
| Paid ad batch tied to a named push | `campaigns/<campaign>/ads/...` |
| Organic content sequence tied to a named push | `campaigns/<campaign>/posts/...` |
| Email/newsletter launch sequence | `campaigns/<campaign>/emails/...` |
| Site or landing-page launch record | `campaigns/<campaign>/site.md` or child site repo |
| Campaign review notes | `campaigns/<campaign>/review-log.md` or `reviews/` |
| Raw transcripts and source captures | `documents/transcripts/...` |
| Synthesized findings | `research/YYYY-MM-DD-slug.md` |
| Throwaway code, HTML, image, or script prototypes | `documents/prototypes/...` |
| Inert legacy imports and demos | `documents/archive/...` or separate archive repo |
| Session recovery notes and daily work records | `log/YYYY-MM-DD.md` |
| Engine work and PR review | GitHub issues and pull requests |
| Accepted product or architecture choices | `decisions/YYYY-MM-DD-slug.md` |

This decision blesses `documents/transcripts/`, `documents/prototypes/`, and
`documents/archive/` as conventional subfolders. They are not new top-level
primitives.

## Legacy `outputs/`

Legacy `outputs/` content should be read as historical generated work. It
should not be the default write target for new skills.

Do not bulk-move old `outputs/` into `campaigns/`. Some old content belongs in
campaigns. Some belongs in documents, research, log, decisions, GitHub, a child
repo, or private storage. Automated migration should classify only safe,
obvious cases and leave ambiguous items for operator review.

## Research Inputs

External campaign systems converge on a few stable ideas:

- Campaign tools group multiple assets under one campaign for management and
  reporting, as in HubSpot's campaign APIs.
- Campaign planning templates usually include goals, deadlines, messaging,
  tasks, channels, owners, and deliverables, as in Asana's campaign template.
- Launch planning emphasizes goals, measurement, target audiences, channels,
  owners, and readiness gates, as in Atlassian's product launch template.
- Internal stakeholder communication plans still have the shape of a campaign
  when they identify who needs what information, through which channels, and at
  what cadence.

Main Branch should borrow the invariant shape, not mirror any provider schema.

References:

- https://developers.hubspot.com/docs/api-reference/latest/marketing/campaigns/guide
- https://asana.com/templates/campaign-management
- https://www.atlassian.com/software/confluence/templates/product-launch
- https://www.atlassian.com/team-playbook/plays/stakeholder-communications-plan

## Consequences

- `docs/system-architecture.md` is current architecture again and no longer a
  legacy reference-path document.
- `campaigns/` has a business meaning that graph, status, skills, and future
  dashboards can consume.
- `documents/transcripts/`, `documents/prototypes/`, and `documents/archive/`
  give agents a safe route for non-campaign generated or imported artifacts.
- Provider IDs and metrics pointers can be stored in campaign files when they
  are safe to share, but raw provider data and secrets stay outside committed
  repo truth.

## Implementation Follow-Ups

- #323 should implement the deterministic `mb` side: campaign schema,
  validation compatibility, graph indexing, and status/start JSON facts.
- #324 should update bundled skills, migration guidance, and doctor repair
  planning so new writes follow the campaign primitive and legacy `outputs/`
  content gets an operator review path.
