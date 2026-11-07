# Durable OpenSEO setup

Use this reference for the Sense and Ship loops: keep evidence readable and
keep the setup usable after a deploy or an idle gap.
For setup steps, use [setup.md](setup.md).
For recovery steps, use [upgrades-and-backups.md](upgrades-and-backups.md).
This file records requirements and evidence limits, not another install recipe.

## Read the status before acting

These labels apply to every claim and requirement in its paragraph or table row.
They describe the supplied evidence as of 4 November 2026.
They are not live checks of the business you are helping.

- OBSERVED means a recorded deployment or configuration read showed the result.
- PROBE ONLY means a signed-out request showed the result, without a login.
- SOURCE REVIEW means inspected code or vendor documentation supports the claim.
- REQUIRED means a setup must meet this rule; it is not a claim that it does.
- UNPROVEN means the complete behavior has not passed an acceptance check.

REQUIRED: record each business's own pin, check date, result and unchecked items.
Do not inherit a pass from another copy or a different release.
Keep private evidence and identifiers out of public examples.

## What must survive

REQUIRED: give each business its own accounts, deployment state and credentials.
Use a stable app host, such as `seo.example.com`, and its own Access team,
such as `example-team.cloudflareaccess.com`.
Keep the deployed code and installed upstream skills at compatible revisions.
Keep one declared owner for every domain, policy and OAuth setting.

OBSERVED: a custom host survived a redeploy when deployment configuration and
post-deploy enforcement both covered it. Declaring routes disabled in deployment
configuration alone did not keep alternate routes disabled in that deployment.
This is evidence for that checked setup, not a general deployment guarantee.

SOURCE REVIEW: dashboard-only settings can disappear during reconciliation.
A newer infrastructure dependency can support OAuth preservation even when the
OpenSEO release in use still pins an older dependency.
An upgrade alone is not proof that OAuth or domain reconciliation is fixed.

REQUIRED: keep the stable domain in reviewed deployment configuration.
Disable alternate public Worker and preview routes, or prove Access covers them.
Protect a new host before attaching it to the Worker.
Check the health endpoint too; application middleware need not protect it.

OBSERVED: attaching a domain before Access covered it briefly exposed health
output. App-route JWT checks did not protect that health endpoint.
A later signed-out denial does not erase an earlier exposure.

REQUIRED: preserve D1, KV, R2, workflow bindings, deployment state and encryption
secrets across redeploys. Keep resource identity stable, not just resource names.
Separate infrastructure continuity from login continuity in the setup record.

SOURCE REVIEW: a D1 export omits R2, KV, chat Durable Objects and the deployment
state store. A credentials-profile copy is not a full deployment-state backup.
UNPROVEN: complete service recovery has not passed a restore drill in this evidence.
Do not promise full recovery from a database export or a Worker rollback.

## Lifetimes and login triggers

SOURCE REVIEW: browser Access sessions, OAuth access tokens and OAuth grants have
separate lifetimes. A working browser cookie does not prove the agent can refresh.
The following durations describe evidence, not defaults to apply to every copy.

| Status | Item | What it means after an idle gap |
|---|---|---|
| SOURCE REVIEW | Managed OAuth access token | A short token lifetime, commonly 15 minutes, can refresh silently while the grant remains valid and the client supports refresh. |
| OBSERVED | Managed OAuth grant configuration | One inspected setup had a 336-hour grant. That is a finite human-login horizon, not an indefinite connection. |
| OBSERVED | Managed OAuth grant lapse | One setup with a 168-hour grant lost access when the grant ended, seven days after login. The client then offered only authenticate tools, and no read ran until a person logged in again. |
| SOURCE REVIEW | Managed OAuth grant expiry | Expiry requires identity-provider authentication again. Policy changes or revoked consent can also end access. |
| OBSERVED | Browser app session configuration | A separately configured 24-hour session did not change the inspected OAuth grant's lifetime. |
| SOURCE REVIEW | Access service token | Its selected expiry and renewal policy bound unattended access. A finite token cannot cover a longer idle gap without renewal. |
| UNPROVEN | Native OpenSEO API key lifetime | An omitted expiry field in the UI does not prove indefinite validity. Read actual key metadata and verify revocation behavior. |
| SOURCE REVIEW | Google token encryption | Losing or changing `BETTER_AUTH_SECRET` prevents use of stored encrypted tokens and can force Google reconnection. |
| SOURCE REVIEW | Google External Testing consent | Refresh tokens can expire after seven days. Review consent publishing status separately from MCP OAuth. |

