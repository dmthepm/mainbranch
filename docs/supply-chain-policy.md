# Supply-Chain Policy

Main Branch is a small public Python CLI that publishes to PyPI through a
GitHub Actions workflow. The supply chain is short, and the trade-offs are
explicit. This doc is the durable reference for the rules locked in
[`decisions/2026-05-11-supply-chain-security-gates.md`](../decisions/2026-05-11-supply-chain-security-gates.md).

The product stance is: small, boring, explicit, biased toward deliberate
human approval over clever automation.

## Current Posture

### PyPI publishing

- The PyPI publisher for `mainbranch` is configured as a **trusted
  publisher** (OIDC) bound to:
  - `owner=dmthepm`
  - `repo=mainbranch`
  - `workflow=publish-pypi.yml`
  - `environment=pypi`
- No long-lived PyPI API token lives in repo secrets, in maintainer
  dotfiles, or in any GitHub Actions workflow.
- The publish workflow triggers on `release: published`, not on raw tag
  push. A release is a deliberate Releases-UI action by a maintainer.
- A release metadata job validates the tag as `oe-vMAJOR.MINOR.PATCH` before
  downstream jobs use the tag-derived version. Defense in depth — the trusted
  publisher binding is the primary gate.
- The release artifact is built once in the `build` job, uploaded as an
  artifact, then downloaded and published by the `publish` job. No
  rebuild happens inside the publishing environment.

### GitHub Environments and manual approval

- The `pypi` GitHub Environment is the human approval gate. It is
  configured in repo settings (not in YAML) to require at least one
  reviewer before the `publish` job can claim its OIDC identity.
- Trusted publishing without an approval gate would let any successful
  release event publish. The environment gate is what makes the publish
  step deliberate.
- The reviewer must understand what is being published: which tag, which
  build artifact, and which CHANGELOG section.

### GitHub Actions permissions

- Both `.github/workflows/ci.yml` and `.github/workflows/publish-pypi.yml`
  declare `permissions: contents: read` at the top level. Every job
  inherits the most restrictive default.
- `id-token: write` is granted to exactly one job in exactly one
  workflow: `publish-pypi.yml` -> `publish`. This permission is required
  by the OIDC trusted-publishing exchange and must not appear anywhere
  else without a new accepted decision.
- The `release-notes` job in `publish-pypi.yml` requests `contents: write`
  scoped to itself, only to update the GitHub Release body with the
  CHANGELOG slice. It does not have `id-token: write` and cannot publish
  to PyPI.
- The `linear-release` job requests `contents: read` and uses the
  `LINEAR_ACCESS_KEY` secret. It uses the same strict release metadata output
  as the PyPI publish job and only runs after `publish` succeeds.
- New workflows or jobs must declare the minimum permissions they need
  and document any deviation from `contents: read` in the workflow file
  header.

### Action pinning

- Actions in `.github/workflows/publish-pypi.yml` are pinned to full commit
  SHAs because the release path can claim PyPI OIDC and use release-related
  secrets.
- Maintainers update release-workflow actions intentionally during dependency
  or security maintenance. Verify the upstream tag or branch maps to the chosen
  SHA before changing the workflow, and keep the trailing version comment next
  to the pinned SHA current.
- Lower-risk CI actions may remain pinned to major-version tags
  (e.g. `actions/checkout@v6`) until their risk profile changes.
- Dependabot's `github-actions` ecosystem opens weekly PRs when a pinned
  major changes, with minor/patch updates grouped into a `github-actions-official`
  PR (the `actions/*` family) and a `github-actions-release` PR (the
  PyPA publisher and Linear release action). Major bumps still open as
  individual PRs so the release-pipeline review is not hidden inside a
  group diff. See
  [`.github/dependabot.yml`](../.github/dependabot.yml).
- Pinning to commit SHAs remains the preferred control for higher-risk supply
  chains. The original release-gates decision tracked SHA pinning as follow-up;
  the release workflow now carries that control. See
  [`decisions/2026-05-11-supply-chain-security-gates.md`](../decisions/2026-05-11-supply-chain-security-gates.md).

### Package metadata and dependency surface

- `mb/pyproject.toml` declares four runtime dependencies on every platform
  (`openai`, `typer`, `pyyaml`, `rich`) plus one Linux-only dependency
  (`SecretStorage`, for Secret Service credential storage). Each has a
  documented floor (`>=`) and no upper
  bound. Floors come from the lowest version known to work; upper bounds
  would force premature compatibility breaks. The `minimum-dependencies`
  CI job installs every declared floor
  (`uv pip install --resolution lowest-direct`) on the lowest supported
  Python and on 3.12 and loads the CLI, so a floor `mb` cannot run on fails the PR.
  The job runs on Linux, so the Linux-only `SecretStorage` floor is installed
  and covered too.
- The dev extras (`ruff`, `mypy`, `pytest`, `pytest-cov`,
  `pytest-xdist`, `types-PyYAML`) are pinned by compatibility-friendly ranges
  (`~=`, `>=,<`).
- Optional extras (e.g. `ogrender`) follow the same floor-only rule.
- The base install footprint stays small on purpose. Adding a runtime
  dependency requires the dependency rubric in
  [`docs/dependency-choices.md`](dependency-choices.md).

### Dependency update policy

- Dependabot manages two ecosystems: `pip` (rooted at `/mb`) and
  `github-actions` (rooted at `/`).
- pip updates are grouped (security-only PRs separate from version
  upgrades), opened weekly, capped at five open PRs per ecosystem, and
  carry a release-age cooldown so a freshly-published version is not
  proposed the same hour it lands on the index.
