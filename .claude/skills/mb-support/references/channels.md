# The channels register

`core/support/channels.md` lists every place a customer can reach the business.
Each business names its own channels; the list is not fixed. Voicemail, text and
community chat below are examples only.

```markdown
# Support channels

| Channel | Where it lives | Who owns replies | Read route | Read or reply |
|---|---|---|---|---|
| email | the shared support inbox | the owner | `mb connect` mail read | read; reply asks |
| chat | the store's Messaging and Inbox | the owner | store access the owner granted | read; reply asks |
| voicemail | the phone provider's inbox | the owner | none | the owner logs by hand |
| text | the business phone's messages | the owner | none | the owner logs by hand |
| community chat | the group the business runs | the moderator role | none | read only; reply asks |
```

## Columns

- **Channel**: the name the business uses.
- **Where it lives**: the provider or app that holds the conversations.
- **Who owns replies**: a role label (owner, support lead, moderator), never
  "the agent". Prefer the role over a person's name, so no private identity is
  committed.
- **Read route**: how the agent reads it (an `mb connect` provider, a granted
  store access). Write `none` if there is no way to read it.
- **Read or reply**: what the agent may do there. Reading is one permission;
  replying is another and always asks (see "Always ask" in SKILL.md).

## A channel with no read route

The agent cannot see it, so the owner logs its cases by hand and the gap is
stated in every check and weekly review: "voicemail: no read route, last logged
by hand on <date>". A channel with no read route is never treated as no
messages.
