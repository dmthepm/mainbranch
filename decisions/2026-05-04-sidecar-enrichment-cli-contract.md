---
type: decision
date: 2026-05-04
status: accepted
topic: Sidecar enrichment CLI contract
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-02-github-native-business-os.md
  - decisions/2026-05-04-skill-cli-runtime-adapter-contract.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/265
participants: [Devon, Codex]
tags: [v0-3, sidecars, integrations, cli, context, product-boundary]
---

# Sidecar Enrichment CLI Contract

## Decision

Main Branch should support optional context-enrichment sidecars through a
narrow, one-shot CLI contract. A sidecar is an external provider tool that does
one specialized job, returns a stable JSON envelope, and exits. `mb` may
discover, connect, health-check, invoke, cache, and summarize sidecar output,
but the sidecar must not become a hard dependency of the core engine.

The first reference sidecar is `companyctx` for public company context. It is a
reference implementation, not a required install. Main Branch must continue to
work when `companyctx` is missing, unauthenticated, degraded, or replaced by a
different provider.

Sidecars enrich the Sense and Ship loops:

- Sense: fetch public or external context and report whether connected context
  providers are configured, healthy, stale, or degraded.
- Ship: give skills and future dashboards structured facts without making each
  workflow invent a new integration style.

The core rule is simple: sidecars return evidence; Main Branch decides how to
surface it; humans and skills decide which durable business truth to write back
to the repo.

## Product Boundary

`mb` remains deterministic and scriptable. It may:

- list available sidecar providers;
- register safe provider metadata through `mb connect`;
- store or reference credentials outside the business repo;
- run a provider health check;
- invoke a sidecar once and read JSON from stdout;
- cache rebuildable sidecar responses outside tracked business truth;
- expose sidecar status in `mb status --json`, `mb connect status --json`, and
  future dashboard JSON;
- print exact repair commands when a sidecar is missing, unhealthy, or stale.

`mb` must not:

- import a sidecar package as a required dependency;
- run background sync by default;
- turn sidecar output into canonical business truth automatically;
- commit raw third-party exports, account data, credentials, or bearer tokens;
- hide external account mutations behind a context-fetch command;
- become a provider marketplace.

Sidecars must be optional. A missing provider is a degraded enrichment path, not
a broken Main Branch install.

## Provider Discovery

Provider discovery has two layers.

The Main Branch provider registry defines provider ids that `mb` knows how to
reason about. Each sidecar provider entry must include:

- `id`, such as `companyctx`;
- display name;
- provider kind, such as `context`, `analytics`, `bookkeeping`,
  `transcription`, or `deployment`;
- executable or command name;
- minimum supported sidecar contract version;
- supported context subjects, such as company, domain, website, account,
  ledger, recording, or deployment target;
- whether auth is required;
- safe health-check command;
- default cache policy and TTL;
- safe repair command;
- whether the provider may read local repo files;
- whether the provider may call external networks.

The local business repo records only safe connection metadata in
`.mb/connect.yaml`, following the existing `mb connect` boundary. This file may
record provider id, account label, non-secret account identifiers, credential
backend, last health-check time, contract version, and cache policy. It must not
contain API keys, OAuth refresh tokens, service-account JSON, bearer tokens,
raw exports, or customer/member data.

Discovery should be boring:

1. `mb connect list` shows known providers and whether the sidecar executable is
   available.
2. `mb connect status --json` shows configured providers, missing executables,
   missing credentials, stale checks, and repair commands.
3. `mb connect test <provider>` runs the provider's safest available health
   check without fetching broad account data.
4. `mb context fetch <provider> ...` refuses to run when required health checks
   have not passed, unless the user explicitly asks for best-effort behavior.

## Minimal CLI Surface

Sidecar setup stays under the existing provider boundary:

```bash
mb connect <provider>
mb connect test <provider>
mb connect status --json
mb connect doctor
```

`mb connect status --json` is the read contract for configured providers.
`mb connect doctor` is the repair-oriented view over the same provider state:
it may include broader environment checks and should prioritize exact commands
that get the operator back to a healthy connection.

Context retrieval uses one new command family:

```bash
mb context fetch <provider> --subject <value> --json
```

The first implementation should keep the surface intentionally small:

- `<provider>` is a registered provider id, such as `companyctx`.
- `--subject <value>` is the human-provided lookup target. For `companyctx`,
  this can be a company name or domain.
- `--kind <kind>` may disambiguate the subject when a provider supports more
  than one subject kind.
- `--refresh` ignores any cached entry and fetches again, replacing the cache on
  success.
- `--offline` reads only cache and fails clearly when no cache exists.
- `--no-cache` avoids writing a local cache for sensitive or throwaway lookups.
- `--json` emits the sidecar envelope plus Main Branch wrapper metadata.

The first implementation may reject unsupported combinations rather than
guess. For example, if `companyctx` only supports public company/domain context,
`mb context fetch companyctx --kind ledger ...` should fail with an exact repair
or "unsupported kind" message.

