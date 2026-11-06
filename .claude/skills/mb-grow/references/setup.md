# Setup: the goal and the limits

Do this once with the owner, in one sitting. Save nothing without approval.

First settle the home (see "The files" in SKILL.md): the owner's hub if this
agent can commit there, otherwise the agent's private `growth/` folder.

## goal.md

Ask, in order, and stop when each has a real answer:

1. Which one number shows the business is growing? Prefer money or a step just
   before it: paid bookings, checkout starts, new paying members, collected
   revenue. Search clicks or followers only when the business has nothing
   closer to revenue yet.
2. Exactly how is it counted, over what window, and from which source?
3. Can this agent read that source today? Check with `mb connect doctor --json`
   or the provider's read. If not, record the gap and pick a number it can read
   until the gap is fixed.
4. What is it now? Read it; do not take it from memory.
5. What target, by when?
6. Which day is the weekly review?

```markdown
# Growth goal

- Number: paid bookings per week
- Counted: bookings with a completed payment, Monday to Sunday, from the
  booking system
- Read path: booking system read key via mb connect
- Baseline: 3 (week of 2026-10-27)
- Target: 8 per week by 2026-12-31
- Review day: Monday
```

## autonomy.md

Copy this shape and fill it with the owner. Blank means "ask".

```markdown
# Growth autonomy

Always ask (cannot be loosened here): spend, publishing to strangers, customer
contact, account or pricing changes, deleting others' work.

| Move | No ask needed | Limit |
|---|---|---|
| Research and analysis | yes | none |
| Draft copy, pages, posts, ads | yes | drafts only |
| Site copy on owned pages | | |
| SEO fixes (titles, meta, internal links) | | |
| Merge to the site's preview or dev branch | | |
| Ask CRO, data or SEO agents for reads | yes | named reads only |
| Ad budget changes | always ask | |
| Publish a post or email | always ask | |

Talks to: (list the agents by name)
Escalate to: (the owner, and how)
```
