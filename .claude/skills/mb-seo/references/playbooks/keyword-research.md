# Keyword research playbook

Upstream skills: `keyword-research` and `keyword-clustering` (OpenSEO v0.1.26). Load them for the procedure. This file adds the business layer.

## Use it for
- Choosing which pages to make or improve, and which one URL each cluster of terms belongs to.
- Deciding what not to chase: wrong intent, too little demand, or a SERP the site cannot enter yet.
- Finding terms the site has no data on yet. For terms it already ranks for, Search Console is free and better.
- Spotting two pages that split one query (cannibalization).
- Feeding the `/mb-think` keyword gate with a short list of fits, not a long list of volumes.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `get_search_console_performance`, `get_suggested_keywords`, `list_saved_keywords`, `save_keywords`, `search_serp_locations` | no | nothing | source map 1, "no OpenSEO credits" |
| `research_keywords` | yes | seeds (1 to 5), `resultLimit` 150/300/500, clickstream x2, thin-seed fallback, local `locationName`; market decides Labs or Ads | Labs countries: $0.012 per task + $0.00012 per row (`pricing.ts:84-85,166-168`); default blend runs two tasks of half the limit. Ads-served countries: one $0.09 Ads ideas task per seed, no clickstream doubling (`pricing.ts:88,241`; `research-data.ts:104-117`). A city `locationName` adds one $0.09 Ads volume call per request, not per seed, after the national research (`research.ts:403-432`; `local-volume.ts:58-68`) |
| `get_keyword_metrics` | yes | keywords per call (up to 700), clickstream x2 in Labs countries | Labs countries: same formula (`pricing.ts:84-85`). Ads-served countries: one $0.09 Ads search-volume task per batch of 700, no doubling (`pricing.ts:242-245`; `keyword-metrics.ts:34,133-147`) |
| `get_serp_results` | yes | keywords (1 to 10), depth, operators in the keyword | at depth 10: 3 reads x 2 (priority) x $0.0006 = $0.0036 per keyword; deeper, 3 x 2 x ($0.0006 + $0.00045 per extra page of 10) (`pricing.ts:256-265`; `rank-tracking.ts:16-19,55-58`); `site:` and similar x5 (`rank-tracking.ts:64-72`) |

Derived per call, raw USD, Labs countries, 150 rows: one seed $0.042; one seed that needs the fallback $0.072; 300 rows $0.060 per seed; 500 rows $0.084 per seed. Metrics for 300 keywords $0.048; for 700, $0.096. One SERP read at depth 10 is $0.0036 per keyword. In an Ads-served country each seed is $0.09 and each metrics batch is $0.09. Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md).

Worked estimate (derived, raw): a small business, first pass. In a Labs-supported market: 5 seeds at 150 rows ($0.21), one metrics call on 300 shortlisted terms ($0.048), 20 SERP checks at depth 10 on borderline terms ($0.072). About $0.33. In an Ads-served market: 5 seeds at $0.09 ($0.45), one metrics call ($0.09), the same 20 SERP checks ($0.072). About $0.61. A later monthly refresh of the shortlist alone is $0.05 (Labs) or $0.09 (Ads). Say which market and provider an estimate assumes.

Estimate tool: none exists for these. Show the owner the table row and the arithmetic. Nothing here creates recurring spend. Ask first on every paid row.

## Run it well
1. Start free. Pull Search Console queries and pages for the longest window. Split brand queries into their own list. Then read the research log and prior `research/` files; reuse anything under 30 days old.
2. Write 5 seeds at most, from the problem the product solves, not the brand name. One market, one language. Keep `resultLimit` 150 and clickstream off. Both choices save money; clickstream doubles each seed and has no effect in Ads-served countries (`research-keywords.ts:73`).
3. Do not add a city to get local volume unless the business serves one. It adds one $0.09 Ads call per request. Local research also forces clickstream off, unlike ordinary Labs research (`research.ts:334`).
4. Shortlist by hand to 100 to 300 terms, then call `get_keyword_metrics` once. One call of 300 costs less than three of 100, because each call carries a $0.012 task fee.
5. Cluster from Search Console pairs of query and page first. Spend on `get_serp_results` only for borderline pairs. Two terms that share about three of the top ten URLs usually want one page; review pairs at exactly that line by hand (a vendor default, not a law).
6. Strike-distance list: queries at average position 5 to 20 with enough impressions to give 20 to 50 rows. Improve the page that already ranks before writing a new one.
7. Cadence: the Search Console pass weekly (free). New seeds monthly at most. A full re-research quarterly or when the offer changes. Each paid run in that cadence still needs the owner's yes.
8. Save accepted and rejected terms with a reason, then offer the page choices to `/mb-think`.

## Read the result
Worth acting on:
- A term that matches a real buyer, has a clear intent, and shows a SERP the site could enter.
- A striking-distance query where the ranking page can be made clearly better.
- A cluster that fits an existing page or one new page. Not one that needs five thin pages.

What this does not prove:
- Volume is a rounded Google Ads average that merges close variants. Do not add the volumes of near-identical terms. It is not traffic and not clicks.
- Difficulty is a backlink-based score from this vendor. A 40 here is not a 40 in another tool, and it ignores content quality and brand strength.
- Intent labels are a classifier. Check the SERP before you trust one.
- A missing value is `unknown`, not zero. Some terms return no data.
- Search Console hides rare queries and caps rows, so it is a floor on demand, not the whole of it.

## Save
`research/YYYY-MM-DD-seo-keywords.md`: seeds, market, language, date, source tool, actual cost (or "unknown"; estimate and say so), result limit, accepted terms with the page each maps to, rejected terms with reasons, clusters, and the limits above. Choices go to `decisions/YYYY-MM-DD-seo-keywords.md`. No raw exports, no secrets.

## App business vs store business
App business:
- Most installs start in the app stores, and none of these tools measure store search. Say so before the owner expects it.
- Research the problem space on the web: how-to, comparison and "best X for Y" terms. Exclude the app name from every list; it will dominate Search Console.
- Volumes are often small. Use tiers (none, low, mid, high) and decide on fit.

Small store:
- Intent is mostly commercial. Map one cluster to one collection page, and to a product page only for a named item.
- Check the Shopify canonical on product URLs under collections before mapping to them.
- Use the 12-month trend in the metrics for gift and holiday peaks, and plan pages before the peak.

## Sources
- OpenSEO: `plugins/openseo/skills/keyword-research/SKILL.md`, `keyword-clustering/SKILL.md`; `src/server/mcp/tools/research-keywords.ts:63-73,125`; `src/server/lib/dataforseo/pricing.ts:84-85,166-168,256-266`; `src/shared/billing.ts:72,130-132`; `src/shared/rank-tracking.ts:64-72`.
- DataForSEO Labs pricing, list price, accessed 9 Nov 2026: https://dataforseo.com/pricing/dataforseo-labs/dataforseo-google-api
- DataForSEO SERP pricing, accessed 9 Nov 2026: https://dataforseo.com/pricing/serp/google-organic-serp-api
- DataForSEO, keyword difficulty, accessed 9 Nov 2026: https://dataforseo.com/help-center/what-is-keyword-difficulty-and-how-is-it-calculated
- Google Ads Help, Keyword Planner metrics, accessed 9 Nov 2026: https://support.google.com/google-ads/answer/3022575
- Google, Search Console performance data limits, 19 Oct 2022: https://developers.google.com/search/blog/2022/10/performance-data-deep-dive
- Apple, App Store search, accessed 9 Nov 2026: https://developer.apple.com/app-store/search/
