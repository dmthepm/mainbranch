# Business Connections

Main Branch should help a person or agent connect the work that actually
matters. It should not turn every repeated word into a link.

Use this guide when writing decisions, research, bets, pushes, playbooks,
outcomes, reports, and generated repo guidance.

## The Short Version

| Situation | Use | Example |
| --- | --- | --- |
| The relationship changes how the work should be understood, audited, or operated. | Frontmatter `linked_*` | A decision depends on research, a push implements a decision, an outcome proves a push. |
| The link helps a reader understand a sentence. | Inline Markdown link | "The [Google Ads weekly report](../reports/2026-05-10-google-ads.md) showed spend was capped by search volume." |
| The note is about a durable concept, not one specific file. | Entity tag | `#channel/google-ads`, `#metric/conversion-rate`, `#platform/meta-ads` |
| The note depends on numbers or platform exports. | Report or data metadata link | Link the weekly report or `data/google-ads/source.md`, not every raw row. |
| The work happened because of code, issue, or review history. | GitHub issue, PR, or commit link | A decision links the PR that implemented it. |
| The connection is weak, generic, or only a passing mention. | Plain text or nearby context | "Google Ads might matter later" stays unlinked. |

The test is simple: does the connection change how someone should understand,
operate, or prove the work? If yes, connect it. If not, leave it alone.

## Decision Matrix

Ask these questions in order:

1. **Does this change the meaning, operation, or audit trail of the work?**
   Use a typed frontmatter link.
2. **Does it support one sentence or claim?**
   Use an inline Markdown link.
3. **Is it a durable concept across many records?**
   Use an entity tag.
4. **Is it source data or a repeatable number pull?**
   Link a report or data metadata file.
5. **Is it useful but uncertain?**
   Keep it as nearby context or an agent suggestion.
6. **Is it just a passing noun?**
   Leave it as plain text.

Do not create typed frontmatter links from weak similarity alone. Do not link
every mention of a platform, metric, offer, person, or company.

## Typed Frontmatter Links

Use frontmatter `linked_*` fields for relationships `mb` should trust:

```yaml
linked_research:
  - research/2026-05-10-google-ads-intent.md
linked_pushes:
  - pushes/2026-05-10-google-ads-test/push.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/468
```

Good typed links:

- A decision depends on Google Ads research.
- A push implements a decision.
- A research note supports a bet.
- A playbook operationalizes a push.
- An outcome proves or disproves a bet.
- A decision supersedes an older decision.
- A PR changed implementation because of a decision.

Avoid typed links when the relationship is only a guess, a vague topic match,
or a passing mention.

## Inline Markdown Links

Use inline links where the reader needs context in the sentence:

```markdown
We chose search first because the
[Google Ads intent research](../research/2026-05-10-google-ads-intent.md)
showed stronger buying intent than cold Meta traffic.
```

Inline links are good for claims, examples, reports, source documents, and
specific prior thoughts. They do not become typed business relationships unless
you also add frontmatter.

## Entity Tags

Use entity tags for durable concepts that appear across records:

```markdown
#channel/google-ads
#platform/meta-ads
#metric/conversion-rate
#offer/main-workshop
```

Tags are useful when a note is about a channel, metric, platform, offer,
company, person, or competitor but is not tied to one specific artifact.

Do not use entity tags for secrets, raw account numbers, private customer
names, legal identifiers, or finance identifiers that should not be visible to
the repo audience.

## Data and Reports

Markdown is where the business meaning lives. Structured data files are where
repeatable facts live.

| Data shape | Use it for | Notes |
| --- | --- | --- |
| SQLite | Daily or weekly local data that needs queries over time: ads, email, Stripe, CRM, analytics. | Strong default for ongoing local data. |
| CSV | Simple snapshots, one-time exports, small tables, and audit-friendly daily cuts. | Easy to inspect and portable. |
| Parquet or Arrow | Larger analytical datasets later. | Useful later, too technical as the default. |
| Markdown report | What the numbers mean, what changed, and what to do next. | Link decisions, pushes, and outcomes here first. |
| Metadata sidecar | Provider, owner, privacy, freshness, cadence, and useful queries. | Lets agents understand a data file before opening it. |

