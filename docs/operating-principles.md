# Operating principles: how a Main Branch business builds

The durable answer to the recurring questions: *where does this data go? how
do we build this feature? how do we not break production?* Every agent (and
human) working a Main Branch business reads this and thinks this way. When a
choice is not obvious, these principles decide it.

Proven on a live business through its full arc — idea, offer, site, paid
checkout, email engine, ads, first leads — before graduating into the
engine. New business repos point here; `mb-setup` introduces this page
during onboarding.

## The twelve principles

### 1. Everything is agent-queryable

Every tool and every piece of data in the business must be something an
agent can see and query — via CLI, API, or MCP. No data lives somewhere an
agent cannot reach. If a system cannot be queried from the terminal, it is
the wrong system or it needs a CLI/API path first. This is the test a new
tool must pass before the business adopts it.

### 2. Own the spine; one system of record per domain

Each domain has exactly one system of record (payments, email, work
tracking, code), and the business holds rich data in each. The owned
contact-and-event store — the person and their full timeline — is the
spine. Everything else (ad platforms, audiences, dashboards) is a deduped
fan-out lens, never a second system of record: sync *to* them from the
spine; never let them become the truth.

### 3. Data shape first

Before building a view or a feature, get the data in the right shape on the
spine: the contact, with every event hung off it — conversations with
content, email opens and clicks, questions asked, purchases. Nurture and
analysis both fall out of the right shape. A dashboard on top of
badly-shaped data is wasted work; fix the shape, not the view.

### 4. Nurture is automated, not manual

Free leads are not hand-worked. Email automations and campaigns work them,
fired by spine behavior and segments. The job is to build systems that work
the leads, then improve those systems — not to sit in a CRM clicking.
Adding a separate CRM creates a second source of record and vendor sprawl;
the spine plus the email provider hold the primitives.

### 5. Analysis is agent-driven from the terminal

Understanding — "what do leads ask?", "who is warm but did not buy?" —
comes from querying the spine with an agent, not from a BI tool. The
conversation is the analysis, and it feeds the next automation. Visuals are
light conveniences, never a maintained surface of record.

### 6. High-quality conversion data out, consented

Conversion signals leave the business server-side, hashed, enriched, and
deduplicated against client pixels by shared event ids. Keep your own forms
and capture the click ids yourself rather than renting the provider's
forms. Consent travels with the data: opt-out is recorded once, on the
contact, and honored everywhere a signal leaves.

### 7. Right-sized platform primitives; writes behind auth

Use the platform primitive that fits, nothing heavier: serverless functions
for logic, key-value for hot lookups, a relational store for the queryable
spine, object storage for artifacts, a gateway for inference telemetry. The
browser never writes to a backend directly — data is written server-side
behind auth; obscurity and CORS are not security.

### 8. Protect the golden path

The live money path is sacred. Production repos run protected main — PR
plus green checks before merge, no silent direct-to-main. A canary guards
runtime money-path invariants; browser-layer checks catch the class of
breaks HTTP checks miss. Every shipped change is functionally verified —
exercised live — not just built. When in doubt: the smallest correct,
durable change; defer speculative work.

### 9. Codify learnings (compound)

Each unit of work makes the next easier. Decisions and reasoning live in
docs and commit messages so the next agent does not relearn them. Docs are
the clean source of truth: README → accurate docs → an agent onboards cold.
Nothing stays marked "proposed" once it has shipped. When a lesson is
learned, it becomes a check or a doc line so it cannot recur silently.

### 10. Lean, no sprawl, no pre-test commitments

Build the smallest thing that is correct and durable; reuse existing
patterns; no new abstraction or vendor until a primitive plus the spine
plus agents genuinely cannot do it. Do not name unproven vendors or APIs as
committed public primitives until the loop is proven.

### 11. Validate against live state with fresh-context agents

Build-green is not done. Verify every substantive change by (a) reading the
live state — the deployed site, the real API read-back, the rendered
preview, the actual database row — never the local build or your own
assumptions, and (b) using independent agents with fresh context to
adversarially check the work; a builder marking its own homework misses
what a cold reviewer catches. Provider APIs return success on swallowed
parameters — trust read-backs and rendered proof, never the 200 (see
[delivery-truth.md](delivery-truth.md)).

### 12. Codify and surface as you go

Keep docs current in the same pass that changes reality — a doc that lags
code is an agent trap. Capture the adjacent ideas the work surfaces: when
building X makes "Y should exist" obvious, write it down durably right then
— a dated note, a backlog line, an engine issue for the reusable ones. The
discovery process is the product; do not let the insight die in a
transcript.

## The decision rule

Faced with "where does this data go / how do we build this": it goes on the
**spine**, in the **right shape**, **agent-queryable**, written
**server-side behind auth**, fanned out **high-quality and consented** to
the ad and email platforms, **without breaking the golden path**, in the
**leanest** form that is durable. If a step cannot be satisfied, that is
the thing to fix first.

## The subagent operating contract

Fleets of subagents amplify a business loop only when they cannot silently
lose work. The contract, dictated repeatedly by operators before it was
written down:

- **Deliver within the assignment.** Follow the assignment's authority to edit,
  save checkpoints, push, or open proposals. An edits-only lane returns its
  files; a read-only lane returns its findings. Commit and push only when
  authorized. The orchestrator verifies the actual files or saved work before
  accepting the report.
- **Worktree per file-mutating agent.** Parallel agents that mutate files
  are isolated in their own worktrees; they never share a checkout.
- **Liveness over silence.** Long-running agents are checked for liveness;
  a dead agent's task is reassigned, not assumed complete.
- **Read-only auditors stay read-only.** Verification agents and change
  agents are separate; an auditor never fixes what it finds, it reports.
- **Docs first, cleanup last.** Agents read the relevant docs before
  building, and remove or update stale docs as part of completing the work
  — not as a follow-up that never comes.

## How a new agent onboards

1. `/mb-start` → the business repo's CLAUDE.md → this page.
2. Then the offer and the spine: the active offer file and the business's
   architecture and data-model docs.
3. Build by the decision rule. Verify what you ship. Codify what you learn.
