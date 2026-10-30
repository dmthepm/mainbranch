# Weekly Search Review

Turn four weeks of Search Console data into a short action list. It needs Search
Console through `mb google`. It does not need OpenSEO.

No paid calls. Five actions at most. Every fix goes to the owner for approval, and
page changes go through `/mb-site`.

## Rules

- Run from the business repo. It records the site; never pass or guess one.
- Search Console rows are private. Share conclusions and small totals, not raw
  rows. Put full pulls in a git-ignored folder such as `.mb/private/pulls/`.
- Compare two equal windows. One snapshot is not a trend.
- A drop beside a site change, a season, or a Google update is a lead, not a cause.
- Never recommend changing a page's date without changing its substance.

## 1. Pull

Use two 28-day windows, the current one ending three days ago, and name the dates in
the answer. Pacific Time days apply, as `docs/google.md` explains.

```bash
mb google sc query --start <cur_start> --end <cur_end> --dimensions query,page --row-limit 25000 --out .mb/private/pulls/sc-<cur_end>.json
mb google sc query --start <prev_start> --end <prev_end> --dimensions query,page --row-limit 25000 --out .mb/private/pulls/sc-<prev_end>.json
mb google sc sitemaps list --json
```

If a result has `may_have_more`, repeat with `--start-row <next_start_row>`. Google
returns only its top rows, so state that coverage limit. If a command reports
`not_connected`, `grant_missing`, or a refused sign-in, stop and show the owner its
`next:` line. If the owner won't connect Google, read a Search Console Performance
export instead. On `quota_exhausted`, stop and say so.

## 2. Sort

Join the windows by page and query, then build these lists:

| List | Starting rule |
|---|---|
| Near page one | Average position 4 to 20, with above-average impressions for this site |
| Low click-through | High position, but CTR well below the site's own norm at that position |
| Losing clicks | Down 30% or more, from at least 20 clicks |
| No matching page | Real impressions, where the best page is the home page or an unrelated one |
| Key pages | Pages for the offers in `core/`, plus any key pages in `decisions/`, whatever their numbers |

These thresholds are starting points. Adjust them for small sites and say so.

If this business has an OpenSEO copy with Google connected, you may add
`get_search_opportunities`. Treat its score as one input. Check that the tool is
still free at the pinned release before relying on it.

## 2b. Read AI answers, optional

If the owner exports them, add Google's Generative AI report and Bing's AI
Performance, plus visits from AI referrers. These are manual; Google's report has no
documented API. See [ai-agents.md](ai-agents.md). Treat them as baseline numbers,
not causes.

## 3. Check indexing

Inspect at most 10 pages: key pages, plus any page in the top actions.

```bash
mb google sc inspect --url <page> --json
```

Requesting indexing has no API, so the owner does that in Search Console. Flag any
sitemap with errors, warnings, or an old `lastDownloaded`.

## 4. Choose

Rank by business value, then evidence, then effort. Prefer a key page's indexing
problem, then a key page losing clicks, then a buyer page near page one, then a
weak title on a high-impression page, then a query gap matching something the
business sells.

Each action names the page, the evidence with its dates, the proposed change, the
effort, and the main uncertainty. Drop anything that would create near-duplicate
pages or chases a keyword no buyer uses.

## 5. Judge past changes

List logged changes now 28 or 90 days old. Compare that page and its queries against
the matching earlier window, and note any season, sale, or Google update. Report what
moved, not why; the owner decides whether to keep the change.

## 6. Save

After the owner agrees, write `research/YYYY-MM-DD-seo-review.md` with the windows,
headline totals, the actions, a line per list, and what was not read. Keep raw rows
out. When an approved change ships, add the page, date, and change to that file, so
a later review can compare the next 28 and 90 days against it.
