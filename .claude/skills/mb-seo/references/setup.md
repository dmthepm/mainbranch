# OpenSEO Setup

Set up one copy for one business, one step at a time. The recommended sign-in is
password mode with a key per agent; Cloudflare Access is an option for a
human-only app (see [access-hardening.md](access-hardening.md)). Before each step, read the
setup record and skip what is done. Stop on any failed expected result.

**Pin:** OpenSEO v0.1.26, `7d89cfb3ca30b2819356c57c5b746a1048b9743f` (the tag
`v0.1.26` points at this commit). Every setup step, variable name and command below
was read against that source; the playbooks were written at the same release. A
live business ran the password-mode pattern at v0.1.26. No copy has been set up
from this skill alone. A step is marked NOT VERIFIED where the source does not
prove it. **Do not expose the app, and do not give any agent a key, until every
NOT VERIFIED item on the path has been checked and recorded.** Report what
happens at each one.

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

End the record with this section. Daily use reads it before every paid call; see
[daily-use.md](daily-use.md). It can narrow the rules there, never loosen them.

```markdown
## Standing words

- Monthly cap (OpenSEO and DataForSEO together): <amount> USD. Set by <who>, <date>.
- Standing approvals (only as written; none by default):
  - <what is covered, with its limit> — approved by <who>, <date>.
- Approved schedules (none by default):
  - <tracker or check, interval> — about <amount> USD a month — approved by <who>, <date>.
```

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
2. Open Zero Trust once and choose the Free plan. The first deploy runs in Access
   mode (step 6), and it stops if Zero Trust was never turned on
   (`docs/SELF_HOSTING_CLOUDFLARE.md`, Cloudflare Access section).
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
| Access: Apps and Policies | Edit (the first deploy creates the Access application) |
| Access: Organizations, Identity Providers, and Groups | Edit (same) |

Secrets Store Read fails, even though upstream's CI comment says Read. The
custom host (`CUSTOM_DOMAIN`, step 4) must be a zone on this account
(`deploy/alchemy/alchemy.run.ts:155-170`). Which zone, DNS and route permissions
the deploy needs for it is NOT VERIFIED: add them only after a failed deploy names
them, and record which.

Store the token from the owner's own terminal, in the business repo. Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

```bash
mb connect cloudflare-openseo --custom --scope repo
```

Paste the token at the hidden prompt, then press Enter.

**Expected:** `mb connect status cloudflare-openseo --json` reports it connected.
The output holds no token value.

