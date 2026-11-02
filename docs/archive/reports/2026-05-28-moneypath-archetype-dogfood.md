# MoneyPath Archetype Dogfood - 2026-05-28

Issue: #532

Release train: #781

This dogfood pass tested the current Main Branch source against three
sanitized synthetic business repos. The fixtures were created in temporary
directories with `mb onboard`, then populated with public-safe archetype
content. No private customer data, raw strategy, provider exports, transcripts,
or financial records were used.

Commands run for each archetype:

```bash
python -m mb validate <repo> --json
python -m mb status <repo> --json --peek
python -m mb start --repo <repo> --json
```

`mb start --json` was used as runtime/repo-boundary evidence. The business
recommendation notes below are reviewer interpretations of the deterministic
`mb status --json --peek` facts, not a claim that a live Claude or Codex
runtime completed the full `/mb-start` conversation.

## Summary

MoneyPath identified useful bottlenecks in all three archetypes. The strongest
release signal is that MoneyPath and lifecycle facts now produce concrete
routes instead of generic advice:

- solo founder: missing proof, missing financial appetite thresholds, overdue
  bet, and missing exit criteria;
- agency/service: good proof exists, but customer-progress language, audience
  specificity, channel strategy, and repeatable push/playbook shape still need
  work;
- product/SaaS: product exists and a bet is active, but proof quality,
  customer-progress language, CTA path, and private books anchoring are still
  the bottlenecks.

The main calibration note is that `mb status` still leads with onboarding or
repo-operation items when those are present. That is correct for safety, but it
can obscure MoneyPath in already-shaped test repos. This should stay as a
calibration follow-up rather than being changed inside the dogfood report.

## Archetype 1: Solo Founder / Creator

Shape tested: strong ideas, draft offer, thin proof, unclear CTA, no product
ladder, and one overdue active bet.

Validation: pass.

MoneyPath levels:

| Object | Level |
| --- | ---: |
| customer_progress | 1 |
| offer | 2 |
| audience | 1 |
| proof | 0 |
| product_ladder | 1 |
| cta_path | 1 |
| channel_strategy | 0 |
| active_push | 0 |
| playbook | 0 |
| page_readiness | 0 |
| outcome_feedback_loop | 0 |

Overall MoneyPath level: 1.

Top status actions:

1. `resume_onboarding` - finish required onboarding inputs.
2. `update_overdue_bets` - close or update one overdue active bet.
3. `review_file_contract_offer` - offer does not point to proof or outcome
   evidence.

Top MoneyPath actions:

1. `declare-appetite-thresholds` -> `/mb-think`
2. `repair-books-exposure` -> `mb books doctor --plan --json`
3. `define-customer-progress` -> `/mb-think`
4. `define-audience-progress` -> `/mb-think`
5. `attach-proof` -> `/mb-think`

Bet facts:

- active bets: 1
- overdue bets: 1
- missing exit criteria: 1

Recommendation interpretation: correct. The status facts show that this
business is not ready for ads/site/output acceleration yet. It should first
clarify the money appetite for active bets, update the overdue bet, attach
proof, and make the customer-progress language more concrete.

False positives: none serious. Appetite thresholds ranking first is defensible
because there is an active MoneyPath bet, but a human owner might expect the
overdue bet itself to be the first business answer.

False negatives: the missing bet exit criteria showed up in `brain.bets.*`, but
the owner-facing ranked action emphasized overdue status more than the missing
exit rubric. That is acceptable for this release, but worth watching.

## Archetype 2: Agency / Service Business

Shape tested: service business with testimonials and typicality, a reasonably
clear offer, an initial push, but weak product/package ladder and channel
strategy.

Validation: pass.

MoneyPath levels:

| Object | Level |
| --- | ---: |
| customer_progress | 1 |
| offer | 3 |
| audience | 1 |
| proof | 4 |
| product_ladder | 1 |
| cta_path | 2 |
| channel_strategy | 0 |
| active_push | 0 |
| playbook | 0 |
| page_readiness | 0 |
| outcome_feedback_loop | 0 |

Overall MoneyPath level: 1.

Top status actions:

1. `resume_onboarding` - finish required onboarding inputs.
2. `repair_github_context` - no GitHub origin remote.
3. `review_money_path_customer_progress` - customer progress exists as loose
   audience or research text.

Top MoneyPath actions:

1. `define-customer-progress` -> `/mb-think`
2. `define-audience-progress` -> `/mb-think`
3. `strengthen-proof-quality` -> `/mb-think`
4. `connect-channel-strategy` -> `/mb-think`
5. `open-or-select-push` -> `/mb-start`

