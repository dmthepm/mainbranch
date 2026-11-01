# Post-Release Alignment Playbook

Main Branch is moving quickly with multiple concurrent branches. The repo
needs a durable post-release habit so future cold starts, agent reviews,
docs, decisions, and roadmap issues do not drift from the current product
stance. This playbook is the standard sweep to run after every
package-visible release, plus the safe pattern for running multiple
branches in parallel.

Run the same sweep before a package-visible release when a batch changes the
agent contract itself: shared workflow sources, generated runtime guidance,
runtime support claims, release validation, or public/private evidence policy.

It complements the release runbook (`docs/release-simulations.md`), the
release-agent contract (`docs/release-agent-contract.md`), the
OSS operating checklist (`docs/oss-operating-checklist.md`), and the
agent operating contract (`AGENTS.md`). This file owns *post-release
alignment* and *parallel-work hygiene*. Do not duplicate product facts
that live in those documents — link them.

Tracked in MAIN-323 / #490.

## 1. Post-release sequence

After a release merges and publishes, the standard next steps before the
next parallel batch:

1. Merge / release ships (tag, GitHub Release, PyPI publish, Linear release
   sync — see `docs/release-simulations.md`).
2. Pin the plugin to the release commit with its own PR and read back an
   install at that commit (`docs/release-agent-contract.md` Rule 8). Owners
   keep the previous release until this lands.
3. Align Linear and GitHub issue state: close the release-prep issue, comment
   release evidence on GitHub by default so the public thread and Linear mirror
   agree, mark Linear issues shipped via Linear release completion (not on
   merge).
4. Audit release simulation transcripts when the release touched package,
   runtime, first-run, generated guidance, or operator workflow behavior. Use
   the transcript audit below.
5. If a pre-release security sidecar such as DeepSec ran, review the sanitized
   result alongside the release evidence. Route confirmed product gaps to
   GitHub issues or a public-safe report; keep raw logs, local paths, model
   traces, and private security details out of public docs.
6. Align repo docs and decisions if anything shipped changed the product
   stance. Use the alignment sweep below.
7. Audit agent cold-start guidance when the release taught a new protocol,
   review habit, validation rule, or task-triggered read path. Use
   `docs/agent-cold-start.md` as the public source of truth.
8. Align local agent preferences only when a private local workflow reminder
   changed. Use the local-preferences policy below.
9. Start the next parallel batch.

## 2. Alignment sweep

Run this after every release whose surface changed something agents,
operators, or contributors read:

- Review merged issues and PRs since the last tag (`git log oe-vX.Y.Z..main
  --oneline`). For each surface that shipped, check it is described in
  present tense in docs and generated guidance, not future tense.
- Update or remove future-tense language for shipped commands, validators,
  JSON fields, and decisions. Keep the deferred items as deferred — do not
  promote them.
- Update agent cold-start guidance (`AGENTS.md`, `CLAUDE.md.tmpl`,
  `AGENTS.md.tmpl`, generated repo instructions) only if a new decision
  changed how agents should think about the repo.
- Check for stale assumptions: an old engine choice, a deprecated provider
  recommendation, a removed file path, a renamed surface. Surface these as
  follow-up issues if the cleanup is larger than a paragraph.
- Confirm CHANGELOG, README, and roadmap language matches the facts. A
  release is not done until the surfaces agree (see `AGENTS.md` →
  Release Truth).
- Confirm `docs/agent-cold-start.md` still tells agents which docs are
  always-read and which are task-triggered. Do not push release-specific
  instructions into local preferences when they belong in public docs.
- Before a package-visible release, run this same sweep after the last
  release-bearing branch merges and before the release-prep branch. The
  release-prep branch should then only package the already-aligned truth.

Default to a small alignment PR labeled `[docs]`. If the sweep finds nothing
worth changing, write that as a one-line comment on the release-prep issue
and move on.

## 3. Release Simulation Transcript Audit

Run this audit after package-visible releases and after any release whose
changes touched runtime claims, first-run handoff, generated instructions,
release validation, or a core operator workflow.

