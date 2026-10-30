---
name: mb-seo
description: Improve a business's search presence. Reviews public pages straight away, then offers OpenSEO, Main Branch's chosen optional SEO tool, for keyword, competitor, site audit, and AI-visibility data. Use when the owner says SEO, ChatGPT or Claude or Perplexity answers, llms.txt, search rankings, keyword research, competitor keywords, site audit, AI visibility, OpenSEO, Search Console through OpenSEO, or asks why the site is not found on Google.
loops: [sense, decide, ship]
---

# SEO

Support status: **experimental**. It stays experimental until a business deploys
OpenSEO from this skill alone and a Google login survives a seven-day check.
Say so when the owner considers setup. OpenSEO is optional: a business that skips
it loses nothing else in Main Branch.

**CLI facts first:** Run `mb status --json --peek` from the business repo before
advice. Run `mb connect doctor --json` before OpenSEO setup or research. No
`mb seo` command exists; do not invent one.

## First response

If this business has no OpenSEO copy, open with:

> Give me your site and what you want SEO to improve. I'll review the public
> pages and suggest the first useful changes. For keyword and competitor data,
> we can set up OpenSEO, our chosen optional SEO tool. That needs accounts and
> may incur data charges.

Then start useful work with public evidence. Do not hold the review until setup.

## Route the request

| Owner wants | Do this |
|---|---|
| A review of the site, or does not want accounts | Run the public-site review below. |
| Keyword or competitor data, and has no OpenSEO copy | Offer setup. Follow [references/setup.md](references/setup.md) one step at a time. |
| Research from an existing copy | Follow [references/daily-use.md](references/daily-use.md). |
| AI answers, ChatGPT, Claude, Perplexity, or `llms.txt` | Follow [references/ai-agents.md](references/ai-agents.md). |
| A weekly review, "how is SEO doing", or pages losing clicks | Follow [references/search-review.md](references/search-review.md). |
| Search Console or Analytics evidence | Use `mb google` if it is connected. For OpenSEO, follow "Later: Google" in [references/setup.md](references/setup.md). |
| An OpenSEO upgrade, backup, or rollback | Follow [references/upgrades-and-backups.md](references/upgrades-and-backups.md). |
| Page or copy changes | Route to `/mb-site`. |
| A keyword choice for an offer | Route to `/mb-think` keyword gate. |

## Business context

The business repo is the source of truth. Read before advising:

- offers: `core/offer.md` or `core/offers/<slug>/offer.md`;
- audience: `core/audience.md` or the offer's audience file;
- keywords: `research/*-keyword-gate-*.md`;
- public proof: `core/proof/`;
- past choices: `decisions/*-seo-*.md`;
- site domains: each site repo's `.mainbranch/repo.json`.

If a needed fact is missing, such as address, hours, service area, key pages, or
competitors, ask once and save the answer to the repo with approval. OpenSEO's
project context is a working copy: fill it from the repo, and never treat it as the
record.

## Public-site review

Use only pages anyone can open: the home page, key offer pages, `robots.txt`,
`sitemap.xml`, and any pages the owner names. Check:

- what each page is trying to rank for, and whether its title, description, and
  main heading agree;
- whether search engines can reach it: `robots.txt`, noindex tags, canonical
  tags, and sitemap coverage;
- whether `robots.txt` allows the search and user bots, and whether `/llms.txt`
  exists and what it says;
- structured data, internal links, thin or duplicate pages, and broken links;
- whether the pages answer what the business's audience actually searches for,
  using the business context below.

Return the first three to five changes, most useful first, with the page and the
evidence for each.

**Limits to state plainly:** Public pages show what is on the site. They do not
show rankings, search volume, traffic, or what caused a change. Never predict a
ranking or a traffic result.

## Hard rules

- Never promise citations or AI traffic. `llms.txt` is a map for agents sent to the
  site; no vendor says it improves search.
- One OpenSEO copy per business, on that business's own Cloudflare and
  DataForSEO accounts. No shared keys. Its own Worker and resources, with no
  binding to any existing service.
- Paid research needs the owner's yes first, with a cost. MCP read-only hints
  are not a spend limit. `mb` cannot enforce this, so tell the owner to keep the
  DataForSEO balance low.
- Keep rank and AI-visibility schedules off unless the owner approves them.
- Keep Cloudflare Access on. Never set `AUTH_MODE=password` on a copy.
- Deploy only a reviewed release SHA. Never run `alchemy destroy`.
- Owner-run steps stay with the owner: account creation, payment, token creation,
  and browser approvals.
- Keep tokens in `mb connect`. Never print a secret, `.env.selfhost`, or raw
  bootstrap or deploy output.
- Never run a paid call as a setup test.
- Report the guard, the app, and each data connection separately. One passing
  does not prove another.

## Save what matters

Durable findings land in the business repo, so losing a copy costs little. After
the owner agrees, save findings to `research/YYYY-MM-DD-seo-<topic>.md` and choices
to `decisions/YYYY-MM-DD-seo-<topic>.md`. Record the date, source, cost, and what
the numbers do not prove. Keep tokens and raw exports out of the repo.

## Support limits

Claude Code is the only runtime this skill targets. Codex is not supported:
do not offer Codex MCP setup from this skill. Steps marked NOT VERIFIED have not
been run at the current pin; report what happened when one is used.
