---
type: decision
date: 2026-05-11
status: accepted
topic: First registry shape for portable business data sources
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/470
linked_decisions:
  - decisions/2026-05-11-connecting-notes-data-and-history.md
  - decisions/2026-05-09-obsidian-first-class-viewer.md
linked_docs:
  - docs/data-source-registry.md
  - docs/business-connections.md
tags: [docs, data, graph]
---

# Data-source registry for portable business metrics

## Decision

A data-source record is a small markdown file with frontmatter at
`data/<provider>/source.md`. It is the readable handle Main Branch trusts
when decisions, pushes, playbooks, outcomes, bets, research, and reports
reference structured data such as Google Ads, Stripe, email, CRM, or
analytics.

- `type: data_source` is the official primitive marker.
- `provider`, `owner`, and `privacy` are required. `cadence`, `freshness`,
  `storage`, `reports`, `useful_queries`, and `tags` are advisory.
- `linked_data_sources` is the typed frontmatter field other records use to
  reference a registry entry.
- `mb validate` recognizes the schema, checks enum and date shape, rejects
  secret-shaped frontmatter, and warns when the provider id does not match
  the folder name. `mb graph` emits `linked_data_sources` edges and exposes
  the relationship in the registry payload. `mb suggest links` continues to
  rank the record as `link_report_or_data_metadata` and carries
  `field: linked_data_sources` so agents know the typed option exists.
- Obsidian, GitHub, and other markdown viewers can browse the record and
  the linked reports. They are not the data store.

## Why

`docs/business-connections.md` already says decisions, pushes, playbooks,
and outcomes should usually link reports or data metadata, not giant raw
files. Without an official record shape, every mention is a fresh guess
about where the numbers live, what they mean, who owns them, and how fresh
they are. A small contract makes those mentions inspectable.

The contract intentionally stays small. SQLite is the default for ongoing
local data because it is portable, queryable, and inspectable. CSV is the
default for snapshots. The numbers stay in those structured files; markdown
stays the meaning.

The shape is portable and runtime-agnostic. The records are files in the
repo, so they travel with Git regardless of host (local-only, personal
GitHub, a free GitHub org, or a self-hosted Git server). The schema is a
mechanical check, so `mb validate` runs it locally today and the same
`scripts/check.sh` rule can run in CI when a repo opts into pre-merge
automation. Agents read the validation output and explain mechanical fixes
versus operator judgment; they do not own the rule.

## Future-safe framing

`type: data_source` is the **first** record type in the registry, not the
whole registry forever. Sibling record types are plausible later:

- `provider_config` for facts like GitHub org base permission, repo-creation
  policy, or team membership;
- `secret_handle` for non-secret pointers into a keychain or vault;
- `integration_account` for the named account or workspace an integration
  is wired to.

For this slice the contract stays narrow: `storage`, `useful_queries`, and
SQL-flavored examples apply to data-source records, not every future
registry record. Privacy is the read-side visibility axis; mutation /
blast-radius questions (for example, `mutation_risk`, `approval_required`)
are deliberately deferred to whichever record type first needs them.

Cross-link field naming for sibling record types
(`linked_provider_configs`, `linked_integration_accounts`, or a generic
`linked_records`) is intentionally left open. Decide it the first time a
sibling record ships.

## Out of scope

- Scheduled provider sync (`MAIN-315`).
- Provider mutation and Google Ads automation (`MAIN-229`).
- A `mb doctor` stale-data-record check. Add it as a follow-up once the
  contract has been in use.
- `mb onboard` scaffolding of `data/`. The stub at
  `mb/mb/_data/stubs/data-source.md` can be copied on request; first-run
  flow does not change in this slice.
- Sibling registry record types (`provider_config`, `secret_handle`,
  `integration_account`) and the cross-link fields they would need.

## Validation

- `scripts/check.sh` from repo root.
- Targeted: `mb/tests/test_validate.py`, `mb/tests/test_suggest.py`,
  `mb/tests/test_graph.py` cover the new schema, suggestion shape, and
  graph edge.
