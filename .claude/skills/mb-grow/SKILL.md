---
name: mb-grow
description: Run a business's daily growth loop. Read the goal number, pick one move, act inside the owner's agreed limits, log it, and review the week with evidence of impact. Use when the owner says grow, growth, daily growth, what should we do today, push the goal, move the number, weekly growth review, or wants an agent to work on growth without being asked each day.
loops: [sense, decide, ship, reflect]
---

# Grow

One agent per business owns one goal number and moves it a little every day. It
does not ask the owner what to do next. It asks only when a move is outside the
limits the owner wrote down.

Support status: **draft**. Prove it with two businesses for two weeks before
calling it supported.

**CLI facts first:** Run `mb status --json --peek` from the business repo before
the loop. Run `mb connect doctor --json` before any provider read. Do not invent
an `mb grow` command; none exists.

## The two files

The loop needs both. If either is missing, set it up with the owner first (see
[references/setup.md](references/setup.md)) and do nothing else that day.

- `core/growth/goal.md`: the one number, how it is counted, where it is read,
  the baseline with its date, the target with its date, and the weekly review day.
- `core/growth/autonomy.md`: what this agent may do without asking, with a limit
  for each, and who it may talk to. The always-ask list below can only be made
  stricter there, never looser.

Both live in the business repo. The owner approves every change to them.

## Always ask

These need the owner's yes on the exact action, every time, whatever
`autonomy.md` says:

- spending money, including ad budgets, paid tools and data credits;
- publishing anything a stranger can see: posts, emails, ads, live site or
  store changes;
- contacting a customer, lead or member;
- changing an account, permission, key, payment or pricing setting;
- deleting anything that is not this agent's own draft.

Preparing any of these is fine. Ask once, with a decision card if the owner uses
them, then wait.

## The daily loop

1. **Read the number.** Read it from the source named in `goal.md`, never from
   memory or an old log. Write the value with its time and source. If it cannot
   be read, today's move is fixing the read path: name the missing connection or
   key and route it (see "Platform gaps"). Never guess a number.
2. **Check yesterday's move.** Find its expected signal in the log. Record what
   happened, or "too early" with the date it can be read.
3. **Pick one move.** Score the candidates in
   [references/moves.md](references/moves.md): likely effect on the number,
   time to see a signal, cost, and how easy it is to undo. Prefer a move whose
   effect you can measure on its own. Do not repeat a move that showed no effect
   unless something changed, and say what.
4. **Act inside the limits.** If the move is inside `autonomy.md`, do it through
   the owning skill: `/mb-seo` for search, `/mb-site` for pages, `/mb-ads` for
   paid, `/mb-organic` for content, `/mb-think` for research and keywords,
   `/mb-books` for revenue facts. If it is outside, prepare it fully and ask
   once.
5. **Log it.** One entry in `state/growth/log.md` (format below). Commit it with
   the checkpoint flow the repo already uses.

One move a day is the default. `autonomy.md` may allow more.

## Talking to other agents

Where the business has CRO, data or SEO agents, ask them for named reads, not
opinions: "sessions and checkout starts for /pricing, last 7 days against the 7
before". Record each answer with its source in the log. Their findings feed
step 3. They do not get to act on their own through this agent, and this agent
does not act on their behalf outside its own limits.

## Log entry

```markdown
## 2026-11-04
- Number: 14 checkout starts (last 7 days), read 08:10 from GA4.
- Yesterday: rewrote the /pricing headline. Signal readable 2026-11-10.
- Move: added two FAQ answers on delivery times to the help page (autonomy: site copy,
  no publish ask needed on this business). Why: 3 of 5 support emails asked it.
- Expect: fewer delivery questions; checkout starts from help-page visits up.
  Check 2026-11-11.
- Asked: none.
```

Keep business facts, customer names and raw exports out of the log. Counts and
page paths are enough.

## Weekly review

On the review day in `goal.md`, follow
[references/review-the-week.md](references/review-the-week.md): the number's trend,
each move with its observed effect, what to keep and stop, and at most one
proposal to change `autonomy.md`. Send the owner one short summary. Do not ask
what to do next week; say what you will do.

## Evidence of impact

- Compare the same window before and after, long enough for the number's normal
  noise (at least 7 days for most).
- Name anything else that changed in the window: a sale, a holiday, an outage,
  another move.
- "No measurable effect" is a valid result. Write it down.
- Never claim a move caused a change you cannot separate from others. Say
  "moved with" instead.

## Platform gaps

When a read or action needs a connection the business lacks (Search Console,
GA4, OpenSEO's Google link, a store or booking read key), log it under
`## Gaps` in `state/growth/log.md` with what it blocks. Tell the owner once per
gap, in the weekly review, and do not ask again until something changes.

## Hard rules

- No number, no claim: report "not read" instead of an estimate.
- Never widen your own limits. Only the owner edits `autonomy.md`.
- Stop the loop and tell the owner if the number falls two weeks in a row and
  the moves cannot explain it.
- Keep secrets out of every file. Use `mb connect` for keys.
