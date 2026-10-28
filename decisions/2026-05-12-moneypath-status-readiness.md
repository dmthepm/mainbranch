---
type: decision
date: 2026-05-12
status: accepted
topic: MoneyPath status readiness model
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/528
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-06-push-primitive-and-operator-vocabulary.md
  - decisions/2026-05-11-connecting-notes-data-and-history.md
  - decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md
linked_docs:
  - docs/offer-sharpening.md
  - docs/operator-loops.md
  - docs/system-architecture.md
tags: [v0-3, status, moneypath, offers, pushes, readiness]
---

# MoneyPath Status Readiness Model

## Decision

Main Branch adds **MoneyPath** as a read-only `mb status` readiness model over
existing business primitives. It answers whether the repo has a connected path
from customer progress to offer, proof, CTA, channel, push, playbook, outcome,
and durable learning.

MoneyPath is not a new business primitive and does not replace product ladder,
offer files, pushes, playbooks, proof, decisions, or outcomes. It is an
additive status view that helps skills and future dashboards read the path
between those files.

## Boundary

The CLI reports legibility, support, connection, and instrumentation from
observable repo facts. Skills and the operator own strategic judgment.

Good CLI language:

- "Offer is structured but has no linked proof or CTA path."
- "Active push exists, but no outcome feedback link was found."

Bad CLI language:

- "This offer is good."
- "This will convert."
- "This launch is ready to win."

## JSON Contract

`mb status --json --peek` emits an additive top-level `money_path` object:

```json
{
  "money_path": {
    "schema_version": "1.0",
    "overall_level": 2,
    "overall_label": "structured",
    "objects": {
      "offer": {
        "level": 2,
        "label": "structured",
        "status": "structured",
        "summary": "Offer has several expected guardrail signals.",
        "paths": ["core/offer.md"],
        "missing": ["proof", "next_step"],
        "evidence": [],
        "references": ["docs/offer-sharpening.md"],
        "recommended_route": "/mb-think",
        "safe_to_share": true
      }
    },
    "ranked_actions": []
  }
}
```

Every component uses the same object contract where possible: `level`, `label`,
`status`, `summary`, `paths`, `missing`, `evidence`, `references`,
`recommended_route`, and `safe_to_share`. Components may add specific nested
facts, such as an offer `guardrails` block, when the CLI can support them
deterministically.

## Components

V1 reads:

- `offer` from `core/offer.md` and `core/offers/<slug>/offer.md`;
- `audience` from `core/audience.md` and per-offer audience files;
- `proof` from `core/proof/` and offer-specific proof folders;
- `product_ladder` from `core/product-ladder.md`;
- `cta_path` from next-step text, playbook resources, and conversion facts;
- `channel_strategy` from content strategy and push channels;
- `active_push` from `pushes/<slug>/push.md`;
- `playbook` from `pushes/<push>/playbooks/*.md`;
- `page_readiness` from declared `mb site check` readiness facts;
- `outcome_feedback_loop` from typed outcome relationships.

Product ladder is a component, not MoneyPath itself. In single-offer repos it
is optional until offer relationships matter. In multi-offer repos it should
explain entry, ascension, retention, cross-sell, upgrade, or offer-family
logic.

## Scoring

MoneyPath uses the existing issue's 0-5 scale, but scores are gated rather than
averaged:

- `0 missing`: no file, section, relationship, or linked object exists.
- `1 stated`: a claim or object exists as loose text.
- `2 structured`: expected fields, sections, or frontmatter are present.
- `3 evidence_backed`: proof, examples, research, testimonials, typicality,
  decision records, or source-backed notes support the object.
- `4 field_tested`: real-world signals, push outcomes, sales/customer language,
  conversion notes, or reviewed run records are tied to the object.
- `5 instrumented`: offer, proof, CTA/page, channel, push/playbook, metric or
  measurement, and outcome feedback form a connected loop.

A repo cannot reach a high overall level by averaging rich files with missing
links. Missing offer caps the path at 0. Missing audience or unstructured
offer/audience caps it at 1. Missing proof or CTA caps it at 2. Missing
channel, push, or playbook caps it at 3. Missing outcome feedback caps it at 4.
Level 5 requires declared measurement/readiness and outcome feedback.

## Consequences

- `/mb-start`, `/mb-status`, generated Claude Code guidance, and generated
  Codex guidance should read `money_path` facts before falling back to ad hoc
  file checks.
- Top-level `ranked_actions` may incorporate the top MoneyPath recommendation,
  but required updates, broken runtime wiring, validation debt, relationship
  health, and playbook health stay higher priority.
- Multiple live per-offer files with no active-offer status fact are an
  ambiguity. Status should not silently choose one.
- V1 declared readiness is enough. Main Branch reports what is connected and
  instrumented; it does not infer market strength or conversion quality.

## Non-Goals

- No `mb money` command yet.
- No provider mutation, publishing, spend decisions, customer contact, or
  automated edits.
- No universal funnel requirement.
- No claim that every business should use the same channel, CTA, product
  ladder, or proof style.
