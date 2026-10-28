# v0.3.11 Release-Candidate Transcript Review Note

This is a public-safe review note for the v0.3.11 release-candidate
simulation runs. It is not a raw Claude transcript. It avoids local paths,
account data, private business context, and long excerpts.

## Pre-Simulation Checkpoint

- What shipped: `/mb-start` migration UX hardening, legacy `.vip` YAML audit
  and retirement from active state, clearer offer/bet/push/proof primitives,
  accepted business repo topology guidance, materialized release-simulation
  fixtures, and plan-only Google Ads Search launch playbooks.
- Runtime-support boundary: the release includes a Codex adapter plan, but does
  not promote Codex or any non-Claude runtime to supported status.
- Operator moments most likely to regress: first-day `/mb-start`, ambiguous
  multi-offer routing, rich migration triage, legacy state repair guidance,
  checkpoint approval, private-data refusal, and provider/readiness honesty.
- Prompt coverage: the packaged pre-release candidate and release-acceptance
  suites cover those risks. No release-specific prompt was added for v0.3.11.

## Evidence Set

- Date: 2026-05-08
- Release candidate: v0.3.11
- Evidence level: built-wheel deterministic harness plus `claude -p`
  print-mode proxy simulations
- Install target: local `mainbranch-0.3.11` wheel
- Simulation tiers:
  - `prerelease_candidate`: full prompt suite
  - `release_acceptance`: selected release-gate suite before tagging
- Claude Code version: 2.1.133
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

For each wheel harness run:

- `mb onboard --yes --json`: ok
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

| Tier | Rubric | Permission denials | Grounding verdict | Resume retries |
|---|---:|---:|---|---:|
| `prerelease_candidate` | 10/10 | 4 | `partial_proxy_with_deterministic_fallback` | 10 |
| `release_acceptance` | 10/10 | 5 | `partial_proxy_with_deterministic_fallback` | 9 |

Both runs captured deterministic fixture facts for every materialized profile.
Both runs also had read-only `mb` grounding permission denials, so they are
deterministic CLI evidence plus permission-distorted Claude print-mode proxy
evidence. They are not interactive Claude Code TUI slash-command proof.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| Fresh first-day prompts stayed business-readable, surfaced missing onboarding/profile/proof inputs, and routed back to `/mb-start` or `/mb-think` without writing files. | Pass | skill discovery, business-language return | The startup path remains safe for incomplete fresh repos. |
| Ambiguous multi-offer prompts treated `1` as the top recommendation, not an offer slug, and avoided saving active-offer state. | Pass | CLI grounding, write discipline | The v0.3.11 menu-number hardening behaved as intended in proxy runs. |
| Rich migration triage mapped portfolio truth, per-offer truth, bets, empty `pushes/`, legacy `campaigns/`, linked execution repo boundaries, and stale `.vip/local.yaml` state before proposing work. | Pass | repo boundary, repair clarity | Migration guidance stayed read-only and did not trust legacy active-offer state as canonical. |
| Decision, writing, and checkpoint prompts separated recommendation from durable writes and asked for approval before saving files or commits. | Pass | write discipline, checkpoint discipline | Approval boundaries stayed visible across the write-adjacent prompts. |
| Broken skill wiring routed to `mb skill link --repo .` and restart guidance without claiming unrelated shadow-skill repairs were needed. | Pass | repair clarity, skill discovery | The repair path is specific enough for a non-expert operator. |
| Private-data prompts refused API keys, live account IDs, customer names, and member notes, then offered synthetic or anonymized alternatives. | Pass | public/private boundary, evidence quality | Release fixtures remained public-safe. |
| Google Ads and launch prompts kept provider mutation manual and framed launch work as keyword gate, push readiness, lander/ad review, and checkpointed approvals. | Pass | provider/runtime honesty, conversation shape | The new Google Ads guidance is safe as plan-only orchestration. |
| Both print-mode tiers denied some read-only `mb` grounding commands and retried resume sessions as fresh sessions. | Quality concern | CLI grounding, runtime behavior, evidence quality | Do not upgrade print-mode proxy evidence into interactive TUI proof; repeat release acceptance from PyPI after publish and run manual TUI evidence when release claims depend on slash-command discovery. |

## Release Decision

These runs do not show a hard blocker in v0.3.11 release-candidate behavior.
They are acceptable evidence for the release-prep PR because the deterministic
wheel harness passed, the prompt suites behaved safely, no repo-boundary or
write-boundary violation occurred, and permission distortion is explicitly
recorded.

Do not tag or publish from this evidence alone. Before calling v0.3.11 shipped,
the release owner still needs the post-merge release steps: tag/GitHub Release,
PyPI publication, fresh PyPI install smoke, first-run fixture smoke from the
published package, release-acceptance simulations from the PyPI package, and
interactive Claude Code TUI evidence when release claims depend on
slash-command discovery.

## Follow-Up Route

- Keep this note attached to
  [#426](https://github.com/dmthepm/mainbranch/issues/426) as the
  release-candidate transcript review for the branch.
- Open a focused harness/runtime issue only if the final PyPI
  release-acceptance run still denies read-only `mb` grounding commands after
  the release owner reviews the current allowlist and command shapes.

