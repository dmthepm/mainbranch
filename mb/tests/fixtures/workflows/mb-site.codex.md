# Generated Codex Workflow Guidance: Site And Page Production

Source workflow: `workflows/mb-site/workflow.md`
Runtime support: `codex_cli: read_only_planning`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`, `domain_purchase`, `dns_change`, `pages_project`, `custom_domain_attach`, `deploy_or_push`, `account_change`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_absolute_local_paths_in_committed_descriptors`

Codex uses the global Main Branch `mb-site` skill as a read-only planning and
site-readiness route. This guidance is generated from the engine workflow
source and does not claim supported site writes, builds, deploys, publishing,
provider mutation, account changes, customer contact, or Claude Code
entrypoints in Codex.
Modes: plan, brief, build, preview, check, publish, iterate, graduate, or recover.

## Required mb Commands

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
- `mb validate --cross-refs --json`
- `mb checkpoint --plan --json`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `money_path.objects.cta_path`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `validation.file_contracts`
- `content_strategy`
- `content_strategy.overall_state`
- `content_strategy.simple_entry_point`
- `content_strategy.layers`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `integrations`
- `measurement`
- `measurement.available`
- `measurement.state`
- `measurement.facts.expected_events`
- `measurement.facts.instrumentation`
- `measurement.blocked_count`
- `measurement.manual_count`
- `relationship_health.gaps`
- `checkpoint.pending`
- `checkpoint.pending.blockers`
- `runtime.codex_cli`
- `runtime.claude_code`
- `state`
- `blocked`
- `manual`
- `evidence`
- `facts.expected_events`
- `facts.instrumentation`
- `facts.provider_state`
- `facts.app_stack`
- `facts.deploy`
- `facts.commerce`
- `facts.email`
- `facts.measurement`
- `recommended_action`
- `source`
- `child_descriptor`

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, provider readiness,
   site-check readiness, relationship gaps, validation, and checkpoint plan.
3. Detect business repo mode or site repo mode. Use `.mainbranch/repo.json` as
   the preferred site descriptor and legacy `.mainbranch/source.json` only as
   compatibility.
4. Guide plan, brief, build, preview, check, publish, iterate, graduate, or
   recover modes across lander, minisite, website, and sales-video surface
   shapes from the shared contract. Treat instrumentation as the check mode for
   analytics, tags, booking/form widgets, and event mapping.
5. For business-repo site readiness, use `measurement.*` facts from status. For
   site-repo readiness, use top-level `state`, `blocked`, `manual`, `evidence`,
   `facts.expected_events`, `facts.instrumentation`, `facts.provider_state`,
   `source`, and `child_descriptor` from `mb site check`. Use exact readiness
   states such as ready_for_operator_review; do not invent ready_for_launch.
6. Codex may draft patch-shaped recommendations, sample copy, review notes,
   readiness summaries, and exact file targets, then stop before changing files
   or running build/deploy actions.
7. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/site.md`, `research/`, `decisions/`, and
   `.mainbranch/repo.json`.
8. If the operator wants proposed site changes applied, route them to Claude
   Code `/mb-site` or another supported write surface until Codex site-write
   and build/deploy smoke proves this route. Do not run post-change validation,
   checkpoint commands, git pushes, deploys, or provider tools as if Codex
   edited files.
9. Keep provider gates explicit. Do not buy domains, change DNS, create
   Cloudflare Pages projects, attach custom domains, deploy, git push, publish,
   spend, mutate provider accounts, contact customers, or execute account
   changes.

## Push Links

When creating or first writing a push, ask once:
"Which bet does this push serve, and which existing decision or research supports it?"
Offer active bets and recent decisions and research by name from status facts or files already read.
Accept "none yet" and continue. For a deliberate one-off with no bet, write
`linked_bets: []` and a one-line `no_bet_reason`. On an approved write, put the
chosen repo-relative paths in `linked_bets`, `linked_decisions`, and
`linked_research` on the push; add its path to `linked_pushes` on each named
bet, decision, and research file. Leave unanswered links empty; do not invent
a reason. Mirror typed links in `## Related links` as relative Markdown links.
Use docs/business-connections.md; never infer links from body-only references.

For Codex, include these as proposed file edits and stop before applying.

## Handoff Shape

```text
Site mode: <plan, brief, build, preview, check, publish, iterate, graduate,
or recover; instrumentation is a check sub-mode>.
Repo mode: <business repo, site repo, both linked, or unclear>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Shape: <lander, minisite, website, sales-video surface, or unknown>.
Offer/CTA: <resolved, thin, blocked, or needs decision>.
Readiness: <missing, blocked, ready_for_preview, ready_for_operator_review, ready, or not checked>.
Provider posture: <read-only, connected, blocked, approval needed, or unsupported>.
Artifact route: <business push/site/decision/research path, site repo target, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Runtime smoke is required before docs say this
workflow is supported for Codex site writes, builds, deploys, or publishing.