Future command families such as `mb context list`, `mb context cache clear`, or
provider-specific aliases can be added after `fetch` proves useful. They should
not be added up front.

## Sidecar Invocation Contract

A sidecar is invoked as a one-shot command. It receives explicit arguments and
returns JSON on stdout. Diagnostic logs go to stderr. Exit codes are part of the
contract:

| Exit code | Meaning | `mb` behavior |
|---|---|---|
| 0 | Usable response | Accept envelope when schema is valid and status is `ok`, `empty`, `partial`, or `degraded`. |
| 1 | Provider-reported error | Accept envelope only if status is `error`; surface safe errors and repair commands. |
| 2 | User/config/auth problem | Treat as provider not ready; print repair command. |
| 3 | Unsupported request | Treat as deterministic failure; do not retry. |
| 4 | Transient upstream problem | Surface retry guidance; may use stale cache. |
| 5+ | Provider bug or invalid output | Treat as failed provider; include safe diagnostic summary. |

`mb` validates the envelope before exposing it to skills or dashboards. Invalid
JSON, a missing `schema_version`, or an unsupported schema version is a provider
failure even when the process exits successfully.

Status and exit code must agree. `ok`, `empty`, `partial`, and `degraded`
should exit 0 with a valid envelope because they are usable responses.
`error` should exit 1 with a valid envelope because the provider understood the
request but returned no usable data. Exit codes 2 and higher are reserved for
failures where the request could not be completed as a valid sidecar response.

Sidecars must not prompt interactively during `mb context fetch`. A provider
that needs setup should fail with a repair command that points back to
`mb connect <provider>` or provider-specific setup docs.

## JSON Envelope

Every sidecar response must use this top-level shape:

```json
{
  "schema_version": "mb.sidecar.context.v1",
  "status": "ok",
  "provider": {
    "id": "companyctx",
    "name": "Company Context",
    "version": "0.4.0",
    "contract_version": "mb.sidecar.context.v1"
  },
  "request": {
    "id": "01HXAMPLE000000000000000000",
    "subject": {
      "kind": "company",
      "value": "Example Co",
      "domain": "example.com"
    },
    "mode": "fetch",
    "requested_at": "2026-05-04T18:00:00Z"
  },
  "data": {
    "summary": "Public context summary for Example Co.",
    "facts": [],
    "links": [],
    "metrics": []
  },
  "provenance": [
    {
      "source": "https://example.com/about",
      "source_type": "public_web",
      "retrieved_at": "2026-05-04T18:00:00Z",
      "license": "unknown",
      "confidence": "medium"
    }
  ],
  "warnings": [],
  "errors": [],
  "cache": {
    "key": "companyctx/company/example.com",
    "policy": "use",
    "hit": false,
    "ttl_seconds": 604800,
    "expires_at": "2026-05-11T18:00:00Z"
  }
}
```

Required fields:

- `schema_version`: semantic contract string. The first accepted contract is
  `mb.sidecar.context.v1`.
- `status`: one of `ok`, `partial`, `degraded`, `empty`, or `error`.
- `provider`: provider identity, version, and sidecar contract version.
- `request`: request id, subject, mode, and timestamp.
- `data`: provider-specific structured payload. It may be empty.
- `provenance`: source records for externally derived facts.
- `warnings`: non-fatal issues.
- `errors`: fatal or request-scoped issues.

Optional but recommended fields:

- `cache`: cache key, cache policy, freshness, and expiry.
- `limits`: provider rate-limit or quota hints safe to share.
- `redactions`: fields removed because they were secrets, raw account data, or
  unsafe for durable repo storage.
- `next_actions`: provider-suggested repair or refinement actions.

Warnings and errors use this shape:

```json
{
  "code": "auth.unvalidated",
  "message": "Run `mb connect test companyctx` before fetching context.",
  "retryable": false,
  "safe_to_share": true,
  "repair_command": "mb connect test companyctx"
}
```

`safe_to_share` is required for warnings and errors. It lets skills and future
issue-drafting flows avoid leaking local paths, credentials, account details, or
private business data.

## Status Semantics

`status` is about the requested enrichment, not the operator's whole business
repo.

- `ok`: the provider completed the request and returned usable data.
- `partial`: some data is usable, but at least one source, field, account, or
  upstream service was missing.
- `degraded`: the provider could answer only from stale cache, limited auth, or
  a reduced mode.
- `empty`: the provider found no matching context and this is a valid result.
- `error`: no usable data is available for this request.

`mb context fetch` should exit 0 for `ok`, `partial`, `degraded`, and `empty`
when the envelope is valid. It should exit non-zero for `error`, invalid
envelopes, unsupported schemas, missing provider executables, missing required
auth, unsupported requests, or failed health checks.

## Provenance

Every externally derived fact that may influence business judgment needs
provenance. Sidecars do not need to cite every low-level API field, but they
must provide enough evidence for a skill or human to inspect where the context
came from.

