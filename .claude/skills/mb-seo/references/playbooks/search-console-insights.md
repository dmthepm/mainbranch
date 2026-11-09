# Search Console and Analytics insights playbook

Upstream skill: `seo-project-setup` (OpenSEO v0.1.26) connects the data. `seo-audit` and `keyword-research` read Search Console. No upstream skill drives the Analytics tools, `inspect_urls` or `get_search_opportunities`, so the steps below are the procedure for those. Load `seo-project-setup` for the connection steps. This file adds the business layer.

If the business already has `mb google` connected, use the weekly review in [search-review.md](../search-review.md) instead. Use this file when the data comes through OpenSEO.

## Use it for
- Which pages already earn impressions, and which of those get clicked.
- Telling "not visible" (few impressions) from "visible but not clicked" (impressions, weak click rate). They need different work.
- Pages sitting at average position 4 to 20 that have real visits behind them.
- Whether a key page is indexed, and which URL Google chose as canonical.
- What organic visitors did after landing: sign-ups, installs, purchases.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `get_search_console_performance`, `inspect_urls`, `list/set_search_console_site` | No | Google API quota only | "No OpenSEO credits" (`search-console-tools.ts:249,482`) |
| nine `get_google_analytics_*` tools, `get_search_opportunities` | No | Google API quota only | "No OpenSEO credits" (`google-analytics-tools.ts:529-839`) |
| `list/set_google_analytics_property` | No | none | `google-connection-tools.ts:76,168,222,305` |

Worked estimate (derived): a weekly review of 28 days by page, by query and by country is three to five reads. DataForSEO cost is $0. OpenSEO credit use is none. Google's own limits are far above that: per Google's usage-limits page, Search Analytics allows 1,200 queries a minute per site and URL Inspection 2,000 a day (https://developers.google.com/webmaster-tools/limits, accessed 9 Nov 2026; not rechecked in source).

Estimate tool: none needed. Nothing here creates recurring spend. Do not add a DataForSEO call to "confirm" a Search Console number. Search Console is the first-party source. This is why you read it before any paid keyword or rank tool.

One non-cost trap: a self-hosted copy needs its own Google OAuth app. While that app is in Testing, Google expires its refresh tokens after 7 days and Search Console disconnects weekly (`docs/SELF_HOSTING_GOOGLE_SEARCH_CONSOLE.md:28-33,120-123`). Move the app to In production, or a weekly job will fail. The owner does this in the Google Cloud console.

## Run it well
1. Check the connection first with the free list tools. The agent cannot connect a Google account. The owner does it in the OpenSEO dashboard (`google-connection-tools.ts:80`).
2. Use a Domain property in Search Console where the owner can verify one. It covers every subdomain.
3. Before reading any number, write down in the business repo: brand terms (Search Console has no brand split), the goal, and the key events that count (sign-up, install, purchase). Without key events, `get_search_opportunities` falls back to engagement rate (`SearchOpportunityService.ts:213-224`).
4. Weekly, last 28 days against the prior 28, with `dataState: "final"` for comparisons. Dates are Pacific Time and the last ~3 days can be incomplete (`search-console-tools.ts:252`).
5. For queries, page with `startRow`. One call returns at most 1,000 rows sorted by clicks, and position and impression filters run only over those rows (`searchAnalytics.ts:37-41`; `search-console-tools.ts:215`). Zero-click queries sort last, so a long tail can be absent.
6. Run `get_search_opportunities` for the striking-distance list. It takes the top 1,000 pages by clicks, keeps average position 4 to 20, and scores only pages that match a GA4 organic landing page: 50% demand, 30% business value, 20% reachability (`SearchOpportunityService.ts:132-150,167,215-234`). Treat the score as a sort order, not a forecast.
7. Drop branded queries from the list. Compare click rate with the page's own history at the same position, not with an industry curve.
8. Use `inspect_urls` (up to 10 URLs) on pages that changed that week. It reads Google's stored index state. It does not crawl live.
9. Per change, record the date, page, query and the before numbers. Make one change. Confirm a recrawl with `inspect_urls`. Compare matched windows.
10. Monthly, compare whole calendar months. For a small site with low volume, use 90-day windows.

## Read the result
Worth acting on:
- A page with steady impressions at position 4 to 12, click rate below its own norm, and a key-event rate above the site's median. Fix the title and the first screen first.
- A query with real impressions and no page that answers it. Take it to the `/mb-think` keyword gate.
- A page that fell out of the index, or whose Google-chosen canonical differs from the declared one. Check this before any copy change.
- A 28-day click move of more than about 20% either way. Check indexing first, then seasonality, then the change log. The threshold is a starting guess, not a rule.

What this does not prove:
- Rare queries are hidden. Summed query rows will not equal total clicks.
- Average position is an average across impressions. It can rise while clicks fall. A rank of 5 here and 8 in a browser is normal.
- Impressions are results shown, not people reached.
- Search Console and GA4 will not match. Time zones, consent banners and blocked scripts differ. OpenSEO's GA4 join uses the `organic_search` channel, which includes Bing and others, so its sessions run higher than Google clicks. Compare trends.
- Google may report a page under a different canonical URL than the one you wrote.
- A drop does not name its cause. Do not credit or blame one edit.
- GA4 may withhold rows when counts are low.

## Save
Write `research/YYYY-MM-DD-seo-search-console.md`. Record: property, date range and `dataState`, the surface (web search only, or others), which tool produced each number, coverage (rows returned, whether paged, whether branded queries were removed), GA4 key events used, and cost ($0). Add what you rejected and why. Choices go to `decisions/`. No raw exports.

## App business vs store business
App business with a website:
- Search Console covers the website only, not app store pages. Define the win first: install click, sign-up or app open.
- Brand queries are often most of the traffic. Split them out or the totals mislead.
- Few pages and low volume mean noisy positions. Use longer windows.
- Report web organic only, and say it is a small part of total app growth.

Small store:
- Many product and collection pages, long tail. Read collection level, not single products.
- GA4 ecommerce gives revenue per organic landing page (`get_google_analytics_ecommerce_performance`). Use it for "worth acting on".
- Product URLs reached through a collection may report under the canonical `/products/` URL.
- A page missing from the top 1,000 by clicks is missing from the opportunity list.

## Sources
- OpenSEO: `src/server/mcp/tools/search-console-tools.ts`, `google-analytics-tools.ts`, `google-connection-tools.ts`; `src/server/features/gsc/searchAnalytics.ts`; `src/server/features/ga4/services/SearchOpportunityService.ts`; `docs/SELF_HOSTING_GOOGLE_SEARCH_CONSOLE.md`, `docs/SELF_HOSTING_GOOGLE_ANALYTICS.md`.
- Google Search Console Help, "What are impressions, position, and clicks?" https://support.google.com/webmasters/answer/7042828 (accessed 9 Nov 2026).
- Google, Search Console API usage limits. https://developers.google.com/webmaster-tools/limits (accessed 9 Nov 2026).
- Google, "Getting your performance data". https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data (accessed 9 Nov 2026).
- Google Search Console Help, Page indexing report. https://support.google.com/webmasters/answer/7440203 (accessed 9 Nov 2026).
