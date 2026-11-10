# Durable OpenSEO setup

Use this reference for the Sense and Ship loops: keep evidence readable and
keep the setup usable after a deploy or an idle gap.
For setup steps, use [setup.md](setup.md).
For recovery steps, use [upgrades-and-backups.md](upgrades-and-backups.md).
This file records requirements and evidence limits, not another install recipe.

## Read the status before acting

These labels apply to every claim and requirement in its paragraph or table row.
They describe the supplied evidence as of 9 November 2026.
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
Use a stable app host, such as `seo.example.com`. Keep the deployed code and
installed upstream skills at compatible revisions. Keep one declared owner for
every domain, rate limit, user and key.

OBSERVED: in password mode, a custom host, the rate-limit bindings and two agent
keys survived a redeploy, and the keys still authenticated afterwards. Declaring
routes disabled in deployment configuration alone did not keep alternate routes
disabled; a post-deploy check enforced it. This is evidence for that checked
setup, not a general deployment guarantee.

SOURCE REVIEW: dashboard-only settings can disappear during reconciliation.
Keep the stable domain and the rate-limit bindings in reviewed deployment
configuration, and disable the alternate Worker and preview routes.

REQUIRED: preserve D1, KV, R2, workflow bindings, deployment state and encryption
secrets across redeploys. Keep resource identity stable, not just resource names.
Keep `BETTER_AUTH_SECRET` too: it signs sessions and encrypts stored Google tokens.

OBSERVED: a Worker secret survives a redeploy that no longer sets it. Removing the
operator secret takes an explicit delete by name and a 404 proof; see
[access-hardening.md](access-hardening.md).

SOURCE REVIEW: a D1 export omits R2, KV, chat Durable Objects and the deployment
state store. A raw export also does not re-import as written: loading it needs the
PRAGMA lines first, then every `CREATE TABLE`, then the rest in original order.
Time Travel is the primary rollback. Migrations apply only through the deploy.
UNPROVEN: complete service recovery has not passed a restore drill in this evidence.
Do not promise full recovery from a database export or a Worker rollback.

## Lifetimes and login triggers

Password mode has two credentials with different lifetimes: a browser session and
an agent's `oseo_` key. An agent does not depend on a browser login.

| Status | Item | What it means after an idle gap |
|---|---|---|
| OBSERVED | Agent `oseo_` key | Created with a stated expiry: the minimum is one day, the maximum 365 days. Two keys were set to one year. A key that expires answers 401 until the owner makes a new one. |
| OBSERVED | Key revocation | Deleting a key makes the next request 401. A password reset does not revoke keys. Removing the member ends its keys. |
| OBSERVED | Browser sessions | Version 0.1.26 has no sign-out-all control. A leftover session expires by itself, about a week after sign-in in one read. |
| OBSERVED | Self-host MCP OAuth grant | A person who signs in with the app's own OAuth gets a 30-day grant with a refresh token. The self-hosted UI cannot revoke it; it was removed by deleting its two KV entries. |
| SOURCE REVIEW | Google token encryption | Losing or changing `BETTER_AUTH_SECRET` prevents use of stored encrypted tokens and can force Google reconnection. |
| SOURCE REVIEW | Google External Testing consent | Refresh tokens can expire after seven days. Review consent publishing status separately. |

REQUIRED: record the next expiry action and its owner for every key. Renew before
expiry. Never give a research agent authority to mint its own keys.

REQUIRED: keep keys in `mb connect`, and test them with the MCP `initialize`
canary in [access-hardening.md](access-hardening.md). `mb connect test` cannot
verify a custom provider.

SOURCE REVIEW: a missing or changed `Authorization` header, a changed host, or a
client that caches nothing can interrupt MCP access before expiry. A restart with
fresh credentials is useful evidence but does not simulate months of elapsed time.
Record a later real idle-gap check separately.

## The boundary is the user account

REQUIRED: the operating-system user is the boundary for keys. A process running as
the same user can read the stored key and the local Claude config that holds the
header. Run each business under its own user, and do not run another business's
agents or untrusted code as that user. `mb` exec scoping reduces accidents; it is
not a defense against a same-user process.

REQUIRED: self-hosting has no meter and no cap. Before agents resume after any
cutover or upgrade, list active schedules: rank configs that are not manual and
AI-visibility trackers that are enabled. Pause paid calls until the owner's spend
facts are settled, and keep schedules off without a yes.

## After every deploy

REQUIRED: keep a dated receipt with pass, fail or unchecked for each item below.
A missing check remains unchecked. Do not turn it into a pass.
Use [setup.md](setup.md) and [access-hardening.md](access-hardening.md) for checks.

| Status | Check | Evidence needed |
|---|---|---|
| REQUIRED | Host coverage | Inventory custom hosts, alternate Worker routes and previews. workers.dev and previews answer 404 or have no route. |
| REQUIRED | Signed-out boundary | Health 200 with `authMode` `password`; `/mcp` 401; admin and import GET 404; an uninvited sign-up 403. |
| REQUIRED | Operator secret absent | The secret name is absent from the Worker, and a POST `{}` with the old secret to admin and import is 404. |
| REQUIRED | Rate limits | The sign-in, MCP and save-keywords bindings are present. |
| REQUIRED | Users and keys | Only the intended users and one key per agent exist; each key is enabled, unexpired and within a year. Read ids and expiries, never key values. |
| REQUIRED | Canary | An MCP `initialize` with each key returns 200; a missing or invalid key returns 401. |
| REQUIRED | App and data continuity | Health matches the pin; original projects and saved histories remain. Check each Google connection separately. |
| REQUIRED | Free MCP read | Initialize, list tools and run `list_projects`. Do not use paid research as a smoke test. |
| REQUIRED | Schedules | No active rank schedule and no enabled AI-visibility tracker unless the owner approved it. |
| REQUIRED | Recovery coverage | Preserve configuration, encryption-secret custody and deployment-state recovery evidence. Mark an untested restore honestly. |

## Option: Cloudflare Access

Access is for an owner who wants a human-only app. The following was observed on
setups that used it, and does not apply to password mode.

- OBSERVED: attaching a domain before Access covered it briefly exposed health
  output, and a later denial does not erase an earlier exposure. Add the host to
  Access first.
- SOURCE REVIEW: Managed OAuth access tokens are short, commonly 15 minutes, and
  refresh silently while the grant lasts. Grants lapse: one 168-hour grant ended
  seven days after login, the client then offered only authenticate tools, and no
  read ran until a person logged in again. Record when the next browser approval
  is due.
- OBSERVED: each deploy may clear Managed OAuth (upstream issue 304). Compare grant
  duration, token lifetime, registration flags and client callbacks, not only the
  enabled flag, and rerun the signed-out probe.
- PROBE ONLY: `localhost` and `127.0.0.1` callbacks differ; an existing client
  registered with one is refused on the other.
- OBSERVED: an "Invalid redirect URL" in an agent's approval came from the tool that
  opened the URL, not from Access. Navigate directly to the exact URL.
- SOURCE REVIEW: Access service tokens plus a native key is an unproven
  composition. Current Access-mode middleware requires human identity claims, native
  keys are not a drop-in there, and changing the mode can strand the existing
  shared workspace. Do not follow it as a recipe. Moving an existing Access copy to
  password mode needs a rehearsal on a restored copy, a claim of the existing user
  into the workspace, and the checks above; one such move passed that way.

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
