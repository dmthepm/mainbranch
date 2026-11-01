---
name: mb-start
description: "Main Branch business router. Detects repo facts, save/sync state, updates, readiness, and live operator intent, then routes to the right skill or CLI contract. Use when the user starts/returns, asks what to do, needs setup, bookkeeping/books, provider setup, save/checkpoint/sync help, repair/update guidance, launch routing, or help."
loops: [sense, decide]
---

# Start

Single entry point: detect business state, intent, save/sync posture, and the smallest useful next route.

## Router and language contract

This skill routes; it is not the worker for coordinated output. Use
[references/router-and-language.md](references/router-and-language.md) as the
business router before presenting a menu.
Business language comes first. Say saved checkpoint, unsaved local work, catch
up, sync, reconcile, shared repo, workspace, and provider readiness. Keep raw
git terms, checkpoint ids, branch names, `origin`, `ahead`, `behind`, `rebase`,
and `commit` out of the first response unless the user asks for technical detail
or the exact command must be shown.

When summarizing repo state, count `pushes/` records, flag `campaigns/` as
legacy only, and use `core/vocabulary.md` display words (real paths in commands).

**CLI facts first:** Once the business repo path is known, run
`mb status --json --peek` before asking setup or routing questions. Treat JSON
as source of truth for update severity, readiness, drift, onboarding,
integrations, GitHub, team, bets, dirty git, since-last-check,
`content_strategy`, `money_path`, `validation.file_contracts`, and
`ranked_actions`. Use GitHub `author_display`/`author_known` when naming
people. Parse the full JSON once; do not slice status output with `head` or
`sed`.

**Shared source:** The portable daily start/status workflow contract lives
in `workflows/mb-start-status/workflow.md`; this skill is its Claude shell.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:
- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
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

**Continuity facts:** "where we left off" comes from status `journal` and `checkpoint`;
rules in `references/router-and-language.md` (Continuity Facts).
Saving progress: `mb checkpoint --plan --json`, validate the subject (verb from
`references/router-and-language.md`), then after approval `mb checkpoint --message "..." --yes`.

**Provider facts first:** When setup or routing depends on GitHub, Cloudflare,
Google/Workspace, Meta Ads, or Apify, read the status `integrations` facts
first; for a provider choice or repair explanation, run `mb connect plan` or
`mb connect doctor --json` and use the cited `next_command`/`repair_command`.
Never ask for tokens or setup in prose before the CLI names the missing step.

**Paid-traffic facts first:** When routing a paid-traffic minisite, Google Ads,
GTM, retargeting, or "ready to launch" request, load
`docs/google-ads-gtm-conversion-rubric.md`; with a known site repo, run
`mb site check "$SITE_REPO" --business-repo "$REPO_PATH" --json` before any
`/mb-site` or `/mb-ads` launch advice. `blocked` = stop; `ready_for_preview` =
preview-only; `ready_for_operator_review` = manual review first. Never publish
GTM, mutate Google Ads, upload conversions, or ask for tokens in prose; never
invent `ready_for_launch` (valid states: `missing`, `blocked`,
`ready_for_preview`, `ready_for_operator_review`, `ready`).

**Offer launch path:** When the operator asks to launch an offer, use
[references/launch-orchestration.md](references/launch-orchestration.md):
keyword-gate with `/mb-think`, create/select a launch push, build/check the
lander with `/mb-site`, ads with `/mb-ads`, checkpoint approved artifacts.

**Primitive routing:** For live ideas, read `.claude/reference/business-primitives/offer-bet-push-proof.md`
and `.claude/reference/business-primitives/setup-patterns.md`. For a measurable
channel trial with a review or cut point, check `brain.bets` and `bets/`.
Use a covering bet, or offer `/mb-bet` before execution; ask before writes.

**Data/ops surface routing:** whose-data questions → `mb spine declare`/
`show`; money-path-overnight worries (real money flowing unattended) →
`mb canary init`; recurring daily business read → `mb pulse init`; "show me
the business" → `mb dashboard open`; scripts reading credentials →
`mb connect exec <id> -- <cmd>` (never echo values). Full map: mb-help
`references/cli-surfaces.md` — business answer first; triggered surfaces stay triggered.

