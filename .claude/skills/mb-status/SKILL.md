---
name: mb-status
description: "Thin Main Branch status wrapper. Use when the operator asks what changed, what is healthy, what is stale, what to do next, or wants a daily briefing inside Claude Code."
loops: [sense]
---

# Status

Show the operator the deterministic Main Branch briefing without duplicating
repo-health checks in prose.

**CLI facts first:** Run `mb status --json --peek` before answering, then use
that JSON as the source of truth.

**Shared source:** The portable daily start/status workflow contract lives in
`workflows/mb-start-status/workflow.md`. This Claude skill is the Claude Code
status shell over that source.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`

`mb doctor repair --plan` is read-only. If it exits nonzero while returning `plan_interpretation` and `actions`, treat that as findings to review, not as an opaque command failure.

`operator_actions` (in `mb doctor repair` and `mb update` JSON) are steps for the user, such as the plugin-rail switch: show each `command` and `note` as theirs to run at a terminal, and never run them yourself.

Required fact paths:

- `money_path`
- `money_path.policy`
- `money_path.policy.thresholds_declared`
- `money_path.active_bets`
- `money_path.active_bets.unanchored`
- `money_path.active_bets.over_cap`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `relationship_health.gaps`
- `update`
- `readiness`
- `readiness.dimensions.repo_runtime`
- `readiness.dimensions.business_memory`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `since_last_check`
- `git_activity`
- `journal`
- `checkpoint`
- `onboarding`
- `integrations`
- `github`
- `topology.repo_boundary`
- `brain.bets`
- `brain.bets.active`
- `brain.bets.due_soon`
- `brain.bets.overdue`
- `brain.bets.exit_criteria`
- `brain.bets.exit_criteria.missing`
- `brain.bets.exit_criteria.triggered_failure_signals`
- `brain.bets.exit_criteria.triggered_double_down_signals`
- `vocabulary`

Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`,
`provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`,
`destructive_operations`, and `status_marker`.

Public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_customer_member_data`, `no_private_runtime_settings`, and
`no_raw_finance_legal_records`.

Core route: status facts first, runtime mismatch gates before business routing,
one owner-facing recommendation, business language first, and explicit approval
before mutating the status marker or doing durable writes.

Use recent `git_activity` and `since_last_check` from `mb status` to answer
what changed. Business repos need no separate latest or changelog index.

## Workflow

1. Confirm you are in the business repo. If not, ask the operator to `cd` into
   the business repo or pass the repo path.
2. Run:

```bash
mb status --json --peek
```

3. Treat the JSON as the source of truth for setup, update, drift, GitHub,
   onboarding, integrations, team, bets, journal activity, since-last-check,
   readiness, `readiness.dimensions.repo_runtime`,
   `readiness.dimensions.business_memory`, vocabulary, content_strategy,
   money_path, validation.file_contracts, and ranked actions.
4. Summarize the top `ranked_actions` first. For each one, include:
   - title
   - command or slash command
   - reason
   - cited signal summaries
5. Then summarize only the sections that matter for the operator's question.
   Use `money_path` when the question is about the path from customer progress
   to offer, proof, CTA, channel, push, playbook, page readiness, or outcome
   feedback. Keep the language evidence-based: legible, supported, connected,
   instrumented. Do not say the offer is good, bad, likely to convert, or ready
   to win.
   Use `validation.file_contracts` when the question is about a file that
   exists but lacks the business shape needed for the next workflow. Route
   offer-shape gaps to `/mb-think` and ask before editing durable offer files.
   Use `content_strategy` when the question is about content strategy health,
   layered channel/account/person files, stale platform rules, or disconnected
   content layers. Do not infer that health by parsing markdown yourself unless
   status says the section is unavailable.
   Use `brain.bets.active`, `brain.bets.due_soon`, `brain.bets.overdue`, and
   `brain.bets.exit_criteria` for active, due-soon, overdue, missing-exit,
   triggered kill, triggered double-down, close, update, and narrate moments
   before inventing bet state from prose.
   For a measurable channel trial with a review or cut point, check `brain.bets`
   and `bets/`; use a covering bet, or offer `/mb-bet` before execution.
   Use `topology.repo_boundary` when the operator is deciding whether work
   belongs in this business repo, a separate business repo, or a
   child repo.
   If `vocabulary.terms.push` defines display words, use them in
   operator-facing prose without changing current paths, frontmatter, JSON
   keys, validator rules, or command names.
   Use `team` facts and GitHub activity `author_display` / `author_known` fields
   when naming people; keep unknown contributors as handles.
   Do not re-run shell probes that duplicate status facts.
   For "what changed?" or "what happened since last time?", answer from
   `since_last_check.journal` first, then top-level `journal` for recent
   context.
6. If provider readiness is the question, use `integrations.github` and
   `integrations.providers` from status first. If the operator needs choices or
   repair commands, run:

```bash
mb connect plan
mb connect doctor --json
```

Summarize GitHub, Cloudflare, Google/Workspace, Meta Ads, and Apify as numbered
business choices. Use the CLI's `next_command` or `repair_command`; do not ask
the operator to paste tokens into files or public issue text.

## Mutating The Last-Check Marker

`--peek` is the default inside this skill because a conversation may inspect
status before the operator is ready to record a daily check.

If the operator explicitly says this is the daily check-in and wants it
recorded, run:

```bash
mb status --json
```

Use the new report for the answer.

## Privacy

Respect each action and signal's `safe_to_share` field. If `safe_to_share` is
false, keep evidence local to the conversation and do not suggest pasting it
into public GitHub without review.
