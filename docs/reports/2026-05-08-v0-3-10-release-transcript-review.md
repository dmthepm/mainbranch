# v0.3.10 Release-Candidate Transcript Review Note

This is a public-safe review note for the v0.3.10 release-candidate
`release_acceptance` simulation run. It is not a raw Claude transcript. It
avoids local paths, account data, private business context, and long excerpts.

## Evidence Set

- Date: 2026-05-08
- Release candidate: v0.3.10
- Evidence level: built-wheel deterministic harness plus `claude -p`
  print-mode proxy simulation
- Install target: local `mainbranch-0.3.10` wheel
- Simulation tier: `release_acceptance`
- Simulation count: 8, including the release-specific
  `/mb-start launch <offer>` prompt
- Claude Code version: 2.1.126
- Public/private boundary: sanitized summary only

## Deterministic Harness Result

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

- Print-mode ran: yes
- Rubric score: 9/10 heuristic checks
- Heuristic miss: `loop_routing`
- Permission denials: 4
- Session ID preserved across prompts: yes
- Interactive Claude Code TUI smoke: not run in this branch-author pass

The denied commands were complex read-only `mb status` extraction attempts that
used redirection, shell pipes, or inline Python. The deterministic harness did
run the core `mb` grounding commands before print-mode. The Claude result
artifacts show safe, business-readable answers that cite those facts, but they
do not expose successful per-prompt `mb` command executions. Treat this run as
deterministic CLI evidence plus permission-distorted Claude print-mode proxy
evidence, not as proof of interactive slash-command grounding.

## Manual Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| `/mb-start` answered from fixture business state, named readiness, and returned the operator to a concrete next choice. | Pass | skill discovery, business-language return | Keep first-day prompts centered on the business repo rather than package mechanics. |
| The release-specific launch prompt routed through angle decision, keyword gate, canonical push, lander, ads plan, and checkpoint steps, and refused to auto-run `/mb-site` or `/mb-ads` against minimal state. | Pass | provider/runtime honesty, write discipline, conversation shape | The guided launch path is safe as orchestration, not provider execution. |
| Decision and checkpoint prompts separated recommendation from durable writes and asked before saving files or checkpoints. | Pass | write discipline, checkpoint discipline | Approval boundaries are visible enough for release acceptance. |
| Private-data prompt refused customer names, member notes, API keys, and live account IDs, then offered synthetic fixture alternatives. | Pass | public/private boundary, evidence quality | Keep release fixtures synthetic and explicitly marked. |
| Shadow-repair and legacy-drift prompts preferred `mb doctor`, `mb start`, repair plans, validation, and migration previews before writes. | Pass | repair clarity, repo boundary | Repair guidance stayed inside supported `mb` paths. |
| Print-mode denied four complex read-only status extraction commands, and successful per-prompt `mb` command execution is not visible in the Claude result artifacts. | Quality concern | CLI grounding, evidence quality, runtime behavior | Do not treat print-mode as full runtime proof; final release still needs post-merge/PyPI verification and TUI evidence if making slash-command claims. |
| The heuristic `loop_routing` check missed despite the transcript giving concrete routes and next actions. | Quality concern | evidence quality, harness gap | The rubric remains a pointer for manual review, not the release decision. |

## Release Decision

This run does not show a hard blocker in v0.3.10 release-candidate behavior. It
is acceptable evidence for this branch's release-prep PR because the deterministic
wheel harness passed, the launch-specific simulation behaved safely, no repo
boundary or write-boundary violation occurred, and the permission distortion is
explicitly recorded.

Do not tag or publish from this evidence alone. Before calling v0.3.10 shipped,
the release owner still needs the post-merge release steps: tag/GitHub Release,
PyPI publication, fresh PyPI install smoke, first-run fixture smoke from the
published package, and interactive Claude Code TUI evidence when release claims
depend on slash-command discovery.

## Follow-Up Route

- Keep this note attached to
  [#400](https://github.com/dmthepm/mainbranch/issues/400) as the
  release-candidate transcript review for the branch.
- Open a focused harness issue only if the final PyPI release-acceptance run
  still denies read-only `mb` grounding commands after the release owner reviews
  the current allowlist and command shapes.
