---
type: decision
date: 2026-06-12
status: proposed
topic: Spine levels — the contact+event spine as a declared position
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/814
participants: [Devon, Claude]
tags: [spine, contacts, events, data-ownership, mcp, levels]
---

# Spine levels: the contact+event spine is a declared position, not a database

Scope note: "spine" here means the **contact+event spine** — the system
holding a business's people and their event timelines (operating-principles
§2). It does not mean the brand/voice "operating spine" or "git is the
spine" senses used elsewhere.

## Decision (proposed)

`mb spine` is not a database installer. It is a **declare → grade →
build-when-triggered** surface:

1. **Declare.** The business records, as a repo fact, which system plays
   the contact+event spine role (and for intentional minimalists, that
   none does — on purpose).
2. **Grade.** `mb doctor` / `mb spine doctor` grades the declared position
   and names the first business question the current level cannot answer,
   plus what the next level costs.
3. **Build only when a trigger fires.** The owned contact+event schema
   (this issue's original scope) ships as the recommended build path —
   recommended *when a trigger fires*, never as a default migration.

A strong platform can be a business's settled spine forever. The engine
never shames a declared position; it makes the position explicit, queryable,
and honest about what it cannot answer.

## The levels

| Level | Position | What it means |
| --- | --- | --- |
| L0 | None | No person-store. Either a gap (leads scattered across inboxes) or an intentional product stance — declared either way. |
| L1 | Rented | One platform holds the person (commerce platform customers, email-list subscribers, community members). Truth exists; it is theirs. |
| L2 | Declared | Same platform, nothing rebuilt — but the role is recorded as a repo fact, credentialed through `mb connect`, and the operator's agent can query it from the terminal. |
| L3 | Augmented | The platform keeps its domain (customers, orders); an owned event log holds what it cannot — cross-channel touches, delivery truth, identity joins. |
| L4 | Owned | Person + full timeline in the business's own store; every platform becomes a deduped fan-out lens (operating-principles §2 verbatim). |

**Triggers, not schedules:** first customers (0→1) · an agent starts
working the business (1→2; cheap — one connect plus one declared fact) ·
the first question the platform cannot answer (2→3) · the platform's
person-model or export terms become the constraint (3→4).

## What the evidence forced into the model

Validated on three operating businesses we built (which happen to span
L0-intentional, L2, and L4) and an external landscape pass (2026-06).

1. **Grade on three dimensions, not ownership alone.** A spreadsheet is
   *owned* and is the worst spine in the study (no structure, no timeline,
   no agent access); a rented platform profile with a first-party agent
   surface outranks it. The grade therefore scores: **agent-queryability**
   (can the operator's agent read it from the terminal), **event-timeline
   completeness** (how much of the person's story lands in one place), and
   **durability** (export rights; what survives leaving). Ownership is the
   durability axis, not the whole grade.
2. **"Has an MCP" is not the test — check whose agent it serves.** The
   most agent-forward commerce platform ships several first-party agent
   surfaces, all aimed at *buyers'* agents; the merchant-side surface is
   the gap. L2 grading asks specifically whether the **operator's** agent
   can query the person-store.
3. **L2 is real and newly viable — and per-platform.** The 2025–26 wave of
   first-party vendor MCPs (payments, email, CRM, scheduling) is the
   enabling event for "declare the rented spine." But viability is a
   per-platform property that can be feature-gated or revoked, and some
   major community/newsletter platforms remain closed boxes with no public
   API — a declared spine can grade *below* L2 through no fault of the
   operator. The grade names that honestly.
4. **L3 is the expected center of gravity, not L4.** In every business
   type studied, the event timeline is fragmented across 2–4 platforms —
   no rented spine holds the full story. Meanwhile CDP history shows small
   operators skip heavyweight owned stores for cost and ops burden, and
   there is no observable solo-operator pull toward fully-owned
   person-stores. The augmented position — platform keeps the person,
   owned log keeps the events it drops — is the path of least resistance
   and the model's default recommendation when a 2→3 trigger fires.
5. **Rented event history can evaporate.** On one of our businesses, a
   rented email platform's entire peak-era engagement history was
   permanently lost when the account was disabled. Person records usually
   export; *event* history usually does not. That asymmetry is the durable
   argument for the owned event log at L3.

## What ships (revised #814 scope)

- **Slice 1 — `mb spine declare`:** record the declared position as a
  business-repo fact (store, level, lenses, known gaps, revisit trigger).
  Pure facts + existing `mb connect` rails; every business type benefits.
- **Slice 2 — grading:** `mb spine doctor` (and the status surface) grades
  the declaration on the three dimensions, names the first unanswerable
  question, and prices the next level.
- **Slice 3 — `mb spine init --owned`:** the contact+event schema and
  canned queries (this issue's original scope) as the L3/L4 build path,
  including send/delivery events per [delivery-truth](../docs/delivery-truth.md).

Boundary: level declarations and all spine data are business-repo facts —
the engine ships schema, grading, and doctrine only, and never holds a
business's numbers or identifiers.

## Kill criteria

- If operators consistently ignore declarations and only use the owned
  schema, the declare/grade rungs collapse into init documentation.
- If vendor agent surfaces regress (revoked MCPs, API lockdowns), L2
  grading must degrade those platforms honestly rather than carry stale
  "queryable" verdicts — grading reads live capability, not a static list.
