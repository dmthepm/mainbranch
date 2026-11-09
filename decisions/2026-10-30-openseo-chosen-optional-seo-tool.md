---
type: decision
date: 2026-10-30
status: accepted
topic: OpenSEO as the chosen, optional SEO tool for Main Branch
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/1175
linked_decisions:
  - decisions/2026-05-11-mb-books-foundation.md
  - decisions/2026-05-13-provider-cli-api-wrapper-boundary.md
linked_docs:
  - docs/dependency-choices.md
participants: [Devon, Claude]
tags: [seo, openseo, dependency, optional]
---

# OpenSEO as the Chosen, Optional SEO Tool

## Decision

**Main Branch uses OpenSEO as its chosen SEO tool, reached through the `/mb-seo`
skill. It is optional.** This follows the hledger pattern: chosen when a business
uses it, never required. A business that skips it loses nothing else.

**`llms.txt` ships on every site as a map for agents.** This is the owner's
commitment. No visibility claim is made until a test shows one.

**Support is experimental.** Main Branch claims support only after a business
deploys OpenSEO from the skill alone and the login durability check passes on or
after 2026-11-07. Codex is not supported.

## The Contract

- **One copy per business.** Each copy runs on that business's own Cloudflare and
  DataForSEO accounts, with its own Worker and resources and no binding to any
  existing service. There are no shared keys.
- **Useful first.** `/mb-seo` reviews public pages with no accounts. OpenSEO is
  offered, not assumed, and its limits on ranking and traffic claims are stated.
- **Google comes later.** It is set up only when the owner asks for Search Console
  or Analytics evidence through OpenSEO. Each business needs its own Google
  client.
- **Paid research asks first, with a cost.** MCP read-only hints are not a spend
  limit, and `mb` cannot enforce a cap. Rank and AI-visibility schedules stay off
  unless the owner approves them.
- **Password mode with per-agent keys (updated 9 Nov 2026).** Each agent gets its
  own admin user and its own expiring `oseo_` key, stored in `mb connect`; the app
  has no Access app, workers.dev and previews are off, and rate limits are bound.
  One live business ran this way and passed its checks. Cloudflare Access stays an
  option for an owner who wants a human-only app. The earlier rule that kept Access
  on and forbade static tokens is retired, because Access cannot serve an agent
  without a browser approval that lapses.
- **Pinned releases.** Copies move only to a reviewed release SHA. `alchemy
  destroy` is never used.
- **Durable findings land in the business repo.** Losing a copy should cost little.
  A D1 export is not a full backup, and no restore drill has passed.
- **Secrets stay out.** Tokens stay in `mb connect`. Secrets and bootstrap output
  are never printed.

## Why a Skill and No Command

An Access challenge proves the guard is present. It cannot show that OpenSEO or
its data connections work. A deterministic `mb seo check` waits until repeated use
shows which readiness facts owners need and a read-only smoke proves them. Scheduled
pulls and `mb` wrappers are out of scope for the same reason.

## Why OpenSEO

OpenSEO is MIT licensed, self-hostable, and exposes an MCP server. A business pays
DataForSEO directly and needs no subscription suite. It is young and changes
quickly, which is why this decision pins releases and stays experimental.

## Known Risks

- A key lives at least one day after a leak, a password reset does not revoke keys,
  and version 0.1.26 has no sign-out-all.
- Self-hosting has no meter or cap, so schedules are checked before agents resume.
- Same-user processes can read a stored key; the user account is the boundary.
- With Access: OpenSEO issue 304 (each deploy clears Managed OAuth), and agent login
  past the grant lifetime is unproven.
- Workers Free stops site audits at about 40 pages.

## Exit Path

Findings stay in the business repo, so a copy can be dropped without losing what
it taught. A business can call DataForSEO directly or swap the tool. `mb google`
reads are unaffected.

## Review Trigger

Revisit if the first business run or the login check fails, if upstream changes
its license or stops shipping releases, if the password-mode key route changes,
or if repeated use shows a read-only check can prove a useful operation.
