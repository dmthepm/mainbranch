# Setup: policies, money rules, and the clock

Do this once with the owner, in one sitting. Save nothing without approval.

## core/support/policies.md

Ask in order, and stop when each has a real answer:

1. Refunds: when, how much, within how many days, who decides.
2. Shipping: times, regions, what happens when a parcel is late or lost.
3. Returns and exchanges: what is free, what is not, how many per order.
4. What may an agent promise on its own, and what is always the owner's call?
5. Tone: how the business sounds, what it never says.
6. Escalation: which cases go to the owner at once (a complaint about safety,
   money disputes, press, legal threats, anything the agent cannot answer).
7. Which names stay private (a supplier, a partner) and what to say instead.

Where the business keeps a policy in a provider (a store's refund or shipping
page), do not copy it. Write:

```markdown
## Refunds
Source: the store's refund policy page, read with `mb connect` or the page URL.
Read it from there every time. If it disagrees with a rule below, stop and ask.
Extra rules the page does not hold: (anything the owner adds)
```

## core/support/money-rules.md

Ask the owner about every situation where money moves, and write the answer as a
rule with the payer named:

```markdown
# Money rules

| Situation | Who pays | Who acts | Agent may |
|---|---|---|---|
| Supplier misprint or damage | the supplier | the owner asks the supplier for a reorder | prepare the ask only |
| Customer changes size (first per order) | the business | the agent, after approval | prepare |
| Failed refund retry | the business | the owner | prepare |
| Anything not listed | ask the owner | | |
```

Blank means "ask". The owner's rules win over the agent's view of what is fair.

## The clock

Ask the owner how fast customers should hear back, and how often the check
should run. Write both in `policies.md`:

```markdown
Check every: 2 hours
Flag a missed check after: 6 hours
```

Then tell the owner this, in these words: "Main Branch does not run a
scheduler. Please schedule a recurring check in your agent runtime (cron, a
systemd timer, or a Claude Code routine) that opens this repo and runs the
case check. Support is not set up until that exists." Record the date the owner
confirmed it in `state/support/cases.md`.

## The cases file

Create `state/support/cases.md` with the header from
[cases.md](cases.md). The role card and the first article can wait for another day.
