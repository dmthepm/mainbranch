---
type: decision
date: 2026-05-09
status: accepted
topic: Obsidian as a first-class optional viewer
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/455
linked_decisions:
  - decisions/2026-05-08-business-repo-topology-map.md
  - decisions/2026-05-06-main-branch-operating-spine.md
linked_docs:
  - docs/markdown-link-conventions.md
tags: [v0-3, docs, graph, obsidian, links, viewer]
---

# Obsidian as a First-Class Optional Viewer

## Decision

Main Branch does not depend on Obsidian for correctness. It treats Obsidian
as a first-class optional viewer over the same markdown files that `mb`
validates.

`mb` owns the typed business graph: repo shape, frontmatter contracts,
cross-reference validation, relationship health, doctor repair, and
generated guidance. Obsidian owns mature local browsing: clickable files,
the Backlinks pane, Graph view, and link following.

The viewer story is intentionally narrow. A user who opens their business
repo as an Obsidian vault should be able to click around files, see what
links to what, and follow relationships. That is the whole claim. Main
Branch does not market a dashboarding layer, recommend a database plugin,
or take a dependency on any community plugin.

This decision is documentation- and convention-bearing only. It does not
add a CLI flag, a generator, or a packaged starter. Future user-visible
features (an Obsidian companion artifact, a portable starter, an
"open in Obsidian" affordance, or a connection-suggestion playbook) belong
in their own follow-up issues.

## Why

Operators already have plain markdown files in a local folder. Obsidian
already browses markdown, wikilinks, Backlinks, and Graph view without
asking Main Branch to host a dashboard or run a second source of truth.
The cheapest useful viewer is the one the operator already knows or can
adopt without a vendor commitment, and Obsidian is the most established
local-first markdown graph viewer.

The relevant Obsidian behavior that makes this work:

- Both `[[wikilink]]` and `[markdown](path.md)` link syntaxes parse and
  resolve. The Backlinks pane covers both equally.
- Graph view edges come from internal links in note bodies. Folders are
  not containers; tags can be toggled as nodes.
- Properties (Obsidian's typed YAML frontmatter UI, GA 2023-08-31) does
  not recognize plain repo-relative paths as links. Only quoted
  `[[wikilink]]` values in YAML render as graph edges. So canonical
  typed edges in `mb` frontmatter are invisible to Obsidian's graph and
  Backlinks unless we mirror them in note bodies.
- Section-heading link syntax does not agree across GitHub and Obsidian.
  GitHub slugifies headings to lowercase-hyphenated anchors; Obsidian
  uses the heading text after `#`. Heading-fragment links are brittle
  cross-tool.

These constraints decide the convention. Typed edges in frontmatter
remain the source of truth. A body `## Related links` section is a viewer mirror
only — it exists so Obsidian, GitHub, and humans can browse
relationships without `mb` changing its graph model. If frontmatter and
body mirrors disagree, frontmatter wins. `mb validate --cross-refs` can
warn when the mirror is out of date, and `mb doctor repair` can preview and
apply missing mirror links from frontmatter after operator
approval.
See [Markdown link conventions](../docs/markdown-link-conventions.md)
for the link-form rules.

## What this is not

This decision deliberately does not include the following. Each is a
follow-up at most, never a requirement.

- A dashboarding layer recommendation. Main Branch does not endorse the
  Obsidian Bases core plugin, Dataview, Templater, Graph Link Types,
  community Map-of-Content plugins, or any other plugin as part of the
  viewer story. Operators may use any of these locally; nothing in
  Main Branch should depend on them.
- An `mb graph --obsidian` companion artifact, generated index notes,
  or starter `.base` files. None ship with this decision.
- A bundled `.obsidian/` folder. `mb onboard` does not create one.
  `.obsidian/workspace.json` and `.obsidian/workspace-mobile.json`
  contain machine-specific pane state and should never be committed
  shared.
- An `mb open obsidian` affordance. The `obsidian://open` URI scheme
  and the official Obsidian CLI (v1.12+, 2026-02) are interesting future
  integration surfaces but are not part of this decision.
- A change to the `linked_*` frontmatter contract. Repo-relative paths
  with `.md` extensions remain the source of truth. No switch to wikilink-typed
  frontmatter.

## Consequences

- `docs/markdown-link-conventions.md` is the canonical place for link
  authoring rules. It updates to cover the three-rule contract,
  authoring hazards, and the body-mirror pattern.
- `mb graph`, `mb validate --cross-refs`, and `mb status relationship_health`
  remain the deterministic source of graph truth. None of their
  contracts change because of this decision.
- Generated business-repo agent guidance (`CLAUDE.md.tmpl`,
  `AGENTS.md.tmpl`) gains a brief Linking section pointing operators
  and agents at the conventions doc.
- A future ticket may add a connection-discovery playbook that uses
  Obsidian's outgoing-links / Backlinks queries (or the official
  Obsidian CLI) to propose candidate edges to the operator. That work
  sits adjacent to the existing graph-link authoring assistance ticket
  and stays optional.
- Body mirrors are derived browsing aids, not authoritative graph data.
  Validation and doctor repair may warn and add missing mirror links when
  frontmatter links are absent from `## Related links`, but graph
  correctness remains based on structured frontmatter.

## Validation

- `scripts/check.sh` from repo root.
- No CLI behavior changes; no new fixtures required.
- `mb validate --cross-refs --strict` against the existing
  `mb/tests/fixtures/` continues to pass.
- Manual smoke test: open a business repo root as an Obsidian vault and
  confirm body-level `## Related links` entries appear as navigable
  links and produce edges in the Graph view and entries in the
  Backlinks pane. Not automated.

## Related links

- [Business repo topology map](2026-05-08-business-repo-topology-map.md) — prior decision this builds on.
- [Main Branch operating spine](2026-05-06-main-branch-operating-spine.md) — durable operating model this decision sits inside.
- [Markdown link conventions](../docs/markdown-link-conventions.md) — link-form rules this decision points operators at.