The audit asks a product question: what did the simulations prove, what did
they fail to prove, and what should change before the next release naturally
does the right thing?

Use this sequence:

1. Read the local release simulation evidence or the release-prep issue. Start
   from `summary.json`, `rubric.json`, transcript
   excerpts, and `evidence-template.md`; do not rerun simulations just to
   recover wording.
2. Compare each run against `docs/release-simulations.md` transcript-review
   categories and the manifest's `must_observe` / `must_not` rubric.
3. Review in two layers: first confirm deterministic proof, then read the
   transcript as an operator session and ask what product affordance, wording,
   repair path, JSON field, fixture, or evidence template would make the next
   run naturally better.
4. Classify each miss as hard failure, quality concern, or product opportunity.
   Name the likely fix type: skill prose, generated repo guidance, CLI gap,
   docs gap, harness gap, runtime behavior, or user education.
5. Route public product gaps to GitHub issues. Use `Closes #N` only when a PR
   fully resolves the public issue; use `Refs #N` for partial slices.
6. Keep private local runtime logs, raw transcripts, local machine details, and
   maintainer-only notes out of GitHub and public docs. If the synced Linear
   issue needs that context, add a Linear-only comment; otherwise keep it in
   private local scratch space.
7. Update `docs/release-simulations.md`, the packaged simulation manifest, or
   the dogfood harness only when the audit finds a repeatable gap that should
   protect future releases.

Write the result as either:

- a public-safe report under `docs/reports/` when the findings should guide
  future reviewers;
- a concise GitHub issue comment when the release passed and no durable doc
  change is needed;
- a focused GitHub issue when the gap is real but belongs to a later branch.

Do not make print-mode proxy evidence stronger than it is. If a release claim
depends on slash-command discovery, the audit must say whether interactive
Claude Code TUI evidence exists or why it was unavailable.

## 4. Parallel work lanes

Lanes that can usually run concurrently without merge chaos:

