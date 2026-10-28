---
type: decision
date: 2026-05-13
status: accepted
topic: Agentic security review sidecars for releases and pull requests
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/554
linked_decisions:
  - decisions/2026-05-11-supply-chain-security-gates.md
  - decisions/2026-05-11-repo-setup-visibility-and-checks-model.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
linked_docs:
  - docs/supply-chain-policy.md
  - docs/post-release-alignment.md
  - docs/dependency-choices.md
  - SECURITY.md
tags: [security, release, code-review, ai-review, deepsec, greptile]
---

# Agentic Security Review Sidecars For Releases And Pull Requests

## Decision

Main Branch may use agentic security-review tooling as **optional sidecar
evidence**, not as a required release, merge, or support gate.

- **DeepSec is accepted as a local optional pre-release sidecar.** Use it when a
  branch touches security-sensitive release surfaces: GitHub Actions, PyPI
  publishing, dependency handling, install/update paths, credentials, provider
  auth, repo writes, untrusted file parsing, or external-account mutation.
- **For edited release/security files, the spend is justified.** The intended
  use is a targeted review of changed high-risk files or candidates, where a
  few dollars and minutes are worth it if the sidecar catches a publishing,
  credential, or provider-authority flaw before release.
- **DeepSec output is review input, not release truth.** A finding is a lead for
  human/agent review. It does not replace `scripts/check.sh`, package/install
  smoke, release simulations, GitHub Environment approval, Dependabot review,
  or the supply-chain checks in `docs/supply-chain-policy.md`.
- **Run DeepSec from ignored local scratch by default.** Keep workspaces,
  model logs, raw findings, and local paths under `.agent/` or another
  gitignored evidence directory. Public docs, issues, and PR bodies may include
  only sanitized summaries.
- **Do not adopt Greptile as release infrastructure yet.** Greptile remains a
  hosted PR-review candidate because it is designed around GitHub/GitLab PR
  review, repo indexing, comments, status checks, and persistent team rules.
  Evaluate it separately before installing a GitHub App, granting repo access,
  requiring checks, or committing Greptile config.
- **No AI reviewer is a required gate today.** The current release posture stays
  small, boring, explicit, and human-approved. A future branch may promote a
  sidecar only after smoke evidence proves it adds signal without noisy,
  expensive, or privacy-risky automation.

## Why

Main Branch is a public package-publishing project. The highest-risk mistakes
are release-pipeline changes, broadened workflow permissions, dependency
updates hidden inside feature work, credential leakage, and false runtime or
provider claims. Agentic scanners can help spot those issues, but they also add
new risks: repo access, model cost, noisy findings, tool execution authority,
and a temptation to treat model output as proof.

A local DeepSec smoke on this repository showed the useful shape. The regex
scan completed quickly, activated GitHub Actions matchers, and surfaced three
candidate files: CI workflow action refs, publish workflow OIDC/secret/action
refs, and `hashlib` use in `mb connect`. Those candidates are exactly the kind
of review prompts that matter for release hardening, but the initial matches
were candidates rather than confirmed vulnerabilities.

This means DeepSec is built closely enough for Main Branch's current shape to
justify use: it recognized GitHub Actions, Python, workflow permission and
secret-reference surfaces, and crypto-adjacent code in a small public Python
CLI. It is not limited to web applications, though many of its built-in
matchers are strongest around common web, auth, and service-entry patterns.

The bounded AI investigation pass also showed the operational cost. A Codex
`process` run completed the CI workflow candidate with zero findings, taking
about two minutes and roughly $0.64 of model cost for one file. The second
candidate then stalled long enough that the run was stopped, leaving the
remaining local records in a processing state. That is acceptable exploratory
evidence, and it argues for scoped runs with timeouts rather than a blanket
required gate.

DeepSec fits Main Branch best as a deliberate local tool because it can run
from ignored scratch, produce inspectable candidate records, and let release
agents choose a small `process` pass over the files that matter. That matches
the existing validation ladder: extra evidence for risky surfaces, not an
always-on dependency.

Greptile solves a different problem. Its public docs describe a hosted code
review agent that installs into GitHub/GitLab, indexes the codebase, reviews
PRs, posts inline comments, supports manual `@greptileai` triggers, exposes
status-check behavior, and can be configured with `.greptile/` or
`greptile.json`. That may be useful for broad PR quality in repositories like
OpenClaw, Hermes, or Paperclip-adjacent work, but it is a bigger trust and
workflow decision than a local release-sidecar smoke.

## Use DeepSec When

- A PR changes `.github/workflows/`, `.github/dependabot.yml`, package metadata,
  release scripts, or publish behavior.
- A PR adds or changes provider auth, credential references, keychain/env
  handling, repo writes, network calls, external-account mutation, or untrusted
  parsing.
- A release candidate has enough security-sensitive surface that a targeted
  sidecar review would help reviewers ask better questions.

Preferred local sequence:

```bash
npx deepsec init .agent/deepsec . --id mainbranch
cd .agent/deepsec
pnpm install
pnpm deepsec scan --project-id mainbranch
pnpm deepsec process --project-id mainbranch --agent codex --limit <N> --concurrency 1 --batch-size 1
```

For release branches where only a few risky files changed, prefer the diff or
file-scoped process modes after scan:

```bash
pnpm deepsec process --project-id mainbranch --agent codex --diff origin/main --concurrency 1 --batch-size 1
pnpm deepsec process --project-id mainbranch --agent codex --files .github/workflows/publish-pypi.yml --concurrency 1 --batch-size 1
```

Fill `.agent/deepsec/data/mainbranch/INFO.md` before `process`; it is injected
into each AI investigation batch from the gitignored scratch workspace. Keep it
short and public-safe. Time-box the AI phase and record partial/stalled runs
honestly.

## Do Not Use DeepSec When

- The branch is docs-only or does not touch security-sensitive surfaces.
- The release is already published; post-release use should only route sanitized
  findings into issues or reports.
- The run would require publishing credentials, private customer data, raw
  transcripts, or private operator strategy in model prompts or public output.
- The cost or time would displace the required validation ladder.

## Greptile Boundary

Greptile may be evaluated later as a PR-review service, not as the first
security release gate. Before adoption, require a separate issue and decision
covering:

- GitHub App permissions, repository access, data retention, and public/private
  boundary.
- Whether reviews are manual-only, label-triggered, draft-only, or automatic.
- Whether status checks are informational or merge-blocking.
- Repo-level `.greptile/` or `greptile.json` rules that map to Main Branch's
  existing review focus without adding nitpick noise.
- A trial on non-release PRs, with false-positive examples and useful findings
  summarized publicly.

## Evidence Standard

For DeepSec or any comparable sidecar, PR evidence should state:

- command, scope, and whether AI `process` ran;
- exit code and ignored evidence path;
- candidate/finding count;
- which findings were confirmed, rejected as false positives, or routed to
  follow-up issues;
- explicit note that raw local logs and local paths were not committed.

## Consequences

- Release agents can reach for DeepSec on high-risk branches without asking
  whether the tool is allowed.
- Reviewers should not block ordinary PRs because DeepSec or Greptile did not
  run.
- Hosted AI review remains a separate product/workflow decision.
- `docs/supply-chain-policy.md` should name agentic security review as an
  optional pre-release sidecar, not a mandatory release step.
