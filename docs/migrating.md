# Migrating Existing Main Branch Repos

This doc owns old clone-era setup, legacy file-layout, and
clone-to-pipx/source-checkout migration guidance. Beginner docs and skills
should link here instead of restating migration procedures.

Main Branch has two repo shapes in the wild:

- **Legacy shape:** old clone-era folders such as `reference/core/`,
  `reference/domain/`, `reference/proof/`, `reference/visual-identity/`, and
  generated `outputs/`.
- **Current shape:** `core/`, `research/`, `decisions/`, `bets/`, `log/`,
  `pushes/`, and `documents/`. `reference/` is compatibility-only for old
  repos and old readers; `campaigns/` is also compatibility-only and
  detected by `mb doctor` with a preview path via
  `mb migrate campaigns --plan`.

Existing repos do not need an urgent file move. The safe path is to update Main
Branch first, repair skill discovery, and only migrate file layout on a clean
branch when you need the new shape.

The update is urgent. Do not continue a migration against a stale Main Branch
install when a newer package is available. Update first, then repair repos. The
update changes the installed CLI and skills, not the user's business files.

## Why This Matters Now

Current skills depend on `mb` CLI facts before they write or advise. They expect
the business folder, skill links, status output, provider readiness, graph
links, and validation paths to line up with the current CLI contract.

Old clone-era wiring can still make a slash command appear, but it may starve
the skill of the facts it now relies on. Treat migration errors as product
readiness errors, not cosmetic cleanup. If `mb doctor`, `mb status --peek`,
`mb skill link`, `mb skill repair`, or `mb migrate --check` recommends a
change, explain the reason and fix the error before asking the skills to do
serious work.

Use this framing with operators:

```text
The skills now use the `mb` CLI as their source of setup, status, update, and
repair facts. This migration gets your folder aligned with that contract. We
should fix the reported errors first so `/mb-start` and the other skills can
use your business files to their full potential.
```

## `.mb` Is The Current Folder

If you see a `.mb/` folder in your business repo, that is expected. `.mb/` is
Main Branch's repo-local operational state: onboarding progress, provider
metadata, backups, issue drafts, schema markers, and other rebuildable helper
files.

You do **not** need a `.mb-vip/` folder. That name belongs to old clone-based
setup language and the former internal repo name. The current pipx setup does
not require a local Main Branch source checkout inside your business repo.

Open Claude Code or Codex in the business repo folder, not in an old Main Branch
clone. Claude Code uses slash commands such as `/mb-start`; Codex uses global
Main Branch skills such as `mb-start`. If skills are missing, ask the agent to
repair Main Branch setup instead of creating a `.mb-vip/` folder. These are the
underlying commands an agent or power user may run:

```bash
mb update --repo .
mb skill link --repo .
mb skill repair --repo .
mb doctor
mb status --peek
```

## Recommended: Let An Agent Walk You Through It

If you are already using Main Branch and do not want to reason about old
symlinks, clone paths, plugins, or repo shapes, start Claude Code or Codex
anywhere and paste this prompt:

