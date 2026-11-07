---
type: educational
topic: provider-readiness
status: draft
last-updated: 2026-05-19
---

# Provider readiness: connect outside tools only when the job needs them

Providers are outside accounts Main Branch can use for business work: GitHub,
Cloudflare, Google/Workspace, ads platforms, research sidecars, booking tools,
payments, social scheduling, bookkeeping, and future adapters.

You do not need to connect everything during first setup.

## The beginner version

Ask four questions:

1. What am I trying to do next?
2. Which outside account is needed for that job?
3. Does `mb` say that account is ready, missing, planned, or optional?
4. What exact command fixes the next missing step?

Run this from your business repo:

```bash
mb connect plan
```

For machine-readable status, agents and power users can use:

```bash
mb status --json --peek
mb connect doctor --json
```

## Connector readiness decision table

Do not treat every "connected" surface as the same thing. Claude.ai web chat,
Claude Code, Codex, Conductor, provider CLIs, and `mb connect` have different
readiness checks.

| Surface | What it proves | Next smoke check | Restart or OAuth guidance |
| --- | --- | --- | --- |
| `mb connect` provider rail | Main Branch knows a repo-safe provider path, credential reference, metadata, and repair command. | Run `mb connect status --json` or `mb connect doctor --json`; for a specific provider, run the documented `mb connect test ... --json` when available. | No runtime restart is normally required for CLI facts. If the provider uses OAuth and cannot read expected files or accounts, refresh scopes in the provider, then rerun the read-only smoke. |
| Claude.ai connector | The Claude.ai web product can access that connector in web chat. | In Claude.ai, ask for a harmless read-only action against a known non-sensitive file or record. | This does not prove Claude Code or Codex can see the connector. If access fails, update the connector's OAuth scopes or selected resources, then retry in Claude.ai. |
| Claude Code bridged tool, MCP, or plugin | The current Claude Code session exposes a tool to the agent. | Restart Claude Code after installing or changing connectors, MCP servers, plugins, or marketplace tools, then ask the agent to list or perform a harmless read-only check with the tool. | Tool lists can be session-scoped. Restart after install, permission, OAuth, or scope changes before deciding the bridge is missing. |
| Codex or Conductor tool/plugin | The current Codex/Conductor agent session exposes a tool to that agent. | Use the available tool's read-only operation against a safe target, or fall back to deterministic `mb`/CLI checks. | Availability in one hosted/local agent does not prove support in another runtime. Restart or start a new session after installing a plugin or changing connector scopes. |
| Local CLI or API-key setup | The operator's machine can run the provider's official local tool or API path. | Run the provider's auth/status command and the smallest read-only command the provider documents. Store secrets outside the repo. | Shell sessions may need a restart after installing a CLI or changing environment variables. API keys and OAuth refresh tokens do not belong in markdown, GitHub issues, or tracked config. |
| Unsupported, planned, or future provider | The provider may be useful, but Main Branch has no supported setup or smoke path yet. | Create or link a follow-up issue with the desired job, official provider path, privacy boundary, and smoke plan. | Do not claim support from a connector listing, local experiment, or provider marketing page. Keep the work manual until a supported rail exists. |

When a connector exists but cannot read expected files, treat it as a scope or
resource-selection problem before assuming Main Branch is broken. Re-authorize
or refresh the connector with the minimum needed scope, restart the runtime if
the tool list is session-scoped, then rerun a read-only smoke check.

Provider writes, publishing, spend, account mutation, and customer contact need
explicit operator approval and provider authority. A ready connector or passing
read smoke is not approval to mutate the account.

## The default order

1. **GitHub** - tasks, blockers, proposals, reviews, and shipped history.
   - Common fix: `gh auth login`
   - You can start locally without it, but shared work threads and proposals
     are limited.

2. **Cloudflare** - sites, DNS, Pages, and future Workers.
   - Connect it when you are ready to publish, deploy, or attach a domain.
   - Learn more: `mb educational cloudflare-pages`

3. **Google / Workspace** - source material in Drive, Docs, Sheets, and Slides.
   - Connect it when a workflow needs existing Google files.
   - Do not connect it just because you have a Google account.

4. **Meta Ads / Google Ads** - account facts, campaign references, pixels, and
   future performance context where official paths are verified.
   - Meta Ads uses Meta's official `meta-ads` package and `meta` CLI. Main
     Branch can store the token outside the repo, keep safe account metadata
     in `.mb/connect.yaml`, and run read-only account smoke.
   - Connect only when paid work needs account facts and Main Branch reports the
     path ready.

5. **Apify and similar sidecars** - research, scraping, YouTube, Instagram, and
   web mining.
   - Connect when research or organic workflows need structured external data.

6. **Specialized rails** - Cal.com, Stripe, hledger, Forgejo, Postiz, and
   other tools.
   - These are chosen for a specific business job, not as a day-one checklist.

