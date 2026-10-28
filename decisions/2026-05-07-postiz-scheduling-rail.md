---
type: decision
date: 2026-05-07
status: accepted
topic: Postiz scheduling rail
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
  - decisions/2026-05-04-workspace-repo-sensitive-data-boundaries.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/352
participants: [Devon, Codex]
tags: [v0-3, integrations, social, postiz, onboarding, self-hosting]
---

# Postiz Scheduling Rail

## Decision

Main Branch should treat Postiz as the preferred candidate scheduling rail for
social publishing, pending a focused MCP/API smoke. Postiz fits the product
shape better than generic automation suites because it is a social scheduler
with a documented MCP surface, hosted and self-hosted deployment paths, and a
clear role in the Ship loop.

This decision does not make Postiz a broad automation dependency. The intended
scope is scheduling, drafting, connected-account inspection, and publishing
support only where a smoke proves the path. Comment monitoring, DM automation,
auto-replies, auto-likes, auto-follows, and inbox workflows remain out of scope
unless a later decision accepts and tests those surfaces.

## Why This Fits

Main Branch is opinionated infrastructure, not a neutral directory of tools.
The product should teach operators why a provider is recommended, when to own
the service, and when to rent a hosted rail.

The default stance:

- own the boring parts when agents can help maintain them;
- rent provider-heavy or high-friction rails when platform approval, uptime,
  maintenance, or app-review burden would distract from the business;
- choose tools with inspectable APIs, MCP surfaces, or deterministic command
  boundaries;
- keep secrets and runtime state outside committed business repos.

Postiz currently looks like a strong candidate because its public docs describe
MCP tools for listing integrations, reading platform schemas, scheduling posts,
and generating media. Its hosted service can reduce setup burden for normal
operators, while its Docker Compose path supports operators who already maintain
a Linux box, homelab, or VPS.

## Onboarding UX

`mb connect postiz` should eventually guide the operator through a choice, not
dump generic setup links:

```text
Postiz setup

1. Use hosted Postiz
   Best if you want scheduling working today and do not want to maintain
   servers, Docker, DNS, backups, upgrades, or provider app config.

2. Use an existing Linux box / homelab
   Best if you already run Docker services and want ownership.

3. Use a boring VPS
   Best if you want ownership but do not have an always-on machine.

4. Skip for now
   Main Branch can still draft posts and save them under pushes/.
```

Main Branch should not recommend Railway. It also should not make AWS, GCP, or
Azure the beginner default. Those are reasonable only when the operator already
knows that ecosystem. A generic "boring Docker-capable VPS" category is safer
than picking a public canonical host before Main Branch has deployment smoke
evidence.

## Hosting Guidance

Public docs may describe these options generically:

| Option | Recommend when | Tradeoff |
|---|---|---|
| Hosted Postiz | The operator wants scheduling today and does not want server maintenance | Monthly cost, less ownership |
| Existing Linux box / homelab | The operator already runs Docker services and wants ownership | Must maintain backups, upgrades, DNS, TLS, and uptime |
| Boring VPS | The operator wants ownership but has no always-on machine | Still requires server maintenance |
| Skip | The operator only needs drafts for now | No automatic scheduling |

Private operator details, such as specific homelab service locations, belong in
private repos or local setup notes. Public Main Branch docs should say
"existing Linux box / homelab" rather than naming private hosts, internal
network addresses, or runtime-specific paths.

## Future `mb connect` Shape

Tracked business repos may store only safe Postiz metadata:

- provider id: `postiz`;
- install mode: `hosted`, `self_hosted`, `vps`, or `unknown`;
- base URL or account label when safe;
- connected platform labels or ids when safe;
- last health-check timestamp;
- credential backend reference, not the credential itself.

Secrets must stay in the OS keychain, runtime-local config, environment, 1Password,
or another explicit secret store. API keys, OAuth tokens, refresh tokens, and
provider credentials must not be committed.

## Doctor Checks

Future `mb connect doctor` support should check:

- base URL reachable;
- HTTPS/TLS validity when the URL is public;
- MCP or API endpoint reachable;
- auth present outside the repo;
- connected platforms listed;
- account or integration schema readable;
- harmless draft/schedule smoke available;
- timezone/clock sane for scheduled posts;
- self-host only: backup/update note exists.

Doctor should report exact repair steps. It should not try to install Postiz or
choose a host for the operator.

## Validation Before Support Claim

Before public docs call Postiz a supported scheduling rail, run a focused smoke:

1. Read current Postiz MCP/API docs.
2. Configure a private test token outside the repo.
3. Verify the MCP/API endpoint is reachable.
4. List connected integrations.
5. Create a harmless draft or scheduled test post in a safe account.
6. Confirm the draft/scheduled item appears in Postiz.
7. Record public-safe evidence in a PR.

If this passes, update `docs/dependency-choices.md` from planned optional
provider to supported scheduling rail for the tested surface only.

The first smoke on 2026-05-07 America/Los_Angeles proved REST endpoint
reachability and auth, but did not promote Postiz to supported because the
tested organization had no connected channels. See
[the public-safe smoke report](../docs/reports/2026-05-07-postiz-scheduling-smoke.md).

## Sources

- Postiz MCP introduction: https://docs.postiz.com/mcp/introduction
- Postiz Docker Compose install: https://docs.postiz.com/installation/docker-compose
- Postiz pricing and hosted/self-hosted positioning: https://postiz.com/pricing
