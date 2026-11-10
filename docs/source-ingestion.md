# Source Ingestion Privacy Rail

Use this workflow when transcripts, authenticated community content, connected
provider recordings, cloud-drive files, call notes, or exported chats may become
business memory.

The goal is to mine useful signal without copying raw private material into
public docs, GitHub issues, code repos, or agent-visible contexts that do not
need it. Raw sources are evidence. Durable Main Branch output is synthesized
research, decisions, proof candidates, push inputs, logs, or stale-source
cleanup notes.

## How This Fits Where Data Lives

The current storage rule is [where data lives](../.claude/skills/mb-setup/references/where-data-lives.md).
The business repo is the team's private memory, for the team and its agents
only, so real material (recordings, P&L, reviews, real examples) belongs
there. This rail does not forbid that. It is the method for the cases where
more care is needed:

- **Large datasets and full exports:** not in the hub, because commits are
  never deleted. Inventory, filter and keep the synthesis.
- **Customers' customers' data and sensitive categories** (health, date of
  birth, ID photos, signatures, bank details): production systems only,
  encrypted. Never copy them into the hub; inventory and synthesize instead.
- **Media and screen recordings:** on the tracker issue they explain.
- **Real books:** the ledger stays in the private bookkeeping vault per
  [`books.md`](books.md); the hub holds safe summaries.
- **Public docs, public issues and code repos:** never raw private material.
  Going down, it becomes an invented example of the same shape.

## When To Use This

Use this rail before reading source content from:

- meeting, webinar, sales-call, phone-call, voice memo, Loom, or video
  transcripts;
- authenticated community posts, comments, DMs, member wins, classroom
  discussions, or support conversations;
- Google Drive, Dropbox, Notion, CRM, call-recorder, calendar, email, or other
  provider exports;
- mixed personal/business accounts where some material must be skipped;
- any source that may contain customer/member data, private proof, credentials,
  account names, billing, legal, health, finance, or internal team context.

Public web research, public YouTube transcript mining, and operator-pasted
snippets still need synthesis and copyright care, but they do not need the full
manifest workflow unless the source contains private or restricted material.

## Step 1: Inventory Before Content

List sources before opening or transcribing content. The inventory can live in
ignored local scratch space when it names private paths, provider accounts, or
people. Commit only a sanitized version when it is useful as public evidence.

| Field | Purpose |
| --- | --- |
| Source type | Transcript, authenticated community, Drive file, CRM export, call recording, chat log, provider manifest. |
| Location | Private path, provider UI, connector query, or operator-supplied file. Keep private locations out of public artifacts. |
| Owner/account | Which business, account, workspace, or operator owns the source. Use generic public labels. |
| Access posture | Public, team private, restricted, local only, mixed account, or unknown. |
| Business reason | Offer research, proof review, content mining, workflow improvement, fulfillment, support, or stale-source check. |
| Skip rules | Accounts, folders, date ranges, people, channels, tags, topics, or source types to exclude. |
| Allowed use | Internal synthesis, proof candidate, public quote after permission, push input, decision evidence, or do not use. |

If the source set is mixed or ambiguous, stop at inventory and ask the operator
to approve allow/skip filters before content reads.

## Step 2: Manifest-First Review

Create or request a manifest before opening raw content. A manifest is metadata
only: enough to decide what to read, not the source itself.

Good manifest fields:

- source id or safe short label;
- title or sanitized title;
- source type and provider;
- date or date range;
- duration, file size, or item count when useful;
- owner/account/workspace category;
- privacy posture;
- allowed/skip decision;
- reason for reading or skipping;
- expected durable destination.

Avoid manifest fields that expose private value by themselves: full names,
emails, phone numbers, account ids, exact provider account names, private
community URLs, raw comments, transcript excerpts, credential material, or
customer-specific details.

## Step 3: Allow And Skip Filters

Use explicit filters before content reads.

| Filter | Examples |
| --- | --- |
| Account/workspace | Only the business workspace; skip personal or unrelated client accounts. |
| Source type | Include sales calls and webinar chats; skip billing, legal, support inbox, or private DMs. |
| People | Include operator-owned recordings; skip unrelated customers, team members, or family/personal contacts. |
| Date range | Include the launch window; skip older sources unless stale-source cleanup needs them. |
| Topic | Include offer/audience/proof language; skip credentials, billing, health, legal, HR, or finance details. |
| Permission | Include internal proof candidates; skip public testimonial usage until permission is recorded. |

