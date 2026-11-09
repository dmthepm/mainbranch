# How prices work in these playbooks

Read this once. The other playbooks point here instead of repeating it. Source: OpenSEO v0.1.26 at 7d89cfb.

## Raw price, hosted credits, and self-hosted
- A "raw" price is OpenSEO's estimate of what the provider charges for the call. Most worked estimates in these playbooks are raw.
- Hosted OpenSEO charges credits, not dollars. For each metered call it adds a 1.28 markup, then rounds up to a whole credit (`src/shared/billing.ts:72,167-180`). A small call therefore costs more than raw x 1.28. Rounding is per call, so ten small calls round ten times.
- Self-hosted OpenSEO has no meter, no credits and no cap. You pay your providers' raw prices directly.
- The two estimator tools differ on a self-hosted copy:
  - `estimate_rank_tracker_cost` always applies the hosted markup (`src/shared/rank-tracking.ts:97-115`; `src/server/mcp/tools/estimate-rank-tracker-cost.ts:80`). It returns two figures: a dollar estimate (marked up, rounded as dollars) and a credit figure (marked up, then each call rounded up to a whole credit). Its dollars run above the raw worked estimates here. Do not multiply them by 1.28 again.
  - `estimate_ai_visibility_cost` checks the hosting mode. Self-hosted, it returns raw provider dollars and zero credits, and says so in its warning (`src/server/features/ai-visibility/services/aiVisibilityCost.ts:48-54,72-74,90-94`).
  - Either way, show the owner three things apart: the raw estimate, the tool's figure, and what the provider actually billed.

## Source prices are estimates, not bills
- The constants in `src/server/lib/dataforseo/pricing.ts` are raw provider-cost estimates. OpenSEO calibrates them so a reservation is usually enough (`pricing.ts:66-77`), but actual charges can differ either way. They are not measured bills.
- Example: Lighthouse is estimated at $0.005 a call, and the file notes a billed fixture of $0.00425 (`pricing.ts:112-113`).
- Some constants are padded on purpose (model answers, `pricing.ts:122-139`). Treat every figure as an estimate, and label worked estimates "derived".

## Market and provider change the price
- Keyword research and keyword metrics use DataForSEO Labs in countries Labs supports, and Google Ads tasks elsewhere (`src/shared/keyword-locations.ts:860`; `src/server/features/keywords/services/research/research-data.ts:104-117`; `src/server/lib/dataforseo/keyword-metrics.ts:133-147`). The two have different price shapes. Say which market and provider a worked estimate assumes.

## DataForSEO is not the only paid service
Other paid services, none of which show in a DataForSEO balance:
- OpenRouter: language-model calls for website research, prompt relevance checks and prompt generation (`src/server/billing/researchSpend.ts:48-85`). The model and price are not fixed in source.
- Cloudflare Browser Run, for rendered audits (`src/shared/audit-rendering.ts:6-14`).
- Context.dev, the rendering fallback (`src/shared/audit-rendering.ts:14`).
- Google Maps tiles for the local map screen, billed by Google (`docs/GOOGLE_MAPS_SETUP.md`).

So the DataForSEO balance alone cannot measure total spend. Record actual cost by provider. If a provider's bill is not available, write "unknown" for it. A zero DataForSEO change does not show the other services cost zero.

## How to quote a price
1. State the market and provider, the raw arithmetic, and the label "derived".
2. Name any recurring spend and wait for the owner's yes before each paid run.
3. After the run, record the estimate and the actual by provider, or "unknown".
