---
type: educational
topic: cal-com
status: draft
last-updated: 2026-05-08
---

# Cal.com: booking calls without making scheduling the business brain

Cal.com is a scheduling rail. It helps someone book a call, consultation,
fitting, onboarding session, or sales conversation.

Main Branch treats booking tools as provider rails around the business repo,
not as the source of the business record.

## When you need this

Use a booking rail when a push, offer, site, or fulfillment process needs a
scheduled appointment:

- sales calls;
- discovery calls;
- consults;
- onboarding sessions;
- fittings or appointments;
- customer interviews.

The durable Main Branch record should still live in the repo: the offer, the
push, the page, the playbook, the outcome, and the decision about why booking
is the right conversion path.

## What to store in the repo

Safe, useful records:

- booking link URL;
- event type name;
- offer or push that uses the booking link;
- tracking or thank-you page plan when relevant;
- non-secret provider reference.

Do not commit API keys, OAuth tokens, customer records, calendar exports, or
private attendee details.

## How it fits site work

A Main Branch site or minisite can point its primary call to action at a booking
URL when the conversion goal is "schedule." The repo should explain the choice:

- why this offer needs a call;
- which page sends people to the booking link;
- what happens after the appointment is booked;
- which outcome file records the result later.

## What Main Branch does not claim

Main Branch does not claim shipped Cal.com account automation today. Treat
Cal.com as a useful external booking rail unless a current CLI/provider check
states a specific automated path is ready.
