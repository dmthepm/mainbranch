# Hardening a self-hosted copy

Password mode is the recommended setup: the app signs people in with its own
accounts, and each agent reaches MCP with its own `oseo_` key. Checks are
owner-run or owner-approved. Report the app, the keys, and each data connection
separately. Print status codes only, never bodies, keys, or the `.env.selfhost`
file.

Status labels follow [durable-setup.md](durable-setup.md). The pin in
[setup.md](setup.md) is OpenSEO v0.1.26 (`7d89cfb3ca30b2819356c57c5b746a1048b9743f`),
the release the pattern below was OBSERVED on at one live business in November 2026
and the one this skill read in source. Source citations are paths in that checkout.
A step marked NOT VERIFIED is not proven by the source; do not expose the app or
hand out a key until it has been checked and recorded, and a check that fails is a
finding, not a pass.

## First owner: protected bootstrap

Why this comes first. `src/server/standalone/sign-up.ts:13-22` leaves registration
open while no user exists (`isFirstAccountOpen`), and `src/lib/auth-mode.ts:7-11`
says the first visitor creates the administrator's account. A password-mode deploy
on an empty database is therefore public, with a takeover window until the intended
owner signs up, and a later 403 on sign-up cannot tell you the owner was first.
Every route stays protected until the intended owner exists. The order, with no step
skipped or reordered:

1. **Deploy in Access mode with a one-address allow-list** (setup steps 4 and 5:
   `AUTH_MODE=cloudflare_access`, `ACCESS_ALLOWED_EMAILS=<owner>`). In that mode
   `/api/auth/*` answers 404 (`src/routes/api/auth/$.ts:7-11`), so there is no
   sign-up route to take over.
2. **Prove it is protected before anyone signs in.** Signed out, on the custom host
   and the workers.dev host, request `/`, `/mcp`, `/api/standalone/admin` and a
   sign-up path. Pass: an Access redirect or Access 401 on each, never app content.
   `/api/health` may answer 200 for a short time; it is liveness only. Any other 200
   is a stop.
3. **The intended owner signs in once through Access.** That inserts the user row
   (`src/middleware/ensure-user/delegated.ts:22-45`).
4. **Verify the owner's identity.** Owner-run, token from `mb connect exec`, output
   to the owner's terminal only:

   ```bash
   mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" --env CLOUDFLARE_API_TOKEN -- \
     pnpm exec wrangler d1 execute open-seo-db-selfhost --remote \
     --command 'SELECT id, email FROM user'
   ```

   Pass: exactly one row, with the intended owner's email. The database name is
   `open-seo-db-${stage}` with stage `selfhost` (`deploy/alchemy/alchemy.run.ts:96`).
   Anything else: stop and tell the owner; do not switch.
5. **Switch to password login and remove Access.** Edit `.env.selfhost`:
   `AUTH_MODE=password`, `OPENSEO_OPERATOR_SECRET=<at least 32 random characters>`
   (`src/server/standalone/operator-auth.ts:5`), no `ACCESS_ALLOWED_EMAILS`. Deploy.
   The deploy removes the Access application it created
   (`docs/SELF_HOSTING_CLOUDFLARE_OPERATIONS.md`, Switching from Cloudflare Access
   to password accounts). A user already exists, so registration is closed.
6. **Prove an uninvited sign-up creates no user.** Request a sign-up for an address
   nobody invited: 403. Rerun the step 4 query: still one row. A new row or a 200
   means stop, remove the new user, and treat the install as untrusted.
7. **Give the owner a password and the owner role** with the operator command, the
   password on standard input so it is not in argv or history:

   ```bash
   read -rs -p 'Owner password: ' pw; echo
   printf '%s\n' "$pw" | OPENSEO_URL=https://<HOST> pnpm selfhost:admin \
     claim-legacy-user <USER_ID_FROM_STEP_4> <owner-email> shared-workspace
   unset pw
   ```

   `src/server/standalone/admin.ts` sets the email and password and writes an
   `owner` membership in `shared-workspace`.
