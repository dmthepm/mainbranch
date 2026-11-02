---
title: mb connect real-credential dogfood
date: 2026-05-03
linked_issue: https://github.com/dmthepm/mainbranch/issues/224
linked_linear: MAIN-195
release: v0.2.3
status: completed
tags: [integrations, dogfood, credentials, v0-2]
---

# `mb connect` Real-Credential Dogfood

## Summary

`mb connect` passed the most important public/private boundary check: secret
values were not written to `.mb/connect.yaml` and did not appear in the tested
human or JSON command output.

The dogfood also exposed the main product gap: current integration health means
"a credential-like value is stored", not "the provider account was validated".
That is good enough for the credential-storage foundation, but not enough for a
beginner or onboarding agent to trust that a provider-specific sync will work.

Follow-up issues:

- [#227](https://github.com/dmthepm/mainbranch/issues/227) - Add GitHub
  auth and repo context to `mb connect`.
- [#228](https://github.com/dmthepm/mainbranch/issues/228) - Add
  `mb connect test` / provider validation.
- [#229](https://github.com/dmthepm/mainbranch/issues/229) - Improve
  `mb connect` repair JSON for onboarding agents.

## Scope Tested

Tested in disposable business repos created with the local engine checkout.
Temporary repos and temporary local secret stores were removed after the run.

Baseline commands:

- `mb connect list --json`
- `mb connect status --json`
- `mb doctor --json`
- `mb status --json`

Credential and repair commands:

- explicit missing `--from-env`
- explicit successful `--from-env`
- sensitive metadata rejection
- unknown provider rejection
- missing-secret repair state after deleting the local secret
- macOS Keychain storage smoke with a non-secret sentinel value

The only real local credential available in this shell was GitHub CLI auth. No
safe provider-specific environment variable was present for Cloudflare, Meta,
Google, Postiz, Apify, or transcription. To test the explicit env import path
without printing a secret, a locally available `gh` credential was used only as
an opaque in-memory value in a disposable environment. This verified
`--from-env`, storage, status, and leakage behavior. It did not validate Postiz
or any provider API. Future dogfood should use a purpose-created disposable
credential for this kind of opaque storage test, then rotate or delete that
credential after the run.

## Results

Baseline:

- provider registry listed `google`, `meta`, `cloudflare`, `postiz`, `apify`,
  `beancount`, and `transcription`;
- no GitHub provider was present;
- clean `mb connect status --json` returned zero configured providers;
- `mb doctor --json` reported `integration-credentials` as informational:
  "no providers connected";
- `mb status --json` returned integration summary counts with zero configured
  providers.

Successful explicit env import:

- `mb connect postiz --from-env --json` returned success when the provider env
  var was explicitly populated for the command;
- `.mb/connect.yaml` was created and contained provider metadata, account label,
  auth type, backend name, and a `mainbranch://...` secret ref;
- `.mb/connect.yaml` did not contain the credential value;
- command stdout/stderr for `mb connect`, `mb connect status`, `mb doctor`, and
  `mb status` did not contain the credential value;
- local-file fallback storage wrote the secret outside the repo with directory
  mode `0700` and file mode `0600`;
- `mb connect status --json`, `mb doctor --json`, and `mb status --json` all
  reported one configured and healthy provider after storage.

macOS Keychain smoke:

- forcing `MB_CONNECT_SECRET_BACKEND=macos-keychain` stored a non-secret
  sentinel credential successfully;
- `mb connect status --json` read the Keychain item as present;
- command output did not contain the sentinel value;
- the generated Keychain item was deleted successfully after the smoke.

Repair and malformed states:

- missing explicit env var failed with a provider-specific env var name and did
  not create a secret;
- sensitive metadata such as `api_key=...` was rejected;
- deleting the local secret changed provider state to `missing_secret`;
- `mb connect status --json` exited non-zero and reported `needs_repair: 1`;
- `mb doctor --json` reported the integration repair as warning severity, so
  `mb doctor` still exited zero;
- `mb status` showed integration counts, but the human output did not name the
  provider that needed repair.

GitHub check:

- local `gh` auth was available;
- `mb connect github` failed because GitHub is not in the provider registry;
- in a disposable repo with no GitHub remote, `mb status --json` reported
  GitHub as authenticated but degraded with repeated "no git remotes found"
  errors for each GitHub query.

## Beginner / Onboarding-Agent Assessment

Good:

- the credential boundary is understandable: repo metadata is separate from
  local secret storage;
- the status JSON is secret-safe in the tested paths;
- missing secrets are represented as structured state, not as crashes;
- sensitive metadata key rejection prevents common accidental leaks.

Confusing or incomplete:

- `connected` currently means "secret present", not "provider validated";
- there is no `mb connect test` or `mb connect doctor` command;
- GitHub is part of the real onboarding loop but not part of `mb connect`;
- `mb status` summarizes integration counts but does not name broken providers;
- it is not clear whether a missing connected-provider secret should leave
  `mb doctor` at exit zero because the integration check is warning severity,
  or whether credential repair should make doctor fail;
- `mb connect status --json` exposes low-level secret refs that are safe but
  not useful repair copy for a beginner-facing agent;
- missing GitHub repo context creates repeated degraded query errors instead of
  one clear repair state.

## Public / Private Boundary

No credential values, account-private IDs, raw provider responses, customer
data, or local temp paths are included in this report. The dogfood evidence kept
raw command outputs in `.context/` only, and the temporary credential stores
used during the run were removed.
