---
type: educational
topic: stripe
status: draft
last-updated: 2026-05-08
---

# Stripe: payments as a rail, not the business record

Stripe is a payment provider. Main Branch should use it when the business job
needs to charge money, collect a deposit, or point a site at a payment page.

The repo should remember the offer, decision, push, page, and outcome. Stripe
processes the payment.

## When you need this

Use a Stripe rail when:

- an offer needs a checkout link;
- a minisite or landing page needs a payment call to action;
- a deposit validates demand;
- a push needs a simple conversion endpoint;
- a finance summary needs safe provider references.

## What to store in the repo

Safe, useful records:

- product or price IDs when they are not secret;
- payment link URL when it is intended to be public;
- offer slug and payment intent;
- thank-you page path;
- non-sensitive provider references;
- summary outcomes such as purchase count or revenue range when safe.

Do not commit secret keys, webhook secrets, customer records, raw payouts,
cardholder data, account exports, or private transaction rows.

## How it fits site work

For a simple Main Branch site, Stripe can be one conversion endpoint among
several:

- payment page;
- booking link;
- lead form;
- custom approved endpoint.

The operator picks the conversion kind based on the offer. The site should not
pretend every business action is a payment if the real next step is a call,
lead form, or manual approval.

## What Main Branch does not claim

Main Branch does not claim full Stripe business automation today. Treat Stripe
as a provider rail with explicit operator approval around money movement,
customer contact, account mutation, and sensitive data.

Main Branch also does not replace bookkeeping, tax, legal, or compliance
review. Keep raw financial data out of shared repos unless a public decision
and access boundary say otherwise.
