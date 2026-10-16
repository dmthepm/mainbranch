---
name: mb-bet
title: Bet Lifecycle
description: "Create, update, close, list, and narrate time-boxed Main Branch bets from deterministic facts and business-file contracts."
loops:
  - decide
  - reflect
  - ship
runtime_support:
  claude_code: supported_shell
  codex_cli: read_only_planning
runtime_surfaces:
  claude_code: .claude/skills/mb-bet/SKILL.md
  codex_cli: global Main Branch mb-bet skill
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb validate --cross-refs --json
  - mb checkpoint --plan --json
  - mb similar-bets "<thesis>" --repo . --json
  - mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md --json
  - mb books exposure --repo . --active --json
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - validation.file_contracts
  - content_strategy
  - ranked_actions
  - update
  - readiness
  - drift.items
  - brain.bets
  - brain.bets.active
  - brain.bets.due_soon
  - brain.bets.overdue
  - brain.bets.exit_criteria
  - relationship_health.sections.bets
  - relationship_health.gaps
  - checkpoint.pending
  - checkpoint.pending.blockers
  - books
  - runtime.codex_cli
  - runtime.claude_code
approval_gates:
  - updates_repairs_migrations
  - file_writes
  - checkpoint
  - provider_mutation
  - publishing_or_spend
  - customer_contact
  - private_data
  - destructive_operations
  - structured_collection
  - public_issue_or_proposal
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_raw_transcripts
  - no_customer_member_data
  - no_private_runtime_settings
  - no_private_dms_or_gated_communities
  - no_raw_finance_legal_records
  - no_raw_ledger_rows
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Bet Lifecycle

## Intent And Triggers

Use this workflow when the operator wants to frame, inspect, update, close, list,
or narrate a Main Branch bet. A bet is a time-boxed wager with an appetite,
target, deadline, evidence path, and verdict. It is not an offer and it is not a
push.

Also use it when `mb-start` or a channel workflow finds a current trial with a
measurable target and a review or cut point. Check `brain.bets` and relevant
`bets/` files first. If one covers the trial, use and link it. Otherwise offer
to create a bet from the facts already given; ask only for a missing target,
review or cut point, or owner when unclear, and get approval before writing.
Routine channel work without a wager stays in its channel workflow.

Preserve these product distinctions:

- Offer: the durable thing sold.
- Push: coordinated execution.
- Bet: the wager that tests a hypothesis and may link to pushes.

A bet can graduate into an offer, push, decision, content pillar, workflow, or
outcome only when accepted evidence or an accepted decision supports that move.
Failed bets close with learning instead of being rewritten into success.

Supported modes:

- `new`: frame a bet and create `bets/YYYY-MM-DD-slug.md`.
- `update`: append evidence, update links, and keep the verdict open.
- `close`: record the measured result, verdict, learning, and graduation route.
- `list`: summarize active, due, overdue, blocked, and exit-triggered bets.
- `narrate`: draft public-safe narration from accepted repo truth.

## Required Mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`
- `mb similar-bets "<thesis>" --repo . --json`
- `mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md --json`
- `mb books exposure --repo . --active --json`

Read `mb status --json --peek` before direct file reads. Use `mb start --json`
when runtime readiness or handoff facts matter. Use `mb doctor repair --plan`
when status facts name repair or migration blockers. Use cross-reference
validation after bet link edits. Use checkpoint planning before offering to
save changes.

Use similar-bets before creating a new material bet when the thesis may repeat
prior work. Use books exposure only when the bet is financially material or the
bet has a declared `money_path.bet_id`.

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `brain.bets`
- `brain.bets.active`
- `brain.bets.due_soon`
- `brain.bets.overdue`
- `brain.bets.exit_criteria`
- `relationship_health.sections.bets`
- `relationship_health.gaps`
- `checkpoint.pending`
- `checkpoint.pending.blockers`
- `books`
- `runtime.codex_cli`
- `runtime.claude_code`

`validation.file_contracts` is the guided-route source for bet contract gaps.
`brain.bets` is the deterministic source for active, due, overdue, missing-exit,
and triggered kill or double-down signals. Relationship health facts identify
missing reverse links and stale business connections before the agent invents
relationships from prose.

## Routing Rules

Start with deterministic facts, then read only the relevant bet and linked
business files. Keep owner-facing language in business terms: wager, appetite,
target, evidence, deadline, verdict, learning, and next action.

Mode routing:

1. For `new`, ask only for missing essentials: hypothesis, appetite, target,
   deadline, metric, kill rule, and initial execution plan. If the idea sounds
   like a new offer, ask whether the operator wants a wager or an offer
   candidate. Do not create, move, or delete offer files without an accepted
   decision or explicit instruction. Also ask, as optional questions: "What is
   the one thing this bet does every day (or weekdays, or weekly), who does it,
   and what proof shows it happened?" If answered, write `commitment` (`action`,
   `cadence`, `owner`, `evidence` kind: url, commit, send_id, file, other). And
   ask whether the bet is still being tuned, is working, is an ongoing habit,
   is done, or was cut; write that as `stage`. Skip both if the operator has no
   answer. Never write a default, and never record or check daily evidence here.
