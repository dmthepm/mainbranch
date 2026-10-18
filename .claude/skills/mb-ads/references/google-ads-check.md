# Google Ads Daily and Weekly Check

A scored check of a running Google Ads account: money and delivery, tracking
quality, and a weekly read of search terms, products and keywords. It is the
Google half of Check Mode in [launch-plan-check.md](launch-plan-check.md). For
building a campaign, use [google-ads-campaign-plan.md](google-ads-campaign-plan.md).

Source: a live ecommerce dogfood business running Brand Search and Shopping,
September 2026. The structure is general; every threshold marked *(set)* is
filled from the business's own margins and account history and kept in a
decision or rubric file in the business repo.

**Leading rule: evidence.** Every line in the report carries a number from
today's pull and its score. Store orders are the judge of a sale; Google's
Conversions column counts only once purchase parity (T2) is green.

---

## Inputs

Main Branch does not ship a Google Ads read adapter. Prefer
[Google's official read-only Google Ads MCP server](https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server)
when the operator has set it up and approved its use. It can discover accessible
accounts and run reporting queries; it cannot change campaigns, but that does
not make the credential read only: see
[google-ads-agent-access.md](google-ads-agent-access.md) for the reader user,
roles and the Script write route. Otherwise, use the operator's Google Ads
exports. Gather:

- Google Ads campaign, product, search-term and keyword figures for yesterday,
  the last 7 days and since launch; use CSV exports as the fallback, especially
  for anything over about 50 rows;
- store or site analytics: paid Google sessions, sessions with add-to-cart, and
  orders by source and campaign;
- the store or site's attribution report by click id (for T3);
- a check that the purchase tag and any other pixels are on the product page.

Raw exports stay out of git: keep them under `.mb/private/` (add it to
`.gitignore`) and write only counts and your own object ids into the repo.

## Scores

Every line gets **green**, **amber** or **red**, or **thin** when the sample is
below its minimum. A thin line is reported with its numbers and never acted on.

## M: Money and Delivery (Daily)

| # | Line | Measure | Green | Amber | Red: action |
|---|------|---------|-------|-------|-------------|
| M1 | Delivery | Shopping: yesterday's spend vs daily budget. Brand: search impression share (Brand is capped by how often people search the name, not by budget) | Shopping 50-200% of budget; Brand share 80%+ | Shopping under 50% two days running (bids too low to win): propose a bid step; Brand 50-80% | Zero spend while "Eligible", or status not Eligible: tell the operator now (billing, policy) |
| M2 | Stop rules | Cumulative cost since launch, never reset | Under every line | Within 20% of a line | A stop line crossed *(set: e.g. Shopping spend with no add-to-cart, spend with no sale, Brand spend with no sale)*: pause per the standing go, read back, log |
| M3 | Cost per sale | Cost since launch / qualifying store orders from `google / cpc` | At or under target *(set)* | Target to break-even | Over break-even, or no sale by the campaign's review point |
| M4 | Click price | 7-day average CPC | Within the account's history *(set)* | Above it | Above the highest max bid (a bid changed) |
| M5 | Click rate | 7-day CTR | At or above the account's floor *(set; Brand typically far higher than Shopping)* | Below it | Very low CTR on 2,000+ impressions: a product, title or image problem; check the product rows |
| M6 | Carts | Add-to-cart sessions / `google / cpc` sessions | At or above the store baseline *(set)* | Below it | Far below on 50+ sessions: a landing-page question; route to `/mb-site` |

Minimums: M4 and M5 need 100+ clicks or 1,000+ impressions in the window; M3
needs at least one sale; M6 needs 50+ sessions. Below that: thin.

## T: Tracking Quality (Daily)

| # | Line | Measure | Green | Amber | Red: action |
|---|------|---------|-------|-------|-------------|
| T1 | Tags present | Purchase tag and other pixels on the product page | All present | A pixel added or gone since the last run | Purchase tag missing: fix before reading any conversion number |
| T2 | Purchase parity | Store orders credited to Google paid since launch vs Google's purchase conversions | Equal (±1 for lag), or 0 = 0 | | A Google-paid store order that Google didn't count within 24 h: re-test the purchase tag |
| T3 | Click-to-visit | Paid Google sessions by click id (the store's attribution report, not UTM rows) / Google clicks, same dates | 75%+ | 50-75% | Under 50% on 30+ clicks: test the landing URL with the tracking suffix and a test click id (UTMs survive, no redirects), then compare analytics paid sessions |
| T4 | UTM integrity | `utm_campaign` on `google / cpc` sessions | Every paid session carries a live campaign | Known test values; a few feed-sync sessions above the organic baseline | A whole day of paid clicks arriving under another source, or the account suffix gone |
| T5 | Relay or redirect | Any image or link relay the store depends on | OK | A changed header | Any failure |

Why T3 uses click id: UTMs split campaigns, but a missing or overridden tag
doesn't lose the visit, so UTM rows undercount clicks that did arrive.

## W: Weekly Deep Read (Monday, Last 7 Days and Since Launch)

| # | Line | Measure | Green | Amber | Red: action |
|---|------|---------|-------|-------|-------------|
| W1 | Junk spend | Share of non-brand spend on search terms that contain an agreed negative word | 0% | Any spend on an agreed word: the shared negative list isn't attached to that campaign | Over 10% of non-brand spend |
| W2 | New junk | Non-brand terms with some spend *(set)* and no cart that belong to another product | None | Candidates listed for the operator with cost and clicks | |
| W3 | Products | Product rows: cost vs break-even, clicks with no cart | Under break-even, or thin | Over break-even with no sale | 40+ clicks and no add-to-cart by day 14: propose a bid cut |
| W4 | Keywords | New "Not eligible" reasons other than "rarely served" | None | | Disapproved or policy-limited: fix the ad or keyword |
| W5 | Meta pixel quality | Purchase event match quality, browser and server both firing | Good | Middling | Purchase missing on either side |

Keep the agreed negatives as a plain list in the business repo (one word or
phrase per line), and let a search term count as junk when it contains one as a
whole word.

## Prepare Actions, Then Report

1. **Prepare actions only where red says so and a standing go covers it.**
   Agree the standing go with the operator up front, in a decision file. A
   typical one:
   - covered by the standing go: pause by the stop rules, and add negatives
     already on the agreed list;
   - operator: budgets, bids, new campaigns or keywords, new negative words,
     conversion-action changes, settings changes, billing.

   Pausing and adding negatives are account writes. They need the operator, or
   a write tool the operator approved for exactly those actions. Main Branch
   itself doesn't mutate Google Ads. Read every change back after a reload.
2. **Everything else is a proposal** with the number behind it.
3. **Report in owner language:** status, spend (yesterday and since launch),
   clicks, carts, sales, the tracking verdict (T1-T5), what changed, what needs
   the operator. Log the raw figures (counts and your own ids, no customer
   data) in the push's review or outcome file.
4. **Weekly:** anything the week taught that changes a threshold or a step is
   edited in the business's rubric in the same commit, and named in the report.

Settings don't need a routine check once the account is stable. Open change
history only when an M or T line moves with no reason in the data.
