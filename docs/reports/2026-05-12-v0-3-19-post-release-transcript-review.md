# v0.3.19 Post-Release Transcript Review Note

This is a public-safe review note for the v0.3.19 post-publish
`release_acceptance` simulation run. It is not a raw Claude transcript. It
avoids local paths, account data, private business context, and long excerpts.

## Evidence Set

- Date: 2026-05-12
- Published package: `mainbranch 0.3.19` from PyPI
- Evidence level: fresh PyPI install deterministic harness plus `claude -p`
  print-mode proxy simulation
- Simulation tier: `release_acceptance`
- Simulation count: 12 packaged prompts
- Claude Code version: 2.1.140
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

- `pip install --no-cache-dir mainbranch==0.3.19`: ok after PyPI index
  propagation
- `mb --version`: `mb 0.3.19`
- `mb skill list`: ok
- `mb onboard --yes --json`: ok
- `.claude/skills/mb-start/SKILL.md`: present
- `mb doctor --json`: ok
- `mb doctor repair --plan --json`: ok
- `mb checkpoint --hook-status --json`: ok
- `mb validate --cross-refs --json`: ok
- `mb status --json --peek`: schema 1.0, skill wiring ok, `money_path` and
  top-level `content_strategy` present
- `mb start --json`: handoff ready, follow-up `/mb-start`
- `mb books check --fixture --json`: not rerun; the bookkeeping surface was
  unchanged from v0.3.18
- Fresh business repo smoke: ok
- Fixture business repo after run: clean, except the intentional checkpoint
  fixture that leaves approved business-file changes dirty for checkpoint
  planning
- Engine repo unexpected changes: false

## Claude Print-Mode Proxy Result

- Print-mode ran: yes
- Rubric score: 11/11 heuristic checks
- Grounding verdict: partial proxy with deterministic fallback
- Permission denials: 1, the same event as the read-only `mb` grounding denial
- Session ID preserved: yes
- Interactive Claude Code TUI smoke: not run in this branch-author pass

The deterministic harness captured the required `mb` facts. The Claude
print-mode run answered in business language, respected write boundaries, and
kept repo boundaries clean. The read-only grounding denial means this is still
proxy evidence, not proof of interactive slash-command behavior.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| Fresh install and fixture setup proved the published package exposes the expected v0.3.19 surfaces, including MoneyPath and content strategy status facts. | Pass | CLI grounding, evidence quality | The package-visible JSON surfaces are available from PyPI, not only from the release branch wheel. |
| Packaged prompt simulations passed the heuristic rubric and kept write/edit, checkpoint-save, repair-apply, migration, and git-commit operations outside the print-mode allowlist. | Pass | write discipline, repo boundary | The v0.3.19 daily-loop and repair guidance is safe for published proxy evidence. |
| The runtime proxy still produced one denied read-only grounding command through shell-wrapped `mb status` extraction. Deterministic fixture facts were available as fallback. | Quality concern | CLI grounding, harness gap, skill prose | Future `/mb-start` path-to-money work should reduce visible JSON chunking and make `money_path` extraction explicit. |
| The Noontide dogfood path-to-money transcript showed a useful owner loop but did not visibly foreground MoneyPath as the deterministic starting point for that intent. | Product opportunity | business-language return, skill prose | Route the follow-up to #539 rather than treating it as a v0.3.19 release blocker. |

## Release Decision

v0.3.19 is acceptable as shipped. GitHub Release, PyPI publish, fresh PyPI
install, fixture repo smoke, Linear release sync, and post-publish
release-acceptance proxy all succeeded. The transcript review found no hard
failure in skill discovery, write discipline, repo boundary, provider honesty,
or public/private handling.

Do not overstate the runtime evidence. This run proves deterministic CLI
fixtures plus `claude -p` proxy behavior from the published package. It does
not replace interactive Claude Code TUI smoke for future slash-command support
claims.

## Alignment Sweep

- README: no change needed; current command and support language already treats
  MoneyPath/status as shipped and dashboard work as future.
- Roadmap: no change needed; shipped foundation already includes MoneyPath,
  release-simulation fixtures, and future-dashboard boundaries.
- CHANGELOG: v0.3.19 is a dated shipped section and `[Unreleased]` is empty
  before this report entry.
- Local preferences: no new private workflow protocol found; no update needed.

## Follow-Up Route

- Keep
  [#539](https://github.com/dmthepm/mainbranch/issues/539) as the next
  focused branch: make `/mb-start` route path-to-money prompts through
  `money_path` facts before freeform offer/ladder/decision file interpretation.
- Keep the fix public-safe: no raw Noontide transcript text, no private
  operator strategy, and no dashboard or MoneyPath schema expansion.
