---
title: Postiz scheduling rail smoke
date: 2026-05-07
linked_issue: https://github.com/dmthepm/mainbranch/issues/352
linked_linear: MAIN-257
release: v0.3.x
status: partial
tags: [integrations, postiz, social, scheduling, smoke]
---

# Postiz Scheduling Rail Smoke

## Summary

Postiz REST API access is reachable and authenticated in a private safe test
setup, but the scheduling rail is not promoted to supported yet because the
tested organization had zero connected social channels. Without a connected
channel, the smoke could not create a meaningful draft or scheduled post and
could not prove the account/provider/action/evidence loop that Main Branch
needs for playbook/provider-health support.

Main Branch should keep Postiz as a candidate scheduling rail until a follow-up
smoke connects a safe test channel, creates a harmless draft or scheduled item,
confirms that item appears in Postiz, and records sanitized evidence.

## Scope Tested

Public docs reviewed:

- Postiz Public API introduction:
  <https://docs.postiz.com/public-api/introduction>
- Postiz create-post API:
  <https://docs.postiz.com/public-api/posts/create>
- Postiz list-posts API:
  <https://docs.postiz.com/public-api/posts/list>
- Postiz list-integrations API:
  <https://docs.postiz.com/public-api/integrations/list>
- Postiz MCP introduction:
  <https://docs.postiz.com/mcp/introduction>
- Postiz MCP tools reference:
  <https://docs.postiz.com/mcp/tools>

Private setup used:

- One self-hosted Postiz instance in a maintainer-controlled test setup.
- API key read from outside the public repo.
- No API keys, private hostnames, account identifiers, handles, raw payloads,
  screenshots, local host paths, or provider credentials are committed here.

Test time:

- 2026-05-07 America/Los_Angeles, which is 2026-05-08 UTC.

## Checks

| Check | Result | Public-safe evidence |
|---|---|---|
| Route reachable (unauthenticated probe) | Pass | Unauthenticated integrations request returned HTTP 401 with an API-key error, proving the route reached Postiz rather than the login UI. |
| Private API key available outside repo | Pass | Key presence was checked only as present/missing; the value was not printed. |
| Auth accepted | Pass | `GET /api/public/v1/is-connected` returned HTTP 200. |
| Connected integrations listed | Pass, empty | `GET /api/public/v1/integrations` returned HTTP 200 with count `0`. |
| Draft/scheduled test post created | Blocked | The integration list returned zero connected channels, so there was no safe channel id to use for a meaningful post payload. A deliberately empty draft request was also rejected with HTTP 400 because `posts` must contain at least one item. |
| Draft/scheduled item visible in Postiz list | Blocked | `GET /api/public/v1/posts` returned HTTP 200 with count `0`. |
| Cleanup needed | No | No test post was created. |

## What This Proves

- The tested Postiz deployment is alive at its API route.
- The Postiz API key path can authenticate through a secret stored outside the
  repo.
- Main Branch can inspect whether connected channels exist through the public
  integrations API.
- A no-channel setup fails safely before content can be queued.

## What This Does Not Prove

- Creating a draft against a connected social channel.
- Scheduling a post against a connected social channel.
- Listing provider schemas from a live connected account.
- Confirming a draft or scheduled item appears in the Postiz UI.
- MCP transport behavior in a configured runtime.
- Production auto-posting.
- DMs, replies, likes, follows, comment monitoring, inbox mutation, or growth
  bot behavior.
- Provider credential setup, OAuth callback setup, uptime, backups, TLS, or
  self-host maintenance.

## Current Product Decision

Postiz remains a preferred candidate rail for social scheduling, not a
supported Main Branch scheduling rail. The next smoke should connect one safe
test social channel, then prove:

1. approved action: draft or scheduled post only;
2. account/provider visibility: connected channel listed and redacted;
3. mutation evidence: harmless item created with a redacted Postiz id;
4. confirmation evidence: item appears through list/API or UI;
5. cleanup or deliberate safe retained state;
6. recoverable failure notes for normal users.

Provider claims stay narrow until that follow-up passes.