```text
I want to migrate my existing Main Branch setup to the current pipx workflow.
If this is Claude Code, use `/mb-start` after repair. If this is Codex, use the
global `mb-start` skill after repair.

Please go slowly, but treat the Main Branch update as required before repo
repair. I may be new to Terminal, Git, branches, and GitHub.

Main Branch skills now depend on current `mb` CLI facts. Frame migration as
getting my business folder aligned with the CLI contract so the skills can work
fully, not as optional cleanup.

1. First run read-only checks only:
   - mb --version
   - mb update --check --json
   - mb skill list
   - find likely business repos under ~/Documents/GitHub that have CLAUDE.md
     plus core/ or reference/core/, research/, or decisions/
   Treat every command as a possible writer until its help or docs prove
   otherwise. Use `--peek`, `--check`, or equivalent dry-run flags where they
   exist.
2. If Main Branch is outdated, stop repo work and tell me in plain English:
   "Main Branch needs to update before we touch your business folders. This
   updates the tool installed on your computer, not your business files. Should
   I run the update now?"
3. After I confirm, update Main Branch immediately through the Main Branch
   update path. If `/mb-update` is available in Claude Code, use it. In Codex,
   use the global `mb-update` skill. Otherwise run
   `mb update --repo <repo>` from the business repo. Only mention raw package
   commands like `pipx upgrade mainbranch` if `mb update` is unavailable because
   the installed version is too old.
   Do not present the update as an optional phase.
4. Then inspect likely business repos without changing files:
   - mb doctor <repo>
   - mb status <repo> --json --peek
   - mb skill repair --repo <repo>
   - mb migrate --repo <repo> status
5. Explain every recommended repair in terms of the skill behavior it restores.
6. Recommend one repo to repair first, not a whole multi-repo project plan.
7. Show me the one next write action you recommend before running it.
8. Do not delete real files. Only use Main Branch repair/apply commands after I
   confirm.
9. If you create or switch to a git branch, explain that it is a safe draft copy
   of the work. Do not merge, delete, or rename branches unless I explicitly
   confirm.
10. If a command says I need to restart Claude Code, stop and tell me exactly
   which folder to open next and which slash command to run. If this is Codex,
   tell me to start a fresh Codex thread in the business folder and use the
   global `mb-start` skill.
11. Do not end by giving me a list of internal mb commands to choose from. End
   with the exact folder to open and the exact next agent step: Claude Code
   `claude` + `/mb-start`, or Codex + the global `mb-start` skill.
```

After the user confirms the update and one repo repair, Claude should get the
chosen business repo to this state. This is implementation detail for Claude and
power users, not a beginner checklist:

```bash
cd /path/to/your-business
mb update --repo .
mb skill link --repo .
mb skill repair --repo .
mb doctor
mb status --peek
mb start
```

Then restart Claude Code from that business repo and run:

```text
/mb-start
```

If you use Codex instead, start a fresh Codex thread from that business repo and
use the global `mb-start` skill.

This flow is intentionally confirmation-gated. `mb skill link` and
`mb skill repair --apply` only move stale Main Branch symlinks and broken links
with Main Branch skill names out of the way. They do not delete user-authored
skill folders, real files, or live third-party skill links. The two commands
keep their backups in different places:

- `mb skill link` moves each personal link to
  `~/.claude/skills/.mainbranch-backups/skill-link/<name>`. If that name is
  already taken, it adds a number: `<name>-1`, `<name>-2`, and so on.
- `mb skill repair --apply` moves each link into a timestamped folder:
  `~/.claude/skills/.mainbranch-backups/<UTC timestamp>/<name>`.

## If Claude Creates A Branch

Claude Code or `mb migrate --apply` may create or use a git branch before
changing files. That is good: a branch is a safe draft area, not finished work.
Do not leave a beginner wondering whether they should merge it.

When a migration or repair run leaves the user on a branch, Claude should end
with:

- the branch name;
- whether files changed;
- what checks passed or still need attention;
- the exact next folder and `/mb-start` command if the repo is ready;
- whether the branch should be kept as a draft, opened as a GitHub proposal, or
  reviewed by someone more technical before merging.

That final choice belongs to the user. Claude should explain what it thinks the
next git step is and why, then stop. Do not push, open a pull request, merge,
delete, rename, rebase, or force-push unless the user explicitly asks for that
git operation after seeing the branch summary. During migration dogfood or
support, this pause is useful product evidence: the maintainer can see whether
Claude understood branches, commits, review, and merge risk.

Use business language first:

- **branch** = a safe draft copy of the work;
- **pull request** = a proposal for review;
- **merge** = make the draft the main version.

If the user is unsure, the safe answer is to keep the branch local and ask for
review.

