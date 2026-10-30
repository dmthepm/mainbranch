# OpenSEO Setup

Set up one copy for one business, one step at a time. Before each step, read the
setup record and skip what is done. Stop on any failed expected result.

**Pin:** v0.1.21, `beca5c1f5c728acfb243249107dbfaded0ef552e`. One copy has been deployed
by hand at this pin, following these steps, and a listed user has signed in, read
health, and finished an MCP login in about 3 minutes. No copy has been set up from
this skill alone. A real sign-in by an unlisted user being refused is NOT VERIFIED
at this pin.

## Before the first step

Tell the owner, then ask whether to continue:

- It needs a Cloudflare account with a payment method on file, and a funded
  DataForSEO account: $50 minimum top-up. The deploy refuses to run without the
  key, so this comes first.
- The agent's work takes about 5 to 15 minutes. Most of the wait is the owner's
  account work: the deposit, the token, and the key.
- Cloudflare can start at $0. Workers Paid at $5 a month is the sensible plan if
  site audits matter, because Free reads about 40 pages before it fails.
- Support is experimental.

Ask for a monthly spend cap for paid research. After the owner agrees, create
`decisions/YYYY-MM-DD-seo-openseo-setup.md` with the cap, the pin, and a checklist
of the steps below. Update it as steps finish. Write only non-secret facts: pin,
URL, MCP server name, plan, allowed emails, and check results.

Choose `<BIZ>`, a short lowercase name for the business. Choose a private folder
outside the business repo and outside any synced folder: `<CHECKOUT>` holds the
code and `<PRIVATE_LOGS>` holds logs.

## 1. Owner: prepare DataForSEO

1. Create an account for this business. Verify it and add the smallest balance
   allowed. Check that automatic top-up is off, because it can start on, and set
   the daily spend limit at or below the owner's cap before any paid call. It is the
   only limit the provider enforces.
2. On API Access, get the Base64 credential. Upstream describes it as
   `email:password`, but the API login shown there can differ from the sign-up
   email. Use the shown API login and API password.

The owner keeps this value until step 4.

## 2. Owner: prepare Cloudflare

In the business's own Cloudflare account:

1. Open R2 once and add a payment method if asked.
2. Open Zero Trust once and choose the Free plan. A deploy has failed with
   "Access not enabled" when this was skipped. Current upstream code reuses an
   existing team or tries to create one; only reuse has been seen working.
3. Copy the workers.dev subdomain from Workers & Pages.
4. Create a custom API token limited to this account, with these Account
   permissions:

| Permission | Level |
|---|---|
| Account Settings | Read |
| Workers Scripts | Edit |
| Workers KV Storage | Edit |
| D1 | Edit |
| Workers R2 Storage | Edit |
| Secrets Store | Edit |
| Access: Apps and Policies | Edit |
| Access: Organizations, Identity Providers, and Groups | Edit |

Secrets Store Read fails, even though upstream's CI comment says Read. No zone,
DNS, or route permissions are needed for a workers.dev copy.

Store the token from the owner's own terminal, in the business repo:

```bash
mb connect cloudflare-openseo --custom --token-stdin --scope repo
```

Paste the token, press Enter, then press Ctrl-D.

**Expected:** `mb connect status cloudflare-openseo --json` reports it connected.
The output holds no token value.

## 3. Agent: get the pinned code

Requires Node 22.6 or newer, 24 LTS recommended. Newer Node releases do not ship
corepack. If `corepack` is missing, install the pnpm version named in
`package.json` into a private tools folder with `npm install --prefix <folder>
--ignore-scripts pnpm@<version>`, and put that folder's `node_modules/.bin` first
on `PATH`. A different pnpm version can fail here with `spawnSync pnpm ENOENT`.