**Books/finance routing:** When the user mentions bookkeeping, books, finance,
accounting, ledgers, statements, P&L, chart of accounts, tax, payroll, hledger,
or a restricted `finance` child repo, run `mb books check "$REPO_PATH" --json`
before drafting files. Keep raw private finance records out of the
team-safe hub repo; use the books contract, `storage_mode`, and topology
visibility (`restricted` or `local_only`) to route raw records. After `mb books check`,
route books setup, monthly close, reconciliation, and CPA handoff to `/mb-books`; route tooling decisions to `/mb-think`.
**Slug/destructive-operation guardrails:** Load
`.claude/reference/business-primitives/slug-conventions.md` before naming
business objects or topology entries, and
`.claude/reference/business-primitives/destructive-operations.md` before
renaming, deleting, merging, archiving, migrating, publishing, mutating
providers, spending money, changing topology, or creating checkpoints.

---

## Repo Selection Rules

CWD-first wins. If current Main Branch markers exist in CWD, confirm the repo and
continue. If CWD looks like old repo shape, keep CWD as migration input and run
`mb status --json --peek` plus `mb doctor repair --plan` before discovery.

Only ask which repo when CWD is not a business repo. In fallback mode, list all
validated `recent_repos`, include a switch option, and do not treat the saved
default as automatic. Treat legacy config selections as session-scoped unless a
current `mb` command exposes an explicit persistence path. Do not write
`default_repo` into `~/.config/vip/local.yaml`, and do not create or update
`.vip/config.yaml`.

---

## Numbered Options Pattern

Always use numbered lists for multi-choice (repo selection, skill routing,
launch blockers, provider setup). One active choice namespace per turn: if
top recommendations are numbered, use offer slugs or letters for secondary
choices; the same number must never mean two actions — ask when ambiguous.

---

## Detection Flow

1. Detect repo CWD-first; use config only when CWD is not a business repo.
2. Run `mb status --json --peek`; status facts gate updates, repair, readiness,
   onboarding, ranked actions, and continuity.
3. Use status-cited repair/update commands before routing into output work.
4. Route live intent through [references/router-and-language.md](references/router-and-language.md)
   before showing a generic menu.
5. Resume onboarding from status facts; in rich repos, read existing `core/`
   before asking bounded missing-profile questions.
6. Resolve multi-offer context without reusing numbered choices or silently
   writing local state.
7. Present one clear route set or infer intent: `/mb-think`, `/mb-bet`,
   `/mb-ads`, `/mb-organic`, `/mb-site`, `/mb-seo`, `/mb-wiki`, `/mb-help`, or
   `/mb-end`. Conversion-script requests route through the owning workflow,
   not a standalone skill.

---

## Status Preamble: Read Status Facts

After repo selection, run:

```bash
mb status --json --peek
```

- `ranked_actions` is the deterministic list of one to three business moves.
  Surface the first action as the recommendation, including its reason and
  cited signal summaries.
- After that action, name the first warn-level `relationship_health.gaps` item
  once with its repair. Skip it when there is no warning.
- `brain.bets.active`, `brain.bets.due_soon`, `brain.bets.overdue`, and
  `brain.bets.exit_criteria` are the deterministic bet trigger facts. Use them
  for active, due-soon, overdue, missing-exit, triggered kill, triggered
  double-down, close, update, and narrate moments before inventing bet state
  from prose.
- `money_path` maps customer progress, offer, proof, CTA, channel, push,
  playbook, page readiness, and outcome feedback. Use it as evidence; cite
  `money_path.objects.proof.quality` facts instead of claiming an offer will
  convert.
- `validation.file_contracts`, `content_strategy`, `readiness`, and `drift.items` map file gaps, content layers, setup gates, and repair commands.
- `onboarding.summary` and `onboarding.checklist` replace separate onboarding probes unless status is unavailable.
- `git_activity`, `journal`, `since_last_check.journal`, `integrations`, `github`,
  `measurement`, and `brain.bets` supply continuity facts for routing.

Use `git_activity` and `since_last_check` from `mb status` to answer what changed; business repos need no latest or changelog index.

Only run `mb onboard status --json`, `mb doctor`, `mb validate --cross-refs`, or
`mb connect doctor --json` when status marks that section unavailable, degraded, or needing repair.

## Step 1: Check Main Branch Updates

Use the `update` section from `mb status --json --peek`. **Do not bury available
updates inside a general status wall.** Users on stale code get broken
features, and normal operators will miss a one-line version note.

If `update.severity` is `required` or the top ranked action is an update action,
run the cited update command. When status does not cite one, use:

```bash
mb update --repo . --json
```

Then run `mb status --json --peek` again before routing.

If `update.severity` is `recommended`, stop there. Use `update.release_notes_url`
or `update.update_check_command` to answer what changed or run a fresh dry-run.
Ask whether to update now, then rerun `mb status --json --peek` before routing.
Use [references/router-and-language.md](references/router-and-language.md) for
operator-facing wording and fallback details.