2. For `update`, read the bet and linked files, append a dated evidence note,
   update link fields, and keep `result` blank unless there is a real measured
   result.
3. For `close`, ask for the actual result if evidence is thin, then set
   `status` to `closed` or `canceled`, fill `result`, add learning, and name the
   verdict. If the bet changes offer truth, propose a follow-up decision before
   editing the offer.
4. For `list`, summarize active bets by deadline, status, target, metric,
   appetite, exposure posture, exit criteria, triggered kill or double-down
   signals, public posture, blocked state, and overdue state. End with the next
   bet needing attention.
5. For `narrate`, draft public-safe narration only from accepted bet, decision,
   research, push, outcome, and offer truth. Do not invent metrics, testimonials,
   channels, or results. If `public: false`, ask before drafting public copy and
   offer a private retrospective instead.

Primary bet files live in `bets/`. Link fields are typed business connections:
`linked_decisions`, `linked_research`, `linked_pushes`, and `linked_outcomes`.
`linked_campaigns` exists only for legacy compatibility; new work should route
execution through pushes and keep legacy fields empty unless repairing old
repos. Add `linked_bets` reverse links to linked files when the schema supports
them.

Use the body-level `## Related links` mirror to keep human-readable links aligned
with typed frontmatter. When links are missing or stale, present `mb doctor
repair --plan` before applying any repair.

## Read Boundaries

Read:

- deterministic status, start, validation, relationship, checkpoint, and
  exposure facts first;
- the target bet file and directly linked decisions, research, pushes, outcomes,
  logs, documents, and offers;
- similar past bets when a new material thesis may repeat earlier work;
- aggregate exposure output for financially material bets.

Do not read or paste raw private finance rows, provider exports, transcripts,
private direct messages, gated community content, customer/member records, vault
paths, account numbers, payees, or ledger memos. Route those through summarized
operator-provided evidence or deterministic aggregate facts.

## Write Boundaries

This workflow may write business files only after approval. Durable write
targets are:

- `bets/YYYY-MM-DD-slug.md`;
- typed links on directly related decisions, research, pushes, outcomes, and
  offers when the relationship is accepted;
- body-level `## Related links` mirrors;
- an approved checkpoint after validation and checkpoint planning.

Do not create provider mutations, publish content, spend money, contact
customers, send email, mutate dashboards, or create account changes. Do not
graduate a bet into an offer, decision, push, content pillar, workflow, or
outcome without accepted evidence or an accepted decision.

Bet frontmatter should keep the strict contract:

- `status`
- `stage` (optional)
- `commitment` (optional)
- `opened`
- `deadline`
- `appetite`
- `appetite_tier`
- `hypothesis`
- `metric`
- `target`
- `result`
- `owner`
- `money_path`
- `kill_rubric`
- `linked_decisions`
- `linked_research`
- `linked_pushes`
- `linked_campaigns`
- `linked_outcomes`
- `public`
- `channels`
- `tags`

Bet bodies should keep these sections: `Why This Bet`, `Hypothesis`, `Work
Plan`, `Evidence Log`, `Result`, `Narration Notes`, and `Related links`.

## Approval Gates

Always ask before:

- `updates_repairs_migrations`
- `file_writes`
- `checkpoint`
- `provider_mutation`
- `publishing_or_spend`
- `customer_contact`
- `private_data`
- `destructive_operations`
- `structured_collection`
- `public_issue_or_proposal`

Approval must be explicit before creating or editing bet files, repairing links,
adding reverse links, applying migration or doctor repairs, saving checkpoints,
using structured collection, submitting a public issue or proposal, drafting
public narration from `public: false` bets, or promoting bet learning into offer
truth.

## Handoff Format

```text
Bet mode: <new, update, close, list, or narrate>.
Facts read: <status/start/validate/relationship/exposure/similar-bets facts>.
Bet: <path, status, deadline, appetite, metric, target>.
Evidence: <new evidence, missing evidence, or measured result>.
Exit posture: <kill, double-down, continue, close, or unclear>.
Connections: <decisions, research, pushes, outcomes, offers, or none>.
Public posture: <public-safe, private, needs approval, or not narration>.
Write plan: <files to create/edit or none>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

## Validation Commands

After bet or link edits:

1. Run `mb validate --cross-refs --json`.
2. If the checkpoint surface is available, run `mb checkpoint --plan --json`.
3. Show blockers in owner-facing language before offering to save.
4. Save only after approval, using checkpoint tooling rather than raw git
   commands.
5. End by rerunning `mb status --json --peek` when the operator needs the
   refreshed bet state.

## Runtime-Specific Notes

Claude Code uses `.claude/skills/mb-bet/SKILL.md` as the project-local shell for
this workflow. Preserve the existing business flow, mode language, approval
gates, artifact routing, and finance/privacy boundaries from that shell.

Codex uses the global Main Branch `mb-bet` skill generated from this workflow
source. Codex support remains read-only planning and file guidance until runtime
smoke proves lifecycle writes. It may inspect deterministic facts, explain bet
contract gaps, propose guarded edits, and ask for approval, but it must not
claim supported lifecycle execution, provider mutation, publishing, spend,
customer contact, dashboard work, or Claude Code entrypoints.