```bash
set -euo pipefail
umask 077
git clone https://github.com/every-app/open-seo.git "<CHECKOUT>"
cd "<CHECKOUT>"
git checkout --detach beca5c1f5c728acfb243249107dbfaded0ef552e
test "$(git rev-parse HEAD)" = beca5c1f5c728acfb243249107dbfaded0ef552e
test -f deploy/alchemy/alchemy.run.ts
test -f deploy/alchemy/alchemy.access.ts
command -v corepack >/dev/null && corepack enable
pnpm install --frozen-lockfile
install -m 600 /dev/null .env.selfhost
install -d -m 700 "<PRIVATE_LOGS>"
```

**Expected:** every command succeeds. Git ignores `.env.selfhost`. pnpm may list
ignored build scripts; the one recorded deploy worked without approving them.

## 4. Owner: fill in `.env.selfhost`

The owner fills the empty file in their own editor. Do not copy
`deploy/.env.selfhost.example`. **The template turns on password accounts**, which
gives a public login page and no Access. Write exactly these lines:

```text
AUTH_MODE=cloudflare_access
DATABASE_PROVIDER=d1
ACCESS_ALLOWED_EMAILS=owner@example.com
DATAFORSEO_API_KEY=<the Base64 credential>
WORKERS_SUBDOMAIN=<owner-subdomain>.workers.dev
OPENSEO_TELEMETRY_DISABLED=1
```

The key has no `Basic ` prefix, quotes, or line break. Choose the sign-in mode
before the first deploy; the two modes keep separate user records.

The agent checks the file without showing it:

```bash
test "$(grep -c 'AUTH_MODE' .env.selfhost)" = 1
grep -q '^AUTH_MODE=cloudflare_access$' .env.selfhost
test "$(grep -cE "^export |[\$\"']" .env.selfhost)" = 0
test "$(grep -cE '^(TEAM_DOMAIN|POLICY_AUD)=' .env.selfhost)" = 0
test ! -e .env && test ! -e .env.local && test ! -e .env.selfhost.local
test -z "${AUTH_MODE:-}"
grep -q '^ACCESS_ALLOWED_EMAILS=..*' .env.selfhost
grep -q '^DATAFORSEO_API_KEY=..*' .env.selfhost
grep -q '^WORKERS_SUBDOMAIN=.*\.workers\.dev$' .env.selfhost
grep -q '^OPENSEO_TELEMETRY_DISABLED=1$' .env.selfhost
```

Upstream's parsers take the last assignment, so a later `AUTH_MODE=password`, or a
line they read differently, would remove Access. That is why the file stays plain
`KEY=value` lines.

**Expected:** all pass. Do not deploy otherwise.

## 5. Agent: deploy

Raw deploy logs may hold secrets, so logs go only to `<PRIVATE_LOGS>`. Alchemy also
writes its own under `.alchemy/log/` in the checkout. On failure, report a sanitized
error category. Do not print either. Alchemy keeps its state-store token in
`~/.alchemy/credentials/`; keep that private too, because redeploys need it.

Alchemy ignores `ALCHEMY_PROFILE`, so pass `--profile` every time. Without it, every
business in one home folder shares the `default` credentials, and a second business
would read the first one's state store.

```bash
set -euo pipefail
cd "<CHECKOUT>"
export CLOUDFLARE_ACCOUNT_ID='<ACCOUNT_ID>'
PROFILE='openseo-<BIZ>-token'
export CI=true
export ALCHEMY_TELEMETRY_DISABLED=1
export WRANGLER_SEND_METRICS=false
export WRANGLER_SEND_ERROR_REPORTS=false
export WRANGLER_LOG_SANITIZE=true
KEEP=(--keep-env CLOUDFLARE_ACCOUNT_ID --keep-env CI
  --keep-env ALCHEMY_TELEMETRY_DISABLED --keep-env WRANGLER_SEND_METRICS
  --keep-env WRANGLER_SEND_ERROR_REPORTS --keep-env WRANGLER_LOG_SANITIZE)
mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" \
  --env CLOUDFLARE_API_TOKEN "${KEEP[@]}" \
  -- sh -c 'test "$CI" = true && test -n "$CLOUDFLARE_ACCOUNT_ID" && test "$ALCHEMY_TELEMETRY_DISABLED" = 1'
mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" \
  --env CLOUDFLARE_API_TOKEN "${KEEP[@]}" \
  -- pnpm deploy:selfhost --yes --profile "$PROFILE" >"<PRIVATE_LOGS>/deploy.log" 2>&1
test ! -e "$HOME/.alchemy/credentials/default"
```

