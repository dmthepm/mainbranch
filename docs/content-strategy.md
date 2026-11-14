# Content Strategy

Content strategy is the operating model for what a business wants to be known
for, where it publishes, which accounts speak, whose voice they use, what each
asset is trying to do, and how results feed back into the durable business record.

It is not a social-media template. Social is one distribution layer beside
blog, wiki, changelog, email, communities, partner channels, paid
amplification, and public conversations.

## Default Shape

Start simple. A solo operator can keep the whole model in one file:

```text
core/content-strategy.md
```

That file is the business-level strategy and index. It should answer:

- what the business wants to be known or recommended for;
- who the content is for;
- which offers, categories, and problems the content supports;
- the main pillars and point of view;
- what the business does not publish;
- the job each content asset can have: rank, teach, prove, compare, convert,
  announce, or start a conversation;
- the next strategy files, pushes, playbooks, and logs an agent should read.

Use the advanced layers only when the operator needs them.

```text
core/marketing/
  distribution-strategy.md
  channels/
    x.md
    linkedin.md
    reddit.md
    hacker-news.md
    email.md
  accounts/
    x-founder.md
    x-company.md
    linkedin-founder.md
    linkedin-company.md

core/people/
  founder.md
  operator.md
```

Do not copy the same strategy into every file. The business-level strategy
sets the shared direction; the other files specialize it.

## Frontmatter Contract

`mb validate` checks layered content strategy files when they exist. The simple
solo-operator path stays one file, but it should still identify itself:

```yaml
---
type: content_strategy
status: active
linked_strategy_layers: []
---
```

Use `linked_strategy_layers` to index optional layers from
`core/content-strategy.md`. The index is what `mb status --json --peek` turns
into normalized `content_strategy` facts for `/mb-start`, `/mb-status`, and a
future read-only dashboard. A dashboard should read those JSON facts instead of
parsing markdown.

Layer frontmatter:

| File | Required keys |
| --- | --- |
| `core/marketing/distribution-strategy.md` | `type: distribution_strategy`, `status` |
| `core/marketing/channels/<channel>.md` | `type: channel_strategy`, `status`, `channel`, plus freshness keys |
| `core/marketing/accounts/<platform>-<account>.md` | `type: account_strategy`, `status`, `platform`, `account`, `channel_strategy`, `voice_source`, plus freshness keys |
| `core/people/<person>.md` | `type: person`, `status` |

Valid strategy statuses are `draft`, `active`, `paused`, `needs-review`,
`stale`, and `archived`. Account `channel_strategy` should point to the
matching channel file. Account `voice_source` should point to
`core/people/<person>.md` when a person voice is used, or `core/voice.md` for
brand voice.

## Layer Contracts

| Layer | Path | Owns |
| --- | --- | --- |
| Business strategy | `core/content-strategy.md` | Recognition target, audience, pillars, content jobs, non-publishing rules, and links to the rest of the model. |
| Distribution strategy | `core/marketing/distribution-strategy.md` | How owned pages, blog, wiki, changelog, email, social, communities, partners, and paid amplification work together. |
| Channel strategy | `core/marketing/channels/<channel>.md` | Platform norms, fit, timing notes, content types, anti-spam rules, and update triggers. |
| Account strategy | `core/marketing/accounts/<platform>-<account>.md` | Audience, allowed topics, voice reference, cadence, content mix, CTA path, and offers/pages this account can point to. |
| Person voice and knowledge | `core/people/<person>.md` | How a founder/person sounds, what they believe, stories and proof they can draw from, and what agents must not fabricate. |
| Push execution | `pushes/<YYYY-MM-DD-slug>/push.md` | One bounded launch, distribution push, content sequence, announcement, or community participation plan. |
| Push playbook run | `pushes/<push>/playbooks/<playbook>.md` | The plan, approval state, provider boundary, manual steps, evidence, forks, and outcome links for one push. |
| Results log | `log/YYYY-MM-DD-content-distribution.md` | What happened, what language surfaced, what worked, what changed, and what should feed Sense next time. |
| Research | `research/YYYY-MM-DD-<topic>.md` | Source observations, outside research, platform notes, and open questions from when the operator went looking. |

`core/voice.md` remains the brand voice contract. `core/people/<person>.md`
holds person-specific source material that many accounts can reference.

## Distribution Is Not Publishing Automation

Main Branch can plan and draft distribution. It does not post, auto-DM,
auto-reply, spend money, mutate provider accounts, or schedule social content
unless a separate provider adapter has accepted docs, tests, approval gates,
and smoke evidence.

Channel and account files can record provider-native workflows, manual steps,
and candidate rails such as Postiz or Typefully. They should not claim support
that the engine has not proven.

## Weekly Planning

Recurring content work is a living operating loop, not a static template.
Before planning a week for one channel or account, read by reference:

```text
core/content-strategy.md
core/marketing/distribution-strategy.md
core/marketing/channels/<channel>.md
core/marketing/accounts/<platform>-<account>.md
core/people/<person>.md
recent pushes/
recent log/
current bets/
```

Then create or update the current push when the work has a named goal,
audience, timeline, or review moment. Use `pushes/<push>/posts/`,
`emails/`, `site/`, `playbooks/`, `reviews/`, `source/`, and `assets/` for
the artifacts that belong to that push.

Fast-changing channel playbooks or strategy notes should include a lightweight
freshness block:

```yaml
last_reviewed: 2026-05-12
owner: Operator
update_trigger: Platform norms, audience behavior, or distribution results changed.
source_links: []
```

The body should keep:

- recent learnings;
- what changed since last review;
- platform rules or norms that matter;
- what gets reviewed before publishing;
- what gets logged after publishing.

## Source And Learning Flow

Use this routing when content work creates new information:

- Source research and outside observations go to `research/`.
- Accepted strategy choices go to `decisions/` or the relevant `core/` file.
- Durable pillars, recognition targets, and asset jobs go to
  `core/content-strategy.md`.
- Platform rules go to `core/marketing/channels/<channel>.md`.
- Account-specific rules go to `core/marketing/accounts/<platform>-<account>.md`.
- Founder/person voice and reusable stories go to `core/people/<person>.md`.
- Specific execution goes to `pushes/<YYYY-MM-DD-slug>/`.
- Results, questions, and lessons go to `log/` or a push review log.

Do not turn comments, likes, saves, or scraped examples into proof claims by
themselves. They can be audience language, demand signal, objections, or
distribution learning. Proof belongs in `core/proof/` only when the claim is
approved and supportable.

## Offer And Recognition Dependencies

Offer clarity comes before content volume. Use
[`offer-sharpening.md`](offer-sharpening.md) when the content asks people to
believe or buy something and the audience, outcome, mechanism, proof, CTA, or
style is unclear.

Use `/mb-think` research-depth guidance before deep platform, audience, or
competitor research. Repo context can be enough for cleaning up an existing
strategy; public/source-backed research or structured approved-source
collection may be worth it before committing to a new channel, account voice,
campaign angle, or market position.

AI/search recognition work is related but separate. This model records what the
business wants to be known for and how owned/public distribution reinforces
that target. Site/wiki recognition checklists, entity pages, schema, and AI SEO
implementation belong to the recognition work tracked separately.

## Public / Private Boundary

Public examples may describe sanitized patterns. Do not commit raw DMs,
private customer/member data, account exports, unpublished partner strategy,
provider tokens, session cookies, private analytics, screenshots with account
details, or private local paths.

Commit approved summaries, decisions, strategy, public-safe source notes, and
links to safe provider handles. Keep sensitive source material in a private
repo, provider system, OS temp, or local scratch space.
