# Contributing to Main Branch

Main Branch is a public repo. Anyone can read it; not everyone is wired in to the engine cadence. The contributor flow below documents how the work happens, what gates run, and what discipline rules apply.

These rules are **tool-agnostic.** Codex users, Cursor users, Claude Code
users, hosted agents, and direct CLI contributors all follow the same shape:
the rules describe the work, not the editor.

For changes that could affect public product shape, release discipline, runtime
claims, contributor workflow, or public/private boundaries, use
[docs/oss-operating-checklist.md](docs/oss-operating-checklist.md) during cold
start and review.

---

## Branch + PR shape

**One workspace = one branch = one PR.** Hard rule. Keep one concern per PR; a change that needs tests, fixtures or docs alongside it is still one concern. See Work Shape in [AGENTS.md](AGENTS.md). Never reuse a branch.

**Branch convention:** if a Linear issue exists, use Linear's official branch
name so Linear Releases can attach the work. Otherwise use
`<gh-username>/<short-descriptor>`. Descriptor is kebab-case, under 40 chars,
and concrete.

**PR titles** use this repo's bracketed vocabulary when useful:
`[add]`, `[update]`, `[fix]`, `[remove]`, `[refactor]`, `[docs]`, or
`[chore]`. Keep titles product-shaped, for example
`[add] mb status daily briefing`.

---

## Multi-commit organization (CONCERN, not chronology)

Each commit body bullet-lists changes in THAT commit. A reviewer reading `git log --oneline main..HEAD` should see the shape of the work.

| Commit type | What goes in it |
|---|---|
| `[add] ...` | New command, skill, docs surface, or capability |
| `[update] ...` | Existing behavior or docs changed |
| `[fix] ...` | Bug fix |
| `[remove] ...` | Deleted stale behavior, docs, or metadata |
| `[refactor] ...` | Non-behavioral code movement |
| `[docs] ...` | Documentation-only change |
| `[chore] ...` | Dependency, package metadata, or mechanical maintenance |

---

## Local setup

You need Python 3.10 or newer. Check with `python3 --version`; if it is older
(macOS ships 3.9), use a newer interpreter in the first command, for example
`python3.12 -m venv .venv`. From a fresh clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
cd mb
pip install -e ".[dev]"
```

That installs `mb` in editable mode with the tools the checks use (ruff, mypy,
pytest). Keep the virtual environment active when you run the gate below;
`scripts/check.sh` uses whichever `python3` is first on your `PATH`.

To run one test file while you work:

```bash
cd mb
pytest tests/test_<area>.py -q
```

---

## Pre-push gate

Run the repo gate from the repository root before pushing:

```bash
scripts/check.sh
```

It runs formatting, lint, type checks, tests, and the skill line-count gate from
the same working directories CI uses. Do not replace it with root-level
`mypy mb`; that can read the wrong configuration.

When a change touches packaging, entrypoints, bundled data, first-run flows, or
runtime wiring, add the relevant smoke from [AGENTS.md](AGENTS.md): package
install, fixture repo, pipx/update, or runtime discovery.
For release-bearing Claude Code runtime validation, use the
[Claude Code runtime dogfood runbook](docs/claude-code-runtime-dogfood.md).
For repeatable deterministic Claude evidence, start with:

```bash
scripts/claude-runtime-dogfood.py --install-mode editable
```

Add `--run-claude-print --max-budget-usd 0.25` when Claude Code print mode is
available and you want proxy transcript/rubric evidence. Interactive Claude
Code smoke is still required for release-bearing runtime claims. Use the
[release simulation matrix](docs/release-simulations.md) to choose PR smoke,
pre-release candidate, or release acceptance evidence.

Full release simulations are not required for every PR. Package-visible
releases are different: before tagging or publishing, answer the pre-simulation
prompt checkpoint, run the pre-release candidate and `release_acceptance` tiers
against the best available release artifact whenever feasible, and manually
review the transcript for whether Claude actually used `mb` facts or only
handled a permission-distorted fallback.

When a release candidate or PR changes security-sensitive surfaces, add a
targeted agentic security sidecar review over the changed risky files or
scanner candidates. DeepSec is the accepted local sidecar today; keep raw output
under `.agent/`, time-box AI processing, and publish only sanitized summaries.
Do not treat DeepSec, Greptile, or any other AI reviewer as a required gate;
sidecar output is review input. See
[the sidecar decision](decisions/2026-05-13-agentic-security-review-sidecars.md)
and [the supply-chain policy](docs/supply-chain-policy.md).

**No `--no-verify`. No `git commit --no-verify`. No skipping.**

---

## No history rewriting after first push

Never rewrite. Follow-up fixes after review = NEW commits on top. **Never force-push a pushed branch.** Never amend a pushed commit. If a gate fails, fix the root cause and commit the fix as its own commit.

---

## Public/private smell test

Main Branch is a **public repo**. Apply the test on every commit:

> "Would the reader (anyone with internet) be embarrassed or uncomfortable reading this?"

| Answer | Where it goes |
|---|---|
| Yes | Stays in your private repo. Main Branch does not see it. |
| Meh, fine | Main Branch is fine. |
| Not sure | Default private. Sanitize and re-evaluate. |

Specifically:

- Never commit personal-business numbers (MRR, client names, comp data)
- Never commit Skool-member-personal info
- Never commit live Stripe IDs / API keys
- Never commit working URLs to private member resources

---

## Skill changes

Any change to `.claude/skills/*/SKILL.md` or its `references/` should:

1. Review the skill against the bundled skill maintenance rules in [AGENTS.md](AGENTS.md) and the skill line-count/frontmatter gates.
2. Run skill validation: `mb skill validate --all --json` verifies the skill-system invariants.
3. Keep `SKILL.md` under 500 lines (CI gates this). If it grows past, split content into `references/<topic>.md`.
4. Add or update required frontmatter: `name:`, `description:`, and `loops:`
   using canonical loop slugs (`sense`, `decide`, `ship`, `reflect`). Older
   composable/internal skill files may also carry `tier:` and `calls:` while
   they are being migrated, but new bundled skills should use `loops:` as the
   routing contract.

---

## Code review format

PR reviews use this shape:

- Numbered findings, each with file + line citation
- Severity tag: HIGH / MEDIUM / LOW
- MUST FIX (blocks merge) vs SUGGESTIONS (nice-to-have, fine as follow-ups) — separated
- Verdict at end: APPROVE / REQUEST CHANGES (with must-fix count) / NEEDS DISCUSSION

Reviewers should also apply the
[Main Branch OSS operating checklist](docs/oss-operating-checklist.md) when a PR
touches product boundaries, runtime claims, release readiness, state model,
GitHub/Linear workflow, or public/private content.

---

## How to find the work

Start with [AGENTS.md](AGENTS.md). It is the shared operating contract for
Codex, Claude Code, and other agents.

The engine v0.1.0 decision is `decisions/2026-04-29-mb-vip-v0-1-0-master.md`. It locks the first public ship list and historical launch vocabulary.

Historical business-side planning also exists in private Noontide repos. Public contributors should treat this repository's decisions, docs, issues, changelog, and releases as the durable product truth.