`mb connect exec` drops every variable you don't keep, so the first command proves
they arrived. The deploy sets up Alchemy's state store on the first run.

Every business uses the same resource names, so the account ID and profile must
be set each time. Use a fresh profile per business, and never copy one business's
profile to another. Alchemy creates the Workers,
D1, KV, R2, workflows, and the Access application, and applies migrations. There
are no manual wrangler steps. `pnpm deploy` is a different path; do not use it.

**Expected:** every command exits 0, and no `default` credentials folder exists.
`--profile` has reached Alchemy this way in tests with stand-in tools; a first real
deploy with it is NOT VERIFIED.

## 6. Check the guard, then the app, then the data

These are requirements. A failed or unchecked one blocks use of the copy.

The URL is `https://open-seo-selfhost.<owner-subdomain>.workers.dev`. Check that
exact hostname, not a similar one.

| Requirement | How to check | Expected result |
|---|---|---|
| Access mode was set on purpose | Read `AUTH_MODE` in `.env.selfhost` | It is `cloudflare_access`. Never rely on the upstream default, which is password accounts. |
| Access guards every path | Signed out, request `/`, `/api/health`, `/mcp`, and one unknown path | Each redirects to the team's `cloudflareaccess.com` login. After step 7, `/mcp` instead returns a 401 whose challenge and issuer name that Access team. A 401 alone proves nothing. A plain OPTIONS request may get a 400 from Cloudflare. None returns app content or a 2xx. |
| Only listed people get in | Owner signs in, then tries an unlisted email | The listed email reaches the workspace. The unlisted one is refused. |
| The allow list is the intended one | Owner reads the Access app's policies | Only the intended emails are listed. There is no Bypass rule, no Everyone rule, and no other Access app that overrides this one for the hostname or any path. |
| Owner's people can sign in | Owner opens the login page | A method they can use is offered. A new team may offer only Cloudflare-account login; the owner adds One-time PIN if needed. |
| The app is healthy | A listed person signs in and opens `/api/health`. An agent cannot read it, because it sits behind Access. | `status` is `ok`, `authMode` is `cloudflare_access`, the version matches the pin, and the database check is `ok`. |
| DataForSEO is configured | Same page | Its check is `ok`. This shows the key is present, not that a paid call works. |

Worker analytics is thin in the first hour, so it does not prove the app booted.
A long Worker binding list, including empty optional secrets, is normal.

If `/api/health` is reachable signed out, Access is not protecting the app.
Stop and tell the owner. Do not run keyword, rank, prompt, or AI checks as tests.

Rerun the signed-out and unlisted-email checks after step 7 and after every deploy.

## 7. Owner: turn on Managed OAuth

MCP clients need this, and it is off by default.

In Zero Trust, open Access controls, then Applications, then `open-seo selfhost`,
then Additional settings, then OAuth. Turn on Managed OAuth, allow localhost and
loopback clients, and save. Add an HTTPS redirect URI only if a web connector
needs it, and then only that exact URI, never a broad wildcard.

Dynamic registration lets a client register. It does not authorize a user: only
the Access allow list in step 6 does that.

**Requirement:** the setting is on after every deploy. Upstream issue 304 reports
that each deploy clears it. That is not yet seen here, so check, don't assume.

| Requirement | How to check | Expected result |
|---|---|---|
| The login server is advertised | Read `/.well-known/cloudflare-access-protected-resource/mcp`, then the authorization server it names. Do not POST a registration. | It names this copy's Access team. The issuer and `registration_endpoint` are on that team's host, and `resource` is this copy's `/mcp`. |
| An allowed user can sign in over MCP | Finish step 8 for one agent | The client connects and lists OpenSEO's tools. |
| The guard still holds | Rerun the step 6 signed-out and unlisted-email checks | Both are still refused. |