Provenance records should include:

- source identifier, URL, file path, account id, or provider object id when safe;
- source type;
- retrieval timestamp;
- provider confidence when available;
- terms/license hints when available;
- whether the source is public, private, user-supplied, or cached.

Private account ids may appear only when they are already safe connection
metadata for the business repo. Raw third-party account data, customer data,
ledger rows, transcripts, ad account exports, or analytics event streams must
not be committed to tracked business files by default.

## Caching

Sidecar caches are rebuildable local operational state. They are not canonical
business truth.

Default cache location should be outside tracked repo files, under the Main
Branch local state home. A future implementation may use a repo-local
`.mb/cache/` directory only if it is gitignored, repairable, and documented.
Cache entries must include the provider id, subject, schema version, fetched
time, expiry, and enough metadata to explain stale reads.

`mb context fetch` should support three cache modes:

- default: use fresh cache when available, otherwise fetch;
- `--refresh`: fetch again and replace cache when successful;
- `--offline`: read cache only and fail clearly when no cache exists.

Stale cache may be used only when the output status is `degraded` and the
envelope includes a warning. Skills must not treat stale sidecar data as fresh
business truth.

## Auth Boundary

`mb connect` owns the connection boundary. Sidecars may use credentials provided
through a documented secret backend, environment variable, OS keychain, runtime
config, or provider-native auth flow, but secrets must stay outside tracked
business files.

Provider health has three separate states:

- executable discovery: can `mb` find the sidecar command?
- credential presence: can the provider find required credentials?
- safe validation: can the provider prove those credentials work without
  fetching broad or sensitive data?

A secret reference alone is never healthy. A provider that cannot safely probe
the upstream API should report that limitation explicitly and stay below
`ready` until a documented manual validation path exists.

Sidecars must not mutate external accounts during health checks or context
fetches. Spending money, publishing, emailing, deploying, or changing third
party account state belongs behind an explicit Ship command and human approval
gate, not behind enrichment.

## Failure Behavior

Sidecars are allowed to fail. Main Branch must fail soft:

- `mb status` may say context enrichment is unavailable, degraded, or stale.
- `mb start` and skills may continue with repo-local context.
- `mb context fetch` should explain the provider failure and exact next command.
- Future dashboards should show missing sidecars as optional integrations, not
  core engine breakage.
- Cached stale data may be offered only when clearly marked degraded.

Failure messages must avoid leaking secrets, raw account data, customer/member
data, or private local paths. When a low-level provider error is unsafe to share,
the sidecar should return a safe summary plus a local log pointer outside the
business repo.

## Reference and Future Sidecars

`companyctx` is the first reference sidecar because public company/domain
context is useful across Sense and Ship workflows and can stay optional.
It should prove:

- command discovery;
- connection and health status;
- public company/domain lookup;
- stable `mb.sidecar.context.v1` envelope output;
- provenance for public sources;
- graceful degradation when unavailable.

Next plausible sidecars:

- public-site context: sitemap, page inventory, headings, metadata, and broken
  link summaries;
- ads metrics: spend, impressions, CTR, CPA, creative ids, and campaign health
  summaries;
- bookkeeping: ledger/P&L summaries, open invoices, cash movement, and account
  reconciliation hints;
- transcription: local recording or provider transcript summaries with source
  file provenance;
- analytics: site traffic, events, conversions, and attribution summaries;
- deployment helpers: build status, deployment health, DNS checks, and rollback
  metadata.

Each future sidecar should add provider-specific `data` schemas, but it must
reuse the same envelope, provenance, auth, cache, and failure contract.

## Validation Contract

For this decision, Level 0 docs/decision validation is enough: frontmatter is
valid, links resolve, the public/private boundary is preserved, and the decision
does not claim implemented sidecar support before CLI work lands.

Future implementation work must add:

- focused CLI tests for `mb context fetch`, exit codes, cache modes, invalid
  envelopes, missing providers, and `--json` behavior;
- `mb connect` tests for sidecar provider discovery, health checks, repair
  commands, and safe metadata;
- fixture repo smoke when new `.mb/` files or cache paths are introduced;
- package/install smoke when provider registry data or bundled sidecar adapters
  ship in the wheel;
- runtime/manual notes when skills start consuming sidecar context.

## Consequences

- Main Branch gets one integration style for optional enrichment instead of a
  bespoke tool contract per workflow.
- `mb connect` remains the credential and health boundary.
- `mb context fetch` becomes the deterministic retrieval surface for skills,
  scripts, and dashboards.
- Sidecar data is useful evidence, not automatically canonical business truth.
- `companyctx` can become the reference implementation without becoming a core
  dependency.

## Review Trigger

Revisit this decision when either of these becomes true:

- more than two sidecars need provider-specific lifecycle behavior that does
  not fit the envelope; or
- a proposed sidecar wants background sync, account mutation, hosted auth, or a
  marketplace surface inside Main Branch.