8. **Verify owner membership.** Rerun step 4 with
   `SELECT user_id, organization_id, role FROM member` (database column names, from
   `drizzle/sqlite/0003_light_sage.sql:35-43`): exactly one row, `user_id` equal to
   the user ID from step 4, `organization_id` equal to `shared-workspace`, and role
   `owner`. Any other result: stop. Then the owner signs in with the password and opens Team settings.
9. Only now continue with the setup below: shutdown of the other host, limiters,
   per-agent users and keys, then removal of the operator secret.

If the owner will not use Access for the first deploy, stop. The source gives no way
to run an empty password-mode deploy that is closed to the first visitor, and
`pnpm selfhost:admin create-user` (the "before anyone opens the URL" route in the
operations guide) cannot run until the Worker is already reachable. The switch
sequence above is the upstream-documented one, but a full run at this pin is NOT
VERIFIED: report every result.

## The setup

1. **Password mode, no Access app.** `AUTH_MODE=password` in `.env.selfhost` is set
   by the bootstrap above, never on an empty database, and the Access application
   is gone after it. Existing Access users are carried over by
   `claim-legacy-user`; sign-up stays closed to the public: an uninvited sign-up
   request returns 403 and creates no user.
2. **workers.dev and previews off.** Declare the custom host in deploy config
   (`CUSTOM_DOMAIN`, `deploy/alchemy/alchemy.run.ts:160-170`), then turn off the
   `workers.dev` route and version previews. Two hosts means two doors, and a
   preview URL is one more. The stack sets no switch for either on the app Worker
   (only the audit Worker is `url: false`), so turning them off is an owner step
   in the Cloudflare dashboard or API, and whether a later deploy restores them is
   NOT VERIFIED. Probe each after the step and after every deploy; both must answer
   404 or have no route. Until that passes, give no agent a key.
3. **Rate limits bound.** Bind the sign-in, MCP and save-keywords limiters
   (`AUTH_RATE_LIMIT`, `MCP_RATE_LIMIT`, `SAVE_KEYWORDS_RATE_LIMIT`). One
   rehearsal returned 429 inside the window.
4. **One admin user and one key per agent.** Each agent gets its own admin user
   (invitations only create admins) and its own `oseo_` key, so removing one
   agent removes one user and its keys. A key can do everything its user's role
   can over MCP, paid calls included. OBSERVED: the live setup used one owner with
   a named key per agent; per-agent users are the tighter shape this skill asks
   for.
5. **Every key expires.** Create it with `expiresIn` in seconds through
   `/api/auth/api-key/create`, signed in as that agent's user. The minimum is
   one day (86400) and the library maximum is 365 days, so a one-hour test key is
   refused with `EXPIRES_IN_IS_TOO_SMALL`. Read back only the key id and expiry,
   never the key. Record the renewal date and its owner.
6. **Keys live in `mb connect`.** Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check. The owner pipes the key in from a
   password manager, so it never sits in argv, scrollback or shell history:

   ```bash
   op read '<KEY_ITEM_REF>' | mb connect openseo-<AGENT> --custom --token-stdin --scope repo
   ```

   Never type or paste a key into `--token-stdin` at a terminal: stdin is echoed.

   `mb` warns when a shell-expanded credential reaches a child's argv. That
   warning is correct; read the key from stdin or a file, not from an expanded
   variable. On Linux the default backend is the Secret Service; without a D-Bus
   session the store exits 1 and nothing is saved, so set
   `MB_CONNECT_SECRET_BACKEND` on purpose or run it in a real login session. A
   nested `mb connect exec` hides the session bus the same way.
7. **Test with an MCP `initialize` canary.** `mb connect test` cannot check a
   custom provider; it reports "stored, unverified". Run the canary through
   `mb connect exec`, with the key on the request's stdin, not in its arguments:

   ```bash
   mb connect exec openseo-<AGENT> --env OPENSEO_MCP_KEY -- \
     sh -c 'printf "header = \"Authorization: Bearer %s\"\n" "$OPENSEO_MCP_KEY" \
       | curl -sS -o /dev/null -w "%{http_code}\n" -K - \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream" \
         --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"canary\",\"version\":\"0\"}}}" \
         "<URL>/mcp"'
   ```

   **Expected:** 200 with the key. A missing, empty, invalid or revoked key gets
   401. The key gives no app session. Then run `list_projects` once, which costs
   nothing. Do not use a paid call as a test. The exact curl flags are NOT
   VERIFIED as written; the observed canary used a builtin `printf` and a header
   read from stdin, and returned 200 for two keys.