Before recommending merge, Claude should separate structural verification from
runtime verification. `mb doctor`, `mb validate`, rename detection, and line
counts prove the filesystem shape. They do not prove Claude Code skills behave
correctly through compatibility symlinks. On the first migration for a user or
repo family, prefer a small runtime smoke before merge:

1. Open Claude Code from the migrated business repo.
2. Run `/mb-start`.
3. Run a bundled skill smoke and label what it proved:
   - Discovery smoke: ask a read-only factual question such as
     `/mb-think what is the soul of this production?`. Pass means Claude Code
     recognized the slash command and read migrated core context from the
     business repo. It does not prove the full `/mb-think` workflow.
   - Full flow smoke: ask for a real research/decide/codify task and explicitly
     say to pause before writing files. Pass means the skill follows its normal
     workflow, writes only to the business repo after approval, and does not
     write into the Main Branch source checkout.
4. Confirm no skill writes into the Main Branch source checkout.
5. Then summarize whether the branch is ready to push, review, or merge.

If an interactive Claude Code runtime smoke is not possible from the current
session, say that plainly. A static fallback can inspect `mb start`, skill
symlinks, `settings.local.json`, and referenced files, but it is not runtime
smoke. Label it as static fallback and list exactly what it does not prove.

During either static fallback or runtime smoke, inspect `.claude/` for old
clone-path symlinks outside the `mb-*` skill directories, especially
`.claude/lenses/` and `.claude/reference/`. `mb skill link` and
`mb skill repair` currently own Main Branch skill names; they may not repair
older lens/reference symlinks from clone-based setups. If those symlinks still
point at an old Main Branch source checkout, report them as follow-up work and do not claim
the clone-to-pipx migration is fully complete until runtime behavior has been
observed without relying on the clone.

Claude Code app sessions may create `.claude/worktrees/` while you test a repo.
That directory is local runtime state, not migration work. Current `mb init` and
`mb skill link` add `.claude/worktrees/` to `.gitignore`; if an older repo shows
it in `git status`, run `mb skill link --repo .` before judging the migration
diff.

Main Branch only reads or edits a regular `.gitignore` inside the repo. If it
is a symlink or another file type, doctor repair, skill linking and repo
initialisation skip it and report a hint. Replace it with a regular file, then
rerun the command. Other repairs and skill links still proceed.

If Claude accidentally dirties an existing branch during discovery, stop before
running layout migration. Move the already-written Main Branch repair work onto
a branch, keep user-authored files separate, and do not commit local status
markers:

1. Show `git status --short` for the repo.
2. If only Main Branch repair files changed, create a branch such as
   `mainbranch-repair`.
3. Commit durable repair files such as `.gitignore` changes.
4. Do not commit `.mb/last-status-seen.json`; it is local operational state and
   should be gitignored.
5. Do not commit `.claude/worktrees/`; it is local Claude Code app state and
   should be gitignored.
6. If the repo already had unrelated dirty or untracked user files, leave that
   repo out of batch migration until the user reviews it.

## Command Mutability During Migration

Migration work should be one repo at a time. Do not batch `mb update`,
`mb skill link`, `mb status`, or `mb migrate --apply` across many business repos
unless the user explicitly asks for batch writes after seeing the risk.

Useful defaults:

- `mb status` writes `.mb/last-status-seen.json`; use `mb status --peek` for
  read-only discovery.
- `mb update` can update the installed CLI and skills and refresh repo-local skill
  links; treat it as a write.
- `mb skill link` writes Claude Code wiring and `.gitignore` repair entries;
  treat it as a write.
- `.claude/worktrees/` is Claude Code app local state. It should be ignored, not
  committed.
- `mb skill repair` without `--apply` reports personal-skill conflicts;
  `--apply` moves stale Main Branch symlinks to backups.
- `mb migrate status` and `mb migrate --check` inspect; `mb migrate --apply`
  writes the layout migration.

