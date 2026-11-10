# Project context playbook

Upstream skill: `seo-project-setup` (OpenSEO v0.1.26). Every other upstream skill also reads and writes the context. Load `seo-project-setup` for the interview. This file adds the business layer.

## Use it for
- Giving every SEO run the same facts: the offer, the audience, the market, the rivals, the money pages.
- Stopping repeat research spend, through the research log.
- Setting what the agent may claim, what it must leave alone, and what needs a human.
- Keeping a working copy of the business facts inside OpenSEO, while the business repo stays the record.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `whoami`, `list_projects`, `create_project`, `get_project_context`, `update_project_context` | no | nothing | "Uses no credits" (`project-context.ts:43,92`) |
| `save_project_website_setup` | no credits now, but **can create recurring spend** | passing `suggestedTopics` seeds weekly AI tracking on the first three topics; the first paid ChatGPT check is due about a week later | weekly checks, see the AI visibility playbook (`project-website.ts:66,80-87`; `ProjectWebsiteService.ts:83-97`; `websiteTrackingSetup.ts:14-59`) |
| `research_project_website` | yes | a language-model call plus web search, billed after the work | OpenRouter usage; model and price not in source (`project-website.ts:20`; `researchSpend.ts:48-85`) |
| `complete_ai_research_setup` | yes, and it creates recurring checks | see the AI visibility playbook | turns on weekly paid checks when saved (`ai-visibility-tools.ts:172`) |

Worked estimate (derived): the interview, context saves without suggested topics and the monthly review cost $0. The one paid step is `research_project_website`. It spends on a language model and web search, not necessarily on DataForSEO, and its price is not in source. Record the actual by provider, or "unknown"; a DataForSEO balance change does not measure it (see [costs.md](costs.md)). Saving suggested topics is a separate decision: get an estimate from `estimate_ai_visibility_cost` and the owner's yes before the save, and leave `suggestedTopics` out if the owner has not approved weekly checks. If a save did seed tracking and no monthly estimate was approved, call `set_ai_visibility_schedule` to pause it straight away, then read the tracker to confirm it is paused. On a Shopify site, a page that Shopify throttles may be fetched through a paid third-party reader when its key is set, at a per-page cost the docs state (`docs/SELF_HOSTING_CLOUDFLARE_OPERATIONS.md`).

Real use: not measured for this feature.

Estimate tool: none. Do not call `research_project_website` or `complete_ai_research_setup` as part of context setup without a separate yes and a cost. A self-hosted copy has no meter, so "completes before billing" can overspend (`researchSpend.ts:48`). Of the tools here, only `save_project_website_setup` and `complete_ai_research_setup` can create recurring spend; treat both as paid.

## Run it well
1. The business repo is the record. Read `core/`, the keyword gates and `decisions/` first, and fill the context from them. Ask the owner only for what is missing.
2. Confirm every fact with the owner before saving. Mark guesses as guesses, or leave them out.
3. Fill the four prose sections (business overview, current goal, positioning, writing preferences). Each holds about 4,000 characters; aim for two minutes of reading. A long context costs tokens on every later call.
4. Add 5 to 10 rivals by domain with one line each. Add 10 to 30 key pages with a role: hub, spoke, money or other. The cap is 100 each, but a short list is easier to check.
5. Use custom sections for the rest, one slug each: claims allowed (exact wording, with the proof), claims forbidden, exclusions (rival brands, regulated topics, places not served), brand terms, and the approved spend and who approves it.
6. Write the brand name. AI visibility matches on it, and an empty one falls back to the project name.
7. Write the monthly spend ceiling into the context as text so the agent can quote it. The real limits are the balances and caps at each provider account (DataForSEO, OpenRouter and the rest in [costs.md](costs.md)), not this text.
8. After any paid call, append one research-log line: what, market, date, verdict. The read path returns only the latest 20 entries within 90 days, so the repo's `research/` files are the long record.
9. Cadence: the interview once; a monthly owner read and correction; a same-day update when an offer, place, name, price rule or rejected claim changes.
10. Treat edits to the claims, exclusions and spend sections as approval-required. Any caller with the key can run `update_project_context`, and it is flagged destructive. A crawled page that talks the agent into rewriting its own limits is a real risk.
11. Never store secrets, tokens or customers' personal data. The full context returns to every caller.

## Read the result
Worth doing:
- A claim the agent might repeat goes on an allow-list with exact wording. An allow-list is easier to check than a ban list.
- Every key page has a role and one topic. Two pages with the same topic is a cannibalization question.
- The context agrees with the repo. If they differ, the repo wins and the context is fixed.

What this does not prove:
- Context is text in a model's window. It lowers mistakes; it enforces nothing.
- The research log is written by the agent. It is a convenience, not a ledger of spend.
- A full context does not mean a good strategy. It means the facts are in one place.
- Rival lists and key pages age. A stale list sends the agent after the wrong market.

## Save
In the business repo, never only in OpenSEO: the facts in `core/` as they already live there; `decisions/YYYY-MM-DD-seo-context.md` for what was agreed with the owner (goal, exclusions, claims rules, spend ceiling), with the date and who confirmed it; `research/` for any paid setup run, with source, date, market, actual or unknown cost, coverage and uncertainty. If OpenSEO is lost, the context is rebuilt from these. No secrets, no raw exports.

## App business vs store business
App business:
- Describe audiences by the job they hire the app for. List platforms (iOS, Android, web), the store listing, and which web pages must rank.
- Brand name variants and misspellings. The app name will dominate brand queries; list it as a brand term.
- Exclusions: rival app names, and any claim about privacy, security, speed, savings or health beyond the published policy.
- Say what the site is for: installs, support or docs.

Small store:
- List collections and price bands, materials and sourcing claims that can be proved, and what must never be said (investment value, unproved sourcing, "hypoallergenic" without proof).
- Shipping, returns, sizing and custom-work lead time as exact facts.
- Showroom facts exactly as on the door and the profile: address, appointment-only or not, hours. One source of truth.
- Seasonal peaks, and which stable URLs serve them each year.

## Sources
- OpenSEO: `plugins/openseo/skills/seo-project-setup/SKILL.md`; `src/server/mcp/tools/project-context.ts:43-50,92-99`; `src/server/mcp/tools/project-website.ts:20,62`; `src/server/billing/researchSpend.ts:31,48-85`; `src/server/features/project-context/services/ProjectContextService.ts:17-18,84`; `src/types/schemas/projectContext.ts:7-31,78-109`; `docs/SELF_HOSTING_CLOUDFLARE_OPERATIONS.md`.
- Google Search Central, spam policies (scaled content), updated 28 Aug 2026: https://developers.google.com/search/docs/essentials/spam-policies
- OWASP, prompt injection, accessed 9 Nov 2026: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- Simon Willison, the lethal trifecta for AI agents, 16 Jun 2025: https://simonwillison.net/2025/jun/16/the-lethal-trifecta/
