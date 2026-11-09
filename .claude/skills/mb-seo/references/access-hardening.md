# Hardening a self-hosted copy

Password mode is the recommended setup: the app signs people in with its own
accounts, and each agent reaches MCP with its own `oseo_` key. Checks are
owner-run or owner-approved. Report the app, the keys, and each data connection
separately. Print status codes only, never bodies, keys, or the `.env.selfhost`
file.

Status labels follow [durable-setup.md](durable-setup.md). The pattern below is
OBSERVED on one live business at OpenSEO 0.1.26 in November 2026. The pin in
[setup.md](setup.md) is older: at that pin the password steps are NOT VERIFIED,
and any check that fails there is a finding, not a pass.

## The setup

1. **Password mode, no Access app.** Set `AUTH_MODE=password` in `.env.selfhost`
   before the first deploy, and remove any Cloudflare Access app that covered the
   copy. The two modes keep separate user records, so choose once. Sign-up must be
   closed to the public: an uninvited sign-up request returns 403 and creates no
   user.
2. **workers.dev and previews off.** Declare the custom host in deploy config, then
   turn off the `workers.dev` route and version previews. Two hosts means two
   doors, and a preview URL is one more. Probe each; both answer 404 or have no
   route.
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
8. **The owner adds the MCP entry.** Claude Code refuses an agent writing its own
   MCP config. The owner runs one local-scope command with the key as a literal
   header, from the business repo:

   ```bash
   claude mcp add --transport http --scope local 'openseo-<BIZ>' '<URL>/mcp' \
     --header 'Authorization: Bearer <KEY>'
   ```

   The key then sits in the local Claude config, inside the owner's user account.
   Start a new session to see the tools.
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
| A sign-up request from an uninvited address | 403 |

An `Accept: application/json, text/event-stream` request to a non-MCP path can
return 406. That is a probe artifact, not a route. Probe with `Accept: */*`.

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
3. **The pinned code checks the Access JWT.** At v0.1.21
   (`beca5c1f5c728acfb243249107dbfaded0ef552e`),
   `src/middleware/ensure-user/cloudflareAccess.ts` verifies the token with
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