- **Docs-only** (this file's lane): no CLI module, no `mb/_data/`, no
  templates touched.
- **Feature CLI**: one command surface owned by one branch. Do not parallel
  two branches that both touch `mb/<module>.py`, `mb/cli.py`, or shared
  packaged data unless the conflict surface is explicitly enumerated.
- **Release prep**: only release files (`CHANGELOG.md`, `mb/pyproject.toml`,
  `mb/mb/__init__.py`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`).
  Anything else is its own branch.
- **Noontide / business-model**: lives in the operator's business repo, not
  in this engine. Never on the same branch as engine changes.
- **Review-only**: comment-only PR reviews, no commits.

Conflict rules:

- Two branches touching the same CLI module, docs index, CHANGELOG, or a
  generated template should not run blindly in parallel. The second branch
  rebases on the first after merge.
- Two branches updating the same `decisions/<date>-<name>.md` is a smell;
  one branch should own a decision file at a time.
- Each branch writes a local cold-start note before editing, naming what it
  *will not* touch (the "Out" section). That is the parallel-lane contract.

If a branch discovers it needs to touch a file owned by another in-flight
branch, comment on the other branch's PR before editing. Do not silently
race.

## 5. AI code review ritual

When reviewing any PR, the reviewer (human or agent) checks:

- **Diff correctness**: code does what the PR claims.
- **Decision alignment**: does the PR follow current decisions in
  `decisions/` and the relevant PRDs? If it reopens a settled choice,
  flag explicitly.
- **Stale assumptions**: does the PR build on language that is now stale
  (old engine, old file path, deprecated provider)? Block on stale
  assumptions, not only on bugs.
- **Issue hygiene**: does the PR use `Closes #N` only for full completion
  and `Refs #N` for partial slices? Are Linear IDs preserved in branch and
  commit metadata?
- **CHANGELOG and docs**: user-visible CLI, skill, packaging, compatibility,
  or workflow changes update `CHANGELOG.md` and any docs they invalidate.
- **Public/private boundary**: see `docs/oss-operating-checklist.md`. No
  secrets, no private operator strategy, no machine-specific paths in
  committed files.
- **Release impact**: does this PR change a packaging surface, runtime
  claim, or first-run flow? If yes, it needs the corresponding evidence
  from the validation ladder.
- **Follow-ups**: does the PR leave the right follow-up issues open?

Quote only the changed behavior or the risky line in review comments. Do
not restate the product stance — link the decision file or the doc.

## 6. Local Preferences Alignment

Local agent preferences live outside this public engine repo. This playbook
does not own that private file. It owns the policy that governs what should
and should not be there.

Local agent preferences should:

- point agents to `docs/agent-cold-start.md` for the public read order and
  progressive discovery contract;
- enforce private working protocol that is local to the maintainer's
  environment, such as workspace path, target branch, issue/branch workflow,
  and local tool availability;
- remind agents to check accepted decisions before reopening product choices;
- remind agents during AI code review to check stale assumptions, docs and
  changelog updates, issue hygiene, public/private boundaries, and release
  impact;
- surface durable private review habits learned from recent PRs in a sentence
  or two;
- stay short enough to be read and followed.

Local agent preferences should not:

- duplicate detailed product facts that belong in `AGENTS.md`, `README.md`,
  `docs/agent-cold-start.md`, or decision files;
- repeat the whole product stance, folder map, release model, or validation
  ladder;
- carry stale specifics (old engine choices, outdated provider
  recommendations, old paths);
- include implementation details that agents are already required to read
  from the repo.

After every release, ask:

- Did the release teach us a new protocol, review habit, or cold-start
  behavior? If it helps all contributors, update public docs. If it is local
  private workflow, add it briefly to local preferences. If neither, leave
  preferences alone.
- Did any existing preference duplicate repo docs or become stale? If yes,
  remove or compress it.

If the local preferences file lives in a separate private repo, open a
private follow-up there for the change. Do not block this engine's release on
edits to a separate repo's file.

## 7. Current product stance checklist

Use this list as a quick decision-alignment scan during alignment sweeps and
code review. Each line is intentionally a one-line pointer; the durable
truth lives in the linked doc or decision.

- **Bookkeeping engine**: hledger. The shipped command group is `mb books`,
  but the business function is bookkeeping. Real bookkeeping records live
  in a private bookkeeping vault (solo-local under `.mb/private/books/` by
  default, or a separate team-private repo). See `docs/books.md` and
  `decisions/2026-05-11-mb-books-foundation.md`.
- **Scheduled data sync**: operator-owned cron / `launchd` / Task Scheduler
  running one-shot per-provider scripts, not a hidden daemon. See
  `docs/scheduled-data-sync.md` and
  `decisions/2026-05-11-scheduled-data-sync-pattern.md`.
- **Repo rails**: GitHub is the repo, history, PR, and checks rail.
  Cloudflare is the site, DNS, and deploy rail. GitHub Pages is not a
  default Main Branch site host. See `docs/repo-visibility-rubric.md`.
- **Display vs enforcement**: Obsidian and dashboards are display surfaces,
  not enforcement engines. `mb` keeps the typed business graph and
  validation. See `docs/markdown-link-conventions.md`.
- **Affiliate/recommended-tools monetization**: belongs in Noontide first;
  Main Branch does not add public affiliate links until policy, disclosures,
  and real links are accepted.
- **Language**: plain business language first. Technical terms (canonical,
  schema, primitive) are fine in code comments and contributor docs, not in
  user-facing copy. See `docs/agent-writing-style.md`.
- **Runtime claims**: Claude Code is first-class for slash skills. Codex CLI is
  supported for daily Main Branch routes through generated repo guidance and
  global `mb-*` skills under the Codex skills root. Other runtimes are
  compatibility targets until smoke evidence exists. See
  `docs/compatibility.md`.

If a PR or issue contradicts one of these, treat the contradiction as a
stale-assumption finding and block until reconciled or a new decision file
lands.
