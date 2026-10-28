---
type: decision
date: 2026-05-06
status: accepted
topic: Business repo folder model and reference deprecation
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/318
linked_decisions:
  - decisions/2026-04-29-mb-vip-v0-1-0-master.md
---

# Business Repo Folder Model And Reference Deprecation

Committed Main Branch business repos should not use `reference/` as a
canonical folder.

The canonical business brain is `core/`. The `reference/` name survives only as
a legacy compatibility surface for old repos and old readers during migration.
New scaffolds, docs, and skills should teach users to read and write evergreen
business truth under `core/...`.

## Decision

Use this committed business repo shape:

```text
core/
  soul.md
  offer.md
  audience.md
  voice.md
  content-strategy.md
  product-ladder.md
  offers/
  proof/
  brand/
  strategy/
  operations/
  finance/

research/
decisions/
bets/
pushes/
log/
documents/
```

`core/` is deliberately broad. It holds evergreen business truth: the offer,
audience, voice, proof, brand, strategy, operations, and finance boundaries
that skills need to read. Keeping this under one obvious folder is better than
introducing a new `brain/` top-level folder or preserving `reference/` as a
second source of truth.

This decision supersedes only the business-repo folder and path claims from
the 2026-04-29 v0.1.0 master decision. It does not supersede that decision's
vocabulary, packaging, PyPI, dial, archetype, or OSS/paid mechanism choices.

## Path Map

Legacy business-repo paths map to the current model this way:

| Legacy path | Canonical path |
| --- | --- |
| `reference/core/*` | `core/*` |
| `reference/offers/*` | `core/offers/*` |
| `reference/proof/*` | `core/proof/*` |
| `reference/brand/*` | `core/brand/*` |
| `reference/strategy/*` | `core/strategy/*` |
| `reference/visual-identity/*` | `core/brand/*` |
| `reference/domain/content-strategy.md` | `core/content-strategy.md` |
| `reference/domain/product-ladder.md` | `core/product-ladder.md` |
| `reference/domain/classroom/*` | `core/operations/classroom/*` |
| `reference/domain/membership/*` | `core/operations/membership/*` |
| `reference/domain/funnel/*` | `core/operations/funnel/*` |

If a legacy `reference/domain/*` file is tied to one offer rather than the
business as a whole, move it under `core/offers/<offer>/...` during manual
review. Automated migration can safely move general operating context under
`core/operations/`; offer-specific promotion remains a human/agent judgment.

`outputs/` is also legacy product language for generated work. Current
coordinated production artifacts should live under `pushes/` when they belong
to a named push, or under a more specific durable folder when another surface
owns the artifact. Old `outputs/` content should be read as historical work,
not as the default write target for new skills. Legacy `campaigns/` records
remain compatibility reads under the later push primitive decision.

## Compatibility

Legacy repos remain readable:

- Skills may read `reference/*` only as a fallback for old repos.
- Migration may leave compatibility bridges such as `reference/core` and
  `reference/offers` when they point back to canonical `core/` folders.
- Compatibility bridges are not duplicate source files and should not be edited
  directly.
- New evergreen writes go to canonical `core/...` paths only.

Do not auto-delete user-authored `reference/` content. Move it through
`mb migrate`, a doctor repair plan, or explicit manual review so users can see
what changed.

## Consequences

Fresh `mb init` / `mb onboard` repos no longer create real
`reference/proof`, `reference/domain`, or `reference/visual-identity` folders.

Skill and doc validation should warn on active business-repo `reference/*`
guidance unless the surrounding text makes the legacy fallback explicit.

Older decisions and architecture notes that made `reference/`, `domain/`, or
`outputs/` canonical are superseded by this decision. Historical docs may keep
those terms only when they are clearly labeled as legacy context.
