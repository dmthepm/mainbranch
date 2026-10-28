---
type: decision
date: 2026-05-06
status: accepted
topic: Campaigns refuse-list — fields the engine will not add
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/328
linked_decisions:
  - decisions/2026-05-06-campaign-primitive-and-architecture-model.md
  - decisions/2026-05-06-main-branch-operating-spine.md
tags: [v0-3, campaigns, schema, taste]
---

# Campaigns Refuse-List

## Decision

The `campaign.md` frontmatter will not grow the following fields. This refusal
is a feature, not an oversight. Listing it publicly so future PRs and skills
can be evaluated against it.

This is the engineering-taste counterpart to
`decisions/2026-05-06-campaign-primitive-and-architecture-model.md`. That
decision says what a campaign is. This one says what a campaign is not.

## Refused Fields

| Field | Why refused | What to do instead |
| --- | --- | --- |
| `epic` / `parent_epic` | Bundles unrelated work under a heading no operator will look at again. | Use `decisions/` for direction. Use `linked_bets:` when one push is part of a learning sequence. |
| `priority` (numeric: P0/P1/P2) | Fake precision. Two pushes can't both be P1, and the operator is the priority arbiter. | Surface one push at a time in `mb status`. Use `this_week_lever:` (separate issue) to name the single move. |
| `assignee` (multi-person list) | Splits accountability. Coordinated pushes already have one DRI. | Use `owner:` (single, future schema) — one DRI per push. |
| `estimated_hours` / `story_points` | Performative precision. Operators don't track campaigns by hour. | Use `deadline:` and `review_on:` — calendar dates that already exist. |
| `kpi_dashboard` | Visualization is not the campaign record. | Point at the metric source via `metrics_sources[]` or the future flat `external_refs[]`. |
| `linked_okrs` | OKR theater. Most small businesses don't run OKRs and the ones that do already use Linear/Tability/Lattice. | Use `linked_bets` for hypothesis tracking. Use `linked_decisions` for direction. |
| `description` (free-text frontmatter) | Always rots when it tries to carry the campaign's whole story. It also duplicates the markdown body, where narrative belongs. | Use `goal:` (structured), `promise:` (<=140 chars, future schema), and `review-log.md` for narrative. |
| `tier` / `severity` | Imports incident-management vocabulary into a marketing primitive. | If the push is high-stakes, that's evident from the linked offer and bet. |
| `confidence_score` | Performative quantification of judgment. | Operator judgment lives in the linked bet hypothesis. |
| `sentiment` / `mood` | Subjective and stale within a day. | If a push needs a feeling note, it goes in `review-log.md`. |
| `automation_trigger` / `webhook_url` | The `campaign.md` is a record, not a runtime. | Provider integrations belong in sidecars; webhooks belong in the provider. |
| `tags` (free-tagging) | Without governance, tags drift. With governance, they duplicate `kind:`. | Use `kind:` (future schema) for the small bounded set of push types. |

## What This Decision Does

- Future PRs that propose any of these fields must explicitly cite this
  decision and argue why the field is no longer refused.
- `mb validate` should not learn to read these fields. If a user-authored
  campaign carries one, it is tolerated as an extra (the schema tolerates
  extras), but no engine surface treats it as load-bearing.
- Skill prompts (`/mb-ads`, `/mb-organic`, `/mb-site`, future `/mb-push new`)
  must not ask the operator for any of these fields.
- `decisions/2026-05-06-main-branch-operating-spine.md` cites this decision
  as evidence of the principle "the system is judged by what it refuses."

## Reasoning

The merged campaign decision (#327) names the smallest schema that supports
the operator loops. The next pressure on that schema will not come from
operators asking for these fields — it will come from contributors importing
shapes from Salesforce, Jira, HubSpot, or whatever ticketing tool they used
last. Each import looks reasonable in isolation and creates rot in
aggregate. Publishing the refuse list moves that conversation to the front
of the PR, not the middle of a code review.

The Linear precedent: Linear refused estimate fields, story points, and
nested epics for years and was clearer for it. The product's character came
as much from what it didn't ship as from what it did.

## Consequences

- Future schema deltas (Issue: schema deltas v1) cannot quietly land any
  refused field. They land new fields like `owner`, `audience`, `offer`,
  `promise`, `goal: { metric, target, by }`, `health` — which earn their
  place because they answer questions the operator actually asks.
- Migration of legacy `outputs/` content does not import refused fields,
  even if the source artifact carried them.
- Operators with strong preferences for refused fields can store them in
  `documents/` or in their own private repo. They do not become canonical
  campaign memory.

## Open Door

A refused field can be promoted by:

1. A new accepted decision that supersedes this one (in part) and names the
   refused field, the question it answers, and why no existing field can
   answer it.
2. Operator evidence that the omission causes loss in the field — not in
   theory, in dogfood.

This is not a permanent ban. It is a public default with a clear path to
change.
