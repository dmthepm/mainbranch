# Automation loop state — the steered-loop contract

The continuity file for an unattended or steered agent loop. Automation state
must be **inspectable**: anyone (you, the agent, a teammate) can open this one
file and know what the loop is doing, what it has done, and what it is waiting
on. The agent reads this first every iteration, does the next smallest correct
slice, and updates this file as part of the same change. You steer by editing
**Steering**; the loop never overrides it.

## Steering (you edit this; the loop obeys)

- Mission: <what this loop is for, in one or two lines>.
- Cadence: <how often it runs, and how often you review>.
- Park anything ambiguous in **Flagged for me** instead of guessing.

## Priority order

1. <highest-priority work item — the loop works top-down>
2. <next>
3. <next>

## Hard guardrails

- <what the loop may never do — e.g. PR-only to protected branches, read-only
  on business data, no spend/publish/send, never print a credential>.
- Do the smallest correct slice; validate before declaring done.
  For branch work, follow [branch completion](https://github.com/dmthepm/mainbranch/blob/main/docs/operating-principles.md#branch-completion).
- Never rule on owner-only calls — park them in **Flagged for me**.

## Shipped

- <append one line per completed slice, newest at the bottom: date, what
  shipped, the PR/commit, and the evidence it is green>.

## Next intent

- <the next slice the loop will take, concretely enough to resume cold>.

## Flagged for me

- <questions and decisions only the owner can make; the loop appends here
  instead of guessing>.

---

## The two automation shapes

- **Steered loop** — an agent loop that reads this file, acts, and updates it
  each iteration. Use when judgment is needed per iteration and you want to
  steer between runs. This file IS its memory and its handoff.
- **Unattended cron** — a deterministic job on a fixed schedule with no
  per-run judgment (for example a pulse collector run; see `mb pulse install`).
  Use for fetch-and-record work that is safe to run with no one watching.

## Handoffs

A loop handoff is **rendered from this file**, never hand-written somewhere
else. To hand off (to yourself tomorrow, a teammate, or a fresh agent), share
the current **Shipped** tail + **Next intent** + **Flagged for me** — that is
the whole state. If the handoff would say something this file does not, update
this file first.

## Knowing what's armed (follow-up)

Live facts about armed automations — next fire, last run, last outcome — are a
planned `mb` surface. Until then, record each run's outcome in **Shipped** so
the state stays inspectable from this file alone.
