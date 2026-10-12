# Business File Contracts

Main Branch business-file contracts define what a useful business record needs
to contain before an agent routes work from it.

Frontmatter schemas answer whether a file is machine-readable. File contracts
answer whether a file is useful for the operator loop: what it is for, what
business context it must carry, what stays private, which lifecycle states
matter, which `mb-*` route can help, and which writes need approval.

The contract system keeps three promises:

- `mb` reports deterministic facts and owner-facing gaps.
- Claude Code and Codex route from the same JSON facts and workflow names.
- Skills and workflow sources (current and future) reuse one contract
  vocabulary instead of inventing file rules one by one.

## Status

This release defines the full contract map and implements the first enforced
slice.

| Contract | Paths | Status | Route |
| --- | --- | --- | --- |
| Offer | `core/offer.md`, `core/offers/<slug>/offer.md` | Active enforcement | `mb-think` |
| Audience | `core/audience.md`, `core/offers/<slug>/audience.md` | Specified, deferred | `mb-think` |
| Proof | `core/proof/`, `core/offers/<slug>/proof/` | Specified, deferred | `mb-think` |
| Content strategy | `core/content-strategy.md`, `core/marketing/**` | Specified, deferred | `mb-organic` |
| Decision | `decisions/*.md` | Specified, deferred | `mb-think` |
| Research | `research/*.md` | Specified, deferred | `mb-think` |
| Bet | `bets/*.md` | Specified, deferred | `mb-bet` |
| Push | `pushes/<date-slug>/push.md` | Specified, deferred | `mb-start` |
| Playbook run | `pushes/<date-slug>/playbooks/*.md` | Specified, deferred | `mb-start` |
| Log | `log/*.md` | Specified, deferred | `mb-end` |
| Document | `documents/*.md` | Specified, deferred | `mb-think` |
| Provider/data source | `data/*/source.md`, `provider_refs` | Existing schema/readiness checks | `mb-start`, `mb-ads`, `mb-site` |
| Books | `core/finance/`, books policy files | Existing books checks | `mb-start`, books commands |
| Team member | `core/team/*.md` | Existing schema checks | `mb-start` |
| Repo topology | `core/operations/repo-topology.md`, `.mainbranch/repo.json` | Existing schema/topology checks | `mb-start` |

Deferred means the public contract is named here, but this PR does not enforce
body-section findings for that type yet. Existing frontmatter, relationship,
books, content-strategy, topology, provider, and team checks continue to run.

## Contract Fields

Every contract should name:

- purpose;
- required frontmatter;
- required body sections;
- optional body sections;
- privacy boundary;
- lifecycle status;
- validation severity;
- owner-facing message style;
- recommended `mb-*` route;
- write and repair approval rules;
- example good file shape.

Contract findings use business language. They should say "your offer does not
yet tell a qualified buyer what to do next," not "missing H2: CTA."

## Research Placement Across Repos

When a business runs more than one repo (hub plus product/site repos),
research lives where its conclusions codify — not where the session happened
to run:

- conclusions change `core/` (offer, audience, pricing, positioning, bets)
  → the business repo's `research/`;
- conclusions land in one product repo's code or docs → that product repo's
  `research/`;
- mixed → default up to the business repo, folding build notes into the
  product repo's docs in the same pass.

Quick test: if the product were rebuilt from scratch tomorrow and this
research still matters, it belongs in the business repo. Durable conclusions
always codify up into the business repo's `core/` regardless of where the
raw file sits, and research files carry `offer:` frontmatter in multi-offer
repos. `/mb-think` applies this contract in its research and codify phases.

## Current Paths And Legacy Repos

Contracts document current Main Branch paths only: `core/`,
`core/offers/`, `research/`, `decisions/`, `bets/`, `pushes/`,
`pushes/<date-slug>/playbooks/`, `log/`, and `documents/`.

Runtime compatibility remains an engine responsibility. If old repo shapes are
present, `mb status`, `mb doctor`, and migration checks can detect them, label
them as legacy input, and recommend a repair or migration plan. Agent-facing
skills should not present old paths as normal current structure, and new writes
should route to current paths after operator approval.

## Date Policy

Git history is the audit layer. It shows what changed and when. It is not a
replacement for business-effective dates inside files, because operators using
Obsidian or plain Markdown need semantic time context without opening GitHub
history.

Use dates heavily for dated records:

- research;
- decisions;
- bets;
- pushes;
- logs;
- outcomes;
- playbook runs.

Keep evergreen core files mostly date-light. Allow targeted semantic dates when
they change trust or routing, such as `last_reviewed`, `effective_from`,
`review_on`, `superseded_by`, `proof_approved_on`, or `source_decision`.

Do not require generic `created` or `updated` frontmatter on every core file.
That creates maintenance tax. Use Git for edit history and explicit file dates
for business meaning.

## Business Validation Lens

The contract map is checked against ordinary operating needs for small
businesses:

