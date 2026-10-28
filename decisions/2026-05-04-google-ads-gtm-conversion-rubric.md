---
type: decision
date: 2026-05-04
status: accepted
topic: Google Ads, Google Tag Manager, and conversion tracking rubric
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/279
  - https://github.com/dmthepm/mainbranch/issues/273
  - https://github.com/dmthepm/mainbranch/issues/89
participants: [Devon, Codex]
tags: [v0-4, google-ads, gtm, conversion-tracking, integrations, sites]
---

# Google Ads, GTM, and Conversion Tracking Rubric

## Decision

Main Branch-generated landers and sites that are intended for paid traffic
must use one canonical measurement shape:

- a Google Tag Manager web container as the default tag surface;
- Google Ads conversion actions mapped from a small, stable Main Branch event
  vocabulary;
- a Conversion Linker or equivalent Google tag behavior configured in GTM;
- explicit consent/privacy posture before paid launch;
- verification evidence before an agent recommends that traffic is ready.

GTM is not mandatory for every generated site. It is mandatory for a
Main Branch offer launch path once the operator selects paid traffic,
analytics-driven iteration, retargeting, enhanced conversions, or more than one
marketing tag. A content-only site can ship without GTM and add it later.

The full rubric lives in
[docs/google-ads-gtm-conversion-rubric.md](../docs/google-ads-gtm-conversion-rubric.md).

## Why This Exists

The v0.4 offer launch loop needs trustworthy measurement before it can launch
ads, interpret results, or recommend iteration. Without a shared rubric, each
site or ads agent would invent its own event names, conversion actions, consent
posture, and verification checklist.

This decision keeps the boundary clear:

- `mb` owns deterministic readiness facts, local/provider metadata, validation,
  and repair hints.
- `/mb-site`, `/mb-ads`, and `/mb-start` own judgment, handoff, and operator
  approval prompts.
- Google Ads, GTM, Cloudflare, and consent tools remain external provider
  state unless and until a future connector proves safe API behavior.

## Canonical Shape

For paid-traffic landers and sites:

1. One business repo maps to one business/account boundary. Do not reuse a
   GTM container or Google Ads conversion customer across unrelated businesses.
2. Use one GTM web container per site and environment. A production site and a
   preview/staging site should not share live conversion actions.
3. Use GTM to load the Google tag, Google Ads conversion tags, GA4 tags if
   selected, Conversion Linker, consent defaults/updates, and any future
   third-party tags.
4. Generated site code pushes Main Branch events to `window.dataLayer`.
   Provider-specific conversion labels live in GTM/Ads/provider metadata, not
   inside ad or site copy.
5. Cloudflare Pages/static sites inject GTM through build-time configuration
   or environment substitution, not by committing live IDs into public examples
   or reusable templates.
6. Cloudflare Google Tag Gateway is the preferred first-party transport when
   the domain is already on Cloudflare and the operator explicitly enables it.
   Server-side GTM is a later upgrade for higher spend, material EEA/UK volume,
   or multi-platform server event needs.
7. Google Ads conversion action settings should keep one primary optimization
   goal per new campaign when possible, use data-driven attribution when
   available, count leads/calls once, count purchases every time, and treat
   click identifiers such as `gclid`, `gbraid`, and `wbraid` as private
   operational data rather than durable public repo content.

## State Boundary

Committed business repos may contain non-secret identifiers and plans when they
are useful for agents and operators:

- GTM container ID, GA4 measurement ID, Google Ads customer ID, and conversion
  action resource names or labels;
- selected site/domain/environment;
- expected conversion events and primary/secondary status;
- consent posture and policy links;
- sanitized conversion import schemas and summaries.

Committed public templates, docs, fixtures, and examples must use placeholders.
They must not include real account IDs, conversion labels, customer data,
conversion values, upload rows, API tokens, OAuth refresh tokens, service
account JSON, customer lists, or hashed personally identifiable information.

Local/provider state belongs outside git:

- OAuth tokens, API keys, service-account JSON, developer tokens, and refresh
  tokens;
- raw leads, CRM exports, booking records, customer lists, uploaded conversion
  rows, and enhanced-conversion user identifiers;
- GTM draft workspaces, unpublished container versions, account permissions,
  and Google Ads billing/campaign state;
- local verification captures that include account IDs, user data, or private
  URLs.

## Event Vocabulary

Generated sites should push these event names exactly when the matching user
action exists:

| Main Branch event | Use |
|---|---|
| `mb_cta_click` | CTA clicked, before an outcome is known. |
| `mb_form_start` | Lead/signup form interaction began. |
| `mb_lead_submit` | Lead form submitted successfully. |
| `mb_calendar_click` | User clicked an outbound booking/calendar URL. |
| `mb_booked_call` | Booking provider or thank-you page confirms a call. |
| `mb_email_signup` | Email/newsletter signup confirmed. |
| `mb_purchase` | Purchase confirmed. |
| `mb_deposit` | Deposit or paid application fee confirmed. |
| `mb_offline_conversion_ready` | A local offline conversion record is staged for operator review. |

