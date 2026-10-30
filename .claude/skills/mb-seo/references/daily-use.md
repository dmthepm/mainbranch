# OpenSEO Daily Use

Use the MCP server named `openseo-<BIZ>` for this business. If the name does not
match this business, stop.

## Before any paid call

Tell the owner what you will run, why, and the most it can cost. Wait for a yes.
Use an estimate tool when one exists. Keep a running total against the monthly spend
cap in the setup record, and stop when the next call would pass it.

A self-hosted copy does not show the DataForSEO balance, and tool results carry no
cost. Ask the owner to read the balance in their DataForSEO dashboard before and
after paid work, and record the real spend. Cost estimates from tool descriptions
are not a measurement.

```text
This needs paid data: <what>, for <why>. Estimated cost: <amount>.
Spent so far against your <cap> cap: <amount>. Go ahead?
```

`mb` cannot enforce the cap. The real limit is the DataForSEO balance, so keep it
low and leave automatic top-up off.

## What costs money

MCP read-only hints are not a spend limit. For example,
`research_ai_visibility_prompts` is marked read-only and still spends. Treat a tool
as paid unless it is listed as free here.

| Free | Paid or may spend |
|---|---|
| `list_projects`, project context, saved keywords | Keyword research and `get_keyword_metrics` |
| `estimate_rank_tracker_cost`, `estimate_ai_visibility_cost` | SERP, domain, ranked-keyword, and competitor lookups |
| Saved AI-visibility results, trends, and exports | Backlinks, local business, reviews, and Maps grid tools |
| Saved reports | Prompt research (about $0.25 per keyword) and `explore_prompt` |
| Search Console reads, and binding a site or property | `run_ai_visibility_check` and any live rank check |

For `run_ai_visibility_check`, pass the approved estimate as `maxCostUsd`.
Claude and Perplexity engines cost more than ChatGPT and Gemini.

Site audits use the business's Cloudflare plan, and may also cost data credits. Ask
before one. Keep JavaScript rendering and Lighthouse off unless the owner approves
them: Lighthouse is a paid DataForSEO call.

## Schedules stay off

- Rank trackers default to manual. Keep them manual unless the owner approves a
  schedule and its monthly estimate.
- **New AI-visibility trackers start on a weekly schedule.** Before creating one,
  show the estimate. If the owner has not approved a schedule, pause it straight
  away with `set_ai_visibility_schedule`, then confirm it is paused.
- `complete_ai_research_setup` turns on the same weekly paid checks when saved. Treat
  it as paid: ask first, and pause it the same way unless the schedule is approved.
- Enabling an AI-visibility schedule queues a paid check at once.

## Site audits

- On Workers Free, an audit may stop near 50 fetches and show the remaining pages as
  failed. This is reported, not tested. Don't read those rows as broken pages; say
  the audit was cut short.
- JavaScript rendering needs Workers Paid.
- For Shopify, the owner creates a crawler-access signature in Shopify admin and
  pastes it into Project settings > Integrations with the exact hostname. That
  needs `CRAWLER_ACCESS_SECRET` of at least 32 characters in `.env.selfhost`.
  Signatures expire, so record the renewal date in the business repo.
- Run one Shopify audit at a time, and leave rendering off. Shopify throttles
  back-to-back audits, so wait hours before a re-run.

## Report what the data shows

- Name the source, date, market, and cost of each number.
- Search volume and difficulty are estimates, not promised traffic.
- Separate three things: the copy is reachable, the app works, and the data
  connection returned real rows.
- If MCP calls return HTML or an "unexpected content type" error, check Managed
  OAuth first (setup step 7), then ask the owner to sign in again.

## Save and act

With the owner's agreement, save findings and choices as described in
[`SKILL.md`](../SKILL.md). Route page changes to `/mb-site`, and offer keyword
choices to `/mb-think`. A finding that matters should survive the loss of the copy.