**Expected:** all three pass. A check you could not run is NOT VERIFIED, which is
not a pass, so the copy stays out of use.

The app may show a warning that MCP cannot connect (upstream issue 405). That
warning proves nothing either way: the table above decides.

## 8. Connect Claude Code to this business only

From the business repo, using local scope so other businesses cannot see it:

```bash
claude mcp add --transport http --scope local 'openseo-<BIZ>' 'https://open-seo-selfhost.<owner-subdomain>.workers.dev/mcp'
claude mcp login 'openseo-<BIZ>'
```

The owner approves in the browser.

**Expected:** `claude mcp list` shows the server connected, and `list_projects`
returns the default project. `list_projects` costs nothing.

If the printed login URL looks doubled, terminal link escapes wrapped it: cut it
at the first BEL character and use the part before it. Pasting it whole gives
`invalid_target`, "Multiple resources not supported".

An MCP server added during a session does not appear in that session. Start a new
Claude Code session to use its tools.

**Fallback:** the login URL already carried `resource` at this pin. If Access still
refuses it with `invalid_target`, add `&resource=<URL-encoded MCP URL>` and open
that. The code exchange then works unchanged.

Keep these limits in mind:

- Do not install the upstream OpenSEO plugin. Its MCP entry points at the hosted
  service, not this copy.
- Personal API keys do not work behind Access. An agent needs a user sign-in.
- Settings > Connected agents is hosted-only. To remove a person, take them out of
  `ACCESS_ALLOWED_EMAILS`, redeploy, and redo step 7. Whether that ends sessions
  already issued is NOT VERIFIED, so don't treat it as an emergency cutoff. Prove
  their browser and MCP sessions now fail.
- The Access session lasts seven days. Whether an agent stays connected past that
  is unproven.

## Later: Google

Offer this only when the owner asks for Search Console or Analytics evidence
through OpenSEO. Public research does not need it. NOT VERIFIED at this pin.

Each business needs its own Google client:

1. Owner: create a Google Cloud project for this business. Enable the Search
   Console API, and for Analytics the Analytics Admin API and Analytics Data API.
2. Owner: configure the consent screen. Use Internal only if everyone connecting
   is in that Google Workspace; an Internal client refuses other accounts. For
   External, add test users, then publish to production, because refresh tokens
   for Testing apps expire after seven days.
3. Owner: create a Web application OAuth client with these exact redirect URIs:
   `<URL>/api/gsc/oauth/callback` and `<URL>/api/ga4/oauth/callback`.
4. Owner: add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a random
   `BETTER_AUTH_SECRET` of at least 32 characters to `.env.selfhost`. Upstream's
   Google guide says to use the Workers dashboard; do not, because each deploy
   replaces dashboard values. Keep a private copy of the secret: it encrypts the
   stored Google tokens, and losing it means reconnecting Google.
5. Agent: repeat step 4's file check, then step 5's deploy command.
6. Owner: redo step 7. The deploy may have cleared Managed OAuth.
7. Owner: connect Google in OpenSEO under Settings > Integrations. This stays a
   browser step. Agents can then list sites and properties and bind one to a
   project over MCP, at no charge.

**Expected:** `/api/health` shows the Google check as `ok`, and a Search Console
read returns rows for the owner's site.

## Known issues at this pin

| Upstream issue | Effect | What to do |
|---|---|---|
| 304 | A deploy may clear Managed OAuth | Redo step 7 after every deploy |
| 403 | Secrets Store Read fails | Grant Edit |
| 226 | A deploy removes a dashboard-added custom domain | Stay on workers.dev |
| 377 | Free plan audits stop near 50 fetches and report the rest as failures | Use Workers Paid for audits |
| 405 | The MCP warning never clears | It proves nothing; the step 7 checks decide |
| 430 | A Shopify crawler host can be saved so it never matches | Enter the exact hostname |
