---
type: decision
date: 2026-09-10
status: accepted
topic: Platform credential-store boundary
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/959
linked_decisions:
  - decisions/2026-05-13-provider-cli-api-wrapper-boundary.md
linked_docs:
  - docs/connect.md
  - docs/connection-model.md
  - docs/dependency-choices.md
participants: [Devon, Codex]
tags: [credentials, connect, keychain, secret-service, reliability, security]
---

# Platform Credential-Store Boundary

## Decision

Put one credential-store interface between provider workflows and platform
storage. Auto selection chooses the macOS login Keychain on macOS and the
existing Secret Service default collection on Linux. It never chooses the
plaintext local file automatically.

Run every native operation in a killable helper with a fixed deadline, and
share one credential-store deadline across aggregate commands. Send credential
refs and values through stdin/stdout JSON, never process arguments, and discard
helper stderr and raw exceptions. Reads must suppress unlock or access-approval
UI and return sanitized missing, locked, unavailable, incompatible, or
timed-out states.

On macOS, use Security.framework directly. Update existing generic-password
items with `SecItemUpdate`; add only when the exact service/account item is
missing. Default item access trusts the creating application identity. Do not
broaden the ACL to every application.

On Linux, use SecretStorage directly. Use only the existing default collection,
check collection and item lock state, never call unlock, and use Secret
Service's in-place item update for existing records. Preserve matched legacy
Python keyring attributes; use the replacement contract when creating a new
record. SecretStorage is a Linux-only dependency.

## Identity And Resolution

Provider secrets remain keyed by the business `repo_id`, provider, and secret
slot. User-scope fallback is also `repo_id`-indexed so worktrees and scheduled
jobs for one business can share setup without crossing into another business.
Rotating a provider changes only the selected business's reference.

Legacy `keyring` metadata maps to the matching native adapter because the
existing macOS and Secret Service records use the same service/account shape.
Explicit `local-file` remains available for compatibility and tests, but a
malformed file is an unavailable store and is never silently overwritten.
Tokenless reconnects preserve and validate an existing ref/backend because a
store migration requires a new secret value.

The public `--token` option remains deprecated compatibility input and can
expose caller-supplied values in argv. Main Branch does not use it in generated
commands or internal helper calls; those paths use stdin. Removing the public
option requires a separate compatibility decision.

## Operating Boundary

The macOS login Keychain is scoped to a security session. A user `LaunchAgent`
in the logged-in GUI launchd domain is the smallest durable placement for a
scheduled reader; Main Branch does not install a daemon, broker, or launchd
job. A desktop unlock does not guarantee that an already-running remote session
is unlocked.

Keychain lock and item ACL approval are separate. Provision from the intended
stable installed `mb` Python identity. Trusting only `/usr/bin/security` does
not authorize the native reader. A different interpreter identity may require
a one-time Access Control change in Keychain Access; unattended reads fail
closed instead of opening that dialog. Do not grant every application access.

## Deferred

A 1Password service-account reference adapter is a follow-up. Operators may
pipe an externally selected 1Password field into `--token-stdin`, but vault
choice, service-account credentials, desktop integration approval, and
reapproval are operator-owned bootstrap. Main Branch does not claim that path
is implemented or unattended.
