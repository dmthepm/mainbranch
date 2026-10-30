---
type: decision
date: 2026-10-30
status: accepted
topic: who can change the engine repo and publish it
linked_decisions: []
linked_docs:
  - docs/supply-chain-policy.md
participants: [Devon, Claude]
tags: [security, release, supply-chain]
---

# Repo and Release Authority

## Decision

- Intended PyPI publisher: `dmthepm/mainbranch`, `publish-pypi.yml`, environment
  `pypi`. The old `noontide-co` publisher's removal was reported on 2026-10-28.
  PyPI's settings page has not been read back, so exclusivity is NOT VERIFIED.
- Intended access: `dmthepm` is the only collaborator, reported on 2026-10-28. Nobody
  is re-invited unless the owner says so.
- Intended default `GITHUB_TOKEN`: read-only, reported on 2026-10-28.
- Publishing is a human gate: the owner approves the `pypi` environment run.
- The Apify token in old git history: on 2026-10-30 Apify refused it with a 401 in
  one read-only request. Its rotation was reported, not confirmed by Apify.

## Why

An agent asked the owner about two of these on 2026-10-30 after they were settled.
Recording them here means the answer sits with the repo's other decisions.
