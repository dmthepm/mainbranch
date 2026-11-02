# v0.3.34 Post-Release Transcript Review Note

This is a public-safe review note for the v0.3.34 post-publish
`release_acceptance` simulation run and Codex dogfood pass. It is not a raw
runtime transcript. It avoids local paths, account data, private business
context, and long excerpts.

## Evidence Set

- Date: 2026-05-23
- Published package: `mainbranch 0.3.34` from PyPI
- GitHub Release: `oe-v0.3.34`
- Release workflow: release-note sync, PyPI publish, and Linear release sync
  succeeded
- Evidence level: fresh PyPI install deterministic harness, `claude -p`
  print-mode proxy simulation, and read-only Codex CLI dogfood
- Simulation tier: `release_acceptance`
- Claude Code version: 2.1.148
- Codex CLI version: 0.133.0
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

- PyPI latest: `mainbranch 0.3.34`
- `pip install mainbranch==0.3.34`: ok
- `mb --version`: `mb 0.3.34`
- `mb skill list`: ok
- `mb books check --fixture --json`: ok with hledger available
- `mb books check --fixture --json`: ok with hledger hidden from `PATH`
- Fresh business-repo fixture: ok
- Codex repair from fresh install: `codex-plugin-install` applied
- Codex status after repair: plugin install `ok`, support
  `supported_generated_guidance`, `slash_commands_ready: false`
- `mb workflow list --runtime codex --json`: 11 workflow inventory rows
- `mb validate`: ok in the fresh fixture

## Claude Print-Mode Proxy Result

- Print-mode ran: yes
- Rubric score: 11/11 heuristic checks
- Grounding verdict: print proxy, manual review required
- Permission denials: 2
- Read-only `mb` grounding denials: 0
- Session ID preserved: yes
- Interactive Claude Code TUI smoke: not run in this post-release pass

The deterministic harness captured the required `mb` facts. The Claude
print-mode run respected write boundaries, kept fixture boundaries clean, and
did not deny read-only `mb` grounding. It remains proxy evidence, not proof of
interactive TUI behavior.

## Codex Dogfood Result

- Local installed `mainbranch` was upgraded from 0.3.33 to 0.3.34.
- Scoped `mb doctor repair --apply --only codex` refreshed generated Codex
  guidance and installed the global Main Branch Codex plugin.
- `mb status --json --peek` reported Codex ready through generated guidance,
  plugin install `ok`, and `slash_commands_ready: false`.
- Codex CLI used the Main Branch owner-loop skill, ran read-only `mb` fact
  checks, found no Codex runtime mismatch, and did not edit files.
- Codex routed the next action to reviewing existing unsaved local changes
  before substantive work.

The Codex dogfood supports the v0.3.34 claim: Codex is supported through
generated guidance, the global plugin, and deterministic `mb` facts. It does
not claim `/mb-*` Codex slash-command support.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| GitHub Release, PyPI publish, fresh install, installed CLI version, bundled skills, books fixture checks, and Linear release sync all agreed on v0.3.34. | Pass | evidence quality, package/install | The package-visible release is installable and release surfaces agree. |
| Installed-wheel release smoke found and fixed a Codex repair blocker before tagging: missing global plugin repair was skipped when repo guidance was current but the runtime PATH check warned. | Pass | CLI contract, repair path, runtime behavior | Release smoke should keep covering scoped Codex repair with path-warning conditions. |
| The post-publish proxy simulation preserved read-only grounding, write discipline, fixture boundaries, and provider/runtime honesty. | Pass | CLI grounding, write discipline, repo boundary, provider honesty | v0.3.34 did not introduce a release-blocking runtime safety regression in the proxy harness. |
| Codex CLI dogfood used generated guidance and deterministic `mb` facts without claiming slash-command support. | Pass | Codex support, runtime honesty, CLI grounding | The supported Codex path is ready to announce as generated-guidance support, not slash-menu parity. |

## Release Decision

v0.3.34 is acceptable as shipped. GitHub Release, PyPI publish, fresh PyPI
install, fixture checks, Linear release sync, post-publish release-acceptance
proxy, and read-only Codex dogfood all succeeded. The review found no hard
failure in CLI grounding, write discipline, repo boundary, provider honesty,
Codex support vocabulary, or public/private handling.

Do not overstate the runtime evidence. This run proves deterministic CLI
fixtures, `claude -p` proxy behavior from the published package, and read-only
Codex CLI dogfood. It does not prove Codex `/mb-*` slash-menu support.

## Alignment Sweep

- CHANGELOG: v0.3.34 is a dated shipped section; `[Unreleased]` is empty.
- GitHub Release: `oe-v0.3.34` exists and points at the release-prep merge.
- PyPI: `mainbranch 0.3.34` is available with wheel and sdist artifacts.
- README and compatibility docs: no post-release change needed; current language
  describes Claude Code and Codex CLI as supported while keeping Codex support
  scoped to generated guidance, the global plugin, and deterministic `mb`
  facts.
- Decisions: the Codex slash-command bridge decision remains current; no new
  decision needed.
- Release simulations: no process change needed; the existing package-visible
  release gate caught the Codex repair blocker before publish.
- Local preferences: no new private workflow protocol found; no update needed.

## Follow-Up Route

- Continue Codex work through focused generated-guidance and workflow parity
  issues; do not reintroduce Codex slash-command claims until Codex exposes and
  smokes that command surface.
- Keep future Codex release evidence public-safe: summarize results, do not
  publish raw local business repo transcripts, private paths, account data, or
  private operator strategy.
