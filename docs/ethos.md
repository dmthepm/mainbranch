# Main Branch Ethos

Main Branch is public open-source infrastructure for running a business from
markdown files in git.

The product is not another place to paste prompts. The product is a durable
way to keep business memory usable:

- the business repo is the business brain;
- `mb` is the deterministic control plane;
- agent-runtime skills are the judgment-heavy execution layer;
- migration drift detection, `mb doctor repair`, `mb validate`, and `mb graph`
  are the safety net that keeps the repo trustworthy as the engine evolves;
- GitHub issues are durable work threads for tasks, requests, blockers, and
  follow-ups when work needs shared visibility;
- pull requests are proposals and review conversations;
- git history is the evolution story;
- `mb checkpoint` makes long agent runs durable before chat context is lost;
- dashboards, Obsidian graphs, and future team surfaces are views over the same
  files, not replacements for them.

The promise is simple: own the work, rent only the rails.

## What We Are Building

Main Branch should help an operator move through four loops:

1. **Sense** - pull state in: offers, audience, voice, research, decisions,
   `mb status`, drift, freshness, connected tools, GitHub activity.
2. **Decide** - choose what to wager next: the bet, the priority, the override.
   Plain English: pick what matters and make the call.
3. **Ship** - produce and release the work: pages, ads, organic content,
   sales videos, provider connections, fulfillment work, bookkeeping summaries, system
   updates, and saved checkpoints. One verb covers producing the artifact and
   putting it in the world.
4. **Reflect** - extract the lesson, usually scheduled: bet verdicts, retros,
   decisions superseded, core files updated from what you learned. The
   output of Reflect feeds back into Sense.

Those loops are described in detail in [operator-loops.md](operator-loops.md),
and the full reasoning lives in
[decisions/2026-05-05-operator-loops-taxonomy.md](../decisions/2026-05-05-operator-loops-taxonomy.md).

## Product Principles

### 1. Files First

Business truth belongs in git: core files, research, decisions, bets,
pushes, plans, public artifacts, meeting summaries, fulfillment notes, durable
finance summaries, and proposal changes. Rebuildable indexes, local caches,
credentials, runtime preferences, raw finance/legal sources, and live process
state can exist outside git, but they must not replace the repo.

GitHub, Obsidian, `mb graph`, and future dashboards should all read the same
durable memory. If two views disagree, the repo wins.

### 2. Thin CLI, Fat Workflows

`mb` should stay deterministic, inspectable, scriptable, and exit-coded. It
owns repo shape, validation, migration, status, updates, graphing, integration
metadata, skill wiring, and runtime adapter contracts.

The CLI is the fact and safety layer, not the primary product surface for most
operators. Agent-runtime skills are the chat UX and judgment layer: synthesis,
writing, review, routing, and explanation in plain business language. A skill
may call `mb` for facts. It should not reimplement repo-health probes or
structural invariants in prose.

This same shape should hold as the system grows: hledger can be the books
engine while `mb books` provides privacy-bounded JSON and workflow checks;
research-depth guidance can help the agent choose between memory, repo context,
public research, and deeper synthesis without turning research into endless
collection.

### 3. The Operator Decides

Main Branch should recommend, not seize control. The system can tell the
operator what looks stale, risky, blocked, or important. It should cite the
signals behind that recommendation and make override paths explicit. The agent
recommends; the operator makes the call.

Publishing, spending money, contacting customers, mutating accounts, and
shipping public-facing work should remain intentional operator actions unless a
future decision explicitly changes that boundary.

### 4. Beginner-Safe, Power-User-Honest

The product is for non-developers, but it should not hide the real primitives.
GitHub issues are durable work threads that can be described as tasks,
blockers, requests, or follow-ups when the user loop needs that translation.
Pull requests can be described as proposals. Git history can be described as
shipped work. The underlying terms should remain available when the user needs
them.

Beginner flows should end with a clear next action. In chat, the agent should
run deterministic CLI checks internally and explain the result in plain
language. Exact commands should remain available for handoff, debugging, docs,
and power users, but they should not be the default user experience.

### 5. Runtime Honesty

Claude Code is the first supported slash-skill runtime today. Codex CLI is
supported for the daily Main Branch routes through generated repo guidance,
global `mb-*` skills under the Codex skills root, deterministic `mb` facts, and
smoke evidence. Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, and
local runtimes are compatibility targets only when adapter code and smoke
evidence exist.

Main Branch should meet operators where they already work, but it should not
claim support before support is proven.

### 6. Improve Through Friction

If a user hits an error, missing workflow, confusing step, or repeated manual
repair, Main Branch should make it easy to turn that friction into a clean
GitHub issue. That loop is part of the product. The public issue tracker is how
operator usage becomes shared infrastructure.

Issue drafting must be privacy-safe by default. Business context, customer
data, tokens, local paths, and account details must not be sent without an
explicit operator decision. `mb issue draft` and `mb issue open` are the
shipped path: drafts land under `.mb/issue-drafts/` for review, the scrubber
redacts common hazards, and submission is an explicit operator action.

### 7. Sidecars Are Optional

Specialized tools can make Main Branch stronger when they do one narrow job
well and return structured output. Examples include public company context,
ads metrics, bookkeeping, transcription, analytics, or deployment helpers.

Sidecars, MCP servers, and provider rails should be optional,
permission-aware, and behind stable contracts. They are subordinate to repo
truth and deterministic `mb` facts, not replacements for the core engine.

### 8. Curated Rails Beat SaaS Sprawl

Main Branch should not connect every tool an operator has accumulated. The team
should make opinionated, explainable choices: prefer official provider paths,
boring CLIs, portable files, and local-first state. Cloudflare, GitHub,
Google/Workspace, official ads paths, Postiz, hledger, Apify, transcription,
and future sidecars earn their place by improving a loop and by failing in
ways `mb` can explain.

### 9. Evidence Beats Hunches

Do not ship runtime claims, migration paths, packaging changes, or first-run
flows without evidence. Use the validation ladder in [AGENTS.md](../AGENTS.md):
static checks, CLI tests, package smoke, fixture repo smoke, and runtime smoke
when the behavior depends on a real runtime.

Package-visible releases run simulations against fixture repos and review
transcripts by hand. See [release-simulations.md](release-simulations.md).

The product should feel alive; the parts underneath should stay boring.

### 10. Git Is The Hidden App

Main Branch should use git as the invisible save system for business work.
Operators should not need to understand branches, diffs, or commits to benefit
from them. Agents should checkpoint meaningful work throughout a run so future
sessions can reconstruct what changed, what was decided, and what remains open
from repo history.

`mb checkpoint` is the shipped surface for that loop: it plans or saves
business-readable git commits at meaningful boundaries, with privacy and
secret-safety gates before anything is recorded. Checkpointing is not noisy
autosave; it is durable business memory.

## What We Are Not Building Yet

Main Branch is not a hosted SaaS dashboard, chat client, background daemon,
model host, vector database, scheduler, or hosted marketplace product today.
Codex uses global Main Branch skills and generated `AGENTS.md` guidance.
Business repos do not need repo-local Codex plugin or skill copies. Claude Code
plugin wiring is a runtime adapter, not a hosted marketplace product.

Those may become useful surfaces later. They earn their way in by preserving
the same source of truth: the business repo, GitHub, git history, deterministic
CLI contracts, and explicit runtime adapters. A future dashboard may include
team communication, but chat is source material; durable operating truth lands
in issues, proposals, decisions, pushes, logs, commits, and core updates.
