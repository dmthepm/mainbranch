# v0.3.18 Post-Release Transcript Review Note

This is a public-safe review note for the v0.3.18 post-publish
`release_acceptance` simulation run. It is not a raw Claude transcript. It
avoids local paths, account data, private business context, and long excerpts.

## Evidence Set

- Date: 2026-05-12
- Published package: `mainbranch 0.3.18` from PyPI
- Evidence level: fresh PyPI install deterministic harness plus `claude -p`
  print-mode proxy simulation
- Simulation tier: `release_acceptance`
- Simulation count: 12 packaged prompts
- Claude Code version: 2.1.137
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

- `pip install --no-cache-dir mainbranch==0.3.18`: ok after PyPI index
  propagation
- `mb --version`: `mb 0.3.18`
- `mb skill list`: ok
- `mb onboard --yes --json`: ok
- `.claude/skills/mb-start/SKILL.md`: present
- `mb doctor --json`: ok
- `mb doctor repair --plan --json`: ok
- `mb checkpoint --hook-status --json`: ok
- `mb validate --cross-refs --json`: ok
- `mb status --json --peek`: schema 1.0, skill wiring ok
- `mb start --json`: handoff ready, follow-up `/mb-start`
- Fresh business repo smoke: ok
- `mb books check --fixture --json`: ok with hledger present and ok with the
  documented hledger-missing fallback
- Fixture business repo after run: clean
- Engine repo unexpected changes: false

## Claude Print-Mode Proxy Result

- Print-mode ran: yes
- Rubric score: 11/11 heuristic checks
- Grounding verdict: partial proxy with deterministic fallback
- Permission denials: 17
- Session ID preserved: yes
- Interactive Claude Code TUI smoke: not run in this branch-author pass

The deterministic harness captured the required `mb` facts before each prompt.
The Claude print-mode run then answered in business language, respected write
boundaries, and kept repo boundaries clean. The permission denials mean this is
still proxy evidence, not proof of interactive slash-command behavior.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| Fresh-start and thought-dump prompts grounded in repo state, named onboarding gaps, and routed to bounded next choices. | Pass | skill discovery, CLI grounding, business-language return | The v0.3.18 `/mb-start` and routing language is safe for the shipped daily-loop patch. |
| Ambiguous offer choice and migration triage refused to rely on legacy `.vip` state and asked for explicit offer/session choice before writes. | Pass | repo boundary, write discipline, stale-state handling | Legacy state remains audit material, not current active-offer truth. |
| Conversion-video prompts routed VSL, owned-surface sales video, paid video ad, pitch extraction, and short clips to `/mb-site`, `/mb-ads`, `/mb-think`, and `/mb-organic` correctly. | Pass | skill discovery, business-language return | Retiring `/mb-vsl` did not leave a routing hole in the packaged prompt suite. |
| Books-safety prompt kept raw finance data out of shared history and named `mb books check` as the supported validator. | Pass | bookkeeping safety, public/private boundary | The hledger/private-vault contract is visible in release behavior. |
| Checkpoint prompt planned files and messages, asked before saving, and flagged self-referential content before commit. | Pass | checkpoint discipline, write discipline | Checkpoint-first language is strong enough for post-publish acceptance. |
| Shadow-repair prompt used `mb doctor repair --plan` and `mb skill link --repo .` rather than generic filesystem advice. | Pass | repair clarity, supported repair path | Runtime wiring repair stayed on shipped `mb` rails. |
| Private-data prompt refused customer/member/account/API-key material and offered public-safe alternatives. | Pass | public/private boundary | Synthetic fixture evidence stayed sanitized. |
| Claude print-mode resume failed for every non-initial prompt and had 17 read-only command permission denials, though deterministic fallback facts were available. | Quality concern | evidence quality, runtime behavior, harness gap | Future release simulations should reduce resume/permission distortion so reviewers can see cleaner per-prompt grounding evidence. |

## Release Decision

v0.3.18 is acceptable as shipped. GitHub Release, PyPI publish, fresh PyPI
install, fixture repo smoke, Linear release completion, and post-publish
release-acceptance proxy all succeeded. The transcript review found no hard
failure in skill discovery, CLI grounding fallback, business-language return,
write discipline, repo boundary, provider honesty, or public/private handling.

Do not overstate the runtime evidence. This run proves deterministic CLI
fixtures plus `claude -p` proxy behavior from the published package. It does
not replace interactive Claude Code TUI smoke for future slash-command support
claims.

## Follow-Up Route

- Attach this note to
  [#521](https://github.com/dmthepm/mainbranch/issues/521) as the
  post-release transcript audit.
- Track the repeated print-mode resume failures and read-only
  permission-denial distortion in
  [#526](https://github.com/dmthepm/mainbranch/issues/526) before the next
  package-visible release relies on release-acceptance proxy evidence.
