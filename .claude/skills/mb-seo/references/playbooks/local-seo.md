# Local SEO playbook

Upstream skill: `local-seo` (OpenSEO v0.1.26). Load it for the procedure, including how to draw the grid. This file adds the business layer.

## Use it for
- Deciding whether the business can have a Google Business Profile at all. Google lists online-only businesses as ineligible.
- Finding why a listing is weak: category, claim status, reviews, hours, or distance.
- Seeing how far Maps visibility reaches, and who wins where it does not.
- Comparing review volume, recency and owner replies against the two strongest local rivals.
- Stopping local spend for a business that has no place customers can visit.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `list_business_categories` | no | cached 7 days | free list |
| `search_local_businesses` | yes | `limit` (default 20) | $0.012 + $0.00036 per row (`pricing.ts:97-98`) |
| `get_business_profile` | yes | one profile | $0.0054 (`pricing.ts:99`) |
| `get_local_serp_results` | yes | search type and depth | Maps: $0.002 per call through depth 100. Local Finder: $0.002 per page of 10 (`pricing.ts:146-151,272-276`) |
| `get_business_reviews` | yes | reviews wanted (10 to 200, default 20); extended costs more | priority $0.001 + $0.0015 per 10 (`pricing.ts:105-106`); extended $0.01 per 20 (`:107`). Marked uncalibrated in source (`:103-104`) |
| `get_google_business_questions` | yes | depth | $0.0054 per 20 (`pricing.ts:102`) |
| `get_business_updates` | yes | posts wanted | $0.003 + $0.0015 per 10 (`pricing.ts:108-109`) |
| `get_local_rank_grid` | yes | grid size squared, times keywords | $0.0012 per point (`pricing.ts:154,277-281`) |

Derived grid cost per keyword, raw USD: 3x3 is 9 points, $0.0108; 5x5 is 25 points, $0.03. Repeating the exact same call within an hour collects the same searches free (`local-seo-tools.ts:904`). The map screen in the app runs live searches at $0.002 per point, so a grid there costs about two-thirds more than the same grid by tool. The queued grid estimator charges points x $0.0012 with no operator multiplier (`pricing.ts:277-281`). The basemap needs a Google Maps key with its own billing, separate from DataForSEO (`docs/GOOGLE_MAPS_SETUP.md`). Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md).

Worked estimate (derived): one store with a showroom. Find the listing ($0.019), profile ($0.005), one local SERP ($0.002), two rival profiles ($0.011), reviews for three businesses at 20 ($0.012), one 3x3 grid for one keyword ($0.011). About $0.06. A monthly repeat with three keywords on 3x3 grids is about $0.03 for the grids alone.

Real use: none logged for this feature, so there is no order of magnitude from practice. Local calls are cheap; a loop is the risk. 20 keywords on 5x5 live grids is $1.00 a pass.

Estimate tool: none exists for the grid. State points x keywords x $0.0012 before each run. Nothing in the MCP schedules grids. Ask first on every paid row.

## Run it well
1. Eligibility first, and it is free. A business needs a place where customers meet it in person during stated hours. A virtual office or mailbox does not count. If it fails, stop here and spend nothing.
2. Appointment-only showrooms may qualify but should not post regular hours. The owner confirms this with Google, not the agent.
3. Find the listing once and keep its `cid`. Match by `cid` or `place_id`, never by name.
4. Confirm the grid centre is the storefront before any grid. A grid on the wrong centre is worse than none.
5. Start with a 3x3 grid for one keyword a customer would actually type, at the default spacing. Use 5x5 only for a genuinely wide service area. Avoid search operators in keywords; they are noise in a local grid. (The grid estimate has no operator charge in source.)
6. Compare the listing with the top two rivals on primary category, other categories, review count and recency, owner replies, hours and the website link. Category and claim problems come before posting habits.
7. Cadence: one pass at setup. Then monthly at most, one grid per tracked keyword (three keywords at most), plus a drift check on name, hours and category. Weekly only while testing a fix. Each paid run in that cadence still needs the owner's yes.
8. Change nothing on the profile. A named human makes every edit, and the agent never replies to reviews.

## Read the result
Worth acting on:
- A wrong or weak primary category, an unclaimed listing, or a stale website link.
- A review gap against both strong rivals on count and recency.
- A grid change of 2 or more positions on average, or 2 or more points into the top 3, across two scans a week apart (a rule of thumb, not a source).

What this does not prove:
- A grid is simulated searches, not what customers saw. Results vary by device, time and history.
- A missing rank is not invisibility. Read it against that point's result count: a full set means outranked; a near-empty set means a sparse map.
- Compare grids only at the same zoom, spacing, device and keyword.
- Weak ranking far from the store is normal. Distance is the one factor you cannot change.
- Review count and rank rise together at times; that does not show one caused the other.
- National organic strength says nothing about local pack strength.

## Save
`research/YYYY-MM-DD-seo-local.md`: business and `cid`, market, date, tools run, actual cost (or "unknown"; estimate and say so), grid size, spacing, keywords, centre confirmed by whom, the head-to-head table, and the limits above. Proposed profile changes go to `decisions/` as proposals for the owner, not as done. Rival businesses with a site go to the competitor notes with approval. No raw exports, no secrets.

## App business vs store business
App business:
- No profile, no grid, $0. Google lists online-only businesses as ineligible.
- Once a quarter, one search for the brand on Maps, about $0.002, to check no lookalike listing sits on the brand name.
- No city landing pages. Google treats pages that funnel many cities to one page as doorway abuse.

Small store:
- An online-only store has no local route. A staffed showroom may.
- Pop-up eligibility is not settled in Google's pages. Treat a pop-up as ineligible until the owner confirms with Google.
- Review rules apply: no paying, discounting or selective asking for reviews.
- Never put keywords or the city in the business name; Google bans it.
- Skip per-city pages. Use one honest store page with real address facts.

## Sources
- OpenSEO: `plugins/openseo/skills/local-seo/SKILL.md`; `src/server/lib/dataforseo/pricing.ts:97-109,151-154,273-282`; `src/server/mcp/tools/local-seo-tools.ts:758-762,899-905`; `docs/GOOGLE_MAPS_SETUP.md`.
- Google, business eligibility, accessed 9 Nov 2026: https://support.google.com/business/answer/13763036
- Google, improve your local ranking, accessed 9 Nov 2026: https://support.google.com/business/answer/7091
- Google, guidelines for representing your business (name, hours), accessed 9 Nov 2026: https://support.google.com/business/answer/3038177
- Google, tips to get more reviews, accessed 9 Nov 2026: https://support.google.com/business/answer/3474122
- Google, spam policies (doorway pages), updated 28 Aug 2026: https://developers.google.com/search/docs/essentials/spam-policies
- DataForSEO Maps SERP pricing, list price, accessed 9 Nov 2026: https://dataforseo.com/pricing/serp/google-maps-serp-api
- DataForSEO Business Data pricing, list price, accessed 9 Nov 2026: https://dataforseo.com/pricing/business-data
- Whitespark, local search ranking factors, 6 Nov 2025: https://whitespark.ca/local-search-ranking-factors/
- BrightLocal, consumer review survey, 11 Feb 2026: https://www.brightlocal.com/research/local-consumer-review-survey/
