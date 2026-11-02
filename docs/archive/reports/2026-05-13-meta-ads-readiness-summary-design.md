---
title: Meta Ads readiness dogfood and read-only summary design
date: 2026-05-13
linked_issue: https://github.com/dmthepm/mainbranch/issues/581
linked_linear: MAIN-366
release: unreleased
status: complete
tags: [integrations, meta-ads, provider-readiness, paid, privacy]
---

# Meta Ads Readiness And Read-Only Summary Design

## Summary

MAIN-366 keeps Meta Ads at the readiness/read-only boundary. The first useful
account surface should be a compact read-only summary that the agent asks
permission to pull before making ad recommendations. It should not import raw
performance data, cache account payloads, or mutate Meta campaigns, ad sets,
ads, budgets, audiences, pixels, datasets, or account settings.

The next implementation command should be:

```bash
mb ads meta summary --repo <BUSINESS_REPO> --window 7d --json
```

Use a new `mb ads` command group rather than extending `mb connect`. `mb
connect` should remain the setup, credential, readiness, repair, and smoke-test
surface. `mb ads` can become the paid-channel read-only and future
approval-gated work surface without overloading connection verbs.

## Dogfood Status

Local source smoke with fixture credentials proved the command path fails
closed:

- `mb connect meta` stored a token through `SecretStore` and did not write the
  token to `.mb/connect.yaml`;
- `.mb/connect.yaml` was ignored and did not become tracked after `git add .`;
- `mb connect test meta --json` reached `read_smoke_failed` with fixture
  credentials;
- `mb connect status meta --json` and `mb status --json --peek` exposed the
  same safe provider state;
- no raw account payload, account ID, business ID, token, private path, or
  performance dump was included in public evidence.

Real operator smoke reached `ready` with operator-held credentials. Sanitized
evidence:

```text
connect_state=unvalidated
test_state=ready
connect_status_state=ready
status_peek_meta_state=ready
credential_backend=macos-keychain
test_exit=0 status_exit=0 peek_exit=0
business_repo_git_status_count=0
```

Direct `meta` CLI read-only API ping also passed with exit-only evidence:

```text
auth_status_exit=0
adaccount_list_exit=0
campaign_list_exit=0
insights_get_exit=0
dataset_list_exit=0
```

Raw command output belongs in ignored local scratch and should not be copied to
GitHub, docs, PR bodies, or tracked files.

## First Summary Contract

The first summary should answer: "Is there enough live account context to
inform the next ad recommendation?"

Default behavior:

- read only after `mb connect` reports Meta `ready`;
- ask before live account reads;
- read a bounded recent window, defaulting to `7d`;
- summarize account readiness, broad activity, and safe next actions;
- emit JSON to stdout only;
- write no raw provider payloads or cache files;
- redact account IDs and business IDs;
- set `safe_to_share: false` because even compact account summaries can expose
  private account context;
- show spend presence or a coarse spend range by default, not exact spend;
- include exact spend only behind explicit current-run approval such as
  `--include-exact-spend`;
- omit campaign names unless the operator explicitly approves including names
  for the current run.

Suggested options:

```bash
mb ads meta summary --repo <BUSINESS_REPO> --window 7d --json
mb ads meta summary --repo <BUSINESS_REPO> --since 2026-05-01 --until 2026-05-07 --json
mb ads meta summary --repo <BUSINESS_REPO> --include-exact-spend --json
mb ads meta summary --repo <BUSINESS_REPO> --include-campaign-names --json
```

`--include-exact-spend` and `--include-campaign-names` should be current-run
only. They should not change saved provider metadata or cause values or names to
be written into tracked files. Any exact spend output still forces
`safe_to_share: false`.

## JSON Shape

Use the shared `mb.json_result` envelope pattern for the actual CLI response.
Do not invent a competing result shape. The implementation should preserve
normal result fields such as `mb_command`, `result_schema`, `result_status`,
`errors`, and `actions` where current CLI conventions expect them.

The domain payload inside that shared envelope should stay small and stable:

```json
{
  "ok": true,
  "schema_version": "1.0",
  "safe_to_share": false,
  "provider": "meta",
  "command": "mb ads meta summary",
  "state": "ready",
  "checked_at": "2026-05-13T00:00:00Z",
  "window": {
    "label": "7d",
    "since": "2026-05-06",
    "until": "2026-05-13"
  },
  "privacy": {
    "raw_payload_written": false,
    "tracked_files_written": false,
    "account_ids_redacted": true,
    "exact_spend_included": false,
    "campaign_names_included": false
  },
  "readiness": {
    "state": "ready",
    "summary": "Meta Ads read-only account context is ready.",
    "repair_command": ""
  },
  "account": {
    "label": "Meta Ads",
    "currency": "USD",
    "timezone": "America/Los_Angeles",
    "ad_account_id": "<redacted>"
  },
  "campaigns": {
    "active_count": 3,
    "names": [],
    "names_redacted": true
  },
  "spend": {
    "amount": "redacted",
    "range_label": "recent spend present",
    "currency": "USD"
  },
  "performance_direction": {
    "state": "unknown",
    "summary": "Not enough prior-window context to compare direction."
  },
  "datasets": {
    "state": "readable",
    "count": 1
  },
  "creatives": {
    "state": "not_read",
    "count": null,
    "naming_patterns": []
  },
  "findings": [
    "Meta account context is readable for a bounded summary."
  ],
  "next_actions": [
    "Use this summary to choose whether to generate new creative, audit active campaigns, or work from repo reference files."
  ]
}
```

`safe_to_share: false` means the command output is appropriate for the
operator's local chat/session after approval, but should not be copied into
public issues, PRs, docs, or tracked business files. The flag stays false even
when raw IDs are redacted because account activity, spend context,
currency/timezone, counts, and campaign context can still be private.

If Meta is not ready, the command should return a non-zero exit with the same
readiness state and repair command that `mb connect` reports. It should not
probe account data after a readiness failure.

## Chat UX

When Meta is not ready:

```text
I do not have live Meta account context yet. I can still work from your repo, exported screenshots, or manual Ads Manager notes.
```

When Meta is ready:

```text
Meta appears connected for read-only checks. Do you want me to pull a compact account summary before making recommendations?
```

If approved:

```text
I'll pull a read-only summary and avoid saving raw account data.
```

## Boundaries

The summary may include:

- account readiness state;
- safe account label;
- currency and timezone;
- active campaign count;
- recent spend presence or a coarse range by default;
- exact spend only with explicit current-run approval;
- campaign names only with current-run approval;
- broad performance direction;
- dataset or pixel readiness when available;
- creative count or naming patterns when read safely;
- sanitized findings and next actions.

The summary must avoid:

- raw Graph API payloads;
- full campaign, ad set, ad, or creative dumps;
- customer, member, or contact data;
- account IDs in normal output;
- private absolute paths;
- tracked performance caches;
- mutation commands;
- spend recommendations without operator context.

## Follow-Up Implementation

Implementation is tracked in
[GitHub issue #582 / MAIN-367](https://github.com/dmthepm/mainbranch/issues/582).
It is scoped to `mb ads meta summary --json`, focused tests, and a read-only
smoke path. It does not include mutation, dashboards, durable performance
caches, or broad reporting imports.