When a source fails a filter, record the skip reason in private notes or a
sanitized manifest. Do not read it just because a connector can access it.

## Step 4: Read The Smallest Useful Slice

Read only the content needed for the decision. Prefer title-only search,
metadata manifests, excerpts, speaker/topic segments, or operator-approved
files over full raw dumps.

Do not commit to the hub, and never to a public repo, issue or doc:

- full chat exports, provider payloads, scrape dumps, or CRM rows (large
  datasets);
- gated-community content copied in bulk from authenticated spaces;
- credentials, local paths, or customers' customers' data and sensitive
  categories;
- private proof quotes or testimonials used publicly before permission is
  recorded;
- copied source material that would make the repo a shadow database for another
  provider.

A real recording or transcript that the team needs can live in the private hub
under the where-data-lives rule. For anything larger or more sensitive, write
raw output to OS temp or ignored local scratch first and commit only
synthesized findings. A short excerpt may be committed when the operator
approves it and it is sanitized first. No approval lets credentials, sensitive
categories or customers' customers' data into a commit.

## Step 5: Route Durable Output

Route synthesized output by business use:

| Signal | Durable destination |
| --- | --- |
| Audience language, objections, jobs, market signal | `research/YYYY-MM-DD-<topic>-source-mining.md` |
| Accepted change to offer, audience, positioning, operations, or source policy | `decisions/YYYY-MM-DD-<slug>.md` plus approved `core/` edits |
| Testimonial, win, result, case detail, or claim | `core/proof/` or offer-specific proof as a proof candidate with permission fields |
| Launch, ad, organic, page, email, or provider-action input | `pushes/<YYYY-MM-DD-slug>/` or a playbook, with source limits noted |
| Session lesson, fulfillment note, or internal operating lesson | `log/` or `documents/`, sanitized |
| Old claim, retired angle, obsolete offer detail, or source contradiction | `/mb-think` stale-source cleanup |
| Product friction or workflow gap | `mb issue draft` or a public-safe GitHub issue after review |

## Proof Permission Gate

Specific proof is not public proof until permission is recorded. When mining
private or authenticated sources:

- classify wins, quotes, screenshots, and outcomes as proof candidates first;
- record offer linkage, outcome, timeframe, metric, typicality, and caveats
  when known;
- use `permissioned_public: false` until the operator confirms public use;
- do not place private quotes in ads, pages, public issues, docs, or examples
  before permission is explicit;
- if proof is useful internally but not public, keep that boundary visible in
  the proof file and route public work to permission collection.

This gate complements MoneyPath proof-quality facts and the `/mb-start` route
for public-marketing proof collection.

## Stale-Source Handoff

Use this ingestion rail to inventory and filter source material. Use
[`stale-source-cleanup.md`](../.claude/skills/mb-think/references/stale-source-cleanup.md)
after a specific stale claim, source, offer detail, proof usage, or angle is
named.

Do not turn stale-source cleanup into broad transcript ingestion. Do not turn
source ingestion into broad reconciliation across every current-truth file
unless the operator accepts that cleanup scope.

## Provider Boundary

This rail does not make a provider supported. It defines how to handle source
material when the operator has already provided access or a runtime connector
is available.

Provider-specific support still needs its own decision, setup path, smoke
evidence, approval gates, privacy handling, and fallback. Connector availability
is not proof that Main Branch supports authenticated scraping, provider
mutation, bulk export, or background monitoring.

## Handoff Shape

Use this summary when handing work back to the operator:

```text
Source inventory reviewed: <count and categories>.
Allowed sources: <safe labels>.
Skipped sources: <count and generic reasons>.
Content read: <smallest useful slice>.
Durable output proposed: <research/decision/proof/push/log/issue>.
Large or sensitive raw material kept out of git: yes.
Permission gates: <proof/public quote/customer data/account boundaries>.
Next approval needed: <read more, codify, collect proof permission, stale-source cleanup, checkpoint>.
```

The operator should know what was read, what was skipped, where the synthesis
will land, and what private material stayed out of durable public history.
