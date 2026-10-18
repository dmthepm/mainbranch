# Google Ads Access for Agents: Read Path, Write Path, Roles

How a business lets agents read and change a Google Ads account safely. Use it
before setting up Google Ads reads, before any agent-driven negative or bid
change, and when deciding whether an agent should hold a write credential. The
daily read itself is [google-ads-check.md](google-ads-check.md); every write is
a provider mutation under the Main Branch provider mutation contract
(`docs/provider-mutation-contract.md` in the engine repo).

Source: a live ecommerce dogfood business and an earlier agency account,
audited October 2026. Google facts were checked against Google's pages on
18 October 2026 (sources at the end); re-check them before relying on them.

## The one idea

The safety boundary is the **Google Ads role of the user who authorized the
token**. The OAuth scope is not a boundary: `adwords` grants read and write.
The tool is not a boundary either: a read-only MCP server can sit next to a
write-capable token, and a write gate in your own code is advisory if any agent
can read the token file.

## Read path (every business, day one)

- Use Google's official MCP server, `googleads/google-ads-mcp`. Its tools
  (`search`, `get_resource_metadata`, `list_accessible_customers`) cannot
  write. Pin a reviewed commit, never `@latest`.
- Authorize it as a **dedicated Workspace user with the Read only role** in the
  Ads account, never as the owner.
  - Use an **Internal** OAuth consent screen when the business has Workspace.
    External apps in Testing lose refresh tokens after 7 days.
  - Store the refresh token with `mb connect`, never in a repo or `.mcp.json`.
  - Leave `quota_project_id` out of the ADC file; with it set, calls can fail
    with a `serviceusage.serviceUsageConsumer` 403.
- Prove the credential is read only with one `validateOnly` mutate (for example
  `campaignCriteria:mutate`). The expected answer is 403
  `authorizationError: ACTION_NOT_PERMITTED`, and nothing changes.
- API access levels belong to the **Cloud project**. **Explorer** access is
  granted quickly, reaches production accounts and allows 2,880 operations a
  day; one `search` call is one operation whatever the row count. Basic or
  Standard access is needed only for planning (Keyword Planner), user
  management, account creation and billing.
- Agents state their GAQL and date window. Search and Shopping terms come from
  `search_term_view`, Performance Max terms from `campaign_search_term_view`,
  catalog spend from `shopping_performance_view`.
- The `adwords` token often also carries Sheets or Drive scopes, and Ads roles
  do not limit those. Share only the one working Sheet with the reader user.

## Write path: why not a write token

- Google Ads roles are Admin, Standard, Read only, Email only and Billing.
  **Nothing narrower than Standard can edit**, and Standard can raise budgets,
  create campaigns and remove things.
- A Standard-role token on an agent machine lets any agent with file access
  make any campaign change. Allowlists, caps and `validateOnly`-first only help
  if every caller uses them.
- So the default agent write route is a **Google Ads Script**: fixed, reviewed
  code running inside Google as an admin user. Agents change data, never code.
  - Agents write proposed changes as rows in a Google Sheet: negatives, plus an
    allowlisted "Edits" tab.
  - The Script applies only the operations its code allows. A typical
    allowlist: EXACT or PHRASE negatives to a named shared list; pause or
    enable a keyword or ad group; bids inside per-campaign bounds, at most +25%
    per change; positive EXACT or PHRASE keywords; attaching an existing list.
    Never budgets, bid strategies, targeting, ad copy, campaign creation,
    removals or detaches.
  - Guards in code: never negate brand words or their misspellings, product or
    design names, or words the owner listed. Require 0 conversions in the last
    30 days on every term a negative would block, plus minimum evidence (clicks
    or impressions).
  - A circuit breaker: if more rows pass than the cap (for example 25), add
    none and mark them all HOLD.
  - Log each change to a protected tab **before** making it, then read it back
    (VERIFIED or NOT FOUND). Protect the log and approval tabs so only the owner
    account can edit them.
  - Owner approvals for edits live in an owner-only protected tab, one row per
    exact change, single use. A free-text `approved_by` column proves nothing.
- Deploy Script changes by uploading the file and checking its hash. Never let
  a model retype the code into the editor.
- Scripts do not use the Cloud project's API quota. They run daily or more
  often, so writes land within hours, not seconds.

## Graduation: DRY_RUN first

1. Ship with `DRY_RUN = true`. Every run writes "WOULD ADD" (or "WOULD ...")
   results and a Runs row, and changes nothing.
2. The agent fills rows daily; a reviewer reads the WOULD results against the
   guards.
3. Go live only with all three: an independent audit SHIP on the exact deployed
   version (by hash), about 7 days of clean WOULD results, and the owner's
   explicit word.
4. After go-live, stop making the same changes in the UI. Two write routes for
   one change double the work and the audit.

## The UI (browser) route

- Keep it for what the Script cannot do, under the owner's standing rules:
  emergency pauses, ad copy and assets, and deploying the Script.
- The browser is usually signed in as an **Admin**, the widest blast radius in
  the setup. Keep UI writes to a short, named list, one subagent per walk, and
  read every change back through the API.
- Expect Google's "Confirm it's you" checks on UI writes; batch them.

## Audit trail facts

- `change_event` (last 30 days, via the API) shows who changed what and through
  which client: `GOOGLE_ADS_WEB_CLIENT`, `GOOGLE_ADS_SCRIPTS`,
  `GOOGLE_ADS_API`, `GOOGLE_ADS_EDITOR` and others.
- It **does not record shared-list edits** (there is no SHARED_SET or
  SHARED_CRITERION resource type). For negative lists the record is your own
  log plus a `shared_criterion` read-back: member count before and after, and
  each term with its match type.
- When UI writes run as the owner account, agent and owner changes look the
  same in history. One more reason for the Script route.

## When a separate API writer is worth it

Only if same-day write latency costs real money, or Google adds a role narrower
than Standard. Then:

- a dedicated Standard user, separate from the reader;
- one gated command with an allowlist, `validateOnly` first, a daily cap and a
  log;
- the token readable only by that command's runtime, not by every agent.

It runs the provider mutation contract: plan, approve, apply, verify, record.

## Anti-patterns seen in practice

- Authorizing agent tooling with the owner's own login (`gcloud auth
  application-default login` or `print-access-token` as an admin), then writing
  with raw REST: full power, tokens that expire hourly, and credentials in
  transcripts.
- Putting a developer token or secret on a command line, where it lands in the
  transcript.
- Treating a read-only MCP server as proof that the credential is read only.
- Requiring Basic access or a developer token before reads. Explorer is enough.

## Sources

- https://github.com/googleads/google-ads-mcp
- https://developers.google.com/google-ads/api/docs/api-policy/access-levels
- https://developers.google.com/google-ads/api/docs/targeting/shared-sets
- https://support.google.com/google-ads/answer/9978556 (account access levels)
- https://developers.google.com/google-ads/api/reference/rpc/v25/ChangeEventResourceTypeEnum.ChangeEventResourceType
- https://developers.google.com/google-ads/scripts (NegativeKeywordList, ExecutionInfo)
