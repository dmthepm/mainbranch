# Router and Language Contract

`/mb-start` is the business router. It should feel like the operator opened the
business and the system remembered where they are, what changed, and what kind
of work their current words imply.

Use this reference after `mb status --json --peek` is available and before
presenting a menu.

This operationalizes the repo-wide contract in `AGENTS.md`, generated business
repo guidance in `templates/`, and `mb educational git-history-vs-cloud-sync`:
git remains the durable memory layer, but the operator hears business language
first.

---

## Routing Order

1. If the user stated a live intent, route that intent before showing generic
   ranked actions. Ranked actions are for open-ended starts such as "what should
   I do next?", not for overriding "set up bookkeeping" or "save this."
2. Apply hard gates first: required Main Branch update, broken repo wiring,
   missing business repo, provider danger, private-data boundary, or destructive
   operation.
3. Use status facts as evidence: `ranked_actions`, `update`, `readiness`,
   `onboarding`, `drift`, `integrations`, `github`, `brain`, `checkpoint`,
   `since_last_check`, `journal`, and `money_path`.
   When `money_path.objects.proof.quality.public_marketing.status` is
   `blocked`, route public ads/pages/claim work to proof permission collection
   before recommending proof-backed campaigns.
4. Choose the smallest useful next workflow. Do not present the full route menu
   when a clear intent maps to one route.
5. If two routes are plausible, ask one business question that separates them.
   Example: "Is this bookkeeping setup, or are you trying to decide the tool?"

---

## First Screen Shape

For a normal returning session, answer in this order:

1. Working context: business name and the plain-language sync state.
2. Update posture: strongly recommend updates when available, especially when
   the user's stated intent touches a feature added after their installed
   version.
3. Where we left off: 1 to 3 business-readable facts from status, without raw
   hashes or branch names.
4. Current route: the inferred workflow or one compact choice list.

Avoid "Something else" as the main escape hatch. Use "tell me what you came here
to do" only after showing the likely business routes.

---

## Save and Sync Vocabulary

Use business words first. Keep technical terms available only when they are the
exact command, validation evidence, or the operator asks for git details.

| Technical state | Default operator language |
| --- | --- |
| commit | saved checkpoint |
| uncommitted changes | unsaved local work |
| dirty files | local files with unsaved changes |
| push | sync saved checkpoint to the shared repo |
| pull/fetch | catch up with the shared repo |
| rebase | reconcile local saved work with newer shared work |
| ahead | saved locally but not synced |
| behind | newer saved work exists in the shared repo |
| diverged | both your local repo and the shared repo have newer saved work |
| branch/worktree | workspace |
| conflict | the same file changed in two places |
| hash/SHA | checkpoint id |

Do not print checkpoint ids, branch names, `origin`, `ahead`, `behind`,
`diverged`, `rebase`, or `commit` in the first response unless they are inside a
command the user must run or the user asked for technical detail.
Do not put raw git/GitHub terms in parentheses after the translation; use a
separate "Technical detail:" or "Exact command:" line when the raw term is
actually needed.

Before answering a normal owner prompt, translate raw status summaries that leak
from tools:

| Tool phrasing | Owner-facing translation |
| --- | --- |
| `git is clean`, `repo is clean`, `working tree clean`, `working tree: clean`, `clean on main` | nothing unsaved locally |
| `on main`, `branch main`, `branch: main`, `current branch: main` | current business folder or current workspace |
| `one commit`, `only commit so far` | setup baseline saved or last saved checkpoint |
| `staged files` | files queued for save |
| `No GitHub origin remote`, `No origin remote`, `Connected GitHub backup: none surfaced` | local-only folder or no connected GitHub backup |
| `origin remote` | connected GitHub backup or shared task source |
| `PR/issue facts`, `PR and issue facts` | GitHub task and proposal context |
| `before this goes to a remote` | before anything is shared outside your machine |

Good pattern:

> "Your bookkeeping setup is saved locally. The shared repo also has one newer
> saved change, so reconcile before syncing."

Avoid:

> "Local and origin have diverged. Run `git pull --rebase` before pushing."

---

## Update Posture

When `status.update.severity` is `recommended` or `required`, make the update
the only recommendation the operator sees before business routing. Do not show
ranked actions, drift, GitHub facts, or next business moves until the operator
updates or explicitly chooses to continue. Name the installed and latest
versions if present and say how many version steps are behind when the numbers
are obvious.

If the status report includes `update.release_notes_url`, release highlights, or
ranked update actions, use those facts. If the user asks what changed and status
includes `update.update_check_command`, run that dry-run and use its
`release.summary` or `release.url`. If no release context is available, say the
user may be missing recent routing, repair, or skill fixes; do not invent exact
release notes.

Use direct, non-technical language:

> "Update strongly recommended: mb 0.3.15 -> 0.3.17. You are two versions behind,
> and the update brings recent routing, repair, and skill improvements. I
> recommend updating before we continue. Want me to update it for you?"