REQUIRED: preserve `BETTER_AUTH_SECRET` in approved secret custody alongside the
Google client configuration. Never print it or save it in the business repo.
Keep exact Google callback URLs aligned with the stable host.
A configured Google health check proves configuration, not a successful data read.

SOURCE REVIEW: lost client credential caches, missing refresh support and changed
issuer or resource URLs can interrupt MCP access before an expected grant expiry.
An idle process restart with fresh credentials is useful evidence, but it does not
simulate months of elapsed time. Record a later real idle-gap check separately.

REQUIRED: record the next expiry action and its owner for every credential.
For finite human grants, state when browser approval will be needed again.
For machine credentials, record renewal and revocation ownership separately.
Never give a research agent administrative token-renewal authority by accident.

## What the OAuth probe actually proved

OBSERVED: one inspected Access configuration already had Managed OAuth and dynamic
registration enabled, with app-wide localhost and loopback callback allowances.
No configuration change was needed for that inspection.

PROBE ONLY: discovery advertised the expected authorization, token and registration
endpoints. An existing client's `http://localhost:49152/callback` authorization
request reached Access login. No interactive login or code exchange happened.
Full interactive sign-in and tool use were not proven by this probe.

PROBE ONLY: the same existing client using `http://127.0.0.1:49152/callback`
received an invalid-redirect response. `localhost` and `127.0.0.1` differ.
App-wide localhost permission does not extend an existing client's registration
to other callback hosts. Compare the exact host, port and path before changing it.

OBSERVED: on one setup, an agent later completed the MCP approval and the MCP
connection worked. This shows the current Access-mode path can work end to end.
It does not prove another business's setup, or any behavior after an idle gap.

OBSERVED: an "Invalid redirect URL" in that approval came from the agent, not from
Access. Opening the consent URL through Chrome's `/json/new` endpoint changed the
query encoding. Navigating to the exact URL with CDP `Page.navigate` worked three
times out of three. Access settings were correct throughout.

REQUIRED: an agent that approves MCP in a browser navigates directly to the exact
URL. Before changing Access settings or clearing a client for this error, rule out
the tool that opened the URL.

REQUIRED: inspect dynamic registration settings and per-client callback behavior.
An "OAuth enabled" check alone proves neither dynamic registration nor callbacks.
Discovery advertising registration does not prove a registration succeeds.
Do not clear a client or change policy based only on a boolean check.

PROBE ONLY: signed-out requests to the root, health, MCP and an unknown path
received Access challenges; a browser-style request reached the team's login.
These results prove the tested requests were gated at that time.
They do not prove allowed-user login, refused-user behavior or any tool call.

## After every deploy

REQUIRED: keep a dated receipt with pass, fail or unchecked for each item below.
A missing check remains unchecked. Do not turn it into a pass.
Use [setup.md](setup.md) for the checks and owner-run login steps.

| Status | Check | Evidence needed |
|---|---|---|
| REQUIRED | Host coverage | Inventory custom hosts, alternate Worker routes and previews, including the audit Worker. Note any route inventory that could not be read. |
| REQUIRED | Signed-out boundary | Root, health, MCP and an unknown path receive the intended Access denial or login challenge on every live host. A bare 401 is insufficient. |
| REQUIRED | Policy continuity | Intended people, policy precedence, app identity and audience match the approved configuration. No broad bypass appears. |
| REQUIRED | OAuth continuity | Compare grant duration, token lifetime, registration flags and client callbacks, not only the enabled flag. |
| REQUIRED | Allowed and refused people | A listed person reaches the app; an unlisted person is refused. Record browser proof separately from signed-out probes. |
| REQUIRED | App and data continuity | Signed-in health matches the pin; original projects and saved histories remain. Check each Google connection separately. |
| REQUIRED | Free MCP read | Initialize, list tools and run a saved-project read such as `list_projects`. Do not use paid research as a smoke test. |
| REQUIRED | Recovery coverage | Preserve configuration, encryption-secret custody and deployment-state recovery evidence. Mark an untested restore honestly. |

OBSERVED: post-deploy enforcement restored route restrictions in a recorded setup.
OAuth settings also survived a recorded redeploy. Neither observation removes the
need to compare desired and live state after the next deploy.

## UNPROVEN: external Access with machine credentials

