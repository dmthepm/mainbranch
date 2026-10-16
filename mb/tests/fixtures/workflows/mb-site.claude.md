# Generated Claude Shell: Site And Page Production

Source workflow: `workflows/mb-site/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `structured_collection`, `public_issue_or_proposal`, `domain_purchase`, `dns_change`, `pages_project`, `custom_domain_attach`, `deploy_or_push`, `account_change`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_raw_transcripts`, `no_customer_member_data`, `no_private_runtime_settings`, `no_private_dms_or_gated_communities`, `no_raw_finance_legal_records`, `no_absolute_local_paths_in_committed_descriptors`

Use from `/mb-site` when the operator wants to plan, brief, build, preview,
check, publish, iterate, graduate, or recover an owned conversion surface,
including analytics/instrumentation checks.
Modes: plan, brief, build, preview, check, publish, iterate, graduate, or recover.
Preserve the existing Claude skill's lander, minisite, website, sales-video
surface, business-repo mode, site-repo mode, Cloudflare gate, and checkpoint
contract.

This snapshot does not replace shipped `.claude/skills/mb-site/SKILL.md`.

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

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, Cloudflare/provider readiness, site-check
   readiness, relationship gaps, validation, and checkpoint plan.
2. Detect business repo mode or site repo mode. Use `.mainbranch/repo.json` as
   the preferred site descriptor and legacy `.mainbranch/source.json` only as
   compatibility.
3. Support plan, brief, build, preview, check, publish, iterate, graduate, or
   recover modes across lander, minisite, website, and sales-video surface
   shapes. Treat instrumentation as the check mode for analytics, tags,
   booking/form widgets, and event mapping.
4. For business-repo site readiness, use `measurement.*` facts from status. For
   site-repo readiness, use top-level `state`, `blocked`, `manual`, `evidence`,
   `facts.expected_events`, `facts.instrumentation`, `facts.provider_state`,
   `source`, and `child_descriptor` from `mb site check`. Use exact readiness
   states such as ready_for_operator_review; do not invent ready_for_launch.
5. Draft from active offer, audience, voice, content strategy, proof facts,
   relevant research, decisions, active pushes, and MoneyPath facts. Route thin
   offers or unsupported claims to `mb-think` before page copy.
6. Route coordinated site work to `pushes/<YYYY-MM-DD-slug>/push.md`, site
   records to `pushes/<YYYY-MM-DD-slug>/site.md` or the relevant offer note,
   research to `research/`, locked briefs to `decisions/`, and descriptors to
   `.mainbranch/repo.json` in the site repo after approval.
7. Use `mb validate --cross-refs --json` after approved business-repo link,
   push, site, brief, or related-link edits. Use `mb site check` for site repo
   readiness and the checkpoint plan before offering an approval-gated save.
8. Keep provider gates explicit. Do not buy domains, change DNS, create
   Cloudflare Pages projects, attach custom domains, deploy, git push, publish,
   spend, perform provider mutation, mutate provider accounts, or contact
   customers. Do not contact customers or execute account changes without
   explicit approval and runtime evidence for that surface.

## Push Links

When creating or first writing a push, ask once:
"Which bet does this push serve, and which existing decision or research supports it?"
Offer active bets and recent decisions and research by name from status facts or files already read.
If this is a measurable trial with a review or cut point and no covering bet,
route to `mb-bet` before execution.
Accept "none yet" and continue. For a deliberate one-off with no bet, write
`linked_bets: []` and a one-line `no_bet_reason`. On an approved write, put the
chosen repo-relative paths in `linked_bets`, `linked_decisions`, and
`linked_research` on the push; add its path to `linked_pushes` on each named
bet, decision, and research file. Leave unanswered links empty; do not invent
a reason. Mirror typed links in `## Related links` as relative Markdown links.
Use docs/business-connections.md; never infer links from body-only references.

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

Use business language first. Site code commits still use the site repo's normal
git flow; business-repo saves use `mb checkpoint`. Codex support stays
read-only planning until runtime smoke proves site writes, builds, deploys, and
publishing.