## Readiness states

- `not_connected` means no repo-safe provider metadata exists yet.
- `planned` means the provider is a supported direction, but this release does
  not yet wire a safe setup, detection, or validation path.
- `readiness` means the official provider path and setup requirements are known,
  but `mb` does not yet validate the account or use live provider data.
- `wrong_python` means the local install path needs Python 3.12 or newer.
- `missing_cli` means the provider CLI is not installed or cannot run.
- `missing_secret` means metadata exists but the local secret is missing.
- `missing_metadata` means the token exists but a safe local identifier, such as
  `ad_account_id`, is missing.
- `unvalidated` means a credential is stored, but `mb connect test` has not
  been run on it.
- `stored_unverified` means a credential is stored and readable, but Main
  Branch has no safe automated check that it works with the provider. Running
  `mb connect test` again cannot change it; confirm the credential in the
  provider's own dashboard, or let the first real workflow run be the check.
- `needs_hydration` means this repo has provider setup in user scope, but the
  current workspace needs `mb connect hydrate --repo .` before local readiness
  commands can use it.
- `waiting_for_admin_approval` means the provider needs an account admin to
  approve the connection before local validation can pass.
- `auth_failed` and `read_smoke_failed` mean auth or read-only smoke failed
  without exposing raw provider output.
- `invalid` means validation failed and the credential should be replaced.
- `ready` means the safest available check for that provider passed. For a
  provider that requires a credential, that means a provider call actually
  confirmed it, and a provider with no probe never reaches `ready` — it reports
  `stored_unverified` instead. A provider that requires no credential, such as
  `hledger`, sends nothing to a provider, so its `ready` is about repo-local
  metadata and its `provider_verified` stays `false`.

Secrets stay outside the business repo. `.mb/connect.yaml` stores only safe
metadata, labels, secret references, and last-check facts, and is gitignored by
default. Do not paste tokens into markdown files, GitHub issues, screenshots,
or committed config.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check. Disposable workspaces can use user scope:

```bash
mb connect cloudflare --scope user --metadata account_id=...
mb connect hydrate --repo .
```

User scope is keyed by the business repo identity and provider, so a second
repo can use a different Cloudflare connection. Hydration writes only ignored
workspace-local metadata; the token stays in the local secret store.

## Why this is business onboarding

Connected accounts are permissions for business actions:

- publish a site;
- read source documents;
- learn from ads;
- collect research;
- take a payment;
- book a call;
- keep operating summaries current.

Main Branch should teach this while setup happens. Numbered choices,
readiness checks, and exact next commands beat a long essay and a pile of
manual account setup.

## Meta Ads read-only readiness

Meta Ads uses the official Meta Ads CLI:

```bash
pipx install meta-ads
meta --version
meta auth status
```

The CLI binary is `meta`; the package is `meta-ads`. It uses Meta Marketing API
credentials from `ACCESS_TOKEN`, `AD_ACCOUNT_ID`, and optional `BUSINESS_ID`.
Meta's setup docs describe a Meta developer app, Business Manager access, a
system user token, and scopes including `business_management`, `ads_management`,
`pages_show_list`, `pages_read_engagement`, `pages_manage_ads`,
`catalog_management`, and `read_insights`.

Connect through `mb` so the token stays outside the repo. Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

```bash
mb connect meta \
  --metadata=ad_account_id=<act_id> \
  --metadata=business_id=<business_portfolio_id>
mb connect test meta --json
```

Safe metadata in `.mb/connect.yaml` may include `ad_account_id` (use the `act_`
ad account ID), optional `business_id` (Meta calls this the Business portfolio
ID on the business info page), an account label, and validation summaries. Raw
tokens and raw provider responses do not belong in tracked files.

Practical read-only commands that `mb connect test meta` can smoke through the
official CLI include:

```bash
meta ads adaccount list
meta ads campaign list
meta ads adset list
meta ads ad list
meta ads creative list
meta ads insights get --fields spend,impressions,clicks,ctr,cpc
meta ads dataset list
```

Main Branch reports safe readiness facts through `mb connect status`, `mb
connect doctor`, and `mb status --json --peek`. `/mb-ads` should consume those
facts before asking whether to use live account context.

Write-capable CLI commands exist for campaigns, ad sets, ads, creatives,
datasets, and catalogs. They remain out of scope for Main Branch until approval
gates and mutation smoke exist.

## What Main Branch does not claim

Main Branch does not claim all providers are fully automated. Trust the current
CLI status, compatibility docs, and provider-specific smoke evidence. If a
provider is marked planned or readiness, treat it as direction, not shipped live
account support.

Main Branch also does not claim that Claude.ai connector availability means
Claude Code, Codex, Conductor, or another agent runtime can use that connector.
Each runtime needs its own visible tool surface, restart behavior, and read-only
smoke evidence before guidance should rely on it.
