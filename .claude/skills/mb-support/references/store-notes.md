# Where the provider already holds support

Some businesses already keep policies, knowledge and chats in their store or
helpdesk. Then the repo is not the home of that knowledge; it points to it.

## Shopify store

Common shape, read from the store's own surfaces:

- **Policies:** the store's policy pages (refund, shipping, privacy, terms,
  contact), plus pages such as returns, care, sizes. Read them from the store,
  never from a copy.
- **Knowledge Base app:** facts and question-and-answer pairs held as store data.
  Shopify's Messaging and Inbox chat AI answers from it.
- **Messaging and Inbox:** the chat channel and its conversations.
- **Flow:** alerts and routing the store already runs.
- A business may have no returns or helpdesk app: returns are then the refund
  policy plus a returns page.

### What this means for the skill

- **No second knowledge base.** The Knowledge Base already exists as store data
  and the chat AI answers from it. Knowledge work is keeping that base true and
  consistent with the policies: find answers that contradict a policy page, are
  out of date or have gaps. Do not write a parallel set of articles in the repo
  for the same facts. The repo still holds money rules, what an agent may promise,
  escalation and the case log.
- **Conversations are customer data.** Read them in the store when the owner has
  granted that access; never copy bodies, names or addresses into the repo.
  Orders are often denied to agents by design; if so, work from the case line
  and ask the owner.
- **Writes ask.** Any change to a knowledge-base entry or to the chat AI's
  wording or persona asks the owner first: prepare the exact text, ask once.
- **Verify handoffs.** Find out where a chat handoff goes (which inbox, which
  person, what alert) and test that it arrives. Do not assume it. Record the
  answer in `policies.md` under escalation.
- **Keep tests out of the inbox.** An agent's test conversation lands in the real
  inbox. Avoid test chats; if one is needed, mark it clearly as a test (a tag
  or a fixed opening line) and tell the owner so it can be cleared.
- **Gaps are logged, not guessed.** An app the agent has no read access to (such
  as a reviews app) is a gap: log it in the weekly review with what it blocks.

## Store-specific notes (add below)

<!-- STORE-NOTES: more facts from live stores go here. Generic only: no store
names, no customer data, no keys. Remove this comment line when a note is added. -->
