# Source Ingestion Privacy Rail

Use this before reading transcripts, authenticated community content,
connected-provider recordings, cloud-drive files, call notes, exported chats,
or mixed private/business sources into the business record.

The goal is to get useful signal without copying raw private material into git.
Raw sources are evidence. Durable output is synthesized research, decisions,
proof candidates, push inputs, logs, or stale-source cleanup notes.

## Triggers

- "mine these transcripts"
- "ingest community posts"
- "process call recordings"
- "use these Drive files"
- "look through provider exports"
- "some of this account is personal/private"
- "find proof or audience language in member/customer content"

Public web research and public YouTube transcript mining still need synthesis,
but use this full rail when the source may contain private, restricted, mixed,
customer, member, finance, legal, credential, or account-specific material.

## Workflow

1. **Inventory before content.** List source type, private location/provider,
   owner/account, access posture, business reason, skip rules, allowed use, and
   expected durable destination. Keep private paths and account names in
   ignored scratch.
2. **Review a manifest.** Use metadata first: safe label, title or sanitized
   title, date/date range, type, provider, owner/account category, privacy
   posture, allowed/skip decision, read reason, and destination. Do not include
   raw comments, transcript excerpts, customer details, account ids, or private
   URLs in public artifacts.
3. **Apply allow/skip filters.** Filter by account/workspace, source type,
   people, date range, topic, and permission. Skip personal accounts, unrelated
   clients, billing/legal/health/finance, private DMs, credentials, and anything
   outside the approved business reason.
4. **Read the smallest useful slice.** Prefer title-only search, manifests,
   excerpts, topic/speaker segments, or operator-approved files over full raw
   dumps.
5. **Route synthesized output.** Save findings into the right business
   artifact, not a raw source archive.

## Durable Routes

| Signal | Destination |
| --- | --- |
| Audience language, objections, jobs, market signal | `research/YYYY-MM-DD-<topic>-source-mining.md` |
| Accepted offer, audience, positioning, operations, or source-policy change | `decisions/` plus approved `core/` edits |
| Testimonial, win, result, case detail, or claim | `core/proof/` or offer proof as a proof candidate |
| Launch, ad, organic, page, email, or provider-action input | `pushes/<YYYY-MM-DD-slug>/` or a playbook |
| Session lesson, fulfillment note, or operating lesson | `log/` or `documents/`, sanitized |
| Old claim, retired angle, obsolete offer detail, or contradiction | `stale-source-cleanup.md` |
| Product friction or workflow gap | `mb issue draft` after public/private review |

## Proof Permission Gate

Treat wins, quotes, screenshots, and outcomes as proof candidates first.
Specific proof is not public proof until permission is recorded.

- Record offer linkage, outcome, timeframe, metric, typicality, and caveats
  when known.
- Use `permissioned_public: false` until the operator confirms public use.
- Do not place private quotes in ads, pages, public issues, docs, or examples
  before permission is explicit.
- If proof is useful internally but not public, keep that boundary visible and
  route public work to permission collection.

## Never Commit By Default

- raw transcripts;
- full chat exports;
- provider payloads;
- scrape dumps;
- CRM rows;
- customer/member names;
- private community content;
- DMs, emails, phone numbers, account ids, screenshots, credentials, or local
  paths;
- private proof quotes or testimonials before permission is recorded.

Raw transcription output belongs in OS temp or ignored scratch first. Commit
only synthesized findings unless the operator explicitly approves a short,
sanitized excerpt and the public/private boundary is safe.

## Handoff Shape

```text
Source inventory reviewed: <count and categories>.
Allowed sources: <safe labels>.
Skipped sources: <count and generic reasons>.
Content read: <smallest useful slice>.
Durable output proposed: <research/decision/proof/push/log/issue>.
Private evidence kept out of git: yes.
Permission gates: <proof/public quote/customer data/account boundaries>.
Next approval needed: <read more, codify, collect proof permission, stale-source cleanup, checkpoint>.
```

This rail does not make a provider supported. Connector availability is not
proof that Main Branch supports authenticated scraping, provider mutation, bulk
export, or background monitoring.