- offer and positioning clarity;
- audience and customer-progress language;
- proof, typicality, and permission boundaries;
- sales path and next step;
- channel and content strategy;
- launch, push, and playbook execution;
- bet, experiment, and decision memory;
- outcome feedback and review cadence;
- finance/books privacy;
- provider readiness without committed secrets.

Main Branch should not import outside business-framework jargon into the file
system. The durable nouns stay: offers, proof, bets, pushes, decisions,
outcomes, playbooks, logs, documents, checkpoints, connected accounts, and
books.

## Contract Matrix

### Offer

**Purpose:** durable truth for what the business sells, who it helps, why it is
credible, and what a buyer should do next.

**Paths:** `core/offer.md` for a single-offer repo or portfolio thesis;
`core/offers/<slug>/offer.md` for a specific offer in a multi-offer repo.

**Required frontmatter:** per-offer files require `slug` and `status` today.
`core/offer.md` may stay lighter because older repos and single-offer repos use
it as evergreen truth.

**Required body sections:**

- Who this is for
- Promise or transformation
- Mechanism
- Proof
- Price or value
- Next step

**Optional sections:** qualification, deliverables, objections, guarantee or
risk reversal, positioning notes.

**Privacy boundary:** public-safe offer claims only. Do not store private
customer details, private sales call transcripts, raw account data, or secrets.

**Lifecycle:** draft, running, scaling, retired. Existing status values remain
accepted by schema for compatibility.

**Severity:** warning. A weak offer shape should guide the next workflow, not
block all repo validation.

**Route:** `mb-think`.

**Approval rule:** ask before editing offer files or changing durable claims.

**Example:**

```md
---
type: offer
status: running
---

# Setup Sprint

## Who this is for

Solo operators who have useful AI work scattered across chats, docs, and
folders, and want one business repo that future sessions can read.

## Promise

Turn scattered launch and operating context into durable business memory the
operator owns.

## Mechanism

Main Branch creates a repo shape for offers, proof, pushes, decisions, bets,
logs, and checkpoints, then agent workflows read deterministic `mb` facts
before making recommendations.

## Proof

Use public-safe testimonials in `core/proof/testimonials.md` and average-case
context in `core/proof/typicality.md` before using claims in ads or pages.

## Price Or Value

One setup sprint with a fixed scope and a clear handoff into daily use.

## Next Step

Book a fit call or run the setup checklist before writing launch copy.
```

### Audience

**Purpose:** name the customer, the progress they want, their language, and the
objections that shape offer, site, ads, and organic work.

**Required frontmatter:** type/status when layered files need lifecycle.

**Required body sections:** customer progress, buyer language, pain or gain,
objections, disqualification.

**Privacy boundary:** synthesize customer language; do not commit raw private
DMs, customer/member data, or gated-community content without an explicit
sanitized summary.

**Severity:** warning when enforced.

**Route:** `mb-think`.

### Proof

**Purpose:** make claims usable without fabricating outcomes or over-sharing
private customer material.

**Required frontmatter:** permission and offer-link fields where individual
entries need machine detection.

**Required body sections:** testimonials or evidence, offer linkage,
permission status, typicality or caveats, source context.

**Privacy boundary:** specific proof can be internal. Use
`permissioned_public: false` when proof is useful but not approved for public
marketing.

**Severity:** warning or blocked public-marketing finding depending on
permission.

**Route:** `mb-think`; downstream route may be `mb-ads` or `mb-site` after proof
is usable.

### Content Strategy

**Purpose:** describe what the business wants to be known or recommended for,
who the content serves, which channels matter, and what not to publish.

**Required frontmatter:** existing content-strategy schema for layered files.

**Required body sections:** audience, pillars, content jobs, channels, cadence,
CTA path, do-not-publish boundaries.

**Privacy boundary:** keep raw private community content and account secrets out
of strategy files.

**Severity:** warning.

**Route:** `mb-organic` for planning; `mb-think` when the strategy itself needs
research or a decision.

### Decision

**Purpose:** record a durable choice and why it was made.

**Required frontmatter:** `date`, `status`, plus relationship fields when
linked work exists.

**Required body sections:** situation, options, accepted direction, rejected
alternatives, consequences, review/supersession trigger.

**Privacy boundary:** public-safe rationale. Private customer, finance, legal,
or partner details belong in sanitized summaries or restricted repos.

**Severity:** warning for body gaps; error for invalid frontmatter status.

**Route:** `mb-think`.

### Research

**Purpose:** synthesize what mattered when the operator went looking.

**Required frontmatter:** `date`, `topic`, `source`.

**Required body sections:** question, sources, findings, implications, limits,
recommended next move.

**Privacy boundary:** cite or summarize approved sources; avoid raw transcript,
private community, customer/member, or provider exports unless explicitly
sanitized.

**Severity:** warning.

**Route:** `mb-think`.

### Bet

**Purpose:** frame a time-boxed wager with appetite, metric, deadline, evidence,
and a review path.

**Required frontmatter:** existing bet schema, including status, opened,
deadline, appetite, hypothesis, metric, target, links, public flag, channels,
and tags.

