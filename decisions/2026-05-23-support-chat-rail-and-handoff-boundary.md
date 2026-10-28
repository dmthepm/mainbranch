---
type: decision
date: 2026-05-23
status: accepted
topic: Support chat rail and handoff boundary
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/615
  - https://github.com/dmthepm/mainbranch/issues/662
linked_decisions:
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-11-repo-setup-visibility-and-checks-model.md
  - decisions/2026-05-13-provider-cli-api-wrapper-boundary.md
  - decisions/2026-05-15-repo-owned-operating-memory.md
linked_docs:
  - docs/compatibility.md
  - docs/dependency-choices.md
  - docs/issue-drafting.md
  - docs/oss-operating-checklist.md
  - docs/source-ingestion.md
participants: [Devon, Codex]
tags: [support, chat, cloudflare, ai, handoff, privacy, integrations, hermes, shopify]
---

# Support Chat Rail And Handoff Boundary

## Decision

Main Branch should treat support chat as a narrow support-front-door rail, not
as a new helpdesk, inbox, automation suite, or generic AI app builder.

The planned default rail is a Main Branch-owned support-chat contract backed by
Cloudflare site infrastructure where it is smoke-tested:

```text
business repo knowledge -> mb sync/checks -> Cloudflare Worker + AI Search
  -> website chat/front-door widget -> email handoff + sanitized Slack alert
```

Main Branch owns the business-facing contract: approved knowledge sources,
provider readiness, sync/check commands, privacy gates, handoff policy, and
public-safe evidence. Cloudflare owns the site/runtime/search primitives.
Email remains the durable human handoff channel. Slack is a notification rail
only unless a specific business has a compliant Slack setup for the data being
sent.

Dify, Chatwoot, n8n-style workflow tools, Shopify support suites, and future
Hermes routing are not the generic default. They remain candidates or adapters
for specific situations:

| Surface | Current stance |
|---|---|
| Cloudflare Worker + AI Search | Planned default support-chat rail where smoke-tested. |
| Dify | Prototype or special-case AI app builder; not the curated default. |
| Chatwoot | Optional helpdesk rail when a business accepts an inbox/dashboard. |
| Gorgias / Intercom / Yuma-class Shopify tools | Shopify-specific fast lane, not the generic Main Branch default. |
| n8n-style tools | Glue behind the scenes only; not the support-chat product. |
| Hermes | Future orchestration/runtime target; no support claim until an adapter and smoke evidence exist. |

## Context

Main Branch is for normal business owners who need a curated stack they can
operate from business files in git. The product should not ask them to evaluate
and maintain every support, AI, inbox, and automation tool category.

The shape should match the existing dependency strategy:

- curate rails instead of connecting everything;
- prefer official provider surfaces;
- wrap providers only when Main Branch can make a business loop safer and more
  inspectable;
- keep secrets, raw transcripts, and customer data out of public repos;
- do not claim support before adapter docs and smoke evidence exist;
- leave an exit path.

The support-chat rail is similar to the bookkeeping decision: Main Branch does
not need to rebuild a full bookkeeping engine because hledger is the chosen
engine for that domain. Main Branch also should not rebuild a full customer
support platform. It should choose and wrap a narrow default rail, then provide
escape hatches for businesses whose vertical needs justify a heavier system.

## What Main Branch Owns

Main Branch should own the deterministic and durable parts:

- a support-chat config schema for business repos;
- an approved knowledge-source manifest;
- sync/check commands that can push public-safe knowledge into the configured
  provider;
- readiness states and repair guidance through the provider/connect model;
- privacy and regulated-data gates before launch;
- handoff policy for email, Slack, issues, and future adapters;
- transcript-ingestion rules that convert useful friction into sanitized issues,
  decisions, docs, tests, playbooks, or outcomes;
- public-safe launch evidence before any support claim.

The operator-facing language should be business-first: "website front desk,"
"approved answers," "handoff," "follow-up," and "support friction." Provider
names should appear only when setup, cost, credentials, support status, or a
provider-specific workflow matters.

## What Main Branch Does Not Own

Main Branch should not become:

- a hosted support inbox;
- a live-chat dashboard;
- a generic automation builder;
- a raw transcript store;
- a customer-data warehouse;
- a medical, legal, or financial advice bot;
- a Slack bot that posts sensitive conversation content by default;
- a Hermes support claim before the runtime adapter exists.

Support conversations are source material, not durable business truth. Durable
truth should be the sanitized artifact that results from support: an issue,
decision, playbook, test, status note, customer-safe summary, or operator
checkpoint.

## Default Cloudflare Rail

Cloudflare is the best default candidate because it is already the adopted
site/DNS/deploy rail for Main Branch and offers official Workers, storage,
search, AI, email, and deployment primitives. A thin Cloudflare implementation
keeps the support front door close to the website without adding a separate
operator dashboard.

The first supported rail should be intentionally small:

1. A website widget or embedded form sends a visitor question to a Worker.
2. The Worker retrieves relevant approved knowledge from a business-scoped
   search index.
