# Rank tracking playbook

Upstream skill: none ships for rank tracking (OpenSEO v0.1.26). `get_serp_results` is used inside `seo-audit` and the research skills. This file carries the procedure and the business layer.

## Use it for

- Confirming that a page change moved a controlled position for a fixed keyword, device and place.
- Spotting a page that lost ground before clicks fall.
- Seeing which competitor holds a term, with a one-off SERP check.
- Keeping a short saved-keyword list tied to real pages and offers.
- Checking that a keyword the owner wants has a page behind it.

For what real searchers saw, use Search Console. It is free and measures something different.

## Cost before you run

| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `get_serp_results` | Yes | 1 to 10 keywords x depth; 3 reads each | Derived at depth 10: 3 x 2 x $0.0006 = $0.0036 per keyword; deeper, 3 x 2 x ($0.0006 + $0.00045 per extra page of 10) (`pricing.ts:256-265`; `rank-tracking.ts:16-19,55-58`) |
| `estimate_rank_tracker_cost` | Free | | |
| `create_rank_tracker` | Free now; recurring later | Schedule, set on creation | |
| `add_rank_tracking_keywords` | Yes (metrics fetch) + recurring | Adding keywords refreshes the tracker's keyword metrics straight away: volume, difficulty, CPC in batches of up to 700 | Labs countries $0.012 + $0.00012 per row; Ads-served countries $0.09 per batch (`add-rank-tracking-keywords.ts:43-51`; `RankTrackingService.ts:327`; `pricing.ts:239-245,284-287`). Not covered by the SERP-check estimate |
| `run_rank_tracker` | Yes | Keywords x devices x 3 to 6 reads x depth | $0.0006 first page, $0.00045 each extra (`rank-tracking.ts:16,19`) |
| Saved keywords, `get_rank_tracker`, `get_rank_history`, `pin_`, `remove_` | Free | | |
| Search Console reads | Free | | |

A keyword containing `site:`, `intitle:`, `filetype:` and similar operators bills 5x, matched anywhere in the string (`rank-tracking.ts:64-72`).

Worked estimate (derived, raw self-hosted): 30 keywords, one device, depth 30. One read is 30 x ($0.0006 + 2 x $0.00045) = $0.045. A check uses 3 to 6 reads, so $0.135 to $0.27; the tool quotes the maximum. Weekly is up to $1.08 a month, daily up to $8.10. Depth 40 and 50 keywords on both devices is up to $1.17 a check, $4.68 weekly, $35 daily. These are raw figures. `estimate_rank_tracker_cost` always applies the hosted markup, even on a self-hosted copy (`src/shared/rank-tracking.ts:97-115`; `estimate-rank-tracker-cost.ts:80`). Its dollar figure is marked up and rounded as dollars; its separate credit figure also rounds each call up to a whole credit. Both run higher than the raw arithmetic. Do not multiply it by 1.28 again. Keep three figures apart: the raw estimate, the tool's figure (the approval figure for `maxCostCredits`), and what the provider actually billed ([costs.md](costs.md)).

Price conflict: DataForSEO's pricing page says each extra 10 results costs a full base price; OpenSEO assumes 75% (`rank-tracking.ts:19`). If the page is right, the estimate runs about 20% low at depth 30 to 40. Check the real balance change on the first run.

Add the keyword-metrics cost from the table to the estimate for any planned additions. Call `estimate_rank_tracker_cost` first, with `additionalKeywords` for a planned list. `run_rank_tracker` needs `maxCostCredits` and rejects a run above it. Ask first. A schedule is recurring spend: keep every tracker manual unless the owner approves a monthly figure. Self-hosted OpenSEO has no meter and no cap.

## Run it well

1. Pull 100 to 300 candidates from Search Console queries and saved keywords. Keep 30 to 50: 10 to 20 tied to revenue pages, 10 to 20 supporting, about 5 brand terms in a separate pinned group. Drop any term with no page behind it.
2. Create the tracker with every setting stated. The MCP tool defaults to manual, mobile, depth 40 (`create-rank-tracker.ts:93,103-105`), but the service defaults to weekly (`RankTrackingService.ts:60`) and re-adding an archived domain falls back to `both` devices. Pass schedule `manual` and one device yourself.
3. One market, one device. Mobile first for most small businesses. For city-level tracking, call `search_serp_locations` and pass the name verbatim.
4. Depth 30 is enough to start. Real competition usually sits inside the top 30 (vendor claim). Go deeper only for a stated reason.
5. Estimate, show the owner the per-check and monthly figures, get a yes, then add keywords and run once.
6. A check takes about an hour, up to 2. Do not start another while one is running; the tool allows one active run. Check back later.
7. Cadence: manual, about monthly, plus once after a deploy you want to judge. A weekly schedule needs an approved monthly figure. Daily is for at most 10 launch terms, for a short window. Each paid run still needs the owner's yes.
8. For a quick look at a few terms, use `get_serp_results` at depth 10 instead of a tracker.
9. Quote `bestPosition` from `get_serp_results`, not `rank` (`get-serp-results.ts:97`).
10. Record the DataForSEO balance before and after, and any other provider's figure, or "unknown". Results carry no cost.