If the update is required, run or route to the cited update command before
business work.

If the update is recommended, pause and ask for the choice before open-ended
business routing. If the operator declines, continue on the installed version
and keep the stale-version note visible in the session summary.

Only show the command if the operator asks what will run or if automatic update
fails. In that case, show the exact command from `status.update.command` or fall
back to `mb update --repo . --json`, then explain the manual next step in plain
language.

---

## Intent Clusters

### Save, checkpoint, wrap, sync, publish

Signals: save, saved, checkpoint, wrap up, closing out, end my day, sync,
publish my saved work, share for review, pull request, PR, proposal, catch up,
reconcile, shared repo, newer work.

Route:

- If ending the session, use `/mb-end`.
- If saving progress midstream, run `mb checkpoint --plan --json`, then validate
  and save after approval. Checkpoint message examples must name the saved
  business artifact, such as `[updated] offer and founder-call research`; avoid
  broad buckets like `[updated] core and research`, `[drafted] files`, or
  `[ran] changes`.
  The verb must be one `mb checkpoint --validate "<subject>" --json` accepts;
  it lists them. Do not coin one from the action: a repair is `[fixed]`, a
  migration or update run is `[ran]`, a move or rename is `[updated]`. Run
  `--validate` before showing the operator a subject or command.
- If local/shared repo state is involved, explain it with the save/sync
  vocabulary above. Do not prescribe a rebase in first response; say reconcile
  unless technical detail is needed.
- If the user asks to publish, open a PR, or share work for review, use status
  `git.workflow_mode`, `git.summary`, and GitHub facts to explain whether this
  is a saved checkpoint, a sync, or a proposal/review path. The planned
  `mb publish --plan` and packaged publish skill are not shipped yet;
  do not pretend they exist or load ad hoc PR-instruction attachments.

### Bookkeeping, books, finance, accounting

Signals: bookkeeping, books, finance, accounting, monthly close,
reconciliation, CPA handoff, chart of accounts, P&L, ledger, bank statements,
restricted finance child repo, restricted repo topology, hledger, receipts,
tax, payroll, revenue report.

Route:

- Run `mb books check "$REPO_PATH" --json` before inventing structure.
- For books setup, monthly close review, reconciliation review, or CPA handoff,
  route to `/mb-books` after the books check.
- For betting, spend, or risk intent, start from `mb status --json --peek`.
  Read `money_path.policy` and `money_path.active_bets` before recommending
  execution. If an active bet is unanchored, over cap, or thresholds are
  missing, route to `/mb-bet` or `/mb-think` before spend.
- For offer or pricing work that would cause spend, use the offer/bet/push/proof
  rubric before deciding whether this is durable offer truth or a MoneyPath bet.
- Keep raw ledgers, statements, credentials, account numbers, payroll rows, tax
  IDs, and exact private numbers out of the public/team-safe business repo.
- Preserve public topology terms: hub repo, child repo, hub registry
  `core/operations/repo-topology.md`, child descriptor `.mainbranch/repo.json`,
  role `finance`, and visibility `restricted` or `local_only`.
- Use the books contract fields, especially `storage_mode`, and the repo
  topology role `finance` with visibility `restricted` or `local_only` to
  decide where raw books belong. The hub repo should keep only safe summaries,
  decisions, and links.
- If the user is deciding tooling, route to `/mb-think` after the books check.
- If the user is setting up the safe repo contract, draft or update the safe
  finance files named by the books check. Do not create generic finance files
  that bypass the contract.

### Provider and tool setup

Signals: connect, provider, Cloudflare, GitHub, Google, Workspace, Meta Ads,
Stripe, hledger, Apify, Postiz, Cal.com, token, API key, deployment, DNS,
calendar, booking.

Route:

- Read `status.integrations` first.
- Run `mb connect plan` or `mb connect doctor --json` when status says a
  provider is missing, degraded, or needed for the stated route.
- Explain the business capability first, then the command.
- Never ask the user to paste secrets into repo files or chat.

### Repair, update, drift

Signals: broken, not showing up, stale, migration, old layout, warnings, validate
noise, repair, update, missing links, cross refs.

Route:

- Required update or stale skill wiring comes before output work.
- Use `mb doctor repair --plan --json` for repo drift.
- Use `mb validate --cross-refs` only when relationship/link health is the
  stated task or status points there.

### Path to money, revenue, offer readiness

Signals: path to money, revenue, make money, next dollar, what sells, paid step,
CTA, offer readiness, product ladder, proof, launch readiness, sales path.

Route:

- Keep hard gates first. Required updates, broken wiring, unsafe provider
  operations, private-data boundaries, and repair blockers pause business
  routing before MoneyPath interpretation.
- Required update, broken install/runtime/wiring, repair blockers, validation
  blockers, relationship health blockers, playbook health blockers, and unsafe
  provider/private-data blockers all win before MoneyPath routing.
