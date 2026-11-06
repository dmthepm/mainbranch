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

## The files

The loop needs the first two. If either is missing, set it up with the owner first
(see [references/setup.md](references/setup.md)) and do nothing else that day.

- `goal.md`: the one number, how it is counted, where it is read, the baseline
  with its date, the target with its date, and the weekly review day.
- `autonomy.md`: what this agent may do without asking, with a limit for each,
  and who it may talk to. The always-ask list below can only be made stricter
  there, never looser.
- `log.md`: the loop's own daily log (format below). This is not a readout; the
  hub rule against readouts in `log/` does not apply to it.

Where they live:

- **Owner's hub** (the agent can commit to it): `core/growth/goal.md`,
  `core/growth/autonomy.md` and `log/growth.md`. The owner approves every change
  to the first two.
- **Not the owner's hub** (the agent cannot commit there): the same three files
  in a `growth/` folder in the agent's own private state, outside the repo.
  Nothing in `autonomy.md` counts until the owner's yes is written in the first
  log entry with its date. To adopt the loop, the owner takes the folder in one
  reviewed change: `goal.md` and `autonomy.md` into `core/growth/`, `log.md` as
  `log/growth.md`. The agent then reads the repo copies, stops using the private
  ones, and says so in the log.

Use one home at a time, never both.

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
   key and route it (see "Platform gaps"). Never guess a number. Some sources
   lag: Search Console's final numbers arrive 2 to 3 days late, so read the
   latest final day and say which day it is.
2. **Check yesterday's move.** Find its expected signal in the log. Record what
   happened, or "too early" with the date it can be read.
3. **Read the owner's latest.** Before drafting, read the newest entries in
   `log/` and `decisions/`, open bets, and anything the owner told this agent
   since the last log entry. List the calls already made. Do not draft a move
   that repeats or reopens one; if the evidence says a call was wrong, bring it
   to the owner as a question and do not act on it.
4. **Pick one move.** Score the candidates in
   [references/moves.md](references/moves.md): likely effect on the number,
   time to see a signal, cost, and how easy it is to undo. Prefer a move whose
   effect you can measure on its own. Do not repeat a move that showed no effect
   unless something changed, and say what.
5. **Act inside the limits.** If the move is inside `autonomy.md`, do it through
   the owning skill: `/mb-seo` for search, `/mb-site` for pages, `/mb-ads` for
   paid, `/mb-organic` for content, `/mb-think` for research and keywords,
   `/mb-books` for revenue facts. If it is outside, prepare it fully and ask
   once.
6. **Log it.** One entry in `log.md` (format below), in whichever home is in use.
   In the owner's hub, commit it with the checkpoint flow the repo already uses;
   the owner's approval of `autonomy.md` covers these entries.

Record each step's outcome as you go. A run that stops partway says which step
it stopped at, never "done". Before acting, read today's entry: if a step
already finished today, do not repeat it.

One move a day is the default. `autonomy.md` may allow more, but never more than
three pull requests a day. Changes made without asking are labelled unreviewed
until the owner merges or accepts them.

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
`## Gaps` in `log.md` with what it blocks. Tell the owner once per
gap, in the weekly review, and do not ask again until something changes.

## Hard rules

- No number, no claim: report "not read" instead of an estimate.
- Never widen your own limits. Only the owner edits `autonomy.md`.
- Stop the loop and tell the owner if the number falls two weeks in a row and
  the moves cannot explain it.
- Keep secrets out of every file. Use `mb connect` for keys.
