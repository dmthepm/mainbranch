---
type: decision
date: 2026-11-03
status: accepted
topic: Support chat is a primary channel
linked_decisions:
  - decisions/2026-05-23-support-chat-rail-and-handoff-boundary.md
  - decisions/2026-05-13-provider-cli-api-wrapper-boundary.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
linked_docs:
  - docs/compatibility.md
participants: [Devon, Claude]
tags: [support, chat, email, cases, shopify, privacy]
supersedes:
  - decisions/2026-05-23-support-chat-rail-and-handoff-boundary.md
---

# Support Chat Is A Primary Channel

## Decision

Chat is a primary helpdesk channel, not a narrow front door. This supersedes
the May decision that kept chat to a front door that answers from approved
knowledge and hands off by email.

Chat and email are both case channels. Whatever the channel, a customer
request is one case in the same case log, with the same promises, due dates,
send checks and owner approvals. `/mb-support` is designed that way: the
channel is a column, not a separate process.

## What stays the same

- Main Branch does not host an inbox, a chat product or a customer-data
  warehouse. The business's own tools (an inbox, a chat widget, a store's
  messaging app) hold conversations.
- Customer data stays in the system that holds it. The repo carries case ids,
  dates and proof references, never message bodies, addresses or names.
- Messaging a customer, refunds and spend ask the owner first.
- Regulated data needs the stricter gates in the May decision; those gates are
  kept.
- Support claims need adapter code, docs and smoke evidence for the exact
  surface claimed. `/mb-support` is a draft.

## Where knowledge and chats live

A provider may be where the knowledge and the chats live. A Shopify store's
own apps (messaging and inbox, a knowledge-base app, policy pages) can hold
both. Then:

- the skill reads policies and knowledge from the source and does not keep a
  second copy in the repo;
- the repo holds what the provider cannot: money rules, what an agent may
  promise, escalation, and the case log;
- reading conversations is customer data and stays in the provider.

## Consequences

- No "narrow front door" limit on chat in docs or skills.
- Handoff routing for chat is verified for each business, not assumed.
- A business may still choose a heavier helpdesk; the case log works beside it.
