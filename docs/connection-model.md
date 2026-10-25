# Connection Model

Main Branch uses `mb connect` as the durable, secret-safe account handle for
business tools. The model is deliberately smaller than a native integration:
record enough setup truth for agents to reason from facts, keep credentials
outside git, and require separate approval for anything that can change a
provider account.

Field lesson: using a custom Mercury provider for a bookkeeping migration
proved the shape. The same pattern should work for Printful, A2X, Xero, bank
APIs, and niche SaaS tools before Main Branch has native wrappers.

## What worked

- Provider metadata lives in `.mb/connect.yaml`, so setup state is durable and
  inspectable.
- Secret values live outside git through one credential-store interface. Auto
  selection uses the macOS login Keychain or Linux Secret Service and never
  silently falls back to a plaintext local file.
- `mb connect exec <provider> -- <command>` runs one command with the
  credential in its environment only, so agents and scripts use a secret
  without ever seeing it. `mb connect token <provider>` remains the raw read
  path and refuses all output destinations (exit 3) unless `--print` is passed.
  Releases require a local audit write; see [connect.md](connect.md#local-release-audit).
- `status`, `doctor`, `list`, `identity`, `hygiene`, and `test` give agents
  facts without copying credentials into chat or workpapers.
- User scope lets worktrees and scheduled jobs resolve the same credential
  setup without asking the operator to re-auth every day.

## What failed

- Custom providers were stored correctly but broad list/status/doctor surfaces
  initially enumerated only the built-in provider registry.
- Provider-specific status was parsed by the CLI but not handled as a distinct
  status path.
- Repair commands for missing custom secrets did not include `--custom`, which
  made the correct repair easy to miss.
- Custom providers had no identity schema, so agents could see "connected" but
  not the safe role of the account, such as `operating_cash_source`.
- Docs did not show the full finance-token lifecycle or safe script pattern.
- Same-provider rotation treated every user-scope repo as a sibling and could
  rewrite another business's credential. User-scope fallback was already
  `repo_id`-indexed; rotation now preserves the same boundary.
- A desktop-unlocked macOS Keychain did not imply that an already-running
  remote security session was unlocked.
- macOS Keychain items trusted the exact Python that created them. uv's Python
  builds are unsigned, so every Python change brought back an access dialog
  that unattended reads waited on until the safety deadline. Credentials now
  live in items owned by Apple-signed `/usr/bin/security`, existing items move
  there on their first successful read through a staged copy that is never
  removed before the final item reads back, and unattended reads fail fast
  with `keychain_prompt_pending` instead of waiting on a dialog. A hand-edited
  item access list can still raise a dialog; the command deadline bounds it.
- `ready` was reported for providers that were never called, so it meant "a
  credential is stored" rather than "this credential works". Storage and
  verification are now separate facts.

## Lifecycle

1. **Declare.** Choose a provider id and record safe intent metadata.
   Built-ins use the registry; custom providers use `--custom`.
2. **Store secret.** Store token material through `--token-stdin`,
   provider-native auth, the native OS credential store, an explicitly selected
   legacy local file, or a current-process environment command. Never commit
   `.env` files or paste raw tokens into docs, issues, logs, or workpapers.
3. **Smoke test.** Run `mb connect test <provider>` when a safe read-only probe
   exists. Without a probe, the credential reports `stored, unverified`:
   present and readable, with nothing claiming it works. Only a provider call
   sets `provider_verified` and reaches `ready`. See
   [connect.md](connect.md#stored-is-not-verified).
4. **Record identity metadata.** Record non-secret facts that prevent agents
   from guessing: role, access level, data domain, auth state, account label,
   workspace, environment, or provider-specific ids when safe for the repo.
5. **Use the credential through `exec`.** Scripts and agents run
   `mb connect exec <provider> -- <command>`, and the command reads the
   secret from its environment. They do not put tokens in child argv, echo
   them, enable shell trace, write env files, or commit raw exports.
6. **Rotate or repair.** Missing or stale secrets report a reconnect command.
   For custom providers, repair output includes `--custom --token-stdin`. A
   connection with a recorded `--source op://...` reference rotates with
   `mb connect rotate <provider>`, which re-reads, stores and probes.
7. **Audit and hygiene.** `mb connect doctor`, `mb connect status --all`,
   `mb connect identity`, and `mb connect hygiene` are the read-only audit
   surfaces before agents use provider facts.

## Public vs Private

Safe to commit:

- provider id and category;
- account label when it does not expose a private account number;
- secret backend name and secret ref;
- role, access level, data domain, auth state, environment, and source system;
- validation state, whether a provider call confirmed the credential, the
  timestamp of the last successful call, other timestamps, and repair commands.

Keep private:

- API keys, access tokens, refresh tokens, passwords, service-account JSON;
- raw bank, payment, order, customer, member, payroll, tax, or legal exports;
- full account numbers, routing numbers, card numbers, and private debt terms;
- provider payloads, workpapers, logs, or scripts that print secret values.

## Finance Providers

Finance and bookkeeping providers are more sensitive than marketing/site
providers because read access can expose bank balances, customer payments,
vendor names, debt terms, tax records, and payroll context. Treat finance
connections as read-only by default and keep raw source data in a restricted
finance repo, local books vault, or provider export location.

Recommended custom metadata:

```text
role=operating_cash_source
access_level=read_only
data_domain=banking
auth_state=api_token
source_system=mercury
account_ref=operating-cash
```

Avoid raw bank account numbers in repo metadata. Use a business-readable handle
such as `operating-cash` and put the exact mapping in the private finance
workspace if needed.

## Agent Boundary

Agents can do without seeing secrets:

- inspect provider readiness;
- check whether a secret is present;
- read safe identity metadata;
- tell the operator which repair command to run;
- run approved commands through `mb connect exec`, which never prints the
  credential;
- summarize sanitized import counts and freshness.

Approval-gated every time:

- provider mutation;
- spend, budget, campaign, or checkout changes;
- money movement, transfers, bill pay, refunds, or payout changes;
- emailing, publishing, posting, customer/member contact, or fulfillment writes;
- exporting raw private records into a shared repo, public issue, PR, log, or
  model context.

## Implemented Follow-Ups

- Custom providers are included in broad status/list/doctor surfaces.
- Custom provider tests cover status, list, doctor, token, missing secrets, and
  user scope.
- Custom provider identity metadata is surfaced by `mb connect identity`.
- `docs/connect.md` includes Mercury-style Keychain setup and safe token use.
- Credential access is bounded behind native macOS and Linux adapters with
  sanitized missing, locked, unavailable, incompatible, and timeout states.
- User-scope fallback remains `repo_id`-indexed, and rotation no longer changes
  a same-named provider belonging to another business.

## Issue-Ready Follow-Ups

- Add `mb connect rotate <provider>` as a clearer alias over reconnecting with
  `--token-stdin`, preserving the selected business's `repo_id` boundary.
- Add finance-provider metadata validation warnings for raw-looking account
  numbers, missing `access_level`, and missing `data_domain`.
- Add an optional 1Password service-account reference adapter without teaching
  committed `.env` files. Vault selection, service-account credentials, and
  unattended bootstrap remain operator-owned.
- Add native read-only wrappers only after one provider has public-safe smoke
  evidence and a privacy-bounded output contract.