Events must use lower snake case. Event payloads must avoid PII by default and
should use stable non-secret keys such as `mb_site_id`, `mb_offer_id`,
`mb_event_id`, `mb_conversion_kind`, `mb_destination`, `currency`, and
`value_basis`. Do not push email, phone, full name, address, raw order notes, or
hashed customer identifiers unless the operator has explicitly approved
enhanced conversions and accepted the required Google terms.

## Conversion Action Naming

Google Ads conversion actions should be named:

```text
MB - <Offer> - <Action> - <Environment>
```

Examples:

- `MB - Diagnostic Call - Lead Submit - Prod`
- `MB - Diagnostic Call - Booked Call - Prod`
- `MB - Workshop - Purchase - Prod`

Primary conversions are the actions the campaign should optimize toward.
Secondary conversions are diagnostics. For common lander shapes:

| Lander goal | Primary conversions | Secondary conversions |
|---|---|---|
| Lead form | `mb_lead_submit` | `mb_form_start`, `mb_cta_click` |
| Booked call | `mb_booked_call` | `mb_calendar_click`, `mb_lead_submit` |
| Purchase/deposit | `mb_purchase` or `mb_deposit` | `mb_cta_click`, `mb_form_start` |
| Newsletter/signup | `mb_email_signup` | `mb_cta_click` |
| Offline sales | imported offline conversion action | `mb_lead_submit`, `mb_booked_call`, `mb_offline_conversion_ready` |

## Consent and Privacy Guardrails

Main Branch does not provide legal advice. The rubric must still force an
operator decision before paid launch:

- Sites with EEA/UK users or remarketing/personalization must implement Consent
  Mode with `ad_storage`, `analytics_storage`, `ad_user_data`, and
  `ad_personalization` signals through a consent banner or consent management
  platform.
- Enhanced conversions require explicit operator approval and acceptance of
  Google's customer data terms before any user-provided data is collected or
  uploaded.
- Offline conversion imports must preserve user consent status and must be
  reviewed by the operator before upload.
- A US-only informational banner and privacy policy can be enough for simple
  non-personalized measurement, but the site must not imply that Main Branch
  decided legal compliance for the operator.

## Verification Gate

Before `/mb-site`, `/mb-ads`, or `/mb-start` treats a paid-traffic launch as
measurement-ready, a future implementation must be able to report:

1. the business repo declares which GTM container, site, environment, and
   Google Ads conversion customer are in scope;
2. the built site includes the GTM script in `<head>` and the noscript fallback
   immediately after `<body>` when GTM is enabled;
3. the GTM container URL resolves;
4. the built page pushes the expected `mb_*` dataLayer events during a browser
   smoke;
5. GTM Preview/Tag Assistant or a provider API check confirms the expected tags
   fire for those events;
6. Google Ads conversion actions exist, are primary/secondary as planned, and
   point at the expected event triggers;
7. consent posture is explicit and compatible with the selected market;
8. the operator has approved any account mutation, GTM publication, enhanced
   conversion data use, offline upload, or paid campaign launch.

Static and browser checks can prove site instrumentation. They do not prove
that Google Ads attributed conversions. Provider diagnostics and delayed Ads
reporting remain separate evidence.

## Future CLI Contract

Future `mb connect`, `mb status`, and `mb doctor` work should report Google
measurement readiness without pretending a stored secret reference is health.
Core `mb connect` should prove Google credential and metadata readiness when
safe probes exist. A future Google Ads/GTM sidecar should own domain-specific
provider checks such as container contents, conversion action listing, GTM
workspace state, and Ads diagnostics. `/mb-site` should own static and browser
instrumentation checks against generated pages.
The desired states are:

- `missing` - no Google/GTM metadata or credential path is configured;
- `declared` - safe metadata exists, but credentials/provider state have not
  been checked;
- `unvalidated` - local credentials exist, but provider checks are unavailable
  or inconclusive;
- `ready_for_preview` - site instrumentation and GTM container resolution pass;
- `ready_for_operator_review` - conversion plan and provider state are present,
  but operator approval is still required;
- `ready` - all deterministic checks pass and operator approvals are recorded;
- `blocked` - an account, consent, publication, or verification issue prevents
  launch.

The CLI should expose `safe_to_share`, `summary`, `repair`,
`repair_command`, and `evidence` fields so skills can explain next actions
without leaking account details.

## What Main Branch Must Not Automate Yet

Main Branch must not automatically:

- create Google Ads accounts;
- accept Google customer data terms;
- publish GTM containers to Live;
- enable enhanced conversions;
- upload offline conversions or customer lists;
- mutate billing, budgets, keywords, ads, or campaigns;
- claim Google Ads/GTM automation is supported before API and runtime smoke
  evidence exists.

Agents may draft plans, config, naming, checklists, and operator-reviewed
artifacts. Mutating accounts and spending money require explicit operator
approval every time until a later decision changes that boundary.

## Review Triggers

Revisit this decision if:

- Google changes Consent Mode, customer data, or offline conversion
  requirements materially;
- Cloudflare Tag Gateway is no longer the preferred light first-party transport
  for Cloudflare-hosted sites;
- Main Branch adds a Google Ads/GTM connector that can safely inspect or mutate
  provider state;
- v0.4 offer launch needs a more specific campaign/ad-group naming standard.
