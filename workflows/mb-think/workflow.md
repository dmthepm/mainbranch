---
name: mb-think
title: Think Research Decision Codify
description: Research, decide, and codify durable Main Branch business truth from repo facts, source-backed synthesis, and explicit operator approval.
loops: [sense, decide, ship]
runtime_support:
  claude_code: supported_shell
  codex_cli: owner_loop_shell
  future: planned
runtime_surfaces:
  claude_code: .claude/skills/mb-think/SKILL.md
  codex_cli: AGENTS.md#codex-think-route
required_mb_commands:
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
  - mb connect doctor --json
  - mb checkpoint --plan --json
json_facts:
  - money_path
  - money_path.objects.offer
  - money_path.objects.proof
  - money_path.objects.proof.quality
  - money_path.objects.product_ladder
  - money_path.objects.cta_path
  - money_path.objects.channel_strategy
  - money_path.objects.active_push
  - money_path.objects.outcome_feedback_loop
  - money_path.ranked_actions
  - validation.file_contracts
  - content_strategy
  - ranked_actions
  - update
  - readiness
  - drift.items
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
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Think Research Decision Codify

This workflow source is the portable contract for Main Branch thinking work:
research a question, make or document a decision, and codify approved learning
into durable business files.

## Intent And Triggers

Use this workflow when the operator asks to think through an offer, research a
market, compare providers, pressure-test positioning, choose a direction, turn
source material into a decision, mine approved source material, retire stale
source, or codify what was learned.

Trigger phrases include think through, research, decide, figure out, explore,
codify, enrich, sharpen this offer, improve the offer, compare providers,
market research, customer language, proof, objections, guarantees, keyword
gate, sales video research, script teardown, stale source, obsolete claim,
retire this angle, and decision.

Do not use this workflow for a site build, ads generation, organic post
production, provider mutation, publishing, spend, customer contact, or model
execution from `mb`.

## Required Mb Commands

