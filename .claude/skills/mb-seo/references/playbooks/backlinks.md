# Backlinks playbook

Upstream skill: `link-prospecting` (OpenSEO v0.1.26). Load it for the procedure. `competitor-analysis` and `competitive-landscape` also call the backlinks overview. This file adds the business layer.

## Use it for
- Knowing how many sites link to the business and whether that is growing.
- Benchmarking against 3 to 5 rivals, to size how much link work a topic needs.
- Building a short list of sites worth a human pitch: gift guides, resource pages, "best of" lists.
- Spotting cheap fixes: links pointing at pages that moved or broke.
- Saying no to link spend when the gap is not the problem.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `get_backlinks_overview` | yes | one summary call plus one history call; cached 6 h | $0.024 per task + $0.000036 per row (`pricing.ts:91-92,170-172`); history billed per day in range (`pricing.ts:182-185`) |
| `get_backlinks_profile` | yes | page size 50 (default), 100 or 200; spam filter and mode change rows | same formula (`backlinks.ts:210`; `schemas/backlinks.ts:62-63`) |
| `get_serp_results` (prospecting queries) | yes | queries (up to 10 per call), depth | at depth 10: 3 priority reads x 2 x $0.0006 = $0.0036 per query; deeper, add $0.00045 per extra page of 10 to each read price (`pricing.ts:256-265`; `rank-tracking.ts:16-19,55-58`) |
| `get_domain_overview` (qualify a prospect) | yes | one call per domain | Labs one-row call (`pricing.ts:248-253`) |
| `get_search_console_performance` | no | nothing | free; GSC Links report is also free, in the Google UI |

Derived per call, raw USD: overview about $0.061 (summary $0.024, history up to about $0.037); a page of 50 rows $0.026; 200 rows $0.031; a prospect overview $0.012; a SERP read $0.0036 per query. Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md). Self-hosted needs the Backlinks API switched on in the DataForSEO account (`get-backlinks-overview.ts:84`).

Worked estimate (derived): the site and 3 rivals ($0.245), two pages of 200 referring-domain rows for the two biggest rivals ($0.062), 10 prospecting queries ($0.036), 10 prospect overviews ($0.121). About $0.46 for a full first pass. A monthly check on the site and one rival is $0.12.

Estimate tool: none exists. Show the table row and the arithmetic. Nothing here creates recurring spend. Ask first on every paid row.

## Run it well
1. Check the free evidence first: Search Console's Links report for the site's own links. It is a sample and may list removed links, so treat it as a floor.
2. Run the overview on the site and 3 rivals from the competitor list. If those are not confirmed, do the domain playbook first.
3. Use page size 200 and keep the default one link per referring domain. The $0.024 task fee equals about 667 rows, so fewer, larger pages are cheaper. Keep the spam filter on.
4. OpenSEO has no link-intersect call. Compare the rival lists by hand: a domain that links to two or more rivals and not to the site is a candidate.
5. Judge relevance by reading the page. Do not filter on a score alone. Skip homepages, thin affiliate pages, unrelated forums and direct rivals.
6. For a small site, authority floors from big-site guides are too high. Use fit and editorial standards first.
7. Run SERP prospecting queries in one batch of 5 to 10 for the one asset worth linking to. A link needs a reason: data, a guide, a tool, a good comparison.
8. Draft outreach only. Research permission is not permission to contact. Contact details come from the web, not from OpenSEO, and only ones actually found.
9. Cadence: one-off at the start, then monthly for the site and one rotating rival, and a full rival re-benchmark each quarter. Each paid run in that cadence still needs the owner's yes. Weekly is free only (Links report, replies).

## Read the result
Worth acting on:
- A domain that links to several rivals and would plausibly cite the business, with a real asset to offer.
- Broken or moved pages that still earn links, fixed with a redirect by `/mb-site` after approval.
- A rival gap that is mostly links, when the content is already at parity.

What this does not prove:
- Counts differ by tool, because each has its own crawler and index. Never mix two providers in one table.
- Rank and spam score are this vendor's own measures, not Google's. A high spam score is a pattern flag, not proof a link is ignored.
- A link count does not show a ranking effect. Google says it can judge most links itself and most sites need no disavow.
- A lost link may mean a removed page or stale data. Check before you chase it.
- History always includes subdomains, whatever scope you pass.

## Save
`research/YYYY-MM-DD-seo-backlinks.md`: target and rival domains, scope, date, source tools, actual cost (or "unknown"; estimate and say so), referring-domain counts with the caveat that they are one index, the prospect shortlist with the fit reason, and what was rejected. Outreach drafts are kept separate and marked not sent. No raw exports, no contact lists with personal data, no secrets.

## App business vs store business
App business:
- Web links help the web content (help, guides, comparisons, press). They do not set store ranking, which the app stores tie to listing text and user behaviour.
- Prospects: category directories, review sites, newsletters, and "best apps for X" lists. Find them with SERP queries and read the pages.
- Link-worthy assets: original data, free tools, a glossary, honest comparison pages.

Small store:
- Gift guides are the main route. Many publishers prefer informational pages, so pitch the guide, not the shop page.
- A free product given for a link must be qualified with `rel=sponsored` or `nofollow` under Google's spam policy. The owner decides before any offer.
- Link internally and ask for links to the canonical collection URL, not a product path under a collection.
- Pitch ahead of Valentine's, Mother's Day and the holidays. Lead times are not set by a primary source.

## Sources
- OpenSEO: `plugins/openseo/skills/link-prospecting/SKILL.md`; `src/server/lib/dataforseo/pricing.ts:91-92,170-172,182-185,256-266`; `src/server/lib/dataforseo/backlinks.ts:177-323`; `src/server/features/backlinks/services/backlinksServiceData.ts:65,121-140`; `src/types/schemas/backlinks.ts:62-63`; `src/server/mcp/tools/get-backlinks-overview.ts:84`.
- DataForSEO Backlinks pricing, list price, accessed 9 Nov 2026: https://dataforseo.com/pricing/backlinks/backlinks
- DataForSEO, spam score, accessed 9 Nov 2026: https://dataforseo.com/help-center/what-is-spam-score-and-how-is-it-calculated
- Google, spam policies (link spam), updated 28 Aug 2026: https://developers.google.com/search/docs/essentials/spam-policies
- Google, qualify outbound links: https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links
- Google, disavow links: https://support.google.com/webmasters/answer/2648487
- Google, Search Console Links report: https://support.google.com/webmasters/answer/9049606
- Ahrefs, comparing link indexes, 13 Mar 2024: https://ahrefs.com/blog/link-index-comparison/
- Search Engine Land, ecommerce link building, 5 Apr 2023: https://searchengineland.com/6-link-building-techniques-for-ecommerce-395224