Alchemy keeps its state in a Worker on this account. Upstream's order is a login,
then a one-time bootstrap (`docs/SELF_HOSTING_CLOUDFLARE.md`, step 2):
`pnpm alchemy login deploy/alchemy/alchemy.run.ts`, then
`pnpm alchemy cloudflare bootstrap`. Upstream's preflight script (`selfhost-deploy-preflight.mjs`) skips
the login check when `CLOUDFLARE_API_TOKEN` is set, but whether the bootstrap
alone is enough with a token is NOT VERIFIED. Run the bootstrap once, under
`mb connect exec` as in step 5, and report what it needs.

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
git checkout --detach 7d89cfb3ca30b2819356c57c5b746a1048b9743f
test "$(git rev-parse HEAD)" = 7d89cfb3ca30b2819356c57c5b746a1048b9743f
test -f deploy/alchemy/alchemy.run.ts
test -f deploy/alchemy/alchemy.access.ts
test -f "scripts/selfhost-deploy-preflight.mjs"
command -v corepack >/dev/null && corepack enable
pnpm install --frozen-lockfile
install -m 600 /dev/null .env.selfhost
install -d -m 700 "<PRIVATE_LOGS>"
```

**Expected:** every command succeeds. Git ignores `.env.selfhost`. pnpm may list
ignored build scripts; whether the deploy needs them approved at this pin is NOT
VERIFIED.

## 4. Owner: fill in `.env.selfhost`

The owner fills the empty file in their own editor. Do not copy
`deploy/.env.selfhost.example`. The first deploy is in Access mode, so no public
sign-up exists while the first owner is created (step 6, and the reason in
[access-hardening.md](access-hardening.md#first-owner-protected-bootstrap)).
Write the lines below, so every value is chosen. The names are the ones the deploy
reads: `AUTH_MODE`, `ACCESS_ALLOWED_EMAILS`, `CUSTOM_DOMAIN`, `DATAFORSEO_API_KEY`,
`OPENSEO_TELEMETRY_DISABLED` in `deploy/.env.selfhost.example` and
`deploy/alchemy/alchemy.run.ts`. The database defaults to D1 and the workers.dev
subdomain is read from the account, so neither line is needed.

```text
AUTH_MODE=cloudflare_access
ACCESS_ALLOWED_EMAILS=<the intended owner's email, and no one else>
CUSTOM_DOMAIN=<seo.example.com>
DATAFORSEO_API_KEY=<the Base64 credential>
OPENSEO_TELEMETRY_DISABLED=1
```

The key has no `Basic ` prefix, quotes, or line break. The allow-list names only
the intended owner: every address Access admits gets a user row. Set
`CUSTOM_DOMAIN` before any account exists, because the password-mode cookies and
MCP clients work only on that address (`docs/SELF_HOSTING_CLOUDFLARE.md`, Use your
own domain). Upstream's preflight script refuses to deploy Access mode
without `ACCESS_ALLOWED_EMAILS`.

The agent checks the file without showing it:

```bash
test "$(grep -c 'AUTH_MODE' .env.selfhost)" = 1
grep -q '^AUTH_MODE=cloudflare_access$' .env.selfhost
test "$(grep -cE "^export |[\$\"']" .env.selfhost)" = 0
test ! -e .env && test ! -e .env.local && test ! -e .env.selfhost.local
test -z "${AUTH_MODE:-}"
grep -q '^ACCESS_ALLOWED_EMAILS=[^,]*@[^,]*$' .env.selfhost
grep -q '^CUSTOM_DOMAIN=[a-z0-9.-]*$' .env.selfhost
grep -q '^DATAFORSEO_API_KEY=..*' .env.selfhost
grep -q '^OPENSEO_TELEMETRY_DISABLED=1$' .env.selfhost
```

Upstream's parsers take the last assignment, so a later `AUTH_MODE` line would
change the mode. That is why the file stays plain `KEY=value` lines.

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
deploy with it is NOT VERIFIED. The package script at the pin is
`node <preflight script> && ... && pnpm alchemy deploy
deploy/alchemy/alchemy.run.ts --env-file .env.selfhost --stage selfhost`
(`package.json:24`), and the preflight reads `.env.selfhost` for `AUTH_MODE`.

This first deploy is in Access mode. Go straight to step 6; nothing is public until
the owner exists. The same command runs again for the password switch.

## 6. First owner: keep it protected, then switch to passwords

Order matters. At this pin a password-mode install with no users lets the first
visitor create the administrator's account (`src/server/standalone/sign-up.ts:13-22`,
`src/lib/auth-mode.ts:7-11`), and the deploy makes the URL public. So the owner is
created while Access covers every route, and password mode is switched on only
once that owner exists. Full reasoning, probes and the stop rules are in
[access-hardening.md](access-hardening.md#first-owner-protected-bootstrap). Do the
steps in this order and stop on any failed expected result:

1. **Protected.** After the step 5 deploy, probe the custom host and the
   workers.dev host signed out. No path may return app content: an Access login
   redirect or an Access 401 is the pass. Do not sign in yet. A missing or
   misrouted Access application means the app is not protected: stop.
2. **Owner signs in through Access.** The intended owner opens the custom host once.
   That creates the user row (`src/middleware/ensure-user/delegated.ts:22-45`).
3. **Verify identity.** Owner-run read of the `user` table (command in
   access-hardening.md): exactly one row, and its email is the intended owner's.
   Any other row or count: stop, do not switch.
4. **Switch.** The owner edits `.env.selfhost`: `AUTH_MODE=password`, add
   `OPENSEO_OPERATOR_SECRET` (at least 32 random characters, `operator-auth.ts:5`),
   and drop `ACCESS_ALLOWED_EMAILS`. The agent checks the file without showing it,
   then runs the step 5 deploy:

   ```bash
   grep -q '^AUTH_MODE=password$' .env.selfhost
   grep -q '^OPENSEO_OPERATOR_SECRET=.\{32,\}$' .env.selfhost
   ! grep -q '^ACCESS_ALLOWED_EMAILS=' .env.selfhost
   ```

   The deploy removes the Access application
   (`docs/SELF_HOSTING_CLOUDFLARE_OPERATIONS.md`, Switching from Cloudflare Access).
5. **Uninvited sign-up creates no user.** Probe a sign-up from an address nobody
   invited: 403. Read the `user` table again: still the same one row.
6. **Give the owner a password and the owner role.** The owner runs
   `selfhost:admin claim-legacy-user` with the password on standard input (command
   in access-hardening.md; `src/server/standalone/admin.ts` sets the password and an
   `owner` membership in `shared-workspace`).
7. **Verify membership.** Read the `member` table: one row, that user, role `owner`.
   The owner signs in with the password and sees the workspace.

The steps for this switch come from upstream's operations guide and the source
above, which this skill read. A full run at the pin is NOT VERIFIED; report each
result. There is no source-backed way to deploy password mode empty and keep it
closed to the first visitor, so never start there.

## 7. Check the app, the keys, then the data

These are requirements. A failed or unchecked one blocks use of the copy.

The URL is the custom host in deploy config. Check that exact hostname, not a
similar one. Hardening and probe detail is in
[access-hardening.md](access-hardening.md).

| Requirement | How to check | Expected result |
|---|---|---|
| Password mode was set on purpose | Read `AUTH_MODE` in `.env.selfhost` | It is `password`. |
| First owner exists and is the intended one | Step 6 reads of `user` and `member` | One user, role `owner`. |
| Signed-out boundary | Request `/api/health`, `/mcp`, the admin and import paths, and a sign-up from an uninvited address, with `Accept: */*` | Health 200 with `authMode` `password`; `/mcp` 401; admin and import 404; sign-up 403. |
| App OAuth | The OAuth rows in the probe table in access-hardening.md | The policy there holds; this endpoint cannot be switched off at this pin. |
| No second door | Request the workers.dev host and any version preview | 404 or no route. NOT VERIFIED: the stack gives the app Worker no setting to turn workers.dev off, so this is an owner step (access-hardening.md). Until it passes, do not give any agent a key. |
| Rate limits | Read the Worker bindings | The sign-in, MCP and save-keywords limiters are bound (`alchemy.run.ts:570-590`). They do not cover OAuth registration. |
| Operator secret gone | Read the Worker secret names, then POST `{}` with the old secret | The name is absent; both paths answer 404. |
| The owner can sign in | Owner signs in with the password | The workspace opens. Health shows the pin and a database check of `ok`. |
| DataForSEO is configured | Same page | Its check is `ok`. This shows the key is present, not that a paid call works. |

Worker analytics is thin in the first hour, so it does not prove the app booted.
A long Worker binding list, including empty optional secrets, is normal.

If `/api/health` shows an `authMode` other than `password`, or `/mcp` answers without
a key, stop and tell the owner. Do not run keyword, rank, prompt, or AI checks as
tests. Rerun these checks after every deploy.

## 8. Owner: give each agent a user and a key

For each agent, the owner invites an admin user for it, then makes one `oseo_` key
for that user with an expiry (one day to 365 days), signed in as that user. Read
back only the key id and expiry. Store the key from the owner's own terminal,
piped from a password manager so it is never echoed or typed:

```bash
op read '<KEY_ITEM_REF>' | mb connect openseo-<AGENT> --custom --token-stdin --scope repo
```

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

**Expected:** `mb connect status openseo-<AGENT> --json` shows it stored. `mb connect
test` says "stored, unverified" for a custom provider; that is not a pass. Run the
`initialize` canary from [access-hardening.md](access-hardening.md): 200 with the
key, 401 without. Record the key id, expiry and renewal owner in the setup record.

## 9. Connect Claude Code to this business only

Claude Code refuses an agent writing its own MCP config, so the owner runs the
command from the business repo, in local scope so other businesses cannot see it.
The key never appears in the command, the shell history or the config: the header
holds a reference to an environment variable, and `mb connect` supplies the value
only when Claude Code starts. These are required steps, in this order:

1. **Key unset in this shell.** `unset OPENSEO_MCP_KEY`, then
   `test -z "${OPENSEO_MCP_KEY+x}"` must pass. Do not paste a key anywhere in this
   step.
2. **Add the server with the header single-quoted**, so the shell cannot expand it
   and argv holds only the reference text:

   ```bash
   claude mcp add --transport http --scope local 'openseo-<BIZ>' '<URL>/mcp' \
     --header 'Authorization: Bearer ${OPENSEO_MCP_KEY}'
   ```

3. **Read it back.** `claude mcp get 'openseo-<BIZ>'` must show the literal
   `${OPENSEO_MCP_KEY}` and no `oseo_` text. If it shows a value, an empty bearer or
   anything else, stop, run `claude mcp remove 'openseo-<BIZ>' --scope local`, and
   tell the owner. Claude Code's MCP documentation states `${VAR}` expansion for
   `headers` in `.mcp.json` and that `claude mcp get` shows a `${VAR}` reference by
   name for local scope. It does not say the same of `--header` on `claude mcp
   add`, so this read-back is the proof, not an assumption.
4. **Run Claude Code with the key from `mb connect`.** The key reaches its
   environment only for that run:

   ```bash
   mb connect exec openseo-<AGENT> --repo "<BUSINESS_REPO>" --env OPENSEO_MCP_KEY -- claude
   ```

   `mb connect exec` drops every variable it is not told to keep except a short list
   that includes `PATH` and `HOME` (`mb/mb/connect.py`, `EXEC_ENV_ALLOWLIST`), which
   Claude Code needs to find its config. A server added during a session does not
   appear in it, so start a new session.
5. **Missing, empty, invalid and revoked are four separate checks.** Do each and
   record the result. Fake values are not secrets and may be typed.
   - Missing: from a shell with the variable unset, `claude mcp list` reports the
     server not connected (Claude Code warns about the missing variable and sends
     the unexpanded text). The canary with no header: 401.
   - Empty: `OPENSEO_MCP_KEY= claude mcp list` is not connected. The canary with
     `Authorization: Bearer ` and nothing after it: 401.
   - Invalid: `OPENSEO_MCP_KEY=oseo_invalid claude mcp list` is not connected. The
     canary with `oseo_invalid`: 401.
   - Revoked: after the owner deletes a test key (access-hardening.md, What a key
     cannot do), the stored value gives 401 on the canary, and
     `mb connect exec ... -- claude mcp list` shows not connected.
6. **With the real key,** `claude mcp list` shows the server connected and
   `list_projects` returns the default project. `list_projects` costs nothing.

**Custody.** The key lives in `mb connect` and the owner's password manager. The
Claude config holds a reference, not a key. While Claude Code runs, the key is in
that process's environment, so any process under the same operating-system user
can read it: that boundary is accepted, and the answer is one OS user per business.
Never put the key in chat, a tracked file, `.mcp.json`, or a command line.

**Rotation.** Renew before the expiry in the setup record: make the new key, store
it with `mb connect`, repeat the read-back, the canary and the connect check, then
delete the old key and confirm 401 for it. If a key may have leaked, delete it
first. The reference in the Claude config does not change.

`headersHelper` is a documented alternative (Claude Code runs a command at
connection time and merges its JSON output into the headers; for local-scope
servers it runs only after the project trust dialog is accepted). It is not the
route here: a helper is a shell command that must fetch the key itself. If the
environment-reference route fails the read-back, report that instead of switching
silently.

Keep these limits in mind:

- The upstream plugin's MCP entry points at hosted `openseo.so`, not this copy.
  For a self-hosted copy, install skills only (next section).
- A password reset does not revoke keys. To remove an agent, delete its key or
  remove its user, and confirm a 401. Version 0.1.26 has no sign-out-all and no
  grant-revoke screen on a self-hosted copy.
- Self-hosting has no meter or cap. Check for active schedules before agents resume.
- Same-user processes can read the key; the operating-system user is the boundary.
- App OAuth stays on in password mode and cannot be switched off at this pin. Read
  [the OAuth policy](access-hardening.md#app-oauth-in-password-mode) before
  exposing the copy.
- With Access instead, MCP clients use Managed OAuth and a browser approval, and
  personal keys do not work. That route is optional; its checks are in
  [access-hardening.md](access-hardening.md).

## Install the skills only

Upstream documents a skills-only route, separate from MCP. Its Claude Code page
recommends the plugin, which suits the hosted service. A self-hosted copy wants the
skills and its own MCP entry from step 9, so skip the plugin. After the skills are
in, check `claude mcp list` shows no hosted `openseo.so` entry.

Owner-run. Main Branch does not run the installer or update the skills for them.

Upstream's manual route, at the pinned release. The tag `v0.1.26` was checked to
point at the pin's commit, and that commit holds all 12 skills under
`plugins/openseo/skills/`:

```bash
git clone https://github.com/every-app/open-seo.git <SCRATCH>/open-seo
git -C <SCRATCH>/open-seo checkout --detach 7d89cfb3ca30b2819356c57c5b746a1048b9743f
test "$(git -C <SCRATCH>/open-seo rev-parse HEAD)" = 7d89cfb3ca30b2819356c57c5b746a1048b9743f
mkdir -p .claude/skills
cp -R <SCRATCH>/open-seo/plugins/openseo/skills/* .claude/skills/
```

Copy from the commit the business's copy is deployed at, so the skills never call
a tool the app lacks. The example uses the v0.1.26 pin; use the deployed commit.

That is project scope: the skills live in this business repo and nowhere else.
When each business runs as its own OS user, user scope works too: copy the same
folders into the skills folder of every Claude profile that user runs, and keep
the copies identical. A live business set up this way had the 12 skills in both of
its profiles and only its own MCP entry.

Upstream's `npx skills add every-app/open-seo --skill '*' --agent claude-code`
installs whatever is on the default branch. The upstream pages read did not show a
way to pin its ref, so the ref to use with the installer is chosen at review.

Record in the setup record: the ref, the 12 skill names, the scope, and the runtime.
Then check separately: the skills are present, the MCP endpoint is this copy's, a
free read works, and a named skill actually ran. Presence proves neither use nor
compatibility. Keep the skill revision paired with the deployed app revision;
change the pair only after reviewing tool compatibility.

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
4. Owner: add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env.selfhost`.
   Upstream's Google guide says to use the Workers dashboard; do not, because each
   deploy replaces dashboard values. In password mode the deploy mints the secret
   that encrypts stored Google tokens and keeps it in Alchemy's state, so set no
   `BETTER_AUTH_SECRET` (`deploy/.env.selfhost.example`; `alchemy.run.ts`). Losing
   Alchemy's state means reconnecting Google.
5. Agent: repeat step 4's file check, then step 5's deploy command.
6. Owner: rerun the step 7 checks and the canary after the deploy.
7. Owner: connect Google in OpenSEO under Settings > Integrations. This stays a
   browser step. Agents can then list sites and properties and bind one to a
   project over MCP, at no charge.

**Expected:** `/api/health` shows the Google check as `ok`, and a Search Console
read returns rows for the owner's site.

## Known issues at this pin

These were recorded at the older v0.1.21 deploy. Each is NOT VERIFIED at v0.1.26;
recheck it before relying on the row.

| Upstream issue | Effect | What to do |
|---|---|---|
| 304 | With Access, a deploy may clear Managed OAuth | Recheck it after every deploy; not used in password mode |
| 403 | Secrets Store Read fails | Grant Edit |
| 226 | A deploy removes a dashboard-added custom domain | Put the domain in deploy config; see [access-hardening.md](access-hardening.md) |
| 377 | Free plan audits stop near 50 fetches and report the rest as failures | Use Workers Paid for audits |
| 405 | The MCP warning never clears | It proves nothing; the step 8 canary decides |
| 430 | A Shopify crawler host can be saved so it never matches | Enter the exact hostname |