Check command help before assuming flag shape. Some commands take a positional
repo path, while others use `--repo`.

Do not ignore errors because the old skill still appears in Claude Code. A
visible slash command only proves discovery. It does not prove the skill can
read current CLI facts, status sections, migration state, or provider readiness.

## If You Are On `mb 0.1.x`

Old `mb` versions do not have `mb update` yet. Run the bootstrap upgrade once:

```bash
pipx upgrade mainbranch
mb --version
```

After that, use the current update path:

```bash
mb update --repo /path/to/your-business
```

or, from inside Claude Code:

```text
/mb-update
```

Use `/mb-update` or `mb update --repo .` for current installs.

## Power User: Repair An Existing Business Repo

From the business repo:

```bash
cd /path/to/your-business
mb update --repo .
mb skill link --repo .
mb skill repair --repo .
mb doctor
mb status --peek
mb start
```

`mb skill link --repo .` rewrites the local Claude Code wiring so `/mb-start`,
`/mb-think`, `/mb-ads`, and the other bundled skills point at the installed
Main Branch package instead of an old clone path. It also removes stale
Main Branch source-checkout paths from `.claude/settings.local.json` so Claude Code does
not keep access to stale Main Branch paths after a clone-to-pipx migration. During
that link step, Main Branch also moves provably stale or broken personal
symlinks with Main Branch skill names into a timestamped backup.

If you use the Claude Code plugin rail, also re-add the Main Branch plugin after
updating (`claude plugin marketplace add noontide-co/mainbranch`) and restart
Claude Code. The symlink repair path remains the fallback and repair path; the
plugin is the more durable route for fresh Claude Code worktrees.

`mb skill repair --repo .` checks your personal `~/.claude/skills/` directory
for entries that can beat the project-local Main Branch skills in Claude Code.
It reports the resolved target for each finding. If the entry is a provably
stale Main Branch symlink or a broken symlink using one of Main Branch's current
or legacy skill names, run:

```bash
mb skill repair --repo . --apply
```

That moves the symlink itself to a timestamped backup under
`~/.claude/skills/.mainbranch-backups/`. It does not delete or move
user-authored directories, real files, or live third-party skill links.

## Do Not Start By Moving Files

If your repo has `reference/core/`, leave it alone until the setup works again.
Current Main Branch commands understand that legacy shape:

- `mb status` counts `reference/core/`.
- `mb start` treats a repo with `reference/core/`, `research/`, and
  `decisions/` as a business repo.
- Claude Code skills can read compatibility paths under `reference/` when
  `core/` is absent.

After migration, `reference/core` and `reference/offers` are compatibility
links back to `core/` and `core/offers/`. They are not duplicate files. Agents
should write once to the current `core/` or `core/offers/` path and should
not ask users to edit both a current path and its `reference/` bridge.

The only thing legacy users usually need immediately is:

```bash
mb update --repo /path/to/your-business
mb skill link --repo /path/to/your-business
mb skill repair --repo /path/to/your-business
```

For beginners, the agent should run that sequence after confirmation and
translate the result into the simple restart flow: open the business folder, then
use the right start surface. In Claude Code, run `claude` and type `/mb-start`.
In Codex, start a fresh thread from the business folder and use the global
`mb-start` skill.

## Automated Layout Migration

Use `mb migrate` on a clean branch when you are ready to move a legacy v0.1 repo
from `reference/core/` and `reference/offers/` into the current v0.2 paths.

Inspect the current schema state:

```bash
mb migrate status
```

You can put `--repo` before or after `status`; both inspect the same repo:

```bash
mb migrate --repo /path/to/your-business status
mb migrate status --repo /path/to/your-business
```

Preview the filesystem changes before any layout write:

```bash
mb migrate --check
mb migrate --check --json
```

