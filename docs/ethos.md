# Main Branch ethos

Main Branch is public open-source infrastructure for running a business from
Markdown files in git. The owner keeps the business record. Agents read that
record, propose work, and save accepted decisions and lessons for future sessions.

[The working-day example](working-day.md) shows the method.
[Operator loops](operator-loops.md) names its phases.
[The roadmap](roadmap.md) describes future direction.

## Product principles

### 1. Files first

Keep durable business context in the business repo: offers, audience, voice,
research, decisions, bets, coordinated work, and lessons. A text editor should
still open that record without Main Branch.

Keep credentials, caches, raw financial or legal records, and runtime state
outside tracked business memory. Dashboards and graphs are views over the
files. They do not become a second source of truth.

### 2. Deterministic facts, agent judgment

`mb` owns repeatable checks and operations: folder shape, validation, migration,
status, graphing, provider readiness, updates, runtime wiring, and checkpoints.
Its commands should be inspectable, scriptable, and clear about failure.

Skills own synthesis, writing, comparison, review, and explanation. They use
`mb` facts before making recommendations. A skill should not replace a
repeatable health check with a prose-only guess.

### 3. The operator decides

Explain the evidence, uncertainty, and proposed action. Work within the owner's
stated authority. Publishing, spending, customer contact, and account changes
require explicit approval and a tested execution path.

Approval to draft does not authorize publication. A stored credential does not
authorize account changes. Show what happened after an approved action and
keep unresolved results visible.

### 4. Business language first

Describe tasks, proposals, saved checkpoints, relationship health, provider
readiness, and outcomes before git implementation details. Owners should not
need to manage branches or commits to use their business history.

Keep exact commands available for inspection and support. End setup and repair
flows with a concrete next action.

### 5. Runtime honesty

Claude Code supports the bundled slash skills through its adapter. Codex CLI
supports daily routes through generated `AGENTS.md`, global Main Branch skills,
and deterministic `mb` facts. Its production workflows have narrower limits.
The [compatibility reference](compatibility.md) owns the detailed support matrix.

Business repos do not need local Codex plugin or skill copies. Other runtimes
remain compatibility targets until an adapter and smoke evidence prove the
exact path. A shared workflow source alone does not prove runtime support.

### 6. Improve through friction

Turn confusing steps and missing behavior into reviewable follow-ups.
`mb feedback` records friction locally. `mb issue draft` prepares a scrubbed
public issue; `mb issue open` submits only after review and approval.

Scrubbing reduces common hazards. The owner must still review drafts for
private business details before sharing them.

### 7. Optional specialized tools

Use a specialized tool when it improves a task and has a clear failure and
permission contract. Examples include bookkeeping, analytics, transcription,
and deployment helpers. These are optional connections, not requirements for
starting with business files.

Provider output is evidence to interpret. Save useful summaries in the business
record without copying secrets or raw sensitive data into it.

### 8. Curated rails beat SaaS sprawl

Prefer official provider paths, portable files, and connections with a clear
purpose. Connecting an account should improve a particular owner task, not
add another system to maintain without a benefit.

Keep setup, readiness, read-only access, and account mutation distinct. Do not
claim a working integration from the presence of metadata or a starter script.

### 9. Evidence before claims

Match validation to the behavior changed. Command tests do not prove that a
runtime discovers a skill. A starter monitor does not prove that a business
is being monitored. A generated plan does not prove delivery.

Use the [validation ladder](../AGENTS.md#validation-ladder) for engineering
work. Use [release simulations](release-simulations.md) when release claims
depend on agent behavior. Distinguish available commands from planned services.

### 10. Readable saved history

Use checkpoints to preserve accepted business progress at meaningful boundaries.
Preview included files and the message before saving. A local checkpoint is a
saved point in git history; remote backup requires a separate sync.

Keep history useful enough that another session can reconstruct what changed,
why it changed, and what remains open without the original chat.

## Product boundary

`mb` does not host a model, run a chat session, or schedule agents. A runtime
or external caller handles conversation and ongoing execution. The local
read-only dashboard displays repo facts; it is not a hosted service.

Future interfaces must preserve the same ownership and authority boundaries.
Chat can supply evidence, but accepted business truth belongs in durable files
and saved history.
