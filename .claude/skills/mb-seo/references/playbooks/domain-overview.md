# Domain overview and competitors playbook

Upstream skills: `competitor-analysis` (one named competitor) and `competitive-landscape` (a whole market) (OpenSEO v0.1.26). Load them for the procedure. This file adds the business layer.

## Use it for
- Finding who really competes in Google for the business's topics. They are often not the business's own rivals: publishers, marketplaces and directories show up.
- Sizing the gap: how many keywords and how much estimated traffic a competitor has, and from which pages.
- Finding terms where a competitor ranks and the site does not.
- Deciding where not to compete this quarter.
- Giving the owner a plain read of the market before any content spend.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `get_search_console_performance` | no | nothing | the site's own baseline; free |
| `get_domain_overview` | yes | one call per domain; cached 12 h | Labs one-row call: $0.012 + $0.00012 (`pricing.ts:248-253`; `DomainService.ts:23`) |
| `get_ranked_keywords` | yes | `limit` (default 50, max 100), filters, offset | Labs $0.012 + $0.00012 per row (`dataforseo-research-tools.ts:213-219,916`) |
| `get_domain_keyword_suggestions` | yes | none to set: it takes domain, scope and market only, and always asks for 100 rows | $0.012 + 100 x $0.00012 = $0.024 (`get-domain-keyword-suggestions.ts:42-56`; `DomainService.ts:171-180`) |
| `find_serp_competitors` | yes | `limit` (default 50, max 100) | same Labs formula (`pricing.ts:286-289`) |
| `get_serp_results` | yes | keywords, depth, operators x5 | at depth 10: 3 priority reads x 2 x $0.0006 = $0.0036 per keyword; deeper, add $0.00045 per extra page of 10 to each read price (`pricing.ts:256-265`; `rank-tracking.ts:16-19,55-58`) |

Derived per call, raw USD: overview $0.0121; ranked keywords 50 rows $0.018, 100 rows $0.024; keyword suggestions always $0.024; competitors 50 rows $0.018. A tool description says "~100-300 typical" credits for an overview. The code makes one one-row Labs call, about 16 hosted credits. The source wins; the text looks stale. Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md).

Worked estimate (derived): the site and 5 named competitors ($0.073), one `find_serp_competitors` on a 15-keyword seed set ($0.018), ranked keywords at 100 rows for the 3 closest rivals ($0.072). About $0.16. A monthly refresh of the 6 overviews is $0.07.

Estimate tool: none exists. Show the owner the table row and the arithmetic. Nothing here creates recurring spend. Ask first on every paid row.

## Run it well
1. Read the saved competitors and the research log first. Reuse anything under 30 days old.
2. Ask the owner to name 3 to 5 rivals. Do not pay to discover them without a yes. If they cannot name any, run `find_serp_competitors` once on 10 to 20 seed keywords from the keyword work, not on one keyword.
3. Use the site's own Search Console for the site's own numbers. Use the overview for rivals only.
4. Drop marketplaces, giant publishers and directories by hand. Label each domain: direct rival, publisher, marketplace, community.
5. Pull ranked keywords (not suggestions, which take no filters) for the 3 closest rivals at 100 rows, filtered in the request (position, minimum volume, brand excluded). Rows are billed as returned, so filter first. Do not page past 200 rows; each page is a new $0.012 task fee.
6. Join the rival rows with Search Console. A term the rival ranks in the top 10 for and the site has no impressions on is a gap candidate. Judge fit before you keep it.
7. Group a rival's terms by the URL path they rank on. That tells you what page types win. Check the live page before you claim anything about its content.
8. Use one market and language. A second market is a full repeat.
9. Cadence: one pass at the start, a monthly overview refresh for the rival set, and a quarterly rerun of competitors and ranked keywords. Each paid run in that cadence still needs the owner's yes. The vendor refreshes Labs data on 30 to 90 day cycles, so a second pull inside a month usually returns the same thing.

## Read the result
Worth acting on:
- A rival that shows up across many of your seed SERPs, not one.
- A gap on a page type the business can honestly build.
- A rival far ahead on estimated traffic and links: skip that theme this quarter and say why.

What this does not prove:
- Estimated traffic is volume times an assumed click rate by position. It is not visits. One vendor study of its own data found a median error near 50% against Search Console.
- It ignores shopping results, so it undervalues product-led queries.
- The overview always covers the host plus its subdomains, whatever scope you pass. A blog on a subdomain merges with the store.
- A new or small site often shows no data. That means "not in the database", not "no traffic".
- Brand terms inflate a rival's numbers. Filter them before you compare.
- Keyword rows show what ranks, not why. Do not infer a rival's content plan from rows alone.
- Numbers from two tools do not mix in one table.

## Save
`research/YYYY-MM-DD-seo-competitors.md`: the domains with their type labels, market, date, source tools, actual cost (or "unknown"; estimate and say so), the gap list with fit notes, and the limits above. Confirmed rivals go to the repo's competitor notes with approval. Choices go to `decisions/`. No raw exports, no secrets.

## App business vs store business
App business:
- A rival's website shows only its web side. Its installs may come from store search, which no web overview shows.
- Use the overview to see which help, comparison and guide topics rivals rank for. Copy topics, never pages.
- OpenSEO does not call app-store keyword data, and no price for it is established here. Adding it is a human decision.

Small store:
- Results are full of marketplaces and big retailers. Filter to organic, and drop them by hand.
- Group rival rows by `/collections/` and `/products/` paths to see whether they win on category pages or on single items.
- Compare on organic position, not estimated traffic alone, because shopping results are not counted.

## Sources
- OpenSEO: `plugins/openseo/skills/competitor-analysis/SKILL.md`, `competitive-landscape/SKILL.md`; `src/server/lib/dataforseo/pricing.ts:248-253,256-266,286-289`; `src/server/features/domain/services/DomainService.ts:23,45-90`; `src/server/mcp/tools/get-domain-overview.ts:50`; `src/server/mcp/tools/dataforseo-research-tools.ts:213-219,916,1122`.
- DataForSEO Labs pricing, list price, accessed 9 Nov 2026: https://dataforseo.com/pricing/dataforseo-labs/dataforseo-google-api
- DataForSEO, how estimated traffic is calculated, accessed 9 Nov 2026: https://dataforseo.com/help-center/how-is-etv-calculated
- DataForSEO, analysing SERP competition, accessed 9 Nov 2026: https://dataforseo.com/help-center/how-to-analyze-serp-competition-for-any-keyword-with-dataforseo-labs-api
- Ahrefs, traffic estimate accuracy, 3 May 2022: https://ahrefs.com/blog/traffic-estimations-accuracy/
