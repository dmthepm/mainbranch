# Site audit playbook

Upstream skill: `seo-audit` (OpenSEO v0.1.26); `local-seo` also calls `run_site_audit`. Load `seo-audit` for the procedure. Deliver through `seo-report`. This file adds the business layer.

## Use it for
- Finding what blocks crawling or indexing: robots rules, noindex, server errors, bot blocks.
- Finding template-level faults that repeat across many URLs: duplicate titles, canonical conflicts, redirect chains, orphan pages.
- Deciding what to fix once in a theme or template, what to leave alone, and what needs the owner.
- A month-to-month count of issues, so the owner sees a trend.
- Checking a launch, redesign or theme change before and after.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `run_site_audit` (crawl only) | No DataForSEO charge | Worker compute on the business's own Cloudflare plan | crawl price not in source |
| `run_site_audit` with `runLighthouse` | Yes | up to 10 sampled pages x mobile and desktop = up to 20 calls | $0.005 per call (`pricing.ts:113`; `lighthouse.ts:130-166`; `siteAuditWorkflowPhases.ts:238-239`) |
| `run_site_audit` with `renderJavaScript` | Yes, outside DataForSEO | pages rendered; Cloudflare Browser Run, Context.dev fallback | Cloudflare: $0.09 per browser hour, billed as a 20 s attempt each, so $0.0005 a page. Fallback to Context.dev adds $0.0025 a page (`audit-rendering.ts:6-14`) |
| `get_audit_status`, `get_audit_issues`, `get_audit_pages`, `list_site_audits` | No | none | reads |
| `delete_site_audit` | No, but permanent | none | `site-audit-cleanup-tools.ts:66` |

Worked estimate (derived): a 100-page site, crawl only, costs nothing at DataForSEO. Adding Lighthouse is at most 20 x $0.005 = $0.10 per audit at the raw price. Rendering those 100 pages is $0.05 in Browser Run time if every page renders on Cloudflare, and $0.30 if every page also falls back to Context.dev (100 x $0.0005 + 100 x $0.0025; `audit-rendering.ts:11-14,37-52`). Hosted OpenSEO holds twice the low figure as credits, with markup and rounding (`audit-rendering.ts:61-63`); that hold is a hosted device, not a $0.10 ceiling on a self-hosted copy, which has no meter and no cap. The real cost of an audit is the owner's time reading it and the Cloudflare plan limits. Anything in [daily-use.md](../daily-use.md) still applies: ask first, and keep Lighthouse and rendering off unless the owner approves. Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md).

Estimate tool: none exists. `run_site_audit` returns no cost field, so write down the estimate before you run it and the actual after, by provider: the DataForSEO dashboard for Lighthouse, and the Cloudflare and Context.dev accounts for rendering. A zero DataForSEO change does not show rendering cost nothing ([costs.md](costs.md)). Nothing here recurs: there are no scheduled audits.

## Run it well
1. Read the public-site review first ([SKILL.md](../../SKILL.md)). Do not buy a crawl to learn what a page source shows.
2. Check prior `research/` audits. Compare against the last count, not against a blank.
3. Set `maxPages` to cover the real site. The default is 50, the range 10 to 10,000 (`audit-limits.ts`). Small sites often fit in one pass. A copy on Workers Free may stop near 50 fetches; say the audit was cut short, not that pages are broken.
4. Crawl only. Lighthouse once, as a baseline, after the owner agrees, then after a theme change or a deploy. Never on a schedule.
5. Shopify: the owner makes the crawler-access signature and the copy needs `CRAWLER_ACCESS_SECRET` set (see [daily-use.md](../daily-use.md)). Without it the audit reports `blocked-page`, which is a crawler problem, not a store problem. Run one audit at a time, leave rendering off, and wait hours before a re-run, because Shopify throttles back-to-back audits ([daily-use.md](../daily-use.md)).
6. Read issues in this order, not in OpenSEO's severity order: (a) anything blocking all crawling or indexing; (b) important pages not indexed or with the wrong canonical; (c) broken links and redirect chains on pages that sell; (d) titles, descriptions, headings; (e) the rest. `noindex-page` and `canonicalized-page` are only `info` (`audit-issues.ts:253,261`). Any such finding on a URL in the sitemap goes to the owner.
7. Separate crawl failures from page faults. Rows marked `blocked` or `rate_limited` are access problems.
8. Group findings by template. One theme fix beats fifty page fixes.
9. Check field data in Search Console's Core Web Vitals report. Lighthouse is a lab test of one page load, with no real users. Use it to find causes once field data shows a problem.
10. Route approved fixes to `/mb-site`. The audit does not authorise edits to robots, redirects, canonicals, themes or apps.
11. Cadence: a crawl-only audit monthly, plus after any theme, app or template change, if the owner agrees to each run. Quarterly, a Lighthouse sample on changed templates only may be proposed; each sample is a paid call and needs the owner's yes first. On Shopify, space re-audits by hours and keep rendering off.