UNPROVEN: no business has completed this move yet.
The proposed steps must not be followed as a recipe until results are recorded.
This section grants no exception to the skill's current authentication rules.
Keep the current Access-mode setup until a reviewed migration passes acceptance.

SOURCE REVIEW: the target puts Access under independent ownership and uses native
OpenSEO accounts internally. Agents would send a narrowly scoped Access service
token plus a separate native OpenSEO MCP key. Humans would pass Access and sign
in to their app account. This composition is an inference from separate contracts.
It has not been proved end to end.

SOURCE REVIEW: current Access-mode middleware requires human identity claims.
A service token passing the edge does not establish that app identity.
Native API keys are not a drop-in replacement in that mode.
Changing only the authentication mode can also strand the existing shared workspace.

REQUIRED before any future migration can be accepted:

- Prove a state-ownership handoff preserves the existing Access app, policies and
  audience without provider deletion. Merely omitting tracked resources can delete
  them. Whole-stack state clearing is not a safe handoff.
- Capture a consistent recovery set and prove selective state restoration.
  Preserve unrelated resources and test interruption and repeated execution.
- Prove the same user and workspace retain projects, histories and Google
  connections. Preserve the encryption secret and original resource identities.
- Prove every reachable host remains gated throughout the change.
  A missing route inventory blocks a claim of complete coverage.
- Prove the actual MCP client can supply both Access headers and the native key
  without saving literal secrets in tracked configuration or command arguments.
- Prove both credentials together allow a free saved-project read. Prove either
  credential missing, invalid or revoked denies access on a fresh connection.
- Prove machine access cannot reach dashboard or operator endpoints under the
  chosen path policy. Check path variants and policy precedence.
- Prove credential expiry, replacement and revocation. Define the maximum idle
  horizon and keep renewal authority separate from research authority.
- Prove an unchanged redeploy makes no external Access writes and preserves data.
  Repeat free reads after restart and record a later real idle-gap check.
- Prove rollback preserves the gate and identities. Distinguish an offline
  rehearsal from a rollback actually exercised against the deployed copy.

REQUIRED: stop on failed ownership, identity, lifetime or recovery checks.
Do not substitute a bypass, forged email claim or disabled JWT validation.
No indefinite-access promise follows from a short successful test.

## One home for each SEO fact

REQUIRED: use this ownership table when saving evidence.
OpenSEO is the record for measured items it holds. Read those items live.
Pushes and bets hold the why plus a link, never a copied number.
A source link may identify a project, report or run without repeating its values.

| Status | Fact | Single home |
|---|---|---|
| REQUIRED | Offer, audience, positioning, voice and approved site identity | Business repo. OpenSEO Context is a derived working copy with a link back. |
| REQUIRED | Saved keywords, tracked targets and rank history | OpenSEO keyword and rank records. Read current values there. |
| REQUIRED | Audit findings and supported Lighthouse results | OpenSEO audit run. Link to the run instead of copying counts. |
| REQUIRED | Tracked AI prompts and recommendation results | OpenSEO Prompt Tracking once configured. A planned tracker is not a measured baseline. |
| REQUIRED | Backlink results and supported local listings | OpenSEO project records when those checks exist. Do not imply an unrun check has results. |
| REQUIRED | Search Console and Analytics measurements available through OpenSEO | Read live through OpenSEO. The upstream provider remains the origin; do not keep a second local measurement ledger. |
| REQUIRED | Saved measurement reports | OpenSEO Reports when supported and saved. Link reviews to the report. |
| REQUIRED | Profile live/linked status that OpenSEO cannot hold | One business account register, linked by other plans and checkpoints. |
| REQUIRED | Spend and approved spending limits that OpenSEO cannot hold | One business spend ledger, reconciled with provider billing. Other work links to it. |
| REQUIRED | AI-crawler hits that OpenSEO cannot hold | One site telemetry dataset. Reviews read it and link to it. |
| REQUIRED | Measurements from tools OpenSEO cannot hold | One named external evidence store per measurement kind. Do not create a parallel OpenSEO summary ledger. |
| REQUIRED | Experiment purpose, interpretation and next decision | Business push, bet or decision record with links to evidence, never copied measurement values. |
| REQUIRED | Connection health, last check and next credential action | One private setup record. Reference secret-store items without recording secret values. |

REQUIRED: checkpoints and weekly reviews link to these homes.
They do not repeat rank tables, traffic counts, audit counts or spending totals.
If a tracker or report is absent, state that it is absent before proposing it.
Move duplicated facts to their single home and replace extra copies with links.