---

## Step 2: Detect Business Repo (CWD-First)

The user starts Claude in their business repo. Check CWD first before falling back to config.

**Quick gist:**

```
1. test -d "core"  → THIS IS the business repo. Skip to config.
2. old Main Branch repo markers without current markers → old repo; run
   `mb status --json --peek` and `mb doctor repair --plan` from CWD.
3. test -f ".claude/skills/mb-start/SKILL.md"  → user is in a Main Branch source checkout; migrate.
4. Otherwise → fall back to `~/.config/vip/local.yaml` only as legacy
   machine-local repo memory.
```

See **[references/repo-detection.md](references/repo-detection.md)** for the full flow: CWD detection, migration guidance for users in a source checkout, config loading, multi-repo selection, the discovery algorithm when no config exists, the required `REPO_PATH` variable, and the Main Branch wiring verification block.

---

## Step 3: Read Save/Sync State

Once the business repo is confirmed, use status `git`, `checkpoint`, and
`since_last_check` facts to explain whether work is saved locally, unsaved
locally, synced to the shared repo, or waiting for reconciliation. Do not
blindly pull or rebase the business repo from `/mb-start`. See
[references/router-and-language.md](references/router-and-language.md) for the
save/sync vocabulary.

---

## Onboarding Preamble: Resume Onboarding Progress

Prefer the `onboarding` section from `mb status --json --peek`. If status is
unavailable or the operator specifically asks for onboarding detail, run:

```bash
mb onboard status --repo "$REPO_PATH" --json
```

Use the JSON envelope as the source of truth for onboarding progress:

- `summary.next_recommended_action` tells you what to do next
- `checklist[].missing_inputs` names the bounded inputs to collect
- `profile.team_size` distinguishes solo, small-team, and larger-team setup
- `boundaries.defer_until_needed` names data to avoid collecting in the first context window

If `core_reference` is pending, collect only enough to draft the missing core
files. Do not ask for full finances, credentials, raw customer/member exports,
or exhaustive operations details before the core files exist.

If the repo already has substantive current `core/` files, read and summarize
those facts before asking onboarding questions. Mine `core/offer.md`,
`core/audience.md`, `core/voice.md`, `core/soul.md`, and `core/proof/` when
present; include `core/offers/*/offer.md` names in multi-offer repos. Propose
answers for bounded missing inputs from existing repo truth, cite which files
informed the proposal, and ask the operator only to confirm or correct the
facts that remain uncertain.

If the user's team size or current success stage is missing, ask briefly and
update the plan:

```bash
mb onboard plan --repo "$REPO_PATH" --team-size solo --success-stage working
```

---

## Step 4: Provider And Tool Pre-Flight (Not Full Research Detection)

Check provider and MCP readiness only for skills the user might invoke ([mcp-preflight.md](references/mcp-preflight.md)). Start from `mb status --json --peek`, `mb connect plan` and `mb connect doctor --json` (run doctor when a provider section is degraded, missing or selected by the operator), and use that JSON before checking runtime tool presence. Quote the CLI's `next_command` / `repair_command`; do not re-probe provider credentials from prose or mutate `.vip/config.yaml`. Operator-facing pattern:

> "This action needs [business capability].
>
> 1. Set up [provider] now — `[exact command]`
> 2. Skip for this session — [specific limitation]"

Full research and document tool detection happens in `/mb-think` when the user needs research, not here; most sessions do not need every tool checked upfront. See [tool-status-audit.md](references/tool-status-audit.md) for the audit procedure and messaging rules.

---

## Step 6: Readiness Assessment

Use `readiness`, `money_path`, `ranked_actions`, `onboarding`, `drift.items` and `validation.file_contracts` from `mb status --json --peek` before routing; prefer `money_path.ranked_actions` for path gaps unless the top-level ranked action already incorporates it. [readiness-assessment.md](references/readiness-assessment.md) is fallback detail for gaps status does not expose (scoring rubric, session state, soul health check, skill-specific requirements, display format, exact fallback thresholds). Adapt display to `user.experience` without making the repo feel audited or behind.

Fallback: check `core/*.md`. If CWD looks like an old Main Branch repo, run `mb status --json --peek` and/or `mb doctor repair --plan` before routing. No folder -> `/mb-setup`. Two or more core files missing/thin -> `/mb-think codify`; otherwise route by intent. In multi-offer repos, a thin/missing active-offer `offer.md` routes to `/mb-think`.

## Step 7: Defer Full Context Loading

