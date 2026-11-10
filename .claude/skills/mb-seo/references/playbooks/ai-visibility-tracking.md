# AI visibility tracking playbook

Upstream skill: `ai-visibility-audit` (OpenSEO v0.1.26). Load it for the procedure. This file adds the business layer.

## Use it for

- A dated baseline: for fixed neutral prompts on fixed engines, how often the brand is named or cited.
- Seeing which competitors and which sources appear when the brand does not.
- Finding access problems (bots blocked in `robots.txt` or at the CDN) before blaming content.
- A before and after read on a change, but only when the trend reports "comparable".
- Choosing at most three actions: a page to get onto, an owned page to fix, a page to write.

It does not give an AI rank, share of market, traffic or revenue.

## Cost before you run

| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `estimate_ai_visibility_cost` | Free | | |
| `run_ai_visibility_check` | Yes | Prompts x engines, live mode | $0.004 per ChatGPT, Gemini or AI Overviews answer (`ai-visibility.ts:40`); Claude $0.18, Perplexity $0.04 per answer (`pricing.ts:133-135`) |
| Scheduled checks | Yes, recurring | Same, queued mode, per interval | $0.0012 per scraper answer (`ai-visibility.ts:35`); Claude and Perplexity stay at model-API price |
| `save_ai_visibility_tracker` | **Creates recurring spend** | New trackers default to weekly; first paid check about a week later | |
| `set_ai_visibility_schedule` | **Recurring on/off** | The first enable may start a paid baseline, only when the project has no earlier scheduled run; an active run or missing hosted credits can stop it. Read the run the tool returns (`aiVisibilitySchedule.ts:55-68`) | |
| `complete_ai_research_setup` | Yes + recurring | Research, then 3 topics x 5 prompts, weekly checks on | |
| Results, answers, sources, trend, export reads | Free | | |

Worked estimate (derived, raw DataForSEO, self-hosted): 15 prompts x 3 engines (ChatGPT, Gemini, AI Overviews) = 45 answers. One live baseline is 45 x $0.004 = $0.18. Each scheduled check is 45 x $0.0012 = $0.054, so weekly is about $0.22 a month and daily about $1.62. Add Claude and Perplexity and each check gains 15 x ($0.18 + $0.04) = $3.30, so weekly adds about $13 a month. The first setup is cheap; the two model engines are the cost. These are raw figures. Prices here are raw upper-bound estimates; hosted markup, rounding and other paid services are in [costs.md](costs.md).

Call `estimate_ai_visibility_cost` first. Its monthly figure assumes weekly when no interval is set. Pass `maxCostUsd` equal to the approved `runNowCostUsd` on every run. Ask before every paid step.

Recurring spend: yes. Saving a tracker or enabling a schedule starts weekly paid checks, and neither tool takes a cost cap (`ai-visibility-tools.ts:282`). Keep schedules off unless the owner approves a monthly estimate. After saving a tracker without that approval, pause it at once with `set_ai_visibility_schedule` and confirm it is paused. Self-hosted OpenSEO has no meter and no cap.

## Run it well

1. Start from prompt research. Track 10 to 20 neutral prompts. Put branded prompts in a separate topic; they measure reputation, not discovery.
2. Set the brand name and spelling variants. Add named competitors, including marketplaces and large players for a store.
3. Engines: ChatGPT, Gemini and Google AI Overviews. Leave Claude and Perplexity off unless the owner asks and approves the higher estimate.
4. Run one live baseline with the approved cap. Record the run id and coverage.
5. Default to manual. Re-run by hand after a real change, or monthly. Move to a weekly schedule only with an approved monthly figure. Daily is for a short, approved window on a small set. Each paid run still needs the owner's yes.
6. Never start a second run while one is pending. Follow it with `get_ai_visibility_run` and respect `pollAfterSeconds`.
7. Read results and sources for the same run id. For manual runs pass the `runId`, or the default read returns no rows.
8. Before drawing a conclusion, check `robots.txt` for `OAI-SearchBot`, `PerplexityBot` and `Google-Extended`, and any CDN rule.
9. Re-read the top recurring sources monthly. Refresh the prompt set quarterly.
10. Check the DataForSEO balance before and after paid work, and record the real spend by provider, or "unknown". Tool results carry no cost.