8. **The owner adds the MCP entry, with no key in the command.** Claude Code
   refuses an agent writing its own MCP config. The header holds an environment
   reference, and `mb connect` supplies the value at run time. Required steps, from
   the business repo, in this order:
   1. `unset OPENSEO_MCP_KEY`, then `test -z "${OPENSEO_MCP_KEY+x}"` must pass.
   2. Single-quote the header, so argv and shell history hold only the reference:

      ```bash
      claude mcp add --transport http --scope local 'openseo-<BIZ>' '<URL>/mcp' \
        --header 'Authorization: Bearer ${OPENSEO_MCP_KEY}'
      ```

   3. `claude mcp get 'openseo-<BIZ>'` must show the literal `${OPENSEO_MCP_KEY}`
      and no `oseo_` text. Otherwise stop and run `claude mcp remove`. The docs
      state `${VAR}` expansion for `headers` in `.mcp.json` and a `${VAR}` display
      by name for local scope; they do not state it for `--header` on `claude mcp
      add`, so this read-back is the proof.
   4. At run time:
      `mb connect exec openseo-<AGENT> --repo "<BUSINESS_REPO>" --env OPENSEO_MCP_KEY -- claude`.
   5. Check missing, empty, invalid and revoked separately (setup step 9, item 5):
      each is not connected and each canary gives 401.

   Custody and rotation are in setup step 9. The key lives in `mb connect` and the
   password manager, never in the Claude config; same-uid processes can read it
   while Claude runs, and that boundary is accepted. `headersHelper` is a documented
   alternative only, not the route here.
9. **The operator secret is gone.** A first deploy or a claim step may need
   `OPENSEO_OPERATOR_SECRET`. Remove it afterwards, and prove it:
   - A redeploy does not remove a Worker secret. Alchemy never deletes one. Delete
     it by name (`wrangler secret delete OPENSEO_OPERATOR_SECRET --name <WORKER>`),
     then read the secret names back and confirm it is absent.
   - Then POST `{}` with the old secret, with `Accept: */*`, to the admin and
     import paths (`/api/standalone/admin`, `/api/standalone/import`). Both must be
     404. While the secret exists, the right header reaches a parser and answers
     400 or 500, so a 404 from the old secret is the proof. An unauthenticated 404
     alone is only a smoke test, because the handlers also 404 a missing
     credential while enabled.
10. **A sanitized receipt in the business repo.** Date, host, probe status codes,
    pin, key ids and expiries, and who checked. No keys, no emails beyond what the
    owner agrees.

## Signed-out probes

Print status codes only. On every live host, with no credential, a pass is:

