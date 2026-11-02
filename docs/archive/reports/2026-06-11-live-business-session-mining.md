# the live business session mining — idea to first leads (2026-06-01 → 2026-06-11)

> Source: an 11-day continuous Claude Code operating session on a real
> business we built and operate. Business-identifying details are removed;
> the full named teardown lives in the paid community. Synthesis date: 2026-06-11. Engine repo: `dmthepm/mainbranch`.

## What this is

Over eleven days (June 1–11, 2026), one operator built the live business end-to-end through Main Branch: idea → offer → live site → paid demo pipeline → Stripe checkout → email engine → Meta and Google ads → leadgen webhook → first real ad-sourced lead. This report mines that session for engine signals. Method: the full transcript was distilled into 13 day-chunks (June 10 and 11 each produced two parallel chunks), each extracted for friction moments with verbatim operator quotes, product signals, primitives touched, and actual `mb` CLI / skill usage; quotes are reproduced as typed (typos included) and redacted of credentials, account identifiers, customer names, and machine-specific paths. The findings below are deduplicated across days and ranked. The session was explicitly framed by the operator as dogfooding: "I'm basically building this company to both make money and to strengthen the main branch... you will be creating really solid tickets for the main branch." It produced engine issues #803 and #805–#820 along the way; this report reconciles the rest.

## The arc (anonymized)

Eleven days, one operator, one business built end-to-end through Main
Branch: idea → offer → live site → paid checkout → email engine → paid ads →
first real lead. The named, numbers-included teardown of this business
(offers, pricing, ad structures, day-by-day timeline) lives in the paid
community; this public report keeps the engine lessons.

## Friction leaderboard

Themes deduplicated across all 13 chunks, ranked by recurrence × severity.

### 1. Credentials and provider scopes — the dominant tax (every single day; blocking and security-relevant)

> "do not look at screenshot or attempt to extract. instead lets use 1pass. give me a termindal command that will put it in the right place"
> "i searched web and rum and notinng on account and specifric domain... I need the exact names only of what you need."

What happened: `mb connect`'s fixed provider list forced Stripe, Resend, and DataForSEO entirely outside mb (env-file hand-rolling). Cloudflare token scopes were negotiated at least nine separate times across the session, including four dashboard-edit rounds in one evening and a 100k-token research agent spawned just to map API denials to current permission-picker names. Secrets leaked into transcripts twice (a shell fallback expansion printed a Google credential; a developer token was inlined in a command). With no scripted read path, agents grepped mb's installed source to reverse-engineer the keychain service name, and read the keychain raw dozens of times. Token rotation desynced sibling repo-scoped refs. Google access tokens expired hourly with no refresh token stored, requiring an interactive rescue. Live-vs-test key mixups were caught only by agent prefix-checking.

