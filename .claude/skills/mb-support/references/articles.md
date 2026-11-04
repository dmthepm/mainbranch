# Help articles

A help article answers "how do I do this". Marketing pages answer "why"; link
both ways. Every article has one job, and every fact has one home.

Articles are for customers and public: no names, no order detail, nothing the
policy marks private. Words about money go to the owner for a yes.

## One file per article

`core/support/articles/<slug>.md`, with:

```yaml
title: Track your order
job: Tell a customer where to find their order status and what to do if it is late.
owner: <who answers for it>
checkedAgainst: <the product or provider version, date or commit, the facts were read at>
reviewBy: 2027-01-15
topic: orders
```

`job` is one plain sentence. It is the article's whole reason to exist.
`checkedAgainst` is a thing a person can look at again, not "recently".

## The shape

In this order. Skip a section only when it has nothing true to say.

1. **Short answer.** Two to four sentences a customer can act on without reading
   further.
2. **Where it is.** The route as it shows in the product or the provider, with
   button and field text copied from the source.
3. **Steps.** Numbered, one action each. Steps in a provider's product come from
   the provider's own pages.
4. **What goes wrong.** The states and messages a customer can see and what each
   means. Name the screen, not a cause you guessed.
5. **When to tell us.** The cases that need a person, and the public support
   address. Never a customer's address in a public place.
6. **Sources.** Provider pages only. Links to your own pages go in the text.

Never promise what the business does not control, such as where a provider
delivers an email. Promise only what the business does.

## One fact, one home

Keep `core/support/articles/homes.md`: a table of each fact and the one article
that owns it.

```markdown
| Fact | Owning article |
|---|---|
| How long a refund takes to show | refunds |
```

Every other article links to the owner and does not restate the fact. Add the
row in the same change that first states the fact.

Only required disclosures may repeat, such as a legal line, and each is listed
under `## Allowed repeats` in `homes.md` with the reason. Nothing else.

## Duplication check

Before asking the owner to approve a new or changed article, compare it with the
others by reading. It fails when:

- two articles share a sentence of 8 or more words, after lowercasing and
  stripping punctuation;
- two articles have the same section title, or near the same;
- two articles have the same job.

Fix a hit in the article that does not own the fact. Narrow or retire an older
article the new job swallows, in the same change.

## Upkeep

When a product or provider changes something an article quotes, re-read the
source, update `checkedAgainst`, move `reviewBy`. The weekly review lists articles
past `reviewBy`. Retired claims (a price line, a promise the business stopped
making) are removed from every article, not just one.

## Who approves

The agent drafts. The owner approves the words, and anything about money gets
the owner's explicit yes. A public change is a draft first; going live is the
owner's decision.