| Path | Expected |
|---|---|
| `/api/health` | 200 with a fixed liveness body, and `authMode` `password` |
| `/mcp` | 401 |
| `/api/standalone/admin` and `/api/standalone/import` (GET) | 404 |
| `workers.dev` host and any version preview | 404 or no route |
| A sign-up request from an uninvited address | 403, and the `user` table unchanged |
| `/.well-known/oauth-authorization-server`, `/.well-known/oauth-protected-resource` | 200 public metadata, by design (path names are the OAuth library's; NOT VERIFIED) |
| `/api/auth/oauth2/register` (POST, valid metadata, owner approves one probe) | The endpoint accepts registration; this is the open surface the OAuth policy covers. Record the client id, delete it with the inventory steps |
| `/api/auth/oauth2/authorize` (GET) with an unknown client | 400, no redirect to a consent page |
| `/api/auth/oauth2/authorize` with a registered client, signed out | 302 to sign-in; no guest account (`src/server/auth/guest-accounts.ts:70-72` allows guests only in hosted mode) |
| `/api/auth/oauth2/token` (POST) with an invented code | 400 or 401 with an OAuth error body, never a token |
| `/api/oauth/consent` (POST), signed out | 401 `Sign in required`, or 403 on a bad origin |
| `/mcp` with a made-up bearer | 401 |

An `Accept: application/json, text/event-stream` request to a non-MCP path can
return 406. That is a probe artifact, not a route. Probe with `Accept: */*`.

## App OAuth in password mode

**Decision: app OAuth is kept, because it cannot be turned off by configuration at
v0.1.26.** `src/server.ts:224-229` sends every request to the OAuth provider when
the mode uses Better Auth (`usesBetterAuth`), and `src/server/mcp/oauth-provider.ts`
builds that provider with no disable option; no environment variable or deploy
setting gates it. A keys-only setup therefore still has these endpoints: authorize
`/api/auth/oauth2/authorize`, token `/api/auth/oauth2/token`, registration
`/api/auth/oauth2/register` (`oauth-provider.ts:41-45,299-314,352-360`), the consent
call `/api/oauth/consent`, and the well-known metadata. API keys are checked first
(`oauth-provider.ts:352-360`), so keys keep working whatever happens to OAuth.

What the source gives, and where it stops:

| Control | Source | Limit |
|---|---|---|
| A grant needs a signed-in user who accepts consent | `oauth-provider.ts:171-260` (`resolveContextForConsent` returns 401 signed out; `csrfProtected` refuses a bad origin) | Any signed-in user of this copy can approve a client for themselves |
| No guest accounts | `guest-accounts.ts:70-72` | Hosted mode only |
| Token lifetimes | access 24 h, refresh 30 days, client registration 365 days (`oauth-provider.ts:49-51`) | A grant outlives a password reset and a key deletion |
| Expired data is purged | cron `17 3 * * *` (`src/server.ts`) | Live records stay |
| Registration body limit | 1 MiB (`oauth-registration.ts`) | No count or rate limit |
| Sign-in limiter | `src/routes/api/auth/$.ts:19-38` | Covers only POST `/api/auth/sign-in/email`. It does **not** cover OAuth registration, authorization or token calls |

So an anonymous caller can create client records in the OAUTH_KV namespace, each
kept up to 365 days, and nothing in the app rate-limits that. The accepted risk is
storage clutter and a phishing-looking client name on the consent screen, not
unauthorised access: a token needs a signed-in user's consent. Owner requirements:

1. **Record the decision** in the setup record: OAuth kept, endpoints listed above,
   and who reviews the inventory and how often (at least at every key renewal).
2. **Optional edge rule, for keys-only setups.** A Cloudflare WAF rule on the custom
   host that blocks `/api/auth/oauth2/*` and the `/.well-known/oauth-*` paths
   removes the surface without touching the app. NOT VERIFIED: apply it, then prove
   that password sign-in still works and the key canary still returns 200. A WAF
   rate-limit rule on `/api/auth/oauth2/register` is the lighter choice if people
   connect with OAuth.
3. **Run the probe rows** in the table above and record the status codes.
4. **Owner-run inventory of clients and grants.** The namespace is
   `open-seo-oauth-kv-selfhost` (`alchemy.run.ts:125-126`). List key names only,
   never values, and read the id from the account first:

   ```bash
   mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" --env CLOUDFLARE_API_TOKEN -- \
     pnpm exec wrangler kv namespace list
   mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" --env CLOUDFLARE_API_TOKEN -- \
     pnpm exec wrangler kv key list --namespace-id <OAUTH_KV_ID> --remote
   ```

   The key layout is in OpenSEO's own account-deletion code
   (`src/server/account-deletion/storage.ts:57-93`): a grant is
   `grant:<userId>:<grantId>`, and each of its tokens is
   `token:<userId>:<grantId>:<...>`. Client records are separate. List with
   `--prefix`. That code pages through every result; confirm your listing is
   complete too before deleting, and never stop at a first page.
   Compare the clients and grants against the people and tools the owner expects.
5. **Revoke one grant with readback.** For the grant being revoked:
   1. List `token:<userId>:<grantId>:` with `--prefix`, all pages, and delete
      every key it returns.
   2. Delete `grant:<userId>:<grantId>`.
   3. Rerun both lists and confirm nothing is left for that grant.

   ```bash
   mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" --env CLOUDFLARE_API_TOKEN -- \
     pnpm exec wrangler kv key list --namespace-id <OAUTH_KV_ID> --remote \
     --prefix 'token:<USER_ID>:<GRANT_ID>:'
   mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" --env CLOUDFLARE_API_TOKEN -- \
     pnpm exec wrangler kv key delete --namespace-id <OAUTH_KV_ID> --remote '<KEY>'
   ```

   Deleting a client record is a separate step: it stops new sign-ins by that
   client and does not remove grants or tokens already issued. Revoke its grants
   first. Record the date and key names, never values.
6. **Rejected-token check.** Use the revoked client itself, so no token value is
   printed or copied:
   - its next MCP call with the old access token must fail with 401 and ask for
     sign-in;
   - its next refresh must fail, and it must not receive a new access token.

   A made-up bearer on `/mcp` must also give 401. Refresh tokens live for
   `MCP_REFRESH_TOKEN_TTL_SECONDS` (`src/server/mcp/oauth-provider.ts:47,308-309`),
   so an access-token refusal alone does not prove revocation. A signed-out `/mcp`
   401 does not prove the other endpoints are controlled.

## What a key cannot do

- A password reset does not revoke keys. Delete the key or remove the member.
- Version 0.1.26 has no sign-out-all control and no screen to revoke MCP grants
  on a self-hosted copy; "Connected agents" shows only on the hosted service.
  Better Auth's `revoke-sessions` is reachable by API with a session cookie. A
  sign-out request needs a JSON body: `{}` gives 200 and an empty body gives 415.
- A one-day minimum expiry means a leaked key can live that long. Revoke by
  deleting the key (`/api/auth/api-key/delete`, with a session cookie), then
  expect 401 on the next request.
- Self-hosting has no meter and no cap. Before agents resume after any cutover,
  check for active schedules: rank configs that are not manual and AI-visibility
  trackers that are enabled. A disabled tracker keeps its weekly schedule and
  would run unmetered, with no cost check, if re-enabled. The cap that counts is
  the DataForSEO daily limit.
- Same-uid processes can read a stored key. The operating-system user is the
  boundary: run each business under its own user, and do not run agents of
  another business, or untrusted code, as that user.

## Deploy config, not the dashboard

A custom domain belongs in deploy config. A domain added in the dashboard is
dropped on the next deploy (upstream issue 226). Environment values follow the same
rule: keep them in `.env.selfhost`. After a redeploy, repeat the signed-out probes
and one canary. A passing probe before the deploy proves nothing after it.

## Option: Cloudflare Access for a human-only app

Use Access only where the owner wants an app only people can reach and no agent
needs a key. It adds an edge login in front of every path, and MCP clients then
need Managed OAuth and a browser approval. Agents cannot use personal API keys
behind it.

1. **Previews off, or behind Access.** A preview URL that skips Access is an open
   door.
2. **workers.dev off when a custom host serves.**
3. **The pinned code checks the Access JWT.** At v0.1.26
   (`7d89cfb3ca30b2819356c57c5b746a1048b9743f`),
   `src/middleware/ensure-user/cloudflareAccess.ts:78` verifies the token with
   `jwtVerify`, with the team domain as issuer and `POLICY_AUD` as audience.
   Recheck at any other pin. That check does not cover `/api/health`: on a live
   cutover, a custom host not yet in the Access app answered 200 there for about a
   minute while app routes failed closed. Include `/api/health` in every
   signed-out probe.
4. **Probe prints status codes only.** It passes only on an Access-issued 401 for an
   MCP-style request (a `www-authenticate` header naming the team, an OAuth error
   body, no app content), or a 302 to the Access login for a browser request.
5. **Adding a custom host:** add it to the Access app first, then attach the Worker
   domain, probe every path for up to 2 minutes while it propagates, and treat any
   200 as a fail until it becomes an Access response. Then turn workers.dev off and
   probe again.
6. **After every deploy,** a deploy clears Managed OAuth (upstream issue 304). Turn
   it back on, then run the probe.

Access service tokens are not a shortcut for an agent here. See the unproven
section in [durable-setup.md](durable-setup.md).
