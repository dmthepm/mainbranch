# Search for AI Agents

SEO here means Google plus the assistants people ask: ChatGPT, Claude, Perplexity,
and Copilot. Facts below were read from each vendor's docs on 2026-10-30. Recheck a
vendor statement older than six months before relying on it.

Never promise citations or AI traffic. No vendor says `llms.txt` improves search.

## Check access first

This is free and matters most. Vendors say a blocked search bot can drop you out of
their answers, and the block is silent.

| Platform | Search bot | Live user fetch | Training control |
|---|---|---|---|
| Google | Googlebot | Google-Agent and others; may ignore robots | `Google-Extended` token |
| OpenAI | OAI-SearchBot | ChatGPT-User; robots may not apply | GPTBot |
| Anthropic | Claude-SearchBot | Claude-User; honours robots | ClaudeBot |
| Perplexity | PerplexityBot | Perplexity-User; may ignore robots | Not used for training, per Perplexity |
| Microsoft | Bingbot | Unknown | No clean split: see below |

Read `robots.txt` and report each search and user bot as allowed or blocked. Then
check the host's firewall or bot settings. A `curl` with a bot's name is only a hint,
because real bots come from their own addresses. Robots passing doesn't prove a
firewall lets them through; report that as NOT VERIFIED until checked.

For Google, OpenAI, and Anthropic, training controls are separate, and blocking them
leaves search alone. Microsoft differs: Bing's 2023 post says `NOARCHIVE` keeps a page
out of both training and chat answers, and no newer statement was found. Don't use it
without telling the owner that. Ask the owner once, record the answer in `decisions/`,
and never change it silently.

Traps:

- Cloudflare's managed robots.txt can add `Disallow: /` for GPTBot, ClaudeBot, and
  others. Check what is actually served.
- On Shopify, robots.txt edits are unsupported and can lose all traffic. Don't edit
  it for this.

## Publish `llms.txt`

Treat it as a map for agents sent to your site. It is a proposal, not a standard
with a standards body. Google Search ignores it. OpenAI, Anthropic, and Perplexity
state no use either way, though each publishes one on its developer docs. In Ahrefs'
June 2026 study of 137,210 domains, 97% of files got no requests in a month, so agents
find it when something sends them there. Say that plainly.

Follow llmstxt.org: an H1, a one-line blockquote, then H2 sections of links with
short notes, and an `Optional` section.

```markdown
# Acme Plumbing

> Licensed plumbers serving Portland, OR. Same-day repairs and water heater installs.

## Services
- [Water heaters](https://acme.example/water-heaters): Sizes, prices, install time.
- [Emergency repair](https://acme.example/emergency): Hours, area, call-out fee.

## Optional
- [About](https://acme.example/about): Licences and team.
```

- Say what you sell, who it's for, and how to buy. List 10 to 20 key pages, with a
  note on when each helps.
- Link to it, for example from the footer. Agents go where they are directed. Some
  sites also add `<link rel="alternate" type="text/markdown" href="/llms.txt">`; that
  is common practice, not part of the proposal.
- Return 200 quickly. Lighthouse's experimental audit also flags server errors, a
  missing H1, and a file with no Markdown links.
- Version it and limit who edits it. Leave out private contact details.
- Skip `llms-full.txt` unless the site is a docs site.

**Shopify:** every store already serves a default `/llms.txt`, a shopping-agent
script. Read it first. To override it, add `templates/llms.txt.liquid`. Copy the
default, keep its shopping lines using `agents.ucp_discovery_url` and
`agents.mcp_endpoint_url`, and add what the business is. Only the `request` and
`agents` objects work there, so product facts are hand-written. An override stops
picking up Shopify's later changes, so compare it with the default each quarter.

**Other hosts:** serve a plain file. On Cloudflare Workers, static files skip the
Worker unless `assets.run_worker_first` is set, so nothing will log them without it.

The owner approves every site edit.

## Measure

| Source | What it shows | How |
|---|---|---|
| Search Console, Generative AI report | Impressions by page, no clicks or queries | Owner export; no documented API |
| Bing Webmaster Tools, AI Performance | Citations per page and sampled queries | Owner export; the only per-page citation data |
| Analytics or Shopify referrers | Visits from `chatgpt.com`, `perplexity.ai`, `claude.ai`, `copilot.microsoft.com` | `mb google ga4 report`, or Shopify's referrer filter |
| Cloudflare AI Crawl Control | Crawlers, paths, and robots violations | Owner reads it; on all plans |

Keep a monthly baseline in `research/`. A fetch shows that something was requested,
not that it was read or used.

To test `llms.txt` on a site, change one thing, keep matched control pages out of
the file, and run at least 56 days. Fewer than 30 events or 6 usable page pairs is
inconclusive; say so and don't call it a win. Shopify can't log `/llms.txt` hits, so
use a tracked link: one page on a host you control, linked only from the file.

## Other surfaces

- Bing says `lastmod` matters for AI freshness, and Google uses it only when it is
  consistently accurate. Keep it honest.
- IndexNow helps Bing and others, and Cloudflare can send it automatically. No
  statement from Google or OpenAI was found.
- Markdown versions of pages: Claude Code asks for Markdown; other assistants are
  unknown. Google Search doesn't need them. On Shopify, check product pages before
  adding any, because a request for Markdown returned 404 on two stores tested.
- Structured data isn't required for Google's AI features. It still matters for
  rich results.
- Shopify's Catalog feeds ChatGPT and Copilot. Check product eligibility.
