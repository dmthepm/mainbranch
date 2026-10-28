# v0.3.22 Post-Release Transcript Review Note

This is a public-safe review note for the v0.3.22 post-publish
`release_acceptance` simulation run. It is not a raw Claude transcript. It
avoids local paths, account data, private business context, and long excerpts.

## Evidence Set

- Date: 2026-05-14
- Published package: `mainbranch 0.3.22` from PyPI
- GitHub Release: `oe-v0.3.22`
- Release workflow: publish, release-note sync, PyPI publish, and Linear
  release sync succeeded
- Evidence level: fresh PyPI install deterministic harness plus `claude -p`
  print-mode proxy simulation
- Simulation tier: `release_acceptance`
- Claude Code version: 2.1.140
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

- PyPI latest: `mainbranch 0.3.22`
- `pip install mainbranch==0.3.22`: ok
- `mb --version`: `mb 0.3.22`
- `mb skill list`: ok
- `mb books check --fixture --json`: ok with hledger available
- `mb books check --fixture --json`: ok with hledger hidden from `PATH`
- `mb onboard --yes --json`: ok in the dogfood harness
- `.claude/skills/mb-start/SKILL.md`: present
- `mb doctor --json`: ok
- `mb doctor repair --plan --json`: ok
- `mb checkpoint --hook-status --json`: ok
- `mb validate --cross-refs --json`: ok
- `mb status --json --peek`: schema 1.0, skill wiring ok
- `mb start --json`: handoff ready, follow-up `/mb-start`
- Fixture business repo after run: clean
- Engine repo unexpected changes: false

## Claude Print-Mode Proxy Result

- Print-mode ran: yes
- Rubric score: 11/11 heuristic checks
- Grounding verdict: print proxy, manual review required
- Permission denials: 0
- Read-only `mb` grounding denials: 0
- Session ID preserved: yes
- Interactive Claude Code TUI smoke: not run in this post-release pass

The deterministic harness captured the required `mb` facts. The Claude
print-mode run respected write boundaries, kept repo boundaries clean, and did
not hit permission distortions. It remains proxy evidence, not proof of
interactive slash-command behavior.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| GitHub Release, PyPI publish, fresh install, installed CLI version, bundled skills, books fixture checks, and Linear release sync all agreed on v0.3.22. | Pass | evidence quality, package/install | The package-visible release is installable and release surfaces agree. |
| The post-publish proxy simulation preserved read-only grounding, write discipline, repo boundaries, and provider/runtime honesty. | Pass | CLI grounding, write discipline, repo boundary, provider honesty | v0.3.22 did not introduce a release-blocking runtime safety regression in the proxy harness. |
| Owner-facing transcript excerpts still leaked raw git/GitHub words such as branch, working tree, and origin remote after the business translation appeared nearby. Checkpoint examples still included a broad folder-level phrase. | Quality concern | operator-language first, business-language return, skill prose, generated repo guidance | This was routed to #604 after v0.3.22 and resolved by the later owner-language hardening. |

## Release Decision

v0.3.22 is acceptable as shipped. GitHub Release, PyPI publish, fresh PyPI
install, fixture checks, Linear release sync, and post-publish
release-acceptance proxy all succeeded. The transcript review found no hard
failure in skill discovery, write discipline, repo boundary, provider honesty,
or public/private handling.

Do not overstate the runtime evidence. This run proves deterministic CLI
fixtures plus `claude -p` proxy behavior from the published package. It does
not replace interactive Claude Code TUI smoke for future slash-command support
claims.

## Alignment Sweep

- CHANGELOG: v0.3.22 is a dated shipped section; current `[Unreleased]`
  correctly carries post-release v0.3.23 work from #607 and #609.
- GitHub Release: `oe-v0.3.22` exists and points at the release-prep merge
  commit.
- PyPI: `mainbranch 0.3.22` is available with wheel and sdist artifacts.
- README: no change needed; current support and command language already
  treats the shipped daily-loop, books readiness, Meta summary, and image rail
  surfaces accurately.
- Roadmap: no change needed; shipped foundation already includes the
  release-simulation fixture ladder, sample books reporting, Meta read-only
  summary, and image-rail direction while keeping private-vault reporting and
  provider mutation deferred.
- Release simulations: no process change needed; the existing transcript
  rubric caught the owner-language leakage and routed it to #604, which later
  landed as the owner-language hardening follow-up.
- Local preferences: no new private workflow protocol found; no update needed.

## Follow-Up Route

- Treat
  [#604](https://github.com/dmthepm/mainbranch/issues/604) as the
  historical route from this review. It has since landed; open a fresh focused
  issue for any new owner-language misses.
- Keep the fix public-safe: no raw transcript dumps, private paths, local
  machine details, account data, or private operator strategy.