Recommendation interpretation: mostly correct. The status facts did not
over-score the business just because testimonials existed. They correctly kept
the overall level low because the customer-progress, audience, channel,
playbook, and feedback loop are not yet connected.

False positives: `strengthen-proof-quality` still appears even when proof is
level 4. That is directionally useful, but it may be too prominent relative to
packaging/channel gaps for an agency with good-enough proof.

False negatives: repeatable offer packaging is represented indirectly through
product ladder and customer-progress gaps. A future service-business contract
could make package tiers, fit-call CTA, and repeatable delivery shape more
explicit.

## Archetype 3: Product / SaaS Or Open-Source + Paid Tier

Shape tested: product exists, free core plus possible paid support tier, weak
proof, one active pricing/support bet, declared appetite thresholds, no
connected push.

Validation: pass.

MoneyPath levels:

| Object | Level |
| --- | ---: |
| customer_progress | 1 |
| offer | 3 |
| audience | 1 |
| proof | 2 |
| product_ladder | 1 |
| cta_path | 1 |
| channel_strategy | 0 |
| active_push | 0 |
| playbook | 0 |
| page_readiness | 0 |
| outcome_feedback_loop | 0 |

Overall MoneyPath level: 1.

Top status actions:

1. `resume_onboarding` - finish required onboarding inputs.
2. `review_relationship_health` - one active bet needs a linked push.
3. `repair_github_context` - no GitHub origin remote.

Top MoneyPath actions:

1. `repair-books-exposure` -> `mb books doctor --plan --json`
2. `define-customer-progress` -> `/mb-think`
3. `define-audience-progress` -> `/mb-think`
4. `strengthen-proof-quality` -> `/mb-think`
5. `define-cta-path` -> `/mb-think`

Bet facts:

- active bets: 1
- overdue bets: 0
- missing exit criteria: 0
- triggered failure signals: 0
- triggered double-down signals: 0

Recommendation interpretation: correct. The active paid-tier bet is visible,
its exit criteria are preserved, and relationship health correctly notices that
the bet has no linked push. The system also avoids treating a product with
generic interest as proof that a paid tier is ready.

False positives: `repair-books-exposure` is expected because the synthetic repo
declared thresholds but did not include a private ledger anchor. In a product
planning conversation this could feel too operational if the operator is only
exploring pricing, but it is correct once a MoneyPath bet is declared.

False negatives: none blocking. A future product-specific contract could
distinguish "free core exists" from "paid ladder is saleable."

## Cross-Archetype Findings

What worked:

- MoneyPath resisted false confidence. All three archetypes stayed at overall
  level 1 even when they had offers, proof, or a product.
- Proof quality is more nuanced than simple existence. Generic or unlinked
  proof did not become a green light for ads or site work.
- Bet facts are now useful enough for release dogfood: active, overdue, missing
  exit criteria, and pending rubric signals are visible without reading raw
  files.
- Route suggestions mostly land on current supported routes: `/mb-think`,
  `/mb-start`, `/mb-bet update`, and safe read-only doctor commands.

What needs follow-up:

- Onboarding and repo-operation actions can dominate the top ranked action even
  in repos that have enough structure for MoneyPath guidance. This is safe, but
  the owner-facing answer should make the MoneyPath bottleneck easy to see when
  the operator asks "what makes money next?"
- Service businesses need a sharper way to represent repeatable packages, fit
  calls, and delivery shape. Today that spreads across offer, product ladder,
  CTA path, push, and playbook.
- Product/SaaS businesses need a sharper distinction between product existence,
  proof of customer progress, and a saleable paid ladder.
- Proof-level-4 agency repos may still get `strengthen-proof-quality` before
  more urgent packaging/channel moves. This may be correct for public marketing
  readiness, but should be calibrated after more real dogfood.

## Recommended Follow-Ups

Do not block the current release on these.

1. Calibrate owner-facing routing so a path-to-money question can surface the
   top MoneyPath bottleneck alongside, not underneath, safe onboarding or repo
   hygiene. Tracked in #785.
2. Add a service-package contract or guidance slice after the shared workflow
   migration work lands for ads/site/organic.
3. Add a product/SaaS paid-ladder calibration note after more real product
   repos are tested.
4. Watch whether `repair-books-exposure` is too eager for exploratory bets that
   have not yet committed spend. Tracked in #785.

## Release Call

The release train is ready to proceed from the MoneyPath perspective. The
current model is conservative, fact-grounded, and useful enough to dogfood:
it does not overclaim readiness, it surfaces concrete next routes, and it keeps
private data out of committed evidence.
