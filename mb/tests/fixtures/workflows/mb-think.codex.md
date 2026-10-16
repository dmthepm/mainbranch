# Generated Codex Workflow Guidance: Think Research Decision Codify

Source workflow: `workflows/mb-think/workflow.md`
Runtime support: `codex_cli: owner_loop_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`

Codex supports the proven owner loop. Use this generated `AGENTS.md` guidance
as the Codex shell for natural-language thinking tasks. The business repo does
not need to contain `workflows/mb-think/workflow.md`. Claude Code entrypoints stay separate.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb checkpoint --plan --json`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.offer`
- `money_path.objects.proof`
- `money_path.objects.proof.quality`
- `money_path.objects.product_ladder`
- `money_path.objects.cta_path`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `money_path.objects.outcome_feedback_loop`
- `money_path.ranked_actions`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `books`
- `runtime.codex_cli`
- `runtime.claude_code`

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Run hard gates first: required updates, repair blockers, readiness
   blockers, unsafe provider operations, private-data boundaries, and
   destructive-operation requests.
3. Read deterministic `mb` facts before raw markdown. Then read only relevant
   `core/`, `research/`, `decisions/`, `bets/`, `pushes/`, `log/`, and `docs/`
   files.
4. Give a Research Depth Recommendation from 0-5 before outside research:
   memory, repo context, lightweight public/manual research, multi-source
   synthesis, structured approved-source collection, or high-resolution market
   analysis.
5. Use parallel research files for multiple sources, then synthesize in the
   main thread. Each source file records source quality, access/permission,
   caveats, promotion limits, and public/private handling.
6. Write a decision when durable business truth changes. Codify only after the
   operator accepts the direction.
7. For observations, ask before a concise sourced research-only readout; changed steering adds a linked decision in the same approved session.
   Set decision `linked_research` and research `linked_decisions`, link a known bet or push, and update an existing trial bet through `mb-bet` after approval.
   Summarize numbers with source and caveat; exclude raw provider rows, account IDs, customer data, and exported tables. Status-only stays status.
8. For transcripts, authenticated community content, provider recordings, or
   mixed private/business sources, use manifest-first allow/skip filters before
   reading content. Route synthesized output, not raw payloads.
9. For stale source, claim, proof, or angle cleanup, identify the stale item,
   find downstream usage, keep history auditable with a stale note, reconcile
   current truth after approval, record and codify the decision, then
   checkpoint only after approval.
10. Ask for approval before creating or editing business files, promoting
   research into core truth, using structured collection, opening public
   issues, publishing, provider mutation, spend, customer contact, or checkpoint.

## Handoff Shape

```text
Thinking task: <research, decision, codify, or full flow>.
Repo facts read: <status/start/connect/repair/checkpoint facts used>.
Current bottleneck: <MoneyPath, content strategy, readiness, drift, or user question>.
Research depth recommendation: <0-5>, because <reason>.
Useful sources: <repo files, public/manual sources, approved providers, or operator input>.
Stop condition: <what is enough signal>.
Durable targets: <research/, decisions/, core/, bets/, pushes/, log/, or documents/>.
Approval needed before writes: yes.
```
Do not tell Codex users to run Claude Code entrypoints. Runtime smoke is
required before docs say this selected workflow is supported in Codex.