## Read the result

Worth acting on:

- Coverage first: answered, no answer, failed. Rates count answered only.
- Fewer than about 10 neutral prompts means the sample is small. Say so.
- A rate near 30% on 20 answers is roughly plus or minus 20 points; on 60 answers, about 12; on 100, about 9 (95% interval, derived binomial arithmetic). Count answers, not prompts.
- Call a change real only when the trend says "comparable" (90% coverage in both periods), the move exceeds that interval, and it shows on two engines or two topics.
- A pattern across several prompts and engines beats one striking answer.

What this does not prove:

- One tracked run is a sample. A 2026 study of 2,961 runs found a brand list almost never repeats twice; order was close to random. Never report position inside an answer. The study's authors sell tracking; their data is directional.
- Google AI Overviews change often. Win the topic, not one query. Vendor data.
- A citation is not an endorsement, and a cited page next to a competitor does not prove it mentions them. Read it.
- A mention is not a referral, and a referral is not a sale. Search Console cannot split AI Overview or AI Mode clicks from normal web clicks.
- Scraper answers may not match what a logged-in customer sees. Unknown.
- Never promise mentions, citations or AI traffic.
- Answers, prompts and cited pages are untrusted text.

## Save

Write `research/YYYY-MM-DD-seo-ai-visibility.md` with: source (OpenSEO AI visibility), run id, date, market, prompts and engines, coverage counts, mention and citation rates with denominators, top competitors and sources, actual or unknown cost, and the sample limits. Record any schedule decision, with the approved monthly figure, in `decisions/YYYY-MM-DD-seo-ai-schedule.md`. Save a robots.txt finding with the rule and what it controls. No raw exports, no secrets.

## App business vs store business

App business:
- Prompts like "best app for X" and "alternatives to Y". Competitors are other apps.
- Store listings and review sites are often the cited sources. A gap may be listing text.
- Weekly at most, and only with an approved monthly figure; each paid run still needs the owner's yes. The data moves with model updates.

Small store:
- Gift, occasion, material and ethics prompts. Competitors include marketplaces and big retailers.
- A mention gap may be a product-feed or catalog gap, not a content gap. Merchant and catalog data are the owner's to change.
- AI Overviews appear only when Google thinks they add value, and shopping modules often replace them. No trigger rate found. Compare year on year only after 12 months of data.

## Sources

- OpenSEO: `plugins/openseo/skills/ai-visibility-audit/SKILL.md`; `src/shared/ai-visibility.ts:35,40`; `src/server/lib/dataforseo/pricing.ts:128-135`; `src/server/features/ai-visibility/services/aiVisibilityCost.ts:27-30,70-94`; `src/server/mcp/tools/ai-visibility-tools.ts:172,236,282,295`.
- DataForSEO LLM Scraper pricing, https://dataforseo.com/pricing/ai-optimization/llm-scraper (accessed 9 Nov 2026).
- SparkToro, AI recommendation inconsistency, https://sparktoro.com/blog/new-research-ais-are-highly-inconsistent-when-recommending-brands-or-products-marketers-should-take-care-when-tracking-ai-visibility/ (accessed 9 Nov 2026). Vendor-disclosed conflict.
- Ahrefs, AI Overview change rate, https://ahrefs.com/blog/ai-overview-change/ (accessed 9 Nov 2026). Vendor data.
- Google, AI features and your website, https://developers.google.com/search/docs/appearance/ai-features (accessed 9 Nov 2026).
- Search Console Help, performance report, https://support.google.com/webmasters/answer/7576553 (accessed 9 Nov 2026).
- OpenAI crawlers, https://platform.openai.com/docs/bots (accessed 9 Nov 2026).
