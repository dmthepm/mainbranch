# IndexNow playbook

Upstream skill: none. No shipped OpenSEO skill uses `submit_indexnow_urls` (OpenSEO v0.1.26). This playbook is the whole procedure, so read the tool text in `T/submit-indexnow-urls.ts` and the spec `docs/maintainers/specs/0016-indexnow.md` first. It also adds the business layer.

## Use it for
- Telling Bing and other IndexNow engines that a page was added, changed, redirected or removed.
- Price, stock or availability changes on a store.
- A new post, changelog entry or help page on an app site.
- Removed or redirected pages after a clean-up.
- Not for Google. Google does not use IndexNow.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `submit_indexnow_urls` | No | URLs submitted count against the site's crawl quota at each engine | "Uses no credits" (`submit-indexnow-urls.ts:23`) |

Worked estimate (derived): ten changed URLs after a content update is one request to Bing, $0 in credits and $0 at DataForSEO. The cost is crawl quota and the time to host a key file. Never submit the whole site to save effort.

Estimate tool: none needed. Nothing here recurs. Do not build a schedule around it; submit when something changed.

Writes outside OpenSEO: this tool contacts search engines. It does not edit the site. Treat it as outward-facing, and ask the owner first on a business's first use.

## Run it well
1. Confirm the case. IndexNow helps Bing, Yandex, Yep and other participants. For Google, use the sitemap and Search Console URL inspection. Do not promise an indexing result.
2. The protocol proves you own a site by a text file named after the key, served from the site's root. OpenSEO looks for it at `https://{host}/{key}.txt` and accepts it only if the body, trimmed, equals the key (`IndexNowService.ts:79-110`). It checks the bare domain and the `www.` host separately (`IndexNowService.ts:136-148`), so a site that serves both needs the file on both. It does not follow redirects: a redirect, even to the same path on another host, is reported as a problem (`IndexNowService.ts:97-106,128-129`). Hosting the file is a site change: the owner approves it, then `/mb-site` makes it.
3. The first call creates the project's 32-character key and returns it. The key is not secret, but it is the project's. Do not post it elsewhere.
4. Submit only changed URLs: added, updated, redirected or removed. Wait at least 5 minutes before resubmitting the same URL (IndexNow FAQ).
5. Read the per-host result. `submitted` means the engine received it. `failed` names the cause, such as a missing key file. If the key file is missing, fix it once, then retry once. Do not loop.
6. The check can be inconclusive: bot protection, server errors and timeouts let the submission go ahead (`0016-indexnow.md`). An engine may answer 202 while it verifies a new key. That is "received", not "accepted".
7. Do not submit URLs blocked by robots.txt, set to noindex, or canonicalised elsewhere. Engines will not index them.
8. Check Bing Webmaster Tools weekly for what IndexNow received, if the owner has an account. The agent has no tool for that report; ask the owner. OpenSEO keeps only the latest result.
9. After a migration or redesign, a full submission is acceptable once. Otherwise changed pages only.
10. Cadence: event-driven. Submit after a real change, not on a calendar.

## Read the result
Worth doing:
- Pages that change often or lose value fast: price, stock, a launch page, a removed product.
- A redirect or removal you want engines to notice.

What this does not prove:
- A 200 or 202 means received, not indexed, not ranked.
- It is not a ranking signal. No source read says it is.
- It does nothing for Google. A Google recrawl request goes through Search Console or the sitemap.
- Faster discovery is not traffic. Bing's help page ties faster indexing to more traffic. That is the vendor describing its own feature, and the business's Bing audience is unknown.
- Engines set their own daily limits and do not publish them. A 429 means wait.
- Every submitted URL counts against crawl quota, so unchanged URLs waste it.

## Save
Write a line in `research/YYYY-MM-DD-seo-indexnow.md` for each submission batch worth keeping: date, host, count of URLs, what changed, per-host result, whether the key file was present, cost ($0), and what the result does not show. No key value is secret, but keep it out of public notes. Decisions about hosting the key file go to `decisions/`.

## App business vs store business
App business with a website:
- Few pages that change rarely. A sitemap is usually enough, so IndexNow is optional.
- It earns its keep for a changelog or blog that posts often.
- If the site is static, or on a host where a root file is easy to add, OpenSEO's flow works as written.

Small store:
- Price and stock changes are the best case.
- A hosted store builder may not let the owner place a file at the store root. A hosted store was not tested. Public sources conflict on whether a major store platform submits to IndexNow on its own. Before doing anything, check the Bing Webmaster Tools IndexNow report for submissions from the platform. If they are already there, stop.
- If the key file cannot be placed at the root, OpenSEO's check may fail or be inconclusive. Do not retry in a loop, and do not install an add-on without owner approval. Use the sitemap and Bing's own URL submission instead.

## Sources
- OpenSEO: `src/server/mcp/tools/submit-indexnow-urls.ts`; `src/server/features/indexnow/services/IndexNowService.ts` (Bing, then Yandex, then Yep; 10 s timeout); `src/types/schemas/indexnow.ts`; `docs/maintainers/specs/0016-indexnow.md`.
- IndexNow.org, Documentation. https://www.indexnow.org/documentation (accessed 9 Nov 2026).
- IndexNow.org, FAQ. https://www.indexnow.org/faq (accessed 9 Nov 2026).
- Bing Webmaster help, IndexNow. https://www4.bing.com/webmasters/help/indexnow-0z209wby (accessed 9 Nov 2026).
- Google Search Central, Ask Google to recrawl your URLs. https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl (accessed 9 Nov 2026).
