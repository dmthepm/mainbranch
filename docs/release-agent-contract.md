# Release Agent Operating Contract

This contract governs how agents (Claude Code, Codex, or any other automated
worker) drive Main Branch release-bearing flows. It is the protocol layer that
sits next to `docs/release-simulations.md`, `docs/claude-code-runtime-dogfood.md`,
and the validation ladder in `AGENTS.md`. Those files describe *what* to run
and *what evidence to keep*. This file describes *how to run it without
wasting time, exit codes, or trust*.

Surfaced from the v0.3.16 release prep (MAIN-322 / #489) where a release
agent re-ran a 3-minute static check because the first run's output was
filtered too aggressively to confirm the result, and bounced between
`python`, `python3`, and bare scripts before committing to a single
interpreter. Tracked in MAIN-323 / #490.

## Scope

Applies to any agent or human driver running:

- `scripts/check.sh` for a release-prep PR;
- wheel build + fresh-install smoke for a release candidate;
- `scripts/claude-runtime-dogfood.py` at any simulation tier;
- post-publish PyPI verification;
- optional agentic security sidecars such as DeepSec when a release candidate
  touches security-sensitive surfaces;
- any other validation that takes more than ~10 seconds and produces output
  worth preserving.

Out of scope: short interactive probes (`mb --version`, `git status`, single
unit tests under a second). Use judgment, but err on the side of capturing
when in doubt.

## Rules

### 0. Run cheap release-file preflight before expensive gates.

Before running `scripts/check.sh` on a release-prep branch, update and inspect
every version-bearing release file in one pass:

- `CHANGELOG.md` has a dated version section and `[Unreleased]` is empty or
  contains only work intentionally left unreleased;
- `mb/pyproject.toml` `project.version` matches the release version;
- `mb/mb/__init__.py` `__version__` matches the release version;
- `.claude-plugin/plugin.json` `version` matches the release version;
- `.claude-plugin/marketplace.json` `metadata.version` matches the release
  version.

All of that is automated:

```bash
scripts/release-preflight.sh oe-vX.Y.Z   # or bare X.Y.Z; no arg = files must agree
```

The script asserts the version files agree (and agree with the tag when
passed), checks `CHANGELOG.md` has the dated section, and runs the targeted
manifest guard
(`tests/test_smoke_coverage.py::test_claude_plugin_manifest_points_at_prefixed_skills`).

If this preflight fails, fix the release files before the full gate. Do not
spend a full `scripts/check.sh` run discovering a mismatched release version.

### 1. Pick the runtime up front. Do not switch mid-flow.

On macOS in this workspace, the documented runtime is `python3` (with
`python3 -m build`, `python3 -m venv`, `python3 -m pytest`). `python` may be
absent; do not probe blindly.

If a different interpreter is needed (a CI matrix, a venv binary,
`/tmp/<smoke>/bin/python3.13`), state the path once at the top of the flow
and reuse it. Do not alternate between `python`, `python3`, `uv`, or bare
scripts without a written reason.

If a test only passes under a different runtime than the one documented,
that is a finding to surface, not something to paper over with silent
switches.

### 2. Capture stdout, stderr, and exit code on the first run.

Pattern (wrapper-safe — propagates the underlying exit code):

```bash
mkdir -p .agent
scripts/check.sh > .agent/check.out 2>&1; rc=$?; printf "%s\n" "$rc" > .agent/check.exit; exit "$rc"
```

The trailing `exit "$rc"` matters. Without it, the chain ends with
`printf` (or `echo`), which succeeds, so a wrapper like Codex, CI, or a
tool call sees exit `0` even when `scripts/check.sh` actually failed.
Drop the `exit "$rc"` only when running the line interactively in
your own shell (where you don't want to close the session).

The variable name matters too. `status` is a read-only special variable
in zsh (it mirrors `$?`), so `status=$?` fails with `read-only variable`.
`rc` is safe in both bash and zsh; so
is `exit_code`, `check_rc`, or any other non-reserved name. Avoid `status`,
`pipestatus`, `path`, `home`, and other zsh special variables in agent-
facing shell snippets.

Or, if live progress is useful (bash-specific; in zsh use
`${pipestatus[1]}` — lowercase, 1-indexed):

```bash
mkdir -p .agent
scripts/check.sh 2>&1 | tee .agent/check.out
rc=${PIPESTATUS[0]}
printf "%s\n" "$rc" > .agent/check.exit
exit "$rc"
```

If the agent's runtime shell is unknown, prefer the first pattern
(redirect + `rc=$?; printf; exit`) which works in both bash and zsh.

For release-bearing flows, the convention is to put logs under
`.agent/release-evidence/<version>/` so the directory is gitignored and
self-documenting:

```bash
mkdir -p .agent/release-evidence/0.3.17
scripts/check.sh > .agent/release-evidence/0.3.17/check.out 2>&1
rc=$?
printf "%s\n" "$rc" > .agent/release-evidence/0.3.17/check.exit
exit "$rc"
```

For background invocations (the dogfood harness), redirect both streams to
the log file and append the exit code line at the end. Capture the status
in a variable first so the trailing `EXIT=` line and the wrapper exit
both reflect the harness's real outcome:

```bash
python3 scripts/claude-runtime-dogfood.py \
  --install-mode pypi --pypi-version 0.3.17 \
  --evidence-dir .agent/release-evidence/0.3.17 \
  --run-claude-print --simulation-tier release_acceptance \
  --max-budget-usd 0.75 \
  > .agent/release-evidence/0.3.17/dogfood.log 2>&1
rc=$?
printf "EXIT=%s\n" "$rc" >> .agent/release-evidence/0.3.17/dogfood.log
exit "$rc"
```

### 3. Read the saved log. Do not re-run to recover evidence.

Before re-running any long check, check in order:

1. Shell exit code from the previous run (`cat .agent/check.exit` or the
   trailing `EXIT=` line in the log).
2. The saved log file.
3. CI output for the same commit (`gh pr checks <N>`, `gh run view <id>`).
4. Targeted failing test output, captured the same way.

Re-run only when the previous result is genuinely unknown or a code change
warrants a fresh run.

### 3a. Time-box optional security sidecars.

Agentic security sidecars are review aids, not release truth. When a
security-sensitive release branch runs DeepSec or a comparable tool, scope it
to changed high-risk files or scanner candidates, capture the first run's log
and exit state, and record partial or stalled runs honestly.

Keep raw model output, local paths, and scanner workspaces under `.agent/` or
another ignored evidence directory. Public PR evidence should include only the
command shape, scope, exit/timeout result, candidate/finding count, and which
items were confirmed, rejected, or routed to follow-up issues.

### 4. Release PRs stay release-only.

A release-prep PR commits only files that change because of the release:
package version sites, the dated CHANGELOG section, and the plugin manifests.
Process improvements (this file, the post-release playbook, agent rubric
updates) belong on their own branch. Process documents drafted *during* a
release flow are committed *after* the release ships, on a separate branch.

Also: do not edit the engine repo working tree while a release-acceptance
simulation is running against it. The dogfood harness fails the run with
"engine repo git status changed during dogfood harness run" as a
repo-boundary check. Either finish the sim before editing or run it from a
clean checkout dedicated to the run.

### 5. Validation-line evidence template.

Each PR validation bullet should answer:

```text
- Level <N> <surface>: <command> — runtime: <python3 or venv path> — exit: <code> — log: <path or excerpt>; <one-line reason if a level was skipped>
```

Example:

```text
- Level 1 static: scripts/check.sh — runtime: /usr/bin/python3 (3.13) — exit: 0 — log: .agent/release-evidence/0.3.17/check.out (546 passed).
- Level 3 package/install: (cd mb && python3 -m build) + venv install of mainbranch-0.3.17-py3-none-any.whl — runtime: /tmp/mb-pypi-smoke/bin/python3 — exit: 0 — log: .agent/release-evidence/0.3.17/install.out (full validation contract returned result_status: ok).
- Level 5 runtime: scripts/claude-runtime-dogfood.py --install-mode pypi --pypi-version 0.3.17 --run-claude-print --simulation-tier release_acceptance --max-budget-usd 0.75 — exit: 0 — evidence: .agent/release-evidence/0.3.17/ (summary.json, rubric.json, transcript excerpts).
```

If a level was not run, say which one and why in one line. "Not required for
docs-only diff" is a valid reason. "Skipped because evidence was lost" is
not — re-read the log instead.

### 6. hledger fixture is a real check, not a soft note.

`mb books check --fixture --json` has two documented modes:

- base install with no hledger: returns the informational fallback finding
  and `result_status: ok`;
- hledger-equipped environment: shells out to `hledger -f <fixture> check`
  and returns the real `fixture-valid` finding.

For a package-visible release, the validation evidence must record both
modes — or, if only one was run, explicitly call out the missing mode as a
pre-tag blocker, not a soft note in the PR description.

### 7. Plugin-load smoke is a manual pre-publish gate when the diff touches the plugin rail.

The Claude Code plugin is the default skill-distribution rail, but no automated
gate loads it — `scripts/claude-runtime-dogfood.py` exercises the installed
package and project-local wiring, not a real plugin install. So when a release
diff touches plugin wiring, the marketplace/plugin manifests, or the runtime
guidance that routes operators to the plugin, the release driver must run a
manual plugin-load smoke before publishing and record it as a validation line:

- `claude plugin marketplace add dmthepm/mainbranch`, enable the plugin,
  then confirm the plugin-native `/mainbranch:mb-start` (and one other
  `/mainbranch:mb-*` skill) resolves in **both** the Claude Desktop app
  **and** the terminal `claude` CLI;
- separately record whether the legacy project-local bridge also exposes
  `/mb-start`. The bridge is allowed as a compatibility path, but the plugin
  smoke must prove the namespaced plugin command before the tag.
- if the release changes plugin update/detection behavior, also smoke an
  old-version plugin cache: install or leave an older Main Branch plugin
  enabled, update the package to the release candidate, and confirm
  `mb update --check --json` reports `plugin_rail.install.state == "stale"`
  with a repair action before publishing.

This is the one true pre-publish gate that lives only here: a green CI run does
not cover it. "Skipped because no Claude Code build was available" is a valid
recorded reason only for a diff that does not touch the plugin rail.

## Where this lives

This file is the protocol. The simulation-tier matrix (`pr_smoke`,
`prerelease_candidate`, `release_acceptance`) and the transcript review
rubric live in `docs/release-simulations.md`. The runtime dogfood harness
itself lives in `scripts/claude-runtime-dogfood.py` and is documented in
`docs/claude-code-runtime-dogfood.md`. The validation ladder lives in
`AGENTS.md`.

If the protocol above contradicts those documents, the protocol document
that names the surface most specifically wins; open an issue to reconcile.
