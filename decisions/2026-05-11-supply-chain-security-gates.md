---
type: decision
date: 2026-05-11
status: accepted
topic: Supply-chain security gates for releases and dependencies
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/491
linked_decisions:
  - decisions/2026-05-11-repo-setup-visibility-and-checks-model.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
linked_docs:
  - docs/supply-chain-policy.md
  - docs/release-simulations.md
  - docs/dependency-choices.md
  - SECURITY.md
tags: [security, release, supply-chain, github-actions, pypi, dependencies]
---

# Supply-Chain Security Gates For Releases And Dependencies

## Decision

Main Branch's supply-chain posture is small, boring, explicit, and biased
toward deliberate human approval over clever automation. The rules below are
the contract; the durable reference lives in
[`docs/supply-chain-policy.md`](../docs/supply-chain-policy.md).

- **PyPI publishing uses trusted publishing (OIDC) only.** No long-lived
  PyPI API token lives in repo secrets, in maintainer dotfiles, or in any
  GitHub Actions workflow.
- **Publishing is gated by a GitHub Environment with required reviewers.**
  The `pypi` environment requires at least one human approver before the
  publish job can claim its OIDC identity. Trusted publishing without an
  approval gate would let any successful release event publish; the gate is
  what makes the publish step deliberate.
- **`id-token: write` is granted to exactly one job in exactly one
  workflow: `publish-pypi.yml` -> `publish`.** Every other job and workflow
  uses the repo default of `contents: read` or narrower. New workflows must
  not request `id-token: write` unless a new decision accepts the surface.
- **The publish workflow triggers on `release: published`, not on raw tag
  push.** The publish job carries a defensive `if:` guard so it only runs
  when the release tag matches `oe-v*`. This prevents a stray release on a
  non-Main-Branch tag from publishing.
- **The release artifact is built once and published from that same
  artifact.** The `build` job uploads the sdist/wheel, the `publish` job
  downloads the same artifact. No rebuild happens inside the publishing
  environment.
- **Dependencies are pinned to documented floors and reviewed in
  isolation.** `mb` has a small dependency surface (`typer`, `pyyaml`,
  `rich`) declared with minimum versions in `mb/pyproject.toml`. Dependabot
  opens grouped weekly PRs with a release-age cooldown so freshly-published
  versions are not pulled the moment the ecosystem releases them. Dependency
  PRs are not bundled with feature work.
- **No hash-locked install path is required today.** `mb` is a small,
  Typer-shaped CLI; introducing `pip-tools`, `uv`, or `poetry` lockfiles
  would force a new dependency manager on contributors before the surface
  earns it. This is revisable if the dependency footprint grows or if a
  specific compromise scenario requires hash-locking.
- **`scripts/check.sh` protects normal development. Release-only checks
  protect users and PyPI.** Release validation runs the package-visible
  release gate documented in
  [`docs/release-simulations.md`](../docs/release-simulations.md) plus the
  supply-chain checks in `docs/supply-chain-policy.md`. PR CI does not run
  the release publish workflow.
- **Post-compromise response has a written path.** If a dependency, a
  release pipeline, or the PyPI account is suspected compromised,
  `docs/supply-chain-policy.md` describes who pauses publishing, which
  GitHub Environment approval is revoked, how to yank an affected release
  on PyPI, and how to notify users through `SECURITY.md` and the GitHub
  Release body.

## Why

Recent npm-ecosystem compromises (publishing-pipeline takeovers, malicious
post-publish replacement of trusted packages, malicious dependency updates
landing in the short window before ecosystem detection) reinforced lessons
that apply to PyPI and GitHub Actions too:

- Trusted publishing / OIDC reduces long-lived-token risk but does not stop
  malicious code from running inside an authorized release workflow.
- CI publishing removes the human second factor unless an environment
  requires manual approval.
- Dependency updates can land malicious versions during the short window
  before the ecosystem detects and removes them.
- Lockfiles, pinned versions, dependency age policies, and release-time
  gates each plug different holes; no single control is sufficient.
- Release workflows should be narrow, manually approved, and isolated from
  normal PR checks.

Main Branch is a small, public, single-maintainer-shaped CLI today. The
right move is not a SLSA Level 3 build chain; it is to make the release
path explicit, narrow, and reviewable. This decision locks the boring
rules so the release process can grow safely without each contributor
re-litigating the trade-offs.

## Scope Locked

- PyPI publishing flow (`publish-pypi.yml`).
- Permissions and `id-token` use across all GitHub Actions workflows.
- Dependency update policy for the `pip` and `github-actions` ecosystems
  managed by Dependabot.
- Package metadata and dependency declaration shape.
- Manual approval gate via GitHub Environments.
- Release-only supply-chain checks layered on top of the existing
  package-visible release gate.
- Public-safe post-compromise response guidance.

## Out Of Scope

- Replacing PyPI.
- Building a private package mirror.
- Full SLSA / Sigstore / in-toto provenance attestation.
- npm ecosystem work (this repo ships no Node runtime surface).
- Emergency incident response execution.
- Hash-locked install via `pip-tools`, `uv`, or `poetry`.
- Branch protection / ruleset configuration on `main` (recommended as a
  follow-up; not configurable from inside the repo).

## What Changes

- `decisions/2026-05-11-supply-chain-security-gates.md` (this file).
- `docs/supply-chain-policy.md` — durable policy and release runbook.
- `.github/workflows/publish-pypi.yml` — defensive `if:` guard so the
  publish job only runs from `oe-v*` releases; comment header documents
  the trusted-publishing posture.
- `.github/dependabot.yml` — release-age cooldown, grouped pip updates,
  and explicit review labels.
- `SECURITY.md` — link to the policy from the existing security report
  surface.
- `docs/oss-operating-checklist.md` — supply-chain checklist items in the
  Release Readiness section.
- `docs/README.md` — link the new policy from the docs index.
- `.github/PULL_REQUEST_TEMPLATE.md` — dependency / release-pipeline
  review checkbox.
- `CHANGELOG.md` — `[Unreleased]` Security entry.

## Follow-ups

- Configure required reviewers on the `pypi` GitHub Environment. Cannot
  be set from inside the repo; requires repo settings access.
- Add branch protection on `main`: require CI green, require PR review,
  block force-push, restrict who can push tags matching `oe-v*`.
- Evaluate SHA-pinning third-party GitHub Actions with Dependabot
  ecosystem updates; tracked as a separate slice.
- Re-evaluate hash-locked installs (`pip-tools` / `uv`) once the
  dependency surface grows past the current three runtime deps or after
  any concrete compromise scenario surfaces.