3. The response answers only from approved sources and cites or records
   provenance where practical.
4. The Worker refuses or hands off on uncertainty, regulated questions,
   billing disputes, medical/legal/financial advice, account changes, or
   provider mutations.
5. Handoff sends an email to the configured team inbox and optionally sends a
   sanitized Slack alert.
6. `mb` can check readiness, sync approved knowledge, and report launch state.

This is not a commitment to a permanent custom chat application. It is a
commitment to a small default rail that can be replaced or bypassed if a
business needs a real helpdesk.

## Dify, Chatwoot, And Workflow Builders

Dify is a strong AI app and chatflow builder, but it introduces a separate
builder/dashboard surface. That makes it useful for prototypes, internal tools,
or special client cases, but a poor default for a curated business-owner stack.
Main Branch should not require Dify just to give a website a support front
door.

Chatwoot is the strongest open-source helpdesk candidate when a business wants
website chat, email, agents, inboxes, APIs, and self-hosting. It should be an
adapter choice for the moment a business accepts a support dashboard. It should
not be the default when the product requirement is email and Slack only.

n8n-style tools are useful glue, but the support-chat rail should not depend on
a broad workflow automation product. Use automation tools behind the scenes
only when a bounded, approved workflow needs them.

## Shopify Adapter Boundary

Shopify is likely a separate vertical doorway, not evidence against the
Cloudflare default.

For ecommerce businesses, order lookup, returns, exchanges, subscriptions,
discounts, customer accounts, and protected customer data can quickly make a
generic website chat rail the wrong tool. Gorgias, Intercom, Yuma, and similar
Shopify-native support tools may be the right fast lane for merchants who need
store-aware automation now.

Main Branch should treat those as Shopify-specific adapters. The support-chat
default can still own public policies, FAQs, and handoff. Store-aware actions
should require explicit Shopify permissions, protected-customer-data review,
operator approval gates, and separate smoke evidence before Main Branch claims
support.

## Regulated Data Boundary

Regulated businesses need a higher bar. Assume a visitor may enter sensitive
data even when the UI asks them not to.

The regulated version of this rail requires:

- a signed business associate or equivalent data-processing agreement for every
  processor that touches regulated data;
- product-specific coverage, not a generic security or compliance badge;
- minimum-necessary collection;
- no sensitive conversation bodies in Slack by default;
- retention, deletion, export, access-control, and audit-log expectations;
- conservative handoff for medical, legal, financial, billing, account, and
  crisis scenarios.

For healthcare workflows, Google Workspace may be the email handoff rail only
when the business has signed the applicable Google Workspace agreement and the
used functionality is covered. Third-party apps and add-ons are not covered by
Google Workspace's agreement just because email is. Slack should be treated as
sanitized notification-only unless the business has a Slack plan and agreement
that covers the exact data being posted.

## Hermes Boundary

Hermes remains a roadmap runtime and orchestration target. It may eventually
supervise support workflows, call packaged `mb` commands, route handoffs, or
host a richer support agent. That belongs in a Hermes adapter.

Until the adapter exists, Main Branch should say:

- Hermes support is planned or roadmap, not supported;
- `mb` remains deterministic and non-conversational;
- Hermes-specific routing belongs outside core `mb`;
- support claims require adapter code, docs, generated-file rules, and
  fresh-repo smoke evidence.

## Validation Before Support Claim

Before public docs describe the support-chat rail as supported, a PR should
include evidence for the exact surface claimed:

1. Current Cloudflare docs reviewed for the used products.
2. A safe test business/site repo configured without committed secrets.
3. Knowledge sync from approved repo/site files into the chosen search source.
4. Worker endpoint smoke with an allowed question, an uncertain question, and a
   handoff question.
5. Email handoff smoke to a safe test inbox.
6. Slack alert smoke that proves sanitization and excludes raw conversation
   bodies.
7. `mb` readiness/check output with public-safe status and repair guidance.
8. Privacy review showing no secrets, raw transcripts, customer data, or private
   local paths entered tracked files or public evidence.
9. Runtime/manual smoke if a skill or runtime adapter claims to operate the
   rail.

If the regulated-data path is claimed, add evidence for the relevant agreements,
product coverage, retention settings, access controls, and failure behavior.

## Sources

- Cloudflare AI Search: https://developers.cloudflare.com/ai-search/
- Cloudflare Workers AI data usage: https://developers.cloudflare.com/workers-ai/platform/data-usage/
- Google Workspace HIPAA compliance: https://knowledge.workspace.google.com/admin/compliance/hipaa-compliance-with-google-workspace-and-cloud-identity
- HHS business associate guidance: https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/
- Slack HIPAA: https://slack.com/trust/compliance/hipaa
- Chatwoot features: https://www.chatwoot.com/features
- Dify documentation: https://docs.dify.ai/
- Shopify protected customer data: https://shopify.dev/docs/apps/launch/protected-customer-data