Do not read full reference files into main; status readiness already names the scores, files and gaps. The selected skill or triage agent loads deep context. Exceptions: read `[repo]/CLAUDE.md` when present (small, helps routing tone), and when onboarding is incomplete but current `core/` files exist, read enough of them to avoid asking for facts the repo already contains (summarize, then ask only for confirmation or missing profile fields). If CLI facts or the session identify an active offer, note it for routing.

## Step 8: Offer Detection (Multi-Offer Only)

Use the active-offer resolution contract in `.claude/reference/business-primitives/offer-bet-push-proof.md` (load `setup-patterns.md` and `slug-conventions.md` from that directory when setup shape or naming is unclear). `find "$REPO_PATH/core/offers" -mindepth 2 -maxdepth 2 -name "offer.md"` lists offers. No `core/offers/` means single-offer mode; if `core/` is also absent, treat old shape as migration input after `mb status --json --peek` or `mb doctor repair --plan`, and do not infer the offer from old paths. If offers exist, use current CLI status facts first, never silently route from `.vip/local.yaml`, present choices by slug/name when route numbers are already visible, and keep selection session-scoped unless the operator approves a current `mb` persistence command. `/mb-start [offer-name]` selects a validated offer for this session; `all` means brand-level `core/` context.

---

## Step 10: Route by Intent

**Respect readiness gates from Step 6.** If status is MINIMAL or EMPTY, do not offer output skills. If THIN, warn. See [readiness-assessment.md](references/readiness-assessment.md) for skill-specific requirements.

**Show context:** "Business: **[repo name]** | Offer: **[active offer or 'single']**"

If the user stated intent, route directly using
[references/router-and-language.md](references/router-and-language.md). If the
session is open-ended, surface the top ranked action, update recommendation, top
non-duplicated MoneyPath action, or compact route menu. Use
[references/triage-menu.md](references/triage-menu.md) only for prioritization
or deep triage.

---

## Step 11: Help Mode

"Help" or confused → route to `/mb-help`. Give quick overview first:

> "Open your business folder, start Claude, then run `/mb-start`. Main Branch
> uses the `mb` CLI for facts and skills for judgment. Details: `/mb-help`."

---

## Context And Experience

Fresh context gets a fuller load; working context routes directly; heavy context
gets a brief warning; critical context routes to `/mb-end`. If legacy
`~/.config/vip/local.yaml` has `user.experience`, use it as a machine-local
fallback: beginner explains more, returning confirms quickly, expert routes
fast. If the user asks for a faster mode, offer to update local experience.

---

## Intent Keywords

Auto-detect user intent through
[references/router-and-language.md](references/router-and-language.md). Key
clusters: save/checkpoint/sync, bookkeeping/books/finance, provider/tool setup,
repair/update/drift, decide/codify/research, bets, launches, sites, ads, organic,
wiki, and help.

Generic "set up" is not enough to route. Use the noun: repo setup routes to
`/mb-setup`, bookkeeping setup runs `mb books check` then `/mb-books`, monthly close also routes to `/mb-books`, provider setup reads
`mb connect`, and decision/tool setup routes to `/mb-think`.

---

## Recovering from Compaction

If re-invoked after compaction: use CWD and `mb status --json --peek` first;
read `~/.config/vip/local.yaml` only as legacy fallback for repo + identity;
treat business `.vip/local.yaml` as audit input only, and do not write it.

---

## References

- [references/router-and-language.md](references/router-and-language.md) — business router, save/sync language, update posture, and intent clusters
- [references/pull-engine-updates.md](references/pull-engine-updates.md) — Step 1 Main Branch update handling
- [references/repo-detection.md](references/repo-detection.md) — Step 2 full CWD detection, migration, multi-repo selection, REPO_PATH, Main Branch wiring verification
- [references/triage-menu.md](references/triage-menu.md) — Step 10 CHANGELOG banner, menu, "while you wait" pattern, auto-suggest/skip rules
- [references/auto-heal.md](references/auto-heal.md) — Bridge link recovery
- [references/config-system.md](references/config-system.md) — Config loading and recovery
- [references/mcp-preflight.md](references/mcp-preflight.md) — MCP pre-flight checks
- [references/readiness-assessment.md](references/readiness-assessment.md) — Step 6 readiness scoring
- [references/tool-status-audit.md](references/tool-status-audit.md) — Step 5 provider/readiness audit
- [references/triage-agent.md](references/triage-agent.md) — Triage agent prompts and synthesis
- [references/launch-orchestration.md](references/launch-orchestration.md) — guided offer-launch path