**Required body sections:** why now, success/failure signals, kill or
double-down rule, execution plan, review notes.

**Optional frontmatter:** `stage` and `commitment`. Neither is written by
default; a bet without them validates exactly as before.

- `stage` is one of `tuning`, `working`, `ongoing`, `done`, `cut`. It sits
  beside the lifecycle `status` (`open`, `paused`, `closed`, `canceled`) and
  does not replace it. An unknown value is an error. `done` or `cut` on an
  `open` or `paused` bet, or `tuning`, `working` or `ongoing` on a `closed` or
  `canceled` bet, is a warning.
- `commitment` is the one thing this bet does on a schedule, and the proof it
  happened. `action` (plain words) is required, `cadence` is required (`daily`,
  `weekdays` or `weekly`), `evidence` is required (the kind of proof: `url`,
  `commit`, `send_id`, `file` or `other`), and `owner` is optional (an agent or
  a person; unlike the bet-level `owner` it is not a team file reference).
  Anything missing or outside those values is an error. One commitment per bet.
  Recording or checking each day's evidence is not part of this contract yet.

```yaml
stage: working
commitment:
  action: "Send one outreach message to a past customer"
  cadence: weekdays
  owner: outreach-agent
  evidence: send_id
```

`mb status --json` reports `stage` (empty string when absent) and `commitment`
(`null` when absent) on each bet item.

**Privacy boundary:** use public-safe summaries for customer, finance, or
provider evidence.

**Severity:** warning for body gaps; existing frontmatter errors stay errors.

**Route:** `mb-bet`.

### Push

**Purpose:** coordinate a bounded ship motion: launch, drop, challenge, promo,
nurture, outreach, event, announcement, round, or wave.

**Required frontmatter:** existing push schema: type, slug, kind, status,
health, goal, owner, audience, offer, promise.

**Required body sections:** goal, audience, channel, assets, approval gates,
timeline, outcome/review plan.

**Privacy boundary:** provider refs and campaign ids can be safe; raw account
exports, spend authority, secrets, and customer contact lists are not.

**Severity:** warning for body gaps; existing schema errors stay errors.

**Route:** `mb-start` for routing, then a supported route such as `mb-ads`,
`mb-organic`, `mb-site`, or `mb-end`.

### Playbook Run

**Purpose:** record one execution of a reusable recipe for a push.

**Required frontmatter:** existing playbook-run schema: type, status, push,
platform, provider, provider boundary, trigger, resource, approval, state,
validation, linked outcomes.

**Required body sections:** operator choice, fork points, manual steps,
approval evidence, validation, outcome link.

**Privacy boundary:** no tokens, raw provider exports, customer lists, spend
mutation, publishing, or account writes without an accepted provider rail.

**Severity:** warning or error depending on the provider boundary.

**Route:** `mb-start` for routing. For channel work, use a concrete supported
route such as `mb-ads`, `mb-organic`, `mb-site`, or `mb-end`.
`google-ads-search-launch` remains draft/manual behind `mb-ads`; retired
`ship-bet` and `weekly-review` are not routes.

### Log

**Purpose:** keep time-bound observations, outcomes, retros, and session notes
that should inform future Sense passes.

**Required frontmatter:** `date`.

**Required body sections:** what happened, evidence, outcome, next action,
linked files.

**Privacy boundary:** durable synthesis, not raw transcript dumps or private
account exports.

**Severity:** warning.

**Route:** `mb-end`.

### Documents

**Purpose:** hold durable artifacts that do not belong in a more specific
primitive.

**Required frontmatter:** `title`.

**Required body sections:** purpose, owner/audience, source context, status,
next action.

**Privacy boundary:** documents may be public-safe or private; mark restricted
material and keep secrets out.

**Severity:** warning.

**Route:** `mb-think` unless a concrete supported route such as `mb-site`,
`mb-organic`, `mb-ads`, or `mb-end` matches the artifact.

## JSON Shape

`mb validate --json` and `mb status --json --peek` expose file contracts as:

```json
{
  "file_contracts": {
    "schema_version": "1.0",
    "summary": {
      "active_contracts": 1,
      "deferred_contracts": 10,
      "findings": 1,
      "routes": {"mb-think": 1}
    },
    "findings": [
      {
        "code": "file_contract_missing_section",
        "contract_id": "offer",
        "path": "core/offer.md",
        "section": "next_step",
        "owner_message": "Your offer does not yet tell a qualified buyer what to do next.",
        "recommended_route": "mb-think",
        "approval_required": true
      }
    ]
  }
}
```

Status ranking may turn those findings into a next action, but hard blockers
still win first: package updates, runtime mismatch, schema errors, repair
blockers, unsafe provider operations, and approval gates.

## Future Work

Future contract-enforcement slices and workflow migrations should plug into
this contract system. They should not revive `ship-bet` or `weekly-review`,
invent new route names, or define parallel file-shape language in skill prose.