Suggested repo shape:

```text
data/
  google-ads/
    source.md
    daily.sqlite
    snapshots/
      2026-05-10.csv
reports/
  2026-05-10-google-ads-weekly.md
```

Suggested metadata:

```yaml
---
type: data_source
provider: google_ads
owner: growth
privacy: team_private
cadence: daily
freshness: 2026-05-10
storage:
  primary: data/google-ads/daily.sqlite
  snapshots:
    - data/google-ads/snapshots/2026-05-10.csv
reports:
  - reports/2026-05-10-google-ads-weekly.md
---
```

Default rule: link markdown records to reports or metadata, not giant raw data
files. Link raw files directly only when the raw file is the thing someone
needs to inspect.

Examples:

- A playbook that uses a platform data table links `data/meta-ads/source.md`
  or a report that explains the table.
- A push whose result is supported by daily ad spend links the weekly report
  and, if needed, the exact CSV snapshot.
- An outcome links the report that proves what happened.

Obsidian can browse the reports, metadata, and links. It should not pretend to
be the data warehouse.

## GitHub and Git History

GitHub and git are part of the business memory:

- Issues are tasks, blockers, requests, or follow-ups.
- Pull requests are proposals and review conversations.
- Commits are saved checkpoints that show what changed.
- Release notes explain what users can install.

Use GitHub links when they explain why work changed:

```yaml
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/468
  - https://github.com/dmthepm/mainbranch/pull/467
```

A decision can link the PR that implemented it. A PR can link the decision it
implements. An outcome can link the report that proved the result. This gives
future agents and people the path from why, to what changed, to what happened
after.

## Related Links

`## Related links` is for browsing. It mirrors typed frontmatter links so
GitHub, Obsidian, and humans can click around.

Run:

```bash
mb doctor repair --plan
```

Then review and apply if the plan is right:

```bash
mb doctor repair --apply
```

Repair adds missing body links from frontmatter. It does not create
frontmatter from body-only links.

## Obsidian Lessons

Obsidian is optional. The useful lesson is that local markdown can be
scriptable and browsable.

As of the current Obsidian CLI docs, Obsidian exposes commands for reading,
creating, appending, prepending, moving, renaming, and deleting files; search;
backlinks; outgoing links; unresolved links; orphan and dead-end files;
outline/headings; tags; properties; Bases queries; and developer/debug
commands. See the official [Obsidian CLI](https://obsidian.md/help/cli) docs.

The Outgoing links core plugin also shows unlinked mentions: text in a note
that matches another note name or alias. See the official
[Outgoing links](https://obsidian.md/help/plugins/outgoing-links) docs.

Main Branch should learn from that without making Obsidian required:

- possible mentions are suggestions, not official relationships;
- relationship checks should be scriptable;
- agents should show reasons before editing graph data;
- local viewers should browse the same files `mb` validates.

## CLI Shape

`mb suggest links` helps agents choose connections without editing files:

```bash
mb suggest links decisions/2026-05-10-google-ads-first.md
```

Use `--json` for skills and future review UI. The output ranks suggestions with
reasons and action types:

- add typed frontmatter link;
- add inline Markdown link;
- add entity tag;
- link report or data metadata;
- leave as nearby context;
- ignore.

It does not silently invent relationships. The operator or agent should approve
what matters before changing frontmatter, inline links, tags, or metadata.

The data-source record shape that decisions, pushes, and outcomes can link
through `linked_data_sources` is documented in
[`docs/data-source-registry.md`](data-source-registry.md).

The scheduled data sync pattern that keeps `data/<provider>/` fresh is
documented in [`docs/scheduled-data-sync.md`](scheduled-data-sync.md).

## Related links

- [How Main Branch connects notes, data, and history](../decisions/2026-05-11-connecting-notes-data-and-history.md)
- [Data-source registry shape](data-source-registry.md)
- [Data-source registry decision](../decisions/2026-05-11-data-source-registry.md)
- [Scheduled data sync pattern](scheduled-data-sync.md)
- [Markdown link conventions](markdown-link-conventions.md)
- [Obsidian viewer decision](../decisions/2026-05-09-obsidian-first-class-viewer.md)
