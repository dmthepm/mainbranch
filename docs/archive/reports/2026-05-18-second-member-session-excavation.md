# Second Member Session Excavation

## Evidence Set

- Date reviewed: 2026-05-18
- Source session dates: 2026-05-16 through 2026-05-18
- Issue: [#653](https://github.com/dmthepm/mainbranch/issues/653)
- Linear: MAIN-408
- Evidence level: sanitized review of a private member/customer agent session
  export, subagent logs, tool outputs, and app/runtime logs
- Public/private boundary: no raw transcript, member/customer names, private
  local paths, private account details, screenshots, tokens, customer data,
  contact rows, proof quotes, or private business strategy are included here

Private evidence remains in ignored local scratch space and Linear-only context.
Do not reconstruct member/customer identity from this public report.

## Summary

The second real session moved past first-run setup into daily operation:
repairing runtime wiring, auditing business context, wiring providers, reading
connected-account facts, mutating external systems with approval, opening a paid
traffic push, and closing the day with saved history.

The product lesson is that Main Branch is now useful enough to expose a bigger
trust boundary. The operator wants one morning system that reads the business,
connectors, calls, content, CRM, ads, files, and schedule, then creates the work
for approval. That is the right direction, but the release plan has to keep
runtime discovery, connector readiness, source-ingestion privacy, provider
mutation gates, and secret hygiene ahead of broader automation claims.

## Timeline

| Phase | What Happened | Product Signal |
|---|---|---|
| Runtime start | `/mb-start` was initially unknown because the active Claude worktree did not have Main Branch skill links wired. | Slash discovery is still a P0 trust point in linked workspaces. |
| Repair | `mb start --json`, `mb doctor`, and repair flow restored handoff readiness and skill links. | Deterministic repair works, but the user should not have to diagnose worktree internals. |
| Business audit | The agent audited authenticated community content and public proof surfaces, then saved research/checkpoints. | Authenticated-source mining is valuable and needs explicit public/private and proof-permission rails. |
| Provider setup | The session worked through Google, HubSpot, Apify, Zoom, Fireflies, Drive, Resend, Meta, YouTube, Cal.com, and Cloudflare surfaces. | Operators experience all of this as "connect my tools"; Main Branch needs clearer connector-readiness states. |
| External writes | The agent performed real CRM updates and email/provider smoke tests, then discussed paused ad creation. | Provider writes need a reusable plan/approve/apply contract, not only conversational caution. |
| Transcript mining | Fireflies, Zoom, phone-call, and Drive sources exposed large volumes of useful source material with mixed-account privacy concerns. | Transcript ingestion should start with source inventory, manifests, skip filters, and permission gates. |
| Push opening | The agent opened and updated a time-boxed paid-ad push using connected provider facts and offer inputs. | Push workflow is a strong Ship loop, but provider mutation and spend remain explicit approval boundaries. |
| Remote/mobile | The operator wanted phone-based note capture and remote approvals; current runtime remote control required a launch flag. | Mobile/remote workflow is a P2/P3 operating signal, not a current Main Branch support claim. |
| Closing | `/mb-end` summarized saved checkpoints and crystallized strategy tensions. | Reflect loop is working; report only the public-safe product implications. |

## Prioritized Findings

| Priority | Area | Finding | Evidence Type | Route |
|---|---|---|---|---|
| P0 | Runtime discovery | A Claude worktree launched without working Main Branch skill links, so `/mb-start` was unknown until repair ran. | Session export, runtime metadata | [#655](https://github.com/dmthepm/mainbranch/issues/655) |
| P0 | Secret hygiene | A provider smoke/debug path retrieved a credential from local secret storage and exposed credential material in the private transcript. | Session export, tool output | [#658](https://github.com/dmthepm/mainbranch/issues/658) |
| P0 | Provider mutation safety | Real external-account writes happened during the session, while broader CRM/ads/email/provider writes rely on conversational approval rather than a reusable Main Branch mutation contract. | Session export, tool output | [#656](https://github.com/dmthepm/mainbranch/issues/656) |
| P1 | Transcript/source privacy | Meeting, call, Drive, and authenticated-community sources produced valuable material but required manual skip filters and manifest-first handling for mixed private/business accounts. | Session export, tool output | [#657](https://github.com/dmthepm/mainbranch/issues/657) |
| P1 | Connector readiness | Claude.ai connectors, Claude Code tools, plugins, local CLIs, API keys, and `mb connect` rails were repeatedly conflated during setup. | Session export, runtime/tool metadata | [#654](https://github.com/dmthepm/mainbranch/issues/654), [#636](https://github.com/dmthepm/mainbranch/issues/636) |
| P1 | Dashboard/approval loop | The operator explicitly wants a morning snapshot plus approval queue over activity, tasks, email/social drafts, provider facts, and decisions. | Session export, closing reflection | [#599](https://github.com/dmthepm/mainbranch/issues/599) |
| P1 | Repo boundary | The operator needs a durable choice for linked repos across related businesses, landing pages, finance, and course operations. | Session export, closing reflection | [#631](https://github.com/dmthepm/mainbranch/issues/631) |
| P1 | Stale-source cleanup | Corrections to ownership, roles, positioning, retired angles, and campaign assumptions required cross-file reconciliation. | Session export, generated history | [#630](https://github.com/dmthepm/mainbranch/issues/630) |
| P2 | Provider roadmap | Google, YouTube, Zoom, Fireflies, Drive, Resend, Meta, Cloudflare, Cal.com, HubSpot, Stripe, Aircall, and Microsoft document surfaces all have pull. | Session export | Backlog by provider; split only after support boundary and smoke target are clear. |
| P2 | Remote/mobile capture | The operator wants mobile note capture and remote approvals during long-running work. | Session export | Roadmap signal; do not claim Main Branch support yet. |
| P2 | Email/content operations | Resend plus CRM plus approval flow suggests a future daily email/social draft queue. | Session export | Route through dashboard/content queue work when scoped. |
| P2 | Paid-ad creation | The agent can draft paused ad objects after approval, but creation/spend should remain gated. | Session export | Route through #656 before provider write support grows. |
| P3 | Newsletter/playbook signal | The operator's workflow vision is a strong content/playbook story for Main Branch. | Closing reflection | Marketing/operator-playbook signal only. |
| P3 | Runtime education | Claude worktree names, restart requirements, and remote-control launch flags needed explanation. | Session export | Fold into runtime guidance where it affects supported surfaces. |

## What Worked

- `mb doctor repair` restored missing Main Branch skill wiring and validation
  returned clean afterward.
- `/mb-start` and `/mb-end` worked once runtime discovery was repaired.
- The agent used `mb` facts before status/start summaries and provider checks
  when Main Branch had the surface.
- Connector work found real provider facts and distinguished read-only checks
  from writes in several moments.
- The agent used title-only searches and skip filters before reading transcript
  content from mixed sources.
- Saved checkpoints told a business-readable story across audits, decisions,
  provider setup, and push work.

## What Failed

### Actual Failures

- `/mb-start` was not discoverable in the active Claude worktree at the first
  start attempt.
- Google/YouTube OAuth paths ran into account, organization, and scope
  confusion before the session found alternate connector paths.
- Zoom plugin access worked but returned empty results because the account and
  cloud-recording assumptions did not match the operator's actual setup.
- Remote/mobile control was debugged late and required a relaunch flag that
  could not be enabled in the already-running session.

### Trust Risks

- Provider credential material appeared in the private transcript during a
  direct smoke/debug path.
- Real CRM data was mutated after approval, but no reusable provider mutation
  gate framed object counts, risk, apply step, and verification.
- Authenticated community comments, call transcripts, phone-call recordings,
  Drive files, and public review content can all become proof or source
  material; permission and privacy boundaries need to be explicit before
  public use.

### UX Gaps

- The operator had to reason through worktree names, plugin restarts, connector
  bridge surfaces, OAuth scope upgrades, local CLIs, API keys, and `mb connect`
  rails in one long session.
- "Connect my tools" is not one product surface yet; the current path mixes
  Main Branch native providers, runtime connectors, marketplace plugins, and
  unsupported provider experiments.
- The operator's desired daily snapshot and approval queue is broader than the
  current dashboard issue, but it should be routed through read-only facts first
  rather than provider mutation.

## Follow-Up Routing

P0 and P1 findings now have concrete public routes:

| Issue | Owner Loop | Validation Need |
|---|---|---|
| [#655](https://github.com/dmthepm/mainbranch/issues/655) | Sense / Decide | Claude worktree fixture or runtime smoke for missing skill wiring and repair |
| [#658](https://github.com/dmthepm/mainbranch/issues/658) | Ship | Secret-redaction tests or provider smoke review proving no token echo |
| [#656](https://github.com/dmthepm/mainbranch/issues/656) | Ship | Provider write plan/apply contract plus at least one smoke or fixture path |
| [#657](https://github.com/dmthepm/mainbranch/issues/657) | Sense / Decide / Reflect | Manifest-first ingestion workflow with skip filters and privacy gates |
| [#654](https://github.com/dmthepm/mainbranch/issues/654) | Sense / Ship | Connector-readiness guidance and smoke expectations by connector type |
| [#636](https://github.com/dmthepm/mainbranch/issues/636) | Sense / Decide / Ship | Shared workflow source architecture should include connector readiness and safety gates |
| [#599](https://github.com/dmthepm/mainbranch/issues/599) | Sense / Decide | Read-only dashboard fixture with provider readiness and next-action facts |
| [#631](https://github.com/dmthepm/mainbranch/issues/631) | Decide | First-run repo-boundary decision helper |
| [#630](https://github.com/dmthepm/mainbranch/issues/630) | Sense / Decide / Reflect | Stale-source reconciliation workflow |

P2/P3 items stay in this report until a narrower issue can own them. Do not
bundle all providers, remote control, dashboard writes, ad creation, and
transcript mining into the shared workflow source branch.

## Release Plan Impact

This excavation should affect the next shared Claude/Codex workflow plan in one
specific way: #636 should include connector readiness, safety gates, and
provider write boundaries as required shared-workflow metadata. It should not
expand into provider implementation or runtime parity.

Immediate release cleanup should prioritize:

- `/mb-start` discoverability and repair in Claude worktrees;
- secret-safe provider smoke guidance;
- connector readiness vocabulary;
- provider mutation plan/approve/apply language;
- transcript/source-ingestion privacy rails.

Do not describe Claude.ai connector availability as Claude Code support without
bridge smoke. Do not claim provider mutation, ad creation, transcript mining, or
mobile remote workflows as supported Main Branch behavior until each has an
adapter, approval boundary, and smoke evidence.

## Public/Private Boundary Notes

- Do not publish the raw session export, tool-result files, screenshots, phone
  call manifests, provider payloads, transcript content, or private local paths.
- Do not name the member/customer, their business, contact rows, account IDs,
  emails, phone numbers, provider account names, or proof quotes in public
  follow-ups.
- Use synthetic businesses and fake provider payloads for tests.
- Use generic terms: operator, business repo, authenticated community, connected
  provider, transcript provider, CRM, ad account, source material, proof
  candidate.

## Process Artifact

This excavation reused [`docs/session-excavation.md`](../../session-excavation.md)
and added a provider/connector pass to that workflow. Future excavations should
explicitly scan for:

- slash/runtime discovery failures;
- connector bridge readiness gaps;
- provider writes and approval gates;
- secret echoes in transcripts;
- transcript/community ingestion privacy boundaries.