- Use the `money_path` object from the already-run `mb status --json --peek`
  report. Parse the full status JSON once; do not slice it with `head`, `sed`,
  or partial shell chunks that can drop late-added sections.
- Start the first business interpretation from `money_path.overall_level`,
  `money_path.overall_label`, `money_path.objects.offer`,
  `money_path.objects.proof`, `money_path.objects.product_ladder`,
  `money_path.objects.cta_path`, `money_path.objects.channel_strategy`,
  `money_path.objects.active_push`,
  `money_path.objects.outcome_feedback_loop`, and
  `money_path.ranked_actions`.
- Translate the facts. Name the current bottleneck and gaps in business
  language without dumping JSON and without conversion judgment.
- Explain whether top-level `ranked_actions` agree with the MoneyPath
  bottleneck. If they disagree, say which gate or route is taking priority.
- Only after that, read supporting offer, product ladder, decision, research,
  finance-summary, push, or channel files for judgment.
- If routing to `/mb-think`, include a MoneyPath snapshot in the handoff so the
  worker starts from the same facts.

Good handoff shape:

> "MoneyPath snapshot: overall Level 2 / structured. Bottleneck: CTA path
> missing. Proof exists but is generic and not outcome-backed. Offer is
> structured but missing risk reversal. Product ladder is stated but has no
> clear paid entry step. Channel strategy exists, but no active push is
> attached. Outcome feedback loop is missing. Recommended route: use `/mb-think`
> to clarify the paid entry step and CTA before creating more content or ads."

Avoid:

> "Your offer is bad."

> "This will not convert."

> "This will convert."

> "The business is weak."

> "This is ready to win."

### Decide, codify, research

Signals: think, decide, figure out, explore, research, compare, tool decision,
strategy, positioning, offer, audience, voice, soul check, vendor choice.

Route to `/mb-think`, with `codify` when the task is to turn known context into
durable repo truth.

Observations and readouts ("I noticed", "the numbers show", "this week's
read") route to `/mb-think` research-only for a concise evidence-backed
readout; a changed course ("we should stop or switch", "change of plan") adds
a linked decision in the same approved session. Ask before writing either
file. Summarize numbers and cite the source; never save raw provider rows,
account IDs, customer data, or exported tables. A status-only request such as
"where are we" or "what changed" gets a status answer without proposed
research or decision. If an observation changes a measurable trial's target
or cut point, use `/mb-think` for the readout and linked decision, then update
or link the existing bet through `/mb-bet` after approval before continuing.

### Stale source, claim, or angle cleanup

Signals: stale source, old source, outdated file, obsolete claim, retire this
claim, retire this angle, stop using that proof, not true anymore, old offer
detail, old SOP.

Route to `/mb-think` stale-source cleanup. Start from `mb status --json --peek`,
then have the worker identify the stale item, find downstream usage, reconcile
current `core/` and per-offer files, record a decision when durable truth
changes, and offer a business-readable checkpoint. Do not ask the operator to
inspect a git diff as the primary workflow.

### Bets, pushes, sites, ads, organic, wiki

Signals and routes:

- bet, wager, deadline, metric, result, outcome: `/mb-bet`
- launch, push, playbook, offer launch: launch orchestration, then `/mb-think`,
  `/mb-site`, `/mb-ads`, or checkpoint as the current step requires
- content strategy, distribution strategy, channel strategy, account strategy,
  founder voice, weekly content plan: `/mb-think` to codify the strategy layer,
  then `/mb-organic`, `/mb-site`, or `/mb-ads` for output
- site, landing page, lander, minisite, publish: `/mb-site`
- ads, Google Ads, Meta Ads, make an ad from this video, compliance: `/mb-ads`
- organic, reels, TikTok, LinkedIn, carousel, short clips or social cuts from a sales video or VSL: `/mb-organic`
- wiki, notes, public knowledge base, atomic notes: `/mb-wiki`
- confused, help, explain the system: `/mb-help`

---

## Dead-End Avoidance

- Do not let generic "set up" override the specific noun. "Set up
  bookkeeping" routes through books; "set up Cloudflare" routes through
  provider checks; "set up the repo" routes to `/mb-setup`.
- Do not turn every returning session into triage. Triage is for open-ended
  prioritization or explicit deep review.
- Do not show raw recent checkpoint ids as proof of continuity. Use journal
  summaries and file/topic names.
- Do not blindly catch up the business repo from the shared remote. First
  explain the sync state and ask before changing local saved work.

---

## Continuity Facts

**Continuity facts:** Use `since_last_check.journal`, top-level `journal`,
GitHub activity, and `checkpoint` from status to explain "where we left off."
Do not run raw `git log` unless status says journal facts are unavailable.
If `core/operations/pulse/` exists, read today's `log/<date>-*-pulse.md` and
carry its ONE action into the session open (offer the pulse skill if missing).