By default, `--check` is privacy-safe: it prints path/action summaries and JSON
counts without embedding full file bodies from your legacy reference files.
Those files can contain private strategy, proof, offer details, or customer
language. It also tells you:

- which old paths were found;
- where each file would move;
- whether a current-path file already exists with different contents;
- whether manual reconciliation is required before apply;
- that apply will create a timestamped backup under `.mb/backups/`;
- the exact next command that is safe to run.

If `--check` reports a conflict, stop. Do not run `--apply`. Open the current
path and the old `reference/` source, decide which content should win, make that
edit intentionally, and rerun:

```bash
mb migrate --check
```

Only print the full unified diff when it will stay local:

```bash
mb migrate --check --diff
mb migrate --check --diff --json
```

`--check` exits non-zero when migrations are pending or blocked so scripts and
agents can detect drift without writing files. The path migration ignores local
OS metadata such as `.DS_Store`, `Thumbs.db`, `Desktop.ini`, and AppleDouble
`._*` files.

Apply only after reading the dry-run and confirming it is the move you want:

```bash
mb migrate --apply
```

`--apply` creates a repo-local backup under `.mb/backups/` before changing
files, moves legacy core files into `core/`, moves legacy offer files into
`core/offers/`, leaves compatibility links under `reference/`, updates stale
`CLAUDE.md` path references, writes a migration decision artifact, and stamps
`.mb/schema_version`. If a current-path file already exists with different
contents, apply refuses before writing and tells you to reconcile the conflict
through another dry-run.

Repos migrated by an earlier Main Branch release may already have
`.mb/schema_version` set and a legacy empty `campaigns/` compatibility folder.
The schema marker intentionally prevents rerunning the old layout migration.
Those repos should add `pushes/` with `mb doctor repair` or normal current
scaffolding, and should preview any existing campaign records separately with
`mb migrate campaigns --plan`.

Those compatibility links exist so older readers keep working. Current skills
and agents should treat `core/` and `core/offers/` as the write targets.

After apply, `mb validate` may still report old frontmatter schema debt in
research and decision files. That means the layout migration worked but older
markdown files still need field/status cleanup. Repair those in small batches,
then run `mb validate --cross-refs` once frontmatter errors are down to zero.

Before merge, inspect git's own view of the migration:

```bash
git diff --stat --find-renames main..HEAD
git status --short
```

Git-reported `100%` renames are stronger evidence than line-count comparisons.
If the first migrated repo is the pilot for a larger set, let the branch sit
until `/mb-start` and at least one bundled skill discovery smoke have been run
from that repo. Require a full skill-flow smoke only when the migration changes
skill behavior, write paths, or runtime discovery.

## Manual Layout Migration

The automated command above is preferred because it reports conflicts and
creates backups before mutation. Keep this manual process only as a power-user
fallback when `mb migrate --check` cannot model the repo and you need to inspect
or repair a copy by hand.

Only do this on a clean branch with everything committed:

```bash
cd /path/to/your-business
git status --short
git switch -c migrate-mainbranch-layout
```

Create your own backup first. Do not delete or overwrite current-path files
while doing a manual migration:

```bash
mkdir -p .mb/backups
cp -a reference ".mb/backups/manual-reference-$(date +%Y%m%d-%H%M%S)"
```

For repos with old `reference/core/`, inspect the move first:

```bash
find reference/core -maxdepth 1 -type f -print
find core -maxdepth 1 -type f -print 2>/dev/null || true
```

If a destination file already exists, reconcile it manually before moving the
old source. Only move files when the target path is empty or you have already
merged the content:

```bash
mkdir -p core
for file in reference/core/*; do
  [ -e "$file" ] || continue
  target="core/$(basename "$file")"
  if [ -e "$target" ]; then
    echo "conflict: $file -> $target"
  else
    git mv "$file" "$target"
  fi
done
```

For repos with old `reference/offers/`, do the same for offer-specific files:

```bash
mkdir -p core/offers
for file in reference/offers/*; do
  [ -e "$file" ] || continue
  target="core/offers/$(basename "$file")"
  if [ -e "$target" ]; then
    echo "conflict: $file -> $target"
  else
    git mv "$file" "$target"
  fi
done
```

After every conflict is resolved and the old folders are empty, leave
compatibility links behind:

```bash
rmdir reference/core reference/offers 2>/dev/null || true
[ -e reference/core ] || ln -s ../core reference/core
[ -e reference/offers ] || ln -s ../core/offers reference/offers
```

Then add the current empty working folders:

```bash
mkdir -p bets log pushes documents core/finance
touch bets/.gitkeep log/.gitkeep pushes/.gitkeep documents/.gitkeep core/finance/.gitkeep
```

If your repo already has a `campaigns/` folder from earlier Main Branch
versions, leave it in place — `mb` reads it as compatibility. Run
`mb doctor` and `mb migrate campaigns --plan` to preview the move to
`pushes/` when you're ready.

Current `mb validate` and `mb doctor repair --plan --json` also report
non-destructive migration drift warnings. These warnings name stale paths and
categories without printing file bodies:

- generated `CLAUDE.md` guidance that still teaches `reference/` or
  `campaigns/` as active write targets;
- legacy active-looking folders such as `reference/`, `campaigns/`, `.vip/`,
  `ops/`, `skills/`, `briefs/`, `content/`, or `staging/`;
- push records that are not shaped as `pushes/<YYYY-MM-DD-slug>/push.md`;
- bet frontmatter that still only links legacy `campaigns/` records.

These are warnings, not destructive repairs. Use them to decide what to move,
rewrite, or leave as compatibility. Folder docs such as `research/README.md`
are not treated as research reports and do not need research-record
frontmatter.

Validate before merging the branch:

```bash
mb doctor
mb status --peek
mb validate
mb start --json
git diff --stat --find-renames
git diff --stat
```

If anything looks wrong, stop and keep the legacy layout.

## What About `.vip/config.yaml` and `~/.config/vip/local.yaml`?

Treat them as legacy cleanup surfaces, not current Main Branch truth.

- `~/.config/vip/local.yaml` is machine-local memory: default repo, recent
  repos, experience level, and last-seen changelog version. Current repo
  detection is CWD-first and should use this only as a legacy fallback.
- `.vip/config.yaml` is repo-local configuration used by older skills. It may
  contain mixed durable facts, provider hints, stale tool snapshots, private
  paths, or client context. Do not copy values out blindly.

Preview legacy `.vip` cleanup with:

```bash
mb doctor repair --plan --json
```

That plan classifies `.vip` key families without printing raw values. Delete or
migrate old `.vip` files only after reviewing the audit and moving any
still-current, non-private facts to the right current surface such as `core/`,
`core/operations/`, provider notes, or machine-local config. `mb doctor repair
--apply` may protect `.vip/local.yaml` in `.gitignore` and untrack it, but it
does not delete or rewrite `.vip` YAML files.

## Current Recommendation

For old business repos:

1. Start with the Claude-led migration prompt above if you want guidance.
2. Update Main Branch through `/mb-update` in Claude Code, or
   `mb update --repo /path/to/repo` for the power-user CLI path. Use
   `pipx upgrade mainbranch` only if the install is still on `0.1.x` and
   `mb update` is unavailable.
3. Run `mb skill link --repo /path/to/repo`.
4. Run `mb skill repair --repo /path/to/repo`; use `--apply` only when it says
   a stale Main Branch symlink is safe to move.
5. Run `mb doctor` and `mb status --peek`.
6. Run `mb migrate --check`, read the diff, then run `mb migrate --apply` on a
   clean branch when you are ready.

For personal knowledge repos that do not have `reference/core/`, treat them as
GitHub-native repos that Main Branch can brief, not as fully migrated business
repos yet.