Run or preserve these deterministic facts before interpreting business files:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb checkpoint --plan --json`

`mb status --json --peek` is the normal first read for repo, MoneyPath, content
strategy, provider, books, drift, readiness, and ranked-action facts.
`mb start --json` is the compact daily-start handoff when the workflow begins
from a new session. `mb doctor repair --plan` supplies repair blockers when
status reports drift or broken wiring. `mb connect doctor --json` supplies
provider-readiness and repair language when a research path needs a provider.
`mb checkpoint --plan --json` is read before recommending a saved checkpoint,
not permission to save one.

## Required JSON Fact Paths

The runtime shell must preserve these paths from the workflow source:

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

Treat these as facts, not strategy. The CLI reports legibility, connection,
readiness, and repair state. The runtime may recommend a research or decision
route, but it must not claim that an offer will or will not convert.

## Routing Rules

Hard gates win before research or codification: required updates, broken repo
wiring, repair blockers, validation blockers, relationship-health blockers,
unsafe provider operations, private-data boundaries, and destructive-operation
requests.

After hard gates, resolve the active business context from `mb` facts and the
business repo before outside research. Read only the files needed for the
question:

- `core/`
- `research/`
- `decisions/`
- `bets/`
- `pushes/`
- `log/`
- `docs/`

Choose the smallest research depth that can make the next decision honest:

- Level 0: operator memory is enough for a low-risk move.
- Level 1: existing repo context and `mb` facts are enough.
- Level 2: lightweight public or operator-provided research is needed.
- Level 3: multi-source synthesis is needed.
- Level 4: structured approved-source collection is justified.
- Level 5: high-resolution market analysis or field evidence is needed.

For multiple source types, split collection into source-specific research files
and synthesize in the main thread. Source files should record the question,
source type, access/permission note, collection method, source quality, key
patterns, counter-signals, caveats, promotion limits, and public/private
handling.

Use decisions when the work changes durable business truth. A decision should
name options, rationale, tradeoffs, consequences, and the specific files that
would change. Codify only after the operator accepts the direction.

For a daily observation or readout, use research-only at the smallest useful
depth: write a concise `research/` record with the observation, summarized
numbers, source and timeframe, what the evidence supports, caveats, and the
next question. Do not expand it into a full research project. If the operator
also changes course, use decide mode in the same approved session: write the
readout and decision after approval, set `linked_research` on the decision and
`linked_decisions` on the research, and link the bet or push being changed when
known. For a bet, use `linked_bets` on the new records and reverse
`linked_research` or `linked_decisions` on the bet; for a push, use
`linked_pushes` on the new records and reverse `linked_research` or
`linked_decisions` on the push. Use repo-relative paths that
`mb validate --cross-refs` checks. If the
change alters a measurable trial's target or cut point, update or link the
existing bet through `mb-bet` after approval before continuing the trial.
Summarize provider numbers and cite their source; never save raw provider rows,
account IDs, customer data, or exported tables in the business repo.

When transcripts, authenticated community content, provider recordings,
cloud-drive files, call notes, exported chats, or mixed private/business
sources may become business memory, route through the source-ingestion privacy
rail before reading content: inventory sources, review a metadata-only
manifest, apply allow/skip filters, read the smallest approved slice, and route
synthesized output into research, decisions, proof candidates, pushes, logs, or
issue drafts. Raw transcripts, provider payloads, gated-community content, and
private customer/member data stay out of committed files by default.

When source material, a claim, an offer detail, proof usage, or an angle is
stale, reconcile current truth instead of erasing history. Identify the stale
item, find downstream usage, keep source/evidence auditable with a stale note,
update `core/` and per-offer files after approval, record a decision when
durable truth changes, and checkpoint only after approval. Do not expand this
cleanup route into transcript ingestion, provider connectors, newsletter
implementation, or dashboard work.

## Read Boundaries

Read deterministic `mb` facts before raw markdown. After the fact pass, read
only business files needed for the current research, decision, or codify route:

- active offer, audience, proof, product ladder, CTA, content strategy, and
  relevant marketing layers;
- relevant research, decisions, bets, pushes, logs, documents, and safe docs;
- safe provider-readiness summaries from `mb connect` when a source path needs
  provider context.

Do not inspect secrets, raw provider exports, raw finance/legal records,
customer/member records, private DMs, gated communities, local runtime
settings, private maintainer notes, or credentials unless the operator gives
explicit permission and the source is appropriate for the business repo.

## Write Boundaries

The workflow may write business files only after the operator approves the
research, decision, codify, or checkpoint action. Valid write targets live in
the business repo:

- `research/`
- `decisions/`
- `core/`
- `bets/`
- `pushes/`
- `log/`
- `documents/`

Research preserves evidence, source quality, caveats, and open questions.
Core files preserve accepted operating truth. Proof files preserve permission,
offer linkage, outcome, timeframe, metric, and typicality facts. Pushes and
playbooks preserve bounded execution plans and approval records. Decisions
explain accepted rationale and what changes because of it.

The workflow source does not authorize writes to provider accounts, public
sites, ad accounts, customer systems, release surfaces, runtime adapter files,
or the Main Branch engine repo.

## Approval Gates

Ask before:

- applying updates, repairs, migrations, or provider setup;
- creating, editing, moving, deleting, or archiving business files;
- marking a decision accepted or codified;
- promoting research into `core/`, proof, pushes, playbooks, or logs;
- saving a checkpoint;
- using structured collection for Level 4 or Level 5 research;
- publishing, opening a public issue, submitting a proposal, spending money,
  mutating provider state, or contacting customers;
- reading or moving private, restricted, local-only, finance, legal, customer,
  member, credential, or raw provider data.

Never ask the operator to paste secrets into repo files or workflow sources.
Never commit raw dumps, full transcripts, private customer/member data,
credential material, session cookies, or unsupported provider exports.

## Handoff Format

When entering thinking work, include a compact snapshot:

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

Use business language. Avoid subjective conversion judgment such as "your offer
is bad," "this will convert," or "this will not convert." Do not tell Codex
users to run Claude Code slash commands.

## Validation Commands

Minimum validation for this port:

- workflow schema tests;
- generated Claude and Codex shell snapshot tests;
- drift tests that fail when a supported shell omits a required `mb` command,
  JSON fact path, research-depth rule, public/private rule, approval gate, or
  Codex support boundary;
- `python3 -m mb skill validate --all --json`;
- `scripts/check.sh`.

Run read-only Codex smoke before docs claim selected `/mb-think` workflow
support in Codex. The smoke should start from a fresh or fixture business repo,
ask a natural thinking prompt, require read-only `mb` facts first, require a
research-depth recommendation, and leave `git status --short` clean.

## Runtime-Specific Notes

### Claude Code

Claude Code remains the supported runtime. Rendered Claude shell snapshots must
preserve slash-command-native language, direct `/mb-think` invocation, re-invoke
guidance after compaction, research-depth routing, source-specific research
files, decision writing, codification approval, and checkpoint approval.

This shared workflow source does not replace
`.claude/skills/mb-think/SKILL.md` unless a branch explicitly chooses that
replacement and includes skill validation plus runtime evidence.

### Codex CLI

Codex is first-class for the proven daily loop only. Rendered Codex shell
snapshots must start from generated `AGENTS.md` style grounding, deterministic
`mb` facts, and natural-language workflow routing.

When the global Main Branch Codex skills are installed, `mb-think` is the Codex
skill route for this workflow. Without current global skills, use the generated
Codex shell fallback in `AGENTS.md` and natural-language routing from read-only
`mb` facts. Do not claim broader Codex workflow support until a fresh fixture
repo and read-only `codex exec --json --ephemeral --sandbox read-only -C <repo>`
smoke prove the generated guidance or global-skill route is actually used.
