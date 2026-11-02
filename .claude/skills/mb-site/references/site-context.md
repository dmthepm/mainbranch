# Site Context

Load this when `/mb-site` needs prerequisites, active offer resolution, required business context, or section mapping. Use the shared primitive reference at `.claude/reference/business-primitives/offer-bet-push-proof.md` for offer/bet/push/proof routing.

## Prerequisites

Deploy target is Cloudflare Pages.

| Tool | Required for | Install |
|---|---|---|
| Cloudflare account | All site shapes by default | https://dash.cloudflare.com |
| `gh` CLI authenticated | Repo creation | `brew install gh` then `gh auth login` |
| Cloudflare API token, account ID, GitHub App install | Domain/DNS/Pages flow | `mb connect cloudflare --token-stdin --metadata token_type=account --metadata account_id=...`, then [`cloudflare-pages-link.md`](cloudflare-pages-link.md) |
| `offer.md` and `audience.md` | Site generation | Build via `/mb-think` first if missing |
| Node 18+ and pnpm | Website shape with an Astro or similar build step | `brew install node && npm install -g pnpm` |

Hard-gate Cloudflare-dependent work with:

```bash
mb connect doctor --json
```

If `provider:cloudflare` is not `ready`, do not run domain buy, DNS, Pages,
custom-domain, or deploy tools. Offer the operator: connect now with
`printf '%s' "$CLOUDFLARE_API_TOKEN" | mb connect cloudflare --token-stdin --metadata token_type=account --metadata account_id=... && mb connect test cloudflare`;
continue read-only for availability checks, naming, brief, and research only;
or skip for now and record the blocker. User API tokens remain supported by
omitting `token_type=account`, but account-scoped tokens are preferred for
multi-business operators.

`verify_live.py` remains a deeper manual smoke after `mb connect` says
Cloudflare is ready. Expect Cloudflare scopes, zone lookup, and domain-check CLI
to pass. Porkbun skipped is fine for the Cloudflare-registered path.

## Active Offer Resolution

Before loading business context, resolve the active offer:

1. If a future `mb` JSON field exposes active offer state, use it.
2. Do not treat `.vip/local.yaml` as the source of truth for active-offer
   state. If legacy state exists, confirm the offer with the user instead of
   silently routing.
3. If an offer is selected and `core/offers/[offer]/offer.md` exists, load it as the active offer.
4. If no offer is selected and `core/offers/` exists, ask which offer this site is for.
5. If no `core/offers/` folder exists, use `core/offer.md` for a single-offer repo.

Follow the shared active-offer contract in
`.claude/reference/business-primitives/offer-bet-push-proof.md`.

Always-core files, never per-offer: `soul.md`, `voice.md`, `content-strategy.md`.
Use `core/marketing/...` and `core/people/...` as optional content strategy
layers when a site, blog, wiki, changelog, or launch page needs channel,
account, distribution, or founder/person voice context.

Offer-aware files, check `core/offers/` first and fall back to `core/`: `offer.md`, `audience.md`.

Accumulate proof: company-wide proof comes from `core/proof/testimonials.md`,
`core/proof/typicality.md`, and `core/proof/angles/`; offer-specific proof
comes from matching files under `core/offers/[active]/proof/`. Older offer
testimonial files can be read as compatibility context.
Before using proof in page claims, read `money_path.objects.proof.quality` from
`mb status --json --peek`. Use it to distinguish generic proof, specific
outcomes, offer-linked proof, typicality-aware proof, and outcome-backed proof.
These are factual page-support signals, not conversion or persuasion scores.
If `quality.public_marketing.status` is `blocked`, do not use those
testimonials in public page copy. Route to permission collection first, or use
the proof only as internal strategy if the operator explicitly reframes the
work that way.

## Required Business Context

| File | Path | Required |
|---|---|---|
| Offer | `core/offers/[active]/offer.md` or `core/offer.md` | Yes |
| Audience | `core/offers/[active]/audience.md` or `core/audience.md` | Yes |
| Voice | `core/voice.md` | Recommended |
| Soul | `core/soul.md` | Optional |
| Testimonials | `core/proof/testimonials.md` plus offer-specific proof and `money_path.objects.proof.quality` | Recommended |
| Angles | `core/proof/angles/*.md` | Optional |
| Content Strategy | `core/content-strategy.md` plus relevant `core/marketing/...` / `core/people/...` layers | Optional |
| Skool Surfaces | `core/operations/funnel/skool-surfaces.md` | Optional for congruence |

Legacy `reference/*` paths are compatibility fallback only. Do not write new evergreen business truth there.

If required files are missing, stop and route to `/mb-think codify`:

> "Your offer.md is missing. I need it to generate the site. Run `/mb-think` to build your core business files first."

## Reference-To-Section Mapping

How business context flows into a generated site:

| Business context | Produces |
|---|---|
| Resolved `offer.md` | Hero headline/subhead, value prop, pricing, CTA copy |
| Resolved `audience.md` | Pain sections, objection handling, copy language/tone |
| `voice.md` | Palette, font selection, aesthetic mood, copy tone |
| `soul.md` | About/mission section, founder story, credibility badge |
| `core/proof/testimonials.md` | Social proof, stat counters, trust badges |
| `core/proof/angles/*.md` | Page structure and section order |
| `core/content-strategy.md` | CTA destinations and newsletter/signup integration |

Detail per shape:

- Minisite: [`minisite-generation-system.md`](minisite-generation-system.md) and [`anti-patterns.md`](anti-patterns.md).
- Website: [`website-build.md`](website-build.md).

If the resolved offer cannot clearly answer audience, problem/outcome,
transformation, mechanism, proof, price/value logic, risk reversal, objections,
reason to act, and next step, load
`.claude/reference/conversion/offer-sharpening.md` and route to `/mb-think`
before treating the site as conversion-ready.

## Pipeline Position

The site is infrastructure, not recurring content. It is the destination the content pipeline drives traffic to.

```text
/mb-think -> core business files
     |
/mb-site -> site conversion endpoint
     |
/mb-ads, /mb-organic, email/newsletter content -> traffic to site
```

When core business files change significantly, such as new offer or pricing, consider re-running build:

> "Your offer.md was updated since the site was last published. Want to run `/mb-site build` to update?"
