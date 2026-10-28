---
title: Meta Ads connect setup UX notes
date: 2026-05-12
linked_issue: https://github.com/dmthepm/mainbranch/issues/542
linked_linear: MAIN-350
release: unreleased
status: notes
tags: [integrations, meta-ads, connect, provider-readiness, dogfood]
---

# Meta Ads Connect Setup UX Notes

## Summary

Meta Ads setup is not just "install the CLI and paste a token." A user needs a
Meta Business Portfolio, an ad account, a developer app, a system user, assigned
business assets, and permission to generate or receive a system user token.

That means `mb connect meta` should behave like a setup guide and readiness
checker, not a raw credential prompt. The command should explain what the user
needs, identify the first missing prerequisite, and make admin approval feel
like a normal waiting state instead of a local failure.

## Setup Shape

The preferred business setup is:

- one business-owned system user for the integration purpose;
- one Meta app selected when generating the token;
- assigned assets for the workflows Main Branch will read: ad account, page,
  pixel/dataset, Instagram account, and catalog only when needed;
- a human admin who can generate or rotate system user tokens;
- local token storage per operator machine through `mb connect`.

Avoid making every teammate create an ad-hoc personal system user. The
integration should belong to the business portfolio, while each operator's token
copy stays local in their OS keychain or supported secret store.

## User Prerequisites

Before asking for a token, `mb connect meta` should explain that the user needs:

- access to the relevant Meta Business Portfolio / Business Manager;
- access to the ad account they want Main Branch to read;
- a system user in Business Settings;
- a Meta developer app available during token generation;
- the system user assigned to the required assets;
- business admin help when the current user cannot create users, assign assets,
  generate tokens, or approve the app/system-user request.

For many users, this will be an admin-mediated setup. That is not an error.

## Values Needed

`ACCESS_TOKEN`

- Generated from the system user.
- Secret. Store outside the repo.
- Never print in command output, chat, GitHub issues, docs, or
  `.mb/connect.yaml`.

`AD_ACCOUNT_ID`

- Required for most Ads CLI commands.
- Usually uses the `act_...` form.
- Can be found in Business Settings > Accounts > Ad accounts, or through
  `meta ads adaccount list` after auth works.
- Treat as account-private local metadata.

`BUSINESS_ID`

- Found in Business Settings > Business info.
- Optional for some CLI commands, but useful for dataset, pixel, catalog, and
  business-level checks.
- Treat as account-private local metadata.

## Token Scopes

Meta's Ads CLI setup docs name these baseline scopes:

- `business_management`
- `ads_management`
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_ads`
- `catalog_management`
- `read_insights`

`mb connect meta` should show this list before token generation and explain that
an admin may need to grant them.

## Admin Approval State

During dogfood, Meta surfaced a state where another business admin had to
approve before setup could continue. Product copy should treat this as:

`waiting_for_admin_approval`

Plain-language meaning:

> Meta needs another business admin to approve this connection before Main
> Branch can read ad account data. Ask an admin to approve the pending
> system-user/app/token request in Meta Business Settings. Nothing is broken
> locally.

While waiting, Main Branch should keep ad workflows available from manual Ads
Manager notes, screenshots the user summarizes, or repo reference files. It
should not imply live account context is connected.

## Install Sharp Edge

The official package requires Python 3.12+. A plain `pipx install meta-ads` can
fail if `pipx` chooses an older Python or a context where no compatible wheel is
visible.

The repair path should detect available Python versions and suggest the exact
interpreter-backed command, for example:

```bash
pipx install --python <python3.12-or-newer> meta-ads
```

Then verify:

```bash
meta --version
meta auth status
```

## Read-Only Smoke

After token, ad account, and business ID are configured, the future read-only
smoke should verify only safe facts:

```bash
meta auth status
meta ads adaccount list
meta ads campaign list
meta ads insights get --fields spend,impressions,clicks,ctr,cpc
meta ads dataset list
```

The command should not print raw account exports or write them to tracked files.
It should summarize capabilities: account readable, campaigns readable,
insights readable, datasets readable.

Global output flags belong before `ads`:

```bash
meta -o json ads campaign list
```

`mb connect meta` should absorb this CLI quirk so users do not need to learn it.

## Product Requirements For The Follow-Up Slice

The next `mb connect meta` implementation should:

- detect Python 3.12+ and the installed `meta` CLI;
- provide a precise install repair when the CLI is missing;
- explain business/admin prerequisites before credential prompts;
- support token input through stdin, prompt, or explicit environment import;
- store token material only in the OS keychain or supported local secret store;
- keep `.mb/connect.yaml` to safe metadata and readiness facts;
- model `waiting_for_admin_approval` distinctly from local install/auth errors;
- run read-only smoke after approval;
- report the first missing requirement in business language.

## Public / Private Boundary

These notes intentionally omit account IDs, system user IDs, business names,
token values, screenshots, raw provider responses, local paths, and private
operator details. They preserve the product lessons only.
