# Playbooks

Playbooks are attributed operating methods for repeatable business work.
They are not platform documentation, universal best practice, or hidden
automation authority.

Main Branch uses two related meanings:

- **Reusable playbook:** an engine or community recipe under
  `playbooks/<name>/playbook.md`. It describes a repeatable method, its
  defaults, its source, and the skills or checks it calls. Runtime shells such
  as `.claude/playbooks/<name>/SKILL.md` adapt that source for a specific
  runtime.
- **Push playbook:** a business repo run record under
  `pushes/<push>/playbooks/<playbook>.md`. It records what happened for one
  offer, push, launch, campaign, resource drop, or operating run.

The reusable playbook teaches the method. The push playbook proves what the
operator actually chose, approved, changed, and learned.

## Business Record

Playbooks should not trap durable learning inside a one-off run file. When a
run discovers something that changes the business, market, offer, audience,
proof, positioning, or conversion path, the agent should route that learning
back into the business repo's durable memory:

- `research/` for dated evidence, synthesis, source notes, and open questions;
- `core/offer.md` or `core/offers/<offer>/offer.md` for durable offer truth;
- `core/audience.md` or `core/offers/<offer>/audience.md` for buyer language,
  pains, objections, and decision criteria;
- `core/proof/` or `core/offers/<offer>/proof/` for approved claims,
  testimonials, proof angles, and typicality context;
- `core/content-strategy.md` or other strategy files when the discovery changes
  channel strategy, positioning, or launch cadence;
- `core/marketing/channels/<channel>.md`,
  `core/marketing/accounts/<platform>-<account>.md`, or
  `core/people/<person>.md` when the discovery changes platform rules, account
  strategy, person voice source material, stories, or fabrication boundaries;
- `decisions/` when the operator chooses a durable rule or tradeoff.

If the operator has not approved a core edit yet, the run record should include
a proposed-core-updates section with target files, proposed changes, evidence,
and approval status. The push playbook remains the run audit trail; core
remains the reusable business truth that future playbooks and skills read.

## Authority Layers

Treat playbook guidance as a stack of authority, not a flat rulebook:

1. **Official platform rules.** Provider docs, policies, field limits, and
   supported features are the source of truth for platform behavior. A Google
   Ads playbook should link to Google Ads Help for character limits, location
   targeting modes, policy surfaces, conversion imports, and asset types when
   it makes factual claims.
2. **Global platform guidance.** Main Branch can keep reusable guidance for a
   platform: provider boundaries, privacy posture, manual approval gates,
   common readiness checks, and durable run-record shape.
3. **Playbook opinion.** A playbook is a method with taste. It can prefer one
   setup over another for a specific use case, as long as it says why. For
   example, a small-budget offer-validation Google Ads playbook can keep AI
   Max and Final URL Expansion off because the method values query, copy, and
   URL control more than reach during the first proof run.
4. **Fork points.** A good playbook names where a reasonable operator might
   diverge. The fork should capture what changed, why, who approved it, and
   whether it changes the review bar.
5. **Run record.** The push playbook is the concrete audit trail: inputs,
   defaults used, forks taken, provider boundary, approval gates, evidence,
   manual steps, and outcome links.

This lets Main Branch be opinionated without pretending that every playbook
default is universally correct.

## Attribution

Reusable playbooks should preserve source and authorship when the method comes
from a person, team, community, transcript, research packet, or proven client
workflow. Attribution helps operators evaluate fit and helps contributors
ship real methods without flattening them into anonymous doctrine.

Good attribution answers:

- who authored or contributed the method;
- what source material or operating runs informed it;
- what type of proof exists: field notes, official docs, research synthesis,
  repeated internal use, customer result, or draft hypothesis;
- what is intentionally opinionated;
- what should be revalidated against current official docs before use.

Do not commit raw private transcripts, account data, customer details,
credentials, screenshots, or exact partner/customer strategy to public
playbooks. Summarize the reusable method and keep private source material in
private repos or local scratch space.

## Forking A Playbook

Forking is normal. A playbook is useful because it gives the operator a
starting stance, not because it removes judgment.

Record a fork when the operator changes:

- target audience, geography, or conversion path;
- provider settings that affect reach, spend, or policy risk;
- copy/creative defaults;
- approval gates;
- budget, review window, or success metric;
- execution tool or provider boundary.

The run record should state the default, the chosen fork, and the rationale.
That rationale becomes part of the business record and may later improve the
reusable playbook.

## Contribution Shape

Third-party or community playbooks can be bundled when they are public-safe and
fit the Main Branch state model. For example, a contributor's Dream 100 email
strategy can be represented as an attributed reusable playbook with its own
defaults, source notes, fork points, and run-record template. Operators can run
it exactly, fork it, or copy its structure into their own business repo.

A submitted playbook should make clear whether it is:

- a skeleton: intended shape, not yet executable as one coherent workflow;
- a draft: usable with manual operator judgment, still collecting evidence;
- a proven method: used repeatedly enough that the defaults are durable;
- deprecated: retained for history, not recommended for new runs.

Current validation focuses on push playbook run records under `pushes/`.
Reusable playbook taxonomy and attribution may become stricter as more
community methods are added.

## Content Playbooks And Freshness

Recurring content workflows should read the layered content strategy model by
reference instead of copying it into the playbook. A weekly X or LinkedIn
workflow can read `core/content-strategy.md`,
`core/marketing/distribution-strategy.md`,
`core/marketing/channels/<channel>.md`,
`core/marketing/accounts/<platform>-<account>.md`,
`core/people/<person>.md`, recent pushes, recent logs, and current bets before
drafting the queue.

If a content playbook depends on a fast-changing platform, keep a lightweight
freshness block: `last_reviewed`, owner, update trigger, source links, recent
learnings, and what changed since the last review. The block can live in the
channel or account strategy file, the reusable playbook, or the push playbook
run record depending on where the lesson belongs.

Do not use a playbook as hidden posting authority. Scheduling, publishing,
replying, DMing, spending, or account mutation stays manual or provider-native
until a separate adapter has accepted docs, tests, approval gates, and smoke
evidence.