- The cooldown gives the ecosystem time to detect malicious versions
  before Main Branch surfaces them as proposals. It is not a guarantee.
- Dependency PRs are reviewed for:
  - the upstream changelog or release notes;
  - new transitive deps introduced;
  - any required code changes;
  - whether the floor in `pyproject.toml` should move with the upgrade.
- Dependency upgrades are not bundled with feature work. Mixing them
  hides the supply-chain review surface inside a feature diff.
- A security advisory (Dependabot security update) is treated as
  expedited: review, validate, and merge as its own PR, ahead of the
  weekly cadence.

### No hash-locked install today

- `mb` is a small Typer-shaped CLI with four runtime dependencies on every
  platform (`openai`, `typer`, `pyyaml`, `rich`), plus the Linux-only
  `SecretStorage` dependency.
  Introducing `pip-tools`, `uv`, or `poetry` lockfiles would force a new
  dependency manager on contributors before the surface earns it.
- This is revisable. If the dependency footprint grows or a specific
  compromise scenario requires hash-locking, the decision will move and
  this section will say so.

### PR-time supply-chain review

When reviewing a PR, surface these checks alongside `scripts/check.sh`:

- Does this PR add a runtime dependency? If yes, does it pass the
  dependency rubric in [`docs/dependency-choices.md`](dependency-choices.md)?
- Does this PR change `.github/workflows/`? If yes, does it touch
  permissions, secrets, environments, or `id-token`?
- Does this PR change `.github/dependabot.yml`?
- Does this PR change `mb/pyproject.toml` dependency floors?
- Does this PR mix a dependency upgrade into a feature change?

The PR template includes a "Supply-chain review" checkbox so reviewers do
not have to remember the list from memory.

## Release-Time Supply-Chain Checks

The package-visible release gate in
[`docs/release-simulations.md`](release-simulations.md) already covers
runtime evidence. The checks below are the supply-chain layer on top of
it. Run them before tagging an `oe-v*` release.

1. Confirm `[Unreleased]` in `CHANGELOG.md` is empty or has been moved
   to the new version section. The published release body is built from
   the matching CHANGELOG section.
2. Confirm no new runtime dependency landed without a dependency-rubric
   note. `git log --oneline main..HEAD -- mb/pyproject.toml` should be
   reviewable in one pass.
3. Confirm no new workflow file landed with `id-token: write` or with a
   `permissions:` block broader than `contents: read`. Search:
   `grep -RIn "id-token\|permissions:" .github/workflows/`.
4. Confirm Dependabot is current. No open security advisories,
   no overdue grouped upgrades that should land in this release.
5. For release candidates that touch security-sensitive surfaces, consider a
   targeted local agentic security review sidecar over the changed risky files
   or candidates. DeepSec is the accepted local sidecar for this optional
   review aid; keep raw output under `.agent/`, publish only sanitized
   summaries, time-box AI processing, and treat findings as review leads rather
   than release truth. See
   [`decisions/2026-05-13-agentic-security-review-sidecars.md`](../decisions/2026-05-13-agentic-security-review-sidecars.md).
6. Confirm the `pypi` GitHub Environment still requires a reviewer.
   This is a settings check, not a YAML check.
7. Tag and publish via the GitHub Releases UI. The publish workflow
   triggers on `release: published`; the publish job blocks on the
   `pypi` environment approval.
8. Approve the deployment in the GitHub Actions UI only after the build
   and release-notes jobs have completed and the artifact looks right.
9. After publish, verify the fresh PyPI install per
   `docs/release-simulations.md` (Release Acceptance tier).

## Post-Compromise Response

If a dependency, the release pipeline, or the PyPI account is suspected
compromised:

1. **Stop publishing.** Do not approve any pending `pypi` environment
   deployment. Cancel any in-flight `publish` job. Revoke the
   pending-publisher binding in the PyPI project settings if the
   workflow file or repo is itself suspected.
2. **Pause Dependabot merges.** Close any open dependency PR that
   matches the suspected upstream package and any PR that updates the
   suspected GitHub Action. Add a comment naming why.
3. **Yank the affected release on PyPI** if a compromised version was
   already published. Yanking keeps existing installs intact while
   blocking new resolutions.
4. **Open a private security advisory** on GitHub. Do not discuss the
   suspected compromise in public issues or PR comments.
5. **Notify users.** Update `SECURITY.md` if the affected version
   range needs documenting. Add a `### Security` entry to
   `CHANGELOG.md` and to the next GitHub Release body.
6. **Rotate any credential that could have been exposed.** This
   includes `LINEAR_ACCESS_KEY` and any other repo secret the
   compromised workflow could have read.
7. **Record what happened.** Add a dated report under
   `docs/reports/YYYY-MM-DD-supply-chain-<short-name>.md` after the
   advisory is public, using the sanitized public-evidence rules in
   [`docs/release-simulations.md`](release-simulations.md).

This response path is intentionally short. Full incident response
playbooks would over-claim. Add new steps only after a real incident
proves the gap.

## Related Links

- [Supply-chain security gates decision](../decisions/2026-05-11-supply-chain-security-gates.md)
- [Agentic security review sidecars decision](../decisions/2026-05-13-agentic-security-review-sidecars.md)
- [Repo setup, visibility, and checks model decision](../decisions/2026-05-11-repo-setup-visibility-and-checks-model.md)
- [Workspace, repo, and sensitive-data boundaries decision](../decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md)
- [Dependency choices](dependency-choices.md)
- [Release simulations](release-simulations.md)
- [Checks and review model](checks-and-review-model.md)
- [OSS operating checklist](oss-operating-checklist.md)
- [SECURITY.md](../SECURITY.md)
