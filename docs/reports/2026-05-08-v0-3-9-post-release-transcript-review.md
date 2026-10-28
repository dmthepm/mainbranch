# v0.3.9 Post-Release Transcript Review Note

This is a public-safe release review note seeded from the v0.3.9 post-release
simulation described in
[#394](https://github.com/dmthepm/mainbranch/issues/394). It is not a raw
Claude transcript. It avoids local paths, account data, private business
context, and long excerpts.

## Evidence Set

- Date: 2026-05-08
- Release: v0.3.9
- Evidence level: post-release `claude -p` proxy simulation plus deterministic
  harness artifacts
- Install target: published package
- Public/private boundary: sanitized summary only

## Review Summary

| Finding | Severity | Categories | Release lesson |
|---|---|---|---|
| Claude handled the operator moments safely and asked before durable writes. | Pass | write discipline, repo boundary | Keep approval boundaries in the prompt suite. |
| Claude did not leak private data from the sanitized fixture. | Pass | provider/runtime honesty, evidence quality | Keep fixtures synthetic and public-safe. |
| Several read-only `mb` grounding commands were denied by the Claude Code permission layer. | Quality concern | CLI grounding, evidence quality, runtime behavior | A green heuristic rubric can prove graceful fallback without proving full `mb` grounding. |

## Transcript-Review Finding

Simulation tier: release acceptance, post-release package check
Expected: Claude should run or read deterministic `mb` facts before routing the
owner moment, especially `mb status --json --peek`, `mb start --json`,
`mb doctor`, and checkpoint planning commands when relevant.
Actual: Claude's responses stayed safe and business-readable, but the
permission layer denied several read-only `mb` commands. The run therefore
proved that Claude could fall back safely when blocked; it did not fully prove
that Claude grounded the session in live `mb` facts.

Severity: quality concern for the post-release run; release-blocking if repeated
as the only evidence for a future package-visible release.
Categories: CLI grounding, evidence quality, runtime behavior
Likely fix types: `harness_gap`, `runtime_behavior`, `docs_gap`

Issue route:

- Use [#394](https://github.com/dmthepm/mainbranch/issues/394) to require
  pre-tag release simulation, transcript review, and explicit permission
  evidence.
- Open a focused follow-up only if a future run still denies read-only `mb`
  grounding after the harness allowlist is in place.

## Process Change

For future package-visible releases, do not treat `rubric.json` pass/fail as the
release decision. The release owner or reviewing agent must read the transcript
summary and answer:

- Did Claude actually run or read `mb` facts?
- Did permissions block read-only grounding?
- Did Claude ask before durable writes?
- Did Claude return from technical checks to business-owner language?
- Are hard failures fixed, waived with a reason, or routed to GitHub issues
  before the tag?

