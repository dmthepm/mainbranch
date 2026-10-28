---
type: decision
date: 2026-05-11
status: accepted
topic: How Main Branch connects notes, data, and history
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/468
  - https://github.com/dmthepm/mainbranch/issues/469
  - https://github.com/dmthepm/mainbranch/issues/470
  - https://github.com/dmthepm/mainbranch/issues/471
linked_decisions:
  - decisions/2026-05-09-obsidian-first-class-viewer.md
  - decisions/2026-05-02-github-native-business-os.md
linked_docs:
  - docs/business-connections.md
  - docs/markdown-link-conventions.md
tags: [docs, graph, data, git-history, obsidian]
---

# How Main Branch Connects Notes, Data, and History

## Decision

Main Branch uses a small set of connection types instead of treating every
mention as a graph edge.

- Frontmatter `linked_*` fields are the official relationships `mb` trusts.
- Inline Markdown links explain a sentence or claim.
- `## Related links` helps people browse the page and is repaired from
  frontmatter, not the other way around.
- Entity tags mark durable concepts such as channels, offers, metrics,
  platforms, companies, and people.
- Data files hold raw or repeatable facts; markdown reports explain what those
  facts mean.
- GitHub issues, pull requests, and commits show what changed, why, and when.

The goal is useful signal. Main Branch should not link every passing noun,
platform, metric, or offer mention.

## Why

The Related links repair work gives Main Branch a clean maintenance loop:
frontmatter holds the relationship, body links make that relationship easy to
browse, and `mb doctor repair` keeps the mirror current.

The next problem is authoring judgment. When an operator dumps a thought or an
agent drafts a new decision, the system needs to answer: "What should this
connect to, and how strong is that connection?"

One connection surface cannot answer every case. A decision that depends on
research is different from a sentence that cites a report, which is different
from a casual mention of Google Ads. Agents need a plain decision matrix so
they add the links that matter and leave weak mentions alone.

## Connection Model

Use this priority order when deciding what to add:

| Need | Main Branch surface | Why |
| --- | --- | --- |
| The relationship changes how work should be understood, audited, or operated. | Frontmatter `linked_*` field | `mb graph`, `mb validate --cross-refs`, and status checks can trust it. |
| The link helps the reader understand one sentence or claim. | Inline Markdown link | The explanation stays where the idea appears. |
| The concept is durable but not one specific file. | Entity tag such as `#channel/google-ads` | The concept remains searchable without pretending every mention is a dependency. |
| The note depends on numbers, exports, or platform history. | Link a report or data metadata file | The raw facts stay queryable while the business meaning stays readable. |
| The work changed because of an issue, PR, or commit. | Link the GitHub issue/PR/commit URL | Reviewers and future agents can reconstruct why code or business files changed. |
| The match is weak or only nearby context. | Mention it in prose or leave it out | Avoid noisy graphs and false confidence. |

## Data Records

Main Branch should point to structured business data without turning every row
into markdown.

- Use SQLite for ongoing local data that changes over time and needs queries:
  ad stats, email sends, Stripe revenue, CRM leads, analytics events, or daily
  platform syncs.
- Use CSV for simple snapshots, one-time exports, and small tables that are
  useful to inspect directly.
- Consider Parquet or Arrow later for larger analytical datasets, not as the
  default beginner path.
- Put a small markdown or YAML metadata file next to a data source so agents
  can see provider, owner, freshness, privacy level, update cadence, and useful
  queries without opening raw data first.
- Link decisions, pushes, bets, and outcomes to reports or metadata files by
  default. Link directly to raw data only when the file itself is the useful
  artifact.

Obsidian is not the data store. It should help a person browse reports,
decisions, outcomes, and metadata. `mb` and skills can query the structured
files when a workflow needs numbers.

## Git History

Git history is part of the connection system.

- A decision can link the GitHub issue that framed the work.
- A PR can link the decision, issue, or push it implements.
- A commit can be read as a saved checkpoint for what changed.
- An outcome can link the report or data snapshot that proves what happened.

This gives a future agent a practical path from "why did we do this?" to "what
changed?" to "what happened after?"

## Obsidian Lessons

The official Obsidian CLI and core plugins are useful inspiration, not a Main
Branch dependency.

Current [Obsidian CLI](https://obsidian.md/help/cli) docs show command-line
access for file reads/writes, search, backlinks, outgoing links, unresolved
links, orphan/dead-end files, outline/headings, tags, properties, Bases
queries, and developer/debug commands. The
[Outgoing links](https://obsidian.md/help/plugins/outgoing-links) core plugin
also surfaces unlinked mentions: text that matches another note name or alias.

Main Branch should learn from that pattern:

- expose relationship checks as scriptable commands;
- separate "possible mention" from "official relationship";
- show ranked suggestions with reasons before editing files;
- keep Obsidian optional and local.

## Consequences

- `docs/business-connections.md` becomes the plain-language guide for choosing
  typed links, inline links, entity tags, data/report references, GitHub
  references, or no link.
- `docs/markdown-link-conventions.md` stays the syntax guide for Markdown,
  wikilinks, frontmatter links, and Related links repair.
- Generated repo guidance and bundled skills should point agents at the matrix
  before they add relationships.
- `mb suggest links <file>` is the read-only command that returns ranked
  suggestions and reasons; this decision does not implement it, but follow-up
  work has shipped it (#469).
- Implementation status of follow-ups named in this decision: `mb suggest
  links` (#469) shipped; the data-source registry (#470) shipped; the
  scheduled data sync pattern (#471) has an accepted decision and operator
  doc — implementation of `mb data sync` / `mb data status` is still open.

## Related links

- [Business connection guide](../docs/business-connections.md)
- [Markdown link conventions](../docs/markdown-link-conventions.md)
- [Obsidian as a first-class optional viewer](2026-05-09-obsidian-first-class-viewer.md)
