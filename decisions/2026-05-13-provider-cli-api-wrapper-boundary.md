---
type: decision
date: 2026-05-13
status: accepted
topic: Provider CLI/API and mb wrapper boundary
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/585
linked_decisions:
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
  - decisions/2026-05-12-meta-ads-cli-readiness.md
  - decisions/2026-05-13-creative-media-generation-rails.md
linked_docs:
  - docs/dependency-choices.md
  - docs/agent-cold-start.md
participants: [Devon, Codex]
tags: [providers, integrations, cli, connect, privacy, product-boundary]
---

# Provider CLI/API And mb Wrapper Boundary

## Decision

Use provider CLIs, APIs, MCP servers, SDKs, and dashboards as raw capability.
Use `mb` wrappers only when Main Branch needs to turn that capability into a
safe, stable business primitive. Use skills and playbooks for the
human-friendly workflow on top.

The default path is:

```text
provider CLI/API = raw capability
mb wrapper = safe, stable business primitive
agent skill/playbook = human-friendly workflow
```

Provider tools are right for discovery, dogfood, debugging, and one-off
operator smoke. Build an `mb` wrapper when the workflow needs repeatability,
privacy boundaries, stable JSON, approval gates, tests, cross-runtime behavior,
or product support claims.

## Wrapper Rule

Build an `mb` wrapper when **three or more** of these are true:

- the workflow will be repeated;
- agents need to consume the output;
- raw provider output may leak private data;
- the result needs stable JSON;
- the workflow should work across Claude Code, Codex, and future runtimes;
- the workflow needs approval gates;
- the workflow will show up in docs, skills, or release claims;
- the command is part of the product promise.

Use the provider CLI/API directly when:

- the team is still discovering what data exists;
- it is a one-off debug or dogfood check;
- the provider output is small and safe;
- there is no stable product workflow yet;
- only a developer or operator will run it;
- Main Branch is not ready to own support for the surface.

This rule is a decision aid, not an automatic promotion. A wrapper still needs
the validation evidence appropriate to its risk: focused CLI tests, safe
fixtures, read-only or mutation smoke, package/fixture/runtime checks when the
changed surface requires them, and public-safe evidence in the PR.

## Relationship To mb connect

`mb connect` owns setup, credential routing, readiness, repair, and safe
connection metadata. It should answer:

1. Is the provider path known?
2. Is the local tool installed when one is required?
3. Are credentials available without exposing secret values?
4. Can the safest health check or read smoke pass?
5. What exact next command repairs the first missing requirement?

Do not overload `mb connect` with every provider workflow. Once a provider is
ready, repeated domain work should move into a specific wrapper such as
`mb ads meta summary`, `mb books ...`, `mb site check`, or a future narrow
command family. `mb connect` should keep reporting readiness and repair facts
that those wrappers can trust.

Safe repo metadata may record provider ids, setup state, non-sensitive labels,
credential backend names, and readiness timestamps. It must not record tokens,
refresh tokens, API keys, service-account JSON, raw account exports, raw
customer/member data, or private local paths.

## Relationship To Skills And Playbooks

Skills and playbooks are the chat UX and judgment layer. They may call `mb`
wrappers for facts, then translate those facts into plain business guidance.
They should not reimplement provider readiness, auth checks, raw-output
redaction, or JSON normalization in prose.

A skill may call a provider CLI/API directly when the work is exploratory,
operator-approved for the current run, and not a Main Branch support claim.
When that direct call starts appearing in repeatable docs, skill prose,
release evidence, or cross-runtime workflows, the wrapper rule applies.

Provider mutation, publishing, spending, customer contact, and account changes
need explicit operator approval at the workflow boundary. Repo files can
record intent or approval notes, but authority comes from the provider account,
the operator, and the local secret/session context.

## Secrets And Privacy

Credentials never belong in chat, markdown, GitHub issues, PR bodies, fixtures,
committed `.mb/` files, or public evidence.

Supported credential homes are:

- `SecretStore` / OS keychain when `mb` owns the setup path;
- provider-native local auth stores when the provider CLI owns auth;
- environment variables for the current local process;
- GitHub Actions secrets only when a hosted-runner workflow is explicitly
  accepted for that provider.

Raw provider payloads, raw account exports, account-private IDs, customer or
member rows, private analytics, raw ledgers, screenshots containing private
account context, and local absolute paths should stay in ignored scratch,
private operator storage, or the provider system. Public docs and PRs should
record sanitized summaries, exit codes, result shapes, redaction behavior, and
safe next commands.

## JSON Envelope Expectations

An `mb` wrapper that emits machine-readable provider facts should use the
shared `mb.json_result` envelope pattern unless a more specific accepted
contract says otherwise. Keep command-specific payloads small and stable, and
include enough metadata for agents and future dashboards to decide whether the
output can be reused.

Provider wrapper JSON should usually include:

- command and schema metadata through the shared result envelope;
- `ok`, `result_status`, `errors`, `warnings`, and `actions`;
- provider id and checked timestamp;
- readiness state and repair command when not ready;
- privacy flags such as whether raw payloads were written, tracked files were
  changed, ids were redacted, or exact private values were included;
- `safe_to_share` when the output could be copied into chat, issues, docs, or
  tracked files;
- bounded domain facts rather than raw provider dumps;
- provenance for direct provider reads when useful.

`safe_to_share: false` is valid and often correct. It means the output may be
useful in the operator's local session after approval, but should not be copied
into public issues, PRs, docs, or committed business files.

## Support Claims

Main Branch may describe a provider path as:

- **direct/provider-native** when operators or agents can use the provider tool
  outside Main Branch, with no Main Branch support claim;
- **readiness** when `mb connect` can identify setup state and repair path;
- **read-only wrapper** when `mb` owns a bounded safe read with stable JSON and
  smoke evidence;
- **mutation-gated wrapper** only when preview/dry-run behavior, approval
  gates, provider authority, failure handling, tests, and safe-account smoke
  exist;
- **unsupported, planned, candidate, or reference** when the evidence is not
  enough for a stronger claim.

Do not promote support language because a provider CLI exists, a maintainer ran
a local smoke, or a skill can paste a command. Promote only when Main Branch
owns the wrapper contract, docs, tests, and public-safe evidence for the exact
surface being claimed.

## Examples

### Meta Ads

Direct Meta CLI use was right for MAIN-366 / #581 dogfood. It proved the
official `meta-ads` / `meta` path, setup requirements, auth status behavior,
and read-only command surface without making Main Branch own account summaries
yet.

`mb connect meta` is right for readiness because the user needs safe credential
storage, setup state, repair commands, and read-smoke status. It should store
tokens through `SecretStore`, keep `.mb/connect.yaml` to safe metadata, and
surface the same provider state to `mb status --json --peek`.

`mb ads meta summary --json` is right for MAIN-367 because agents need a
compact, safe, repeatable, privacy-bounded account summary across runtimes. The
wrapper should ask before live reads, avoid raw payloads and tracked caches,
redact account IDs, keep `safe_to_share: false`, and use the shared JSON result
envelope.

Meta campaign, ad set, ad, creative, budget, pixel, catalog, page, or audience
mutation remains unsupported until a separate mutation-gated wrapper has
approval gates, authority checks, tests, and safe-account smoke.

### Image Generation

Direct provider calls are fine for fake-asset smoke and current-run creative
experiments. They are not enough for a Main Branch image-generation support
claim.

Main Branch should only claim a supported image rail once artifact records,
media storage boundaries, credential handling, approval language, cost
visibility, provider/model metadata, and smoke evidence exist. Until then,
skills may write prompts and output records, use prompt-only/manual fallback,
or call an approved provider for the current run without presenting it as a
stable Main Branch provider wrapper.

OpenAI GPT Image 2 is the first static-image readiness target from the creative
media decision, but that target still needs setup detection, approval copy, and
fixture-safe smoke before support language moves beyond candidate/readiness.