## Read the result

Worth acting on (vendor rules of thumb; test them on your own data):

- A move of 1 to 3 positions in a day is noise. A shift of 5 or more that holds for 7 to 14 days is worth acting on.
- Several keywords in one cluster moving together matters more than one.
- Look the same day only at drops of 10 or more that match a site change or known update.
- Report branded and non-branded apart. Branded terms inflate averages.
- Pair every move with Search Console clicks and click-through rate.

What this does not prove:

- A null position means "not found within the checked depth", not "ranks below it".
- Tracker position and Search Console position differ by design. One is a controlled read; the other averages what users saw, including personalisation.
- The tracker uses organic position (`rank_group`), not slot on the page. Organic position 1 may be the fifth thing a user sees.
- Search Console impressions and position had a logging error from 13 May 2025 to 27 April 2026, and Google dropped `num=100` in September 2025. Do not compare across those dates without a note.
- A rank gain is not traffic, and a rank is not an AI citation. About 38% of AI Overview citations come from the top ten (vendor data).
- Operator keywords, wrong location and too many pageless terms all give misleading charts.

## Save

Write `research/YYYY-MM-DD-seo-rank-check.md` with: source (OpenSEO rank tracker or SERP check), date, market, device, depth, keyword list, positions with nulls marked, actual or unknown cost, coverage (keywords answered versus total, any failed reads), and the Search Console figures used. Keep the keyword list and its reasons in `decisions/YYYY-MM-DD-seo-tracked-keywords.md`, with any schedule and its approved monthly figure. No raw exports, no secrets.

## App business vs store business

App business:
- This tracks the website, not app store rank. Store keyword rank is a separate dataset OpenSEO does not call.
- Track category, problem and comparison terms that land on web pages, plus brand terms. Mobile. Keep the list to 20 to 30.
- Search Console counts an app install link click as a click, not an install.

Small store:
- Track category pages first, then high-margin product pages, then about 5 brand terms. Product page rank swings with stock and price.
- Mobile first, one country. Shopping and image modules push organic results down; check the SERP for the top 10 terms.
- A physical shop's local pack belongs to local SEO, not here.
- Expect gift-season swings. Compare to last year in Search Console, not the tracker.
- 40 to 60 keywords is reasonable and still cheap.

## Sources

- OpenSEO: `src/shared/rank-tracking.ts:16-30,55-72,158-168`; `src/server/mcp/tools/create-rank-tracker.ts:93-105`; `src/server/mcp/tools/run-rank-tracker.ts:18-24`; `src/server/mcp/tools/estimate-rank-tracker-cost.ts:36-45`; `src/server/mcp/tools/get-serp-results.ts:97`; `src/server/lib/dataforseo/pricing.ts:256-266`; `src/server/features/rank-tracking/services/RankTrackingService.ts:60,104`.
- DataForSEO Google Organic SERP pricing, https://dataforseo.com/pricing/google-serp/google-organic-serp-api (accessed 9 Nov 2026).
- DataForSEO SERP depth FAQ, https://dataforseo.com/help-center/serp-api-pricing-depth-update-faq (accessed 9 Nov 2026).
- DataForSEO, budget-friendly rank tracking, https://dataforseo.com/blog/budget-friendly-rank-tracking-strategies-with-dataforseo-serp-api (accessed 9 Nov 2026). Vendor content.
- Search Console Help, impressions, position and clicks, https://support.google.com/webmasters/answer/7042828 (accessed 9 Nov 2026).
- Search Console Help, data anomalies, https://support.google.com/webmasters/answer/6211453 (accessed 9 Nov 2026).
- Search Engine Land on `num=100`, https://searchengineland.com/google-num100-impact-data-462231 (accessed 9 Nov 2026).
- Nightwatch, rank tracking guide, https://nightwatch.io/blog/rank-tracking/ (accessed 9 Nov 2026). Vendor marketing.