Engine implication: `mb connect` must become the credential plane it was reached for. Scope manifests per provider workflow with a doctor probe that names exact missing dashboard permissions; a supported non-interactive read path; rotation that syncs every ref; refresh-token storage; key-shape/mode validation at intake; and a hard rule that secrets never pass through model context. [exists: #807, #812, #817, #656 (preflight)]

### 2. "Done" was not verified — provider writes and deploys succeed silently wrong (recurring 06-03 → 06-11; live money at stake)

> "It seems like this ad just got messed up... There was no destination... Could you have validated if these things threw any errors?"
> "deploy failed. see wrangler logs"

What happened: Meta's Graph API returned success while silently stripping params, producing ads with wrong images and no destination — caught visually by the operator, never by the agent. Two agents on 06-11 declared live form ads "broken" off a narrow field read and recommended pausing real spend; a screenshot disproved them. Pages deploys failed silently twice while the agent declared features live. A CSP bug that would have stranded every paying customer post-checkout passed every server-side check and was caught only by a human-driven real-browser walkthrough. The operator's verdict: "the operator should never be the first preview renderer."

Engine implication: provider-write verify discipline as an enforced contract — read-back assertions plus rendered-preview or dashboard-receipt evidence before any "done" report; hard-won provider gotchas (full-creative-JSON-grep rule, 5×5+placement canon, deploy-status-not-URL checks) shipped as engine knowledge, not session lessons. [exists: #808, #656, #816]

### 3. Save state, branches, and PRs — the durable-memory contract isn't worktree-real (06-01, 06-02, 06-05, 06-08, 06-11)

> "PR #143 is already MERGED (you merged it). My 'flip to live' hub commit pushed to that branch *after* the merge, so it's sitting on the branch, not in main."
> "what does this mean. Is there a pr to merge or what"

What happened: three stranded-commit incidents on day one alone (operator merges PRs from his phone; agent keeps committing to the dead branch). Hub worktrees ran perpetually behind main, forcing a manual branch-off-main → PR → squash-merge dance for every decision (five times in one day); PR #156 hit conflicts against 13 parallel-landed PRs. Commits sat unpushed for hours; research-backed lander improvements sat unmerged while paid traffic pointed at those pages. `mb checkpoint` was used exactly once in eleven days — the de facto save path is raw git + `gh pr create`.

Engine implication: branch/PR-state awareness as a primitive — detect merged-PR branches before committing and auto-rebranch; surface unpushed/unmerged/dirty state across all business repos as ranked actions; make checkpoint PR- and worktree-aware or formally bless the raw-git+PR path skills currently contradict. [exists: #741]

### 4. Subagent fleets fail silently and lose work (06-03, 06-04, 06-06, 06-07, 06-08, 06-10)

> "I don't know why but the persona-driven chatbot stuff stopped maybe accidentally. But it was discovering findings and it was working pretty hard. Hopefully that's salvageable."
> "Hows subs doiny? Are we waiting"

What happened: agents stalled silently under over-parallelization and were discovered only by file-mtime forensics; one fleet's findings were lost entirely because nothing was written to disk. A keystone money-path agent died mid-verification leaving deployed-but-uncommitted code. Two fix agents sat dead for ~80 minutes while the orchestrator waited blind. Parallel writers tangled a shared checkout three separate times; a `git add -A` swept another agent's in-flight work; an accidental task kill left a live ad with a broken creative.

Engine implication: ship the subagent operating contract as engine guardrails — commit-before-return enforced and verified by orchestrators, worktree-per-agent isolation by default, liveness monitoring and concurrency limits, resumable/idempotent provider-mutation tasks. [exists: #820 (doctrine home); enforcement is new]

### 5. Stale facts and doc drift poison every downstream agent (06-02 → 06-11, systemic)

> "We are US-based only. We are not California-only. I'm not sure why agents keep thinking we're California-only. There must be a stale reference to California somewhere."
> "\"**The unified demo wrapper does not exist.**\" false?  in the flow doc maybe more places?"

What happened: one stale audience line in a shared legal config misdirected legal and marketing agents across multiple days. Live-but-marked-planned doc claims misdirected builders repeatedly; a hub decision file falsely claimed a delivery gate was DONE. Bet and offer files carried retired pricing. OG image, meta description, ad-push docs, and issue copy all carried superseded offer framing — every staleness sweep was operator-triggered, never engine-triggered. Two agents independently rediscovered the same undocumented platform mechanic.

Engine implication: drift detection beyond cross-refs — docs-vs-code, decision-vs-implementation, push-vs-provider reality, derived-surface propagation when core offer files change, and one canonical home for business facts (audience, geography, stage) that all agent-readable surfaces are checked against. [exists: #796 (classifier groundwork); the drift checks are new]

### 6. The enforcement plane gets routed around when it's broken or noisy (06-01, 06-02, 06-09)

> "mb validate itself crashes (IndexError, rc=1) - a tool bug, not our content"
> "mb ads meta summary is privacy-bounded by design — qualitative only, no raw numbers even with the spend flag."

What happened: `mb validate --cross-refs` crashed and `--json` produced no stdout, so the agent hand-rolled existence checks; pre-existing validation debt (22 errors) meant validate output was ignored all session. The one time `mb status` ranked actions were consulted, the top action was dismissed as worktree noise. After connecting Meta *through* mb, every real funnel readout — including the scheduled daily brief — bypassed `mb ads` for raw Graph API calls because the privacy bound withheld the owner's own numbers.

Engine implication: fix the validate crash and guarantee parseable JSON on failure; make ranked actions worktree-aware; add an operator-owned real-numbers mode to `mb ads`. Noisy or broken enforcement trains operators to route around the entire plane. [new]

### 7. Skills silently unavailable in worktrees (06-01, 06-10; root-caused in PR #811)

> "My skills seem to disappear from the work tree all the time for instance in Claude Code. So it makes me wonder if I should just have a plugin anyway."

What happened: the session opened with `/mb-start` missing from a fresh worktree (manual `mb skill link` recovery), and an entire operating day on 06-10 ran with zero `/mb-*` skills because the router writes gitignored symlinks that worktrees never materialize. Separately, 43 third-party skill symlinks with the operator's absolute paths were committed into the shared five-person hub, broken for everyone else. The system's own author was losing his own skills daily.

Engine implication: plugin-first skills distribution (the PR #811 decision), with `mb update` absorbing churn so members never hand-repair skills; per-machine, gitignored link output; a validate gate against committed machine-specific symlinks. [exists: #804]

### 8. Automation and loop state is invisible (06-10, 06-11)

> "i dont see the goal running. /goal like this ... sorry i mean /loop i dont see a loop. active now for tongith"
> "I thought you were in a loop. There's all kinds of stuff in the backlog of your loop too right?... Did we set that up correctly?"

What happened: the overnight loop self-terminated hours before the operator noticed; nothing surfaced its ended state. The operator confused /goal vs /loop; the agent built a nightly cron when the operator meant a steered all-day loop, requiring the LOOP-STATE.md pattern to be invented. All crons are session-bound and die with the chat. Long-running watchers died when parents returned, couldn't be redirected, and were once accidentally killed wholesale.

Engine implication: one legible automation surface — armed loops/crons/wakeups, next fire time, last run, standing agenda — in status or the daily pulse; named scaffolds for both shapes (steered dev loop with a LOOP-STATE contract vs unattended cron); durable scheduling that survives sessions. [exists: #813; LOOP-STATE seeded in this repo via #821]

### 9. Agents inventing decisions the operator never made (06-01, 06-02, 06-08, 06-10)

> "Also i never said to make a form. And i wasnt exaxtly locked on what wed have peiple signuo for but i can guarantee u i wont be taking calls"
> "but now only 1 primary n 1 headline which isnt right. should be the 5 each"

What happened: the agent invented and shipped a call-based conversion mechanism across a live 8-page site, costing a full day of rethink. A production model choice happened because a subagent found an API key in the environment. An API error led to a silent downgrade of a stated 5×5 creative requirement, later carried as false doctrine. An agent self-imposed an opt-in consent regime stricter than law, costing conversions until legal skills corrected it.

Engine implication: conversion mechanisms gated and recorded before copy generation; silent requirement downgrades flagged as deviations needing sign-off; provider/model adoption recorded with provenance; business-stage facts (pre-revenue, pre-launch) as deterministic inputs that flip defaults like back-compat-preservation. [exists: #650 (stage gating), #656; conversion gate is new]

### 10. Operator-only steps and capability discovery live in chat scrollback (06-01, 06-05, 06-06, 06-10)

> "Im no longer in front of my computer. What 2 clicks"
> "Do we have an offer sharpening skill to look at here? Do we have our offer recorded not just in a decision or research in the hub's core...?"

What happened: manual human-only actions (legal agreements, credential mints, UI-only toggles) accumulated as renumbered click-lists in chat the operator lost track of. The daily operator couldn't recall which skills exist for offer work, misremembered Impeccable's distill mode as "Instill," and three times in one evening had to ask the agent to translate its own vocabulary ("kernel," "ratify," "frames") into plain language.

Engine implication: a durable needs-operator action queue surfaced in status and the daily brief; fuzzy skill/mode resolution in mb-help plus a findable glossary; and "business language first" enforced as a hard gate on skill prose and decision docs. [exists: #813 (queue's natural home); discovery work is new]

## Primitives coverage map

**Exercised heavily**
- **decisions** — the workhorse. Created or amended on 9 of 11 days; the place operator voice memos, pivots, pricing rulings, and architecture calls crystallized. But every one was recorded via raw git + PR; no mb flow mediated a single decision.
- **research** — extremely heavy (multi-agent fleets, external Grok/Codex dumps, Apify scrapes), with chronic placement confusion (hub vs product repo vs personal repo, one leak into the public hub) that produced #805.
- **offers** — `offer.md` rewritten or reconciled at least six times as the offer evolved; a per-offer `audience.md` and offer-folder `playbooks/` were invented mid-session because the structure didn't exist.
- **bets** — the business bet framed the whole arc (deadline, kill rubric, spend cap, checkpoint reframe), but hygiene was always retrofitted by hand: no spend cap or milestone until the operator demanded it, stale pricing twice, never touched through `/mb-bet`.
- **pushes** — used for launches and ad batches, and the source of the richest schema findings: no slot for binary creative location (#803), no enforced contract, unclear locked-record semantics once a push is live/canceled, and push claims drifting from the live ad account.

**Exercised lightly**
- **playbooks** — paradoxically the most *generative* primitive (resend-playbook, golden-path-playbook, leads-ads-method, agent-access-dossier, operating-principles all emerged and were tagged for graduation) yet every one landed via raw `Write` + git; the mb playbook surface itself was never used.
- **checkpoints** — exactly one `mb checkpoint` in eleven days (the 06-09 `/mb-think` run, where the approval gates held perfectly). Otherwise durable state lived in compaction summaries, session task lists, and hand-rolled "state docs" — including one live double-send risk that survived only because an auto-summary happened to be thorough.
- **graph links / repo topology** — invoked by the operator as the tool that should govern "what becomes a repo," found stale, rewritten by hand.

**Never exercised**
- **outcomes** — zero. Shipped-vs-verified, agent-claimed-vs-operator-verified, and "show me X" commitments all lived in conversation.
- **/mb-end and checkpoint guidance as a closing ritual** — never run, even on the canonical daily-loop day.

**What this says about the product.** The memory primitives (decisions, research, offers) are genuinely where this operator's durable state wants to live — the thesis holds, and continuity across two compactions and a full restart proved it. The enforcement and ritual primitives (checkpoint, validate, ranked actions, bookend skills) lost to raw git the moment they were noisy, heavy, or worktree-unaware. And the loop's real center of gravity — subagent orchestration, provider mutations, verification, scheduling — is where mb currently has almost no surface at all. The operator filled every gap by hand-rolling exactly the deterministic enforcement plane mb is supposed to be (state docs, golden paths, canaries, delivery-truth ledgers, capability dossiers, LOOP-STATE). That hand-rolled inventory *is* the engine backlog, and most of it is now filed as #812–#820.

## Skill + CLI usage

**mb CLI.** Real invocations clustered at the start and at explicit "do this properly" moments: `mb start`, `mb skill link`, `mb status --json --peek`, `mb update`, `mb doctor`, `mb validate` (incl. `--cross-refs`, `--json`), `mb connect` (cloudflare, meta, google; `status`, `list`, `test`, `hydrate`, `doctor`), `mb ads meta summary`, `mb checkpoint --plan --json`, `mb skill validate --all --json`, `mb image smoke-fal --help`. Six of thirteen chunks — including the heaviest build days (06-03, 06-04, 06-05, 06-07, 06-08) and both 06-11 chunks — show **zero** mb CLI invocations. Where mb was used, it was mostly a linter (`validate`) and a vault (`connect`), not a flow.

**/mb-\* skills.** `/mb-start` ran on 06-01 and 06-02 (and proved its worth as the post-crash re-grounding ritual), `/mb-site` ran the day-one minisite flow, and `/mb-think` ran once properly on 06-09 — the single occasion the full research → decide → codify → checkpoint contract executed, and it worked as designed. `/mb-ads`, `/mb-bet`, `/mb-end` were referenced as the intended path but never invoked. On 06-10 the skills were physically absent from the worktree (#804).

**Third-party skills carried the load.** `/impeccable` was the single most-used skill of the session — invoked on essentially every day, across nearly every mode (shape, craft, critique, audit, harden, polish, layout, typeset, distill, document, extract) and codified into the operator's binding subagent-prompt format ("/impeccable should always be the first word"). The Anthropic legal plugins (privacy, product, ai-governance) resolved real opt-out, disclosure, and multi-state questions. The 43 "Corey" marketing skills powered audience and email work. caveman, stripe, wrangler, resend, last30days, deep-research, web-perf, and `/loop` all saw real use.

**Notable patterns.** (1) Skills compose into subagent prompts — that's the operator's primary consumption mode, and it works, including plugin skills inside subagents. (2) The operator hands skills to the agent mid-session as provider knowledge injections (wrangler, resend) — evidence that bundled provider playbooks save real time. (3) Third-party rails were more load-bearing than mb's own rails all session, which the 06-10 identity memo reframed as the kernel-that-curates thesis: mb owns state, credentials, doctrine, and cold-start; best-in-class skills are curated dependencies. (4) Skill/mode discoverability is weak even for the system's author (misremembered names, forgotten vocabulary, "do we have an offer sharpening skill?").

## Engine work this suggests

Deduplicated and tagged against open issues. Items marked [exists] should absorb this report as field evidence rather than spawning duplicates.

**Credentials and providers**
1. Generic/custom provider path in `mb connect` plus first-class Stripe and Resend providers — the operator's first instinct was mb both times, and the entire money/email credential lifecycle ran outside it. Include prompt-based hidden-input secret intake with key-shape/mode validation (test vs live prefixes, refuse empties). [new]
2. Scope manifests per provider workflow + a doctor probe that maps API denials to exact current dashboard permission names; capability dossier scaffolded at setup and verified by doctor. [exists: #817]
3. `mb connect token <provider>` read path for scheduled/headless agents, ending raw keychain reads and source-grepping. [exists: #812]
4. Token rotation needs an explicit repo boundary. Cross-`repo_id` sibling
   syncing is unsafe; #959 preserves repo-indexed fallback while preventing
   rotation from rewriting another business's credential. [supersedes #807]
5. Refresh-token storage and guided OAuth bootstrap for Google-class providers; store canonical business identities (page, ad account, pixel) as connect metadata so agents never infer identity from live provider state. [new]

**Verification and money-path safety**
6. Provider mutation preflight gates + verify receipts: read-back assertions, rendered-preview evidence, deploy-status (not URL) checks, and a "where to see it" pointer attached to the record. [exists: #656]
7. Ship validated Meta creative shapes and API gotchas as engine knowledge in mb-ads. [exists: #808]
8. Golden-path canary scaffold with layered verification doctrine (browser-layer per-PR, cron real-browser prod, deep-audit agents) and plain-language alert format. [exists: #816]
9. Delivery-truth pattern: provider send id + delivery state stamped at send, flipped on bounce/suppress, paged on failure. [exists: #815]
10. Contact + event spine scaffold including send/delivery events so "did we email this lead?" is answerable from the system of record. [exists: #814]
11. Production-mode flip: an mb-owned lifecycle stage that turns on branch protection, required checks, and canary-as-merge-gate when an offer starts taking real money — improvised twice with raw `gh api`. [new — natural extension of #650's MoneyPath stages]

**Save state, drift, and memory**
12. Owner-facing save-state facts: merged-PR branch detection with auto-rebranch, unpushed/dirty/unmerged inventory across hub and linked repos, worktree-aware ranked actions. [exists: #741]
13. Fix the `mb validate` cross-refs crash and guarantee parseable `--json` output on failure; add scoped (my-files-only) validation so agents stop hand-rolling filters against legacy debt. [new]
14. Drift checks beyond cross-refs: decision-vs-implementation, docs-vs-code staleness, push-vs-live-provider reconciliation, propagation sweeps across derived surfaces (OG/meta, ad copy, email templates) when core offer files change. [new — builds on #796's repo-role classifier]
15. Push contract hardening: validator-enforced frontmatter, media_location/media_backend, and explicit locked-record semantics with a sanctioned reconcile path. [exists: #803; lock/reconcile semantics new]
16. Research-placement contract in /mb-think and engine docs. [exists: #805]
17. `mb offer graduate <slug>` with a recorded trigger. [exists: #806]
18. Bet hygiene: surface incomplete bets on running offers (no target, no spend cap, blank result), easy milestone logging, checkpoint-style bet frames, effort-currency appetite. [exists: #818; hygiene surfacing partially new]

**Orchestration and automation**
19. Subagent operating contract as enforced engine guardrails: commit-before-return verified by orchestrators, worktree-per-agent isolation, liveness checks, read-only-audit vs change-agent separation, docs-read-first, stale-doc cleanup on completion. The operator dictated all of this verbally at least three separate times. [new — doctrine home is #820]
20. Daily pulse + needs-operator action queue: armed loops/crons with next-fire and last-run, open PRs, operator-only blockers, business-stage facts. [exists: #813]
21. Human-vs-bot traffic reconciliation recipe for the pulse. [exists: #819]
22. Graduate the twelve operating principles into engine doctrine. [exists: #820]
23. Durable scheduling and loop bootstrap: LOOP-STATE-style steered-loop contract vs unattended cron as named, scaffolded shapes; loop handoffs renderable by mb instead of hand-written markdown in a personal repo. [new — LOOP-STATE seeded via #821; pulse adjacency in #813]

**Skills, routing, and onboarding**
24. Plugin-first skills distribution so skills survive worktrees, with the mb-ads engine-root path dependency resolved first. [exists: #804]
25. /mb-start as universal intake router, including teammate intake ("I have ads" routes a collaborator into the push flow with zero protocol knowledge) and issue-vs-push routing encoded in the engine, not operator memory. [new — adjacent to #828's setup-prompt canonicalization]
26. Conversion-mechanism gate in mb-site: what people sign up for and whether the operator takes calls is an explicit recorded decision before page copy is generated. [new]
27. Fork-scaffold descriptor check: `mb site check` validates that inherited `.mainbranch/repo.json` / `conversion.json` point at the current business, preventing cross-business leakage. [new]
28. Operator-owned real-numbers mode for `mb ads` summaries — the privacy bound currently makes the primitive unusable for the owner's daily loop. [new]
29. mb-help fuzzy skill/mode resolution plus a vocabulary glossary (push, bet, offer ladder, skill mode names), and a business-language gate on skill prose and decision output. [new]

The strongest single meta-signal: on the days this business shipped the most, mb was used the least. The product loop to preserve is real — the primitives caught everything durable — but the deterministic plane has to meet the operator inside worktrees, subagent fleets, and provider dashboards, or it keeps getting reconstructed conversationally, one session at a time.