## Read the result
Worth acting on:
- A blocker on a page that sells or is in the sitemap.
- The same fault across a whole template.
- A fault paired with a real traffic loss in Search Console.
- A rise in broken links or redirect chains since the last audit.

What this does not prove:
- A crawler warning is not a traffic loss. Observations are not causes.
- The registry has 32 issue types. It has none for hreflang, structured data, HTTPS or sitemap-versus-canonical mismatch, though the crawler reads some of them (`audit-issues.ts`; `page-analyzer.ts:138-141`). Say "not checked", not "no problems".
- Lighthouse samples the home page plus one page per URL pattern, one run per page and device. One product page stands for all products. A 5 to 10 point swing between runs is noise.
- Lighthouse has no lab INP. Use total blocking time as the proxy and report field INP from Search Console.
- A score is not a ranking factor on its own. Google says Core Web Vitals feed its ranking systems, with no promise of position.
- A failed lookup is unknown, not "fine".

## Save
Write `research/YYYY-MM-DD-seo-site-audit.md`: domain, date, pages crawled against pages in the sitemap, options used (Lighthouse and rendering on or off), issue counts by type against last time, which findings were verified by hand, estimated and actual cost by provider (DataForSEO usually $0; rendering, if used, is billed elsewhere), or unknown, and what was not checked. Owner choices go to `decisions/`. Keep the saved HTML report's link, but the readout is the record. No raw page dumps.

## App business vs store business
App business with a website:
- Few pages, so the default audit often covers the whole site. Field Core Web Vitals data may be missing; say so and use lab data as the only signal.
- Field data leaves out Chrome on iOS, which understates an iOS-heavy audience.
- The audit does not check app banners or app-link files. Fetch those by hand and report if present.

Small store:
- Theme and installed apps drive speed. Duplicate product URLs (collection path against `/products/`) and internal links to the non-canonical one cause most orphan and canonical findings.
- Fixes are theme edits. The owner approves each one, including `robots.txt.liquid`.
- Re-audit after every theme change or new app, one audit at a time with hours between them and rendering off. Crawler access signatures expire; record the renewal date.

## Sources
- OpenSEO: `src/server/mcp/tools/site-audit-tools.ts`; `src/shared/audit-limits.ts`, `audit-issues.ts`, `audit-rendering.ts`; `src/server/lib/dataforseo/pricing.ts`, `lighthouse.ts`; `src/server/lib/audit/lighthouse.ts`; `src/server/workflows/siteAuditWorkflowPhases.ts`; `docs/maintainers/specs/0009-site-audit-crawl-architecture.md`.
- Google, Core Web Vitals and Search. https://developers.google.com/search/docs/appearance/core-web-vitals (accessed 9 Nov 2026).
- web.dev, Web Vitals. https://web.dev/articles/vitals (accessed 9 Nov 2026).
- Chrome, CrUX methodology. https://developer.chrome.com/docs/crux/methodology (accessed 9 Nov 2026).
- DataForSEO, Lighthouse API pricing. https://dataforseo.com/pricing/on-page/lighthouse-api (list price, accessed 9 Nov 2026).
- Google Search Console Help, Page indexing report. https://support.google.com/webmasters/answer/7440203 (accessed 9 Nov 2026).
