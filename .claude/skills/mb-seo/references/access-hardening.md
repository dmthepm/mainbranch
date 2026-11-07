# Hardening a self-hosted copy

Checks for the guard in front of a copy. Owner-run or owner-approved. Report the
guard, the app, and each data connection separately. Print status codes only,
never bodies, tokens, or the `.env.selfhost` file.

1. **Previews off, or behind Access.** A preview URL that skips Access is an open
   door. Turn previews off, or confirm Access covers them.
2. **workers.dev off when a custom host serves.** Two hosts means two doors.
3. **The pinned code checks the Access JWT.** At v0.1.21
   (`beca5c1f5c728acfb243249107dbfaded0ef552e`),
   `src/middleware/ensure-user/cloudflareAccess.ts` verifies the token with
   `jwtVerify`, with the team domain as issuer and `POLICY_AUD` as audience.
   Recheck at any other pin. That check does not cover `/api/health`: on a live
   cutover, a custom host not yet in the Access app answered 200 there for about a
   minute while app routes failed closed. So Access is the only guard for that
   path; see "Adding a custom host". The rule to hold upstream code to: no route
   skips the token check, and a health path that must answer without login returns
   a fixed liveness body with no data, pinned by a test. Until the pinned code does
   that, include `/api/health` in every signed-out probe.
4. **Probe prints status codes only.** It passes only on:
   - an Access-issued 401 for an MCP-style request, with a `www-authenticate`
     header naming the team, an OAuth error body, and no app content; or
   - a 302 to the Access login for a browser request.
   Anything else, including a 200 or app content, fails.
5. **No static service tokens.** An agent signs in as a person through Managed
   OAuth. Do not create a service token as a shortcut.
6. **A sanitized Access receipt in the business repo.** Date, hosts, probe status
   codes, pin, and who checked. No tokens, no emails beyond what the owner agrees.

## Deploy config, not the dashboard

A custom domain belongs in deploy config. A domain added in the dashboard is
dropped on the next deploy (upstream issue 226). Environment values follow the same
rule: keep them in `.env.selfhost`.

## Adding a custom host

1. Add the host to the Access app first. This holds in every deploy and
   post-deploy step: Access covers a hostname before it is attached.
2. Then attach the Worker's custom domain in deploy config.
3. Probe every path on the new host, retrying for up to 2 minutes while it
   propagates. Treat any 200 as a fail until it turns into an Access response.
4. Then turn workers.dev off, and probe again.

## After every deploy

A deploy clears Managed OAuth (upstream issue 304). Turn it back on, then run the
probe above. A passing probe before the deploy proves nothing after it.
