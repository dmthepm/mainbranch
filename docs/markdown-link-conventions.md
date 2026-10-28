# Markdown and Link Conventions

Main Branch business repos should be readable in GitHub, local editors, and
Obsidian without becoming dependent on any markdown app.

The repo is the durable source of truth. Markdown tools are views over that
truth. `mb` is the validator and graph engine; Obsidian is an optional
first-class viewer over the same files. See
[the Obsidian viewer decision](../decisions/2026-05-09-obsidian-first-class-viewer.md)
for the product stance, and [Business connections](business-connections.md)
for the plain-language decision matrix on when to use frontmatter links,
inline links, entity tags, data references, GitHub history, or no link.

## Three rules

1. **Official relationship data lives in structured frontmatter**, not in
   viewer-specific link strings. `mb graph`, `mb validate --cross-refs`,
   and `mb status relationship_health` read frontmatter as the source of
   truth.
2. **Body mirrors are generated or repairable viewer output** that creates
   explicit note-level edges for Obsidian Graph and Backlinks. Mirrors do
   not replace structured frontmatter; they sit alongside it.
3. **When interoperability matters, use Markdown relative links** for
   body-level mirrors. Both Obsidian and GitHub render Markdown relative
   links. Wikilinks are also valid in Obsidian-only contexts but are not
   the recommended convention for files that ship to GitHub.

## Filenames

Use stable, lowercase, hyphenated filenames:

```text
decisions/2026-05-04-pricing-model.md
research/2026-05-04-audience-notes.md
bets/2026-05-04-trial-offer.md
pushes/2026-05-04-spring-launch/push.md
core/offers/main-branch/offer.md
```

These examples use the current v0.x folders. If future user
research shows that folder names should change, that change should land
through path-config and migration work, not ad hoc docs or skill examples
that teach a different repo shape.

Avoid spaces, case-only distinctions, and punctuation-heavy names. Avoid
characters Windows reserves in filenames: `< > : " / \ | ? *`. Avoid
characters Obsidian rejects in link targets: `# | ^ : % [ ]`. These
constraints intersect; staying lowercase, hyphenated, and ASCII-safe
keeps every renderer happy.

If you also use Obsidian wikilinks anywhere, prefer unique filename stems.
Bare-stem links like `[[pricing-model]]` depend on Obsidian's basename
resolver and can become ambiguous when multiple folders contain the same
stem. Path-form wikilinks avoid that ambiguity.

## Frontmatter Links

Frontmatter links are machine-readable. Use repo-relative paths with `.md`
extensions:

```yaml
linked_decisions:
  - decisions/2026-05-04-pricing-model.md
linked_research:
  - research/2026-05-04-audience-notes.md
linked_pushes:
  - pushes/2026-05-04-spring-launch/push.md
```

Do not use Obsidian wikilink syntax in frontmatter. Do not omit the
extension. Do not use absolute local paths.

Legacy `linked_campaigns` frontmatter remains readable for migrated repos,
but new records should use `linked_pushes`.

Allowed external references:

```yaml
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/274
```

Use external URLs for public issue, PR, release, or source links. Use
local paths for files inside the same repo.

### Why frontmatter is not where viewer links go

Obsidian's Properties feature treats YAML frontmatter as typed metadata.
A property value containing `[[wikilink]]` syntax is rendered clickable
and contributes to Graph view; a plain repo-relative path is stored as
opaque text and does not become a graph edge or a Linked Mention. So
`linked_pushes: [pushes/.../push.md]` is correct for `mb` and for GitHub
PR review, but invisible to Obsidian's Graph and Backlinks. The body
mirror below is how those edges become visible to Obsidian users.

If you ever do put `[[...]]` in a YAML property, Obsidian requires the
value to be quoted, e.g. `key: "[[Note]]"` or `key: ["[[Note]]"]`.
Markdown formatting is not rendered inside text properties.

## Body Mirrors

When a file declares typed edges in frontmatter, mirror those edges in a
body section so Obsidian Graph and Backlinks pick them up. Use Markdown
relative links at the note level:

```markdown
## Related links

- [Pricing model decision](../decisions/2026-05-04-pricing-model.md)
- [Audience notes](../research/2026-05-04-audience-notes.md)
- [Spring launch push](../pushes/2026-05-04-spring-launch/push.md)
```

Body mirrors are a viewer aid, not a second source of truth. Frontmatter
typed edges remain the source of truth for `mb graph`, `mb validate --cross-refs`,
and `mb status relationship_health`. If frontmatter and the body mirror
disagree, frontmatter wins. `mb validate --cross-refs` warns when the
mirror is missing frontmatter edges, and `mb doctor repair
--plan` / `mb doctor repair --apply` can add missing mirror links after
operator approval.

The body mirror creates one stable note-to-note edge per relationship.
Obsidian's Backlinks pane covers Markdown links and wikilinks equally;
Graph view treats both as edges. GitHub renders Markdown relative links
clickable in PR review and the file viewer.

You may add a short prose description, including the name of the target
section. Keep the link itself note-level; do not encode section identity
in a heading fragment (see below).

Do not manually invent relationships to fill this section. First add the
typed `linked_*` frontmatter field from evidence, then let `mb doctor
repair --plan` preview any missing body mirror links. The repair path adds
missing Markdown links and preserves existing human descriptions; it does
not delete stale body-only links or update frontmatter from body links.

## Authoring Common Relationships

Use the narrowest evidence-backed frontmatter field available. For the
full decision matrix, including inline links, entity tags, data references,
GitHub history, and no-link cases, see
[Business connections](business-connections.md).

- Active bets should link to supporting pushes, playbooks, decisions,
  research, and outcome/log artifacts through `linked_pushes`,
  `linked_playbooks`, `linked_decisions`, `linked_research`, and
  `linked_outcomes`.
- Pushes should set `offer:` to the promoted offer file and use
  `linked_bets`, `linked_decisions`, `linked_research`, or
  `linked_outcomes` when the push is explicitly tied to those records.
- Completed pushes should link outcome, review, or log artifacts through
  `linked_outcomes`.
- Decisions should link the bets, pushes, research, issues, docs, PRDs, or
  superseded decisions they affect through the corresponding typed fields.
- Research and proof files should link to the offer, bet, push, decision,
  or outcome they support when that relationship is explicit.
- Topology entries should link child repos to offers, pushes, playbook run
  records, or operating boundaries only when the repo-topology record has
  evidence for that boundary.

If the evidence is weak, leave the frontmatter link out and add a
plain body reference only if it helps the reader. Body-only links stay
generic references; they are not typed graph data.

### Do not link to section anchors across tools

GitHub slugifies headings to lowercase-hyphenated anchors and changes them
when headings change or collide. Obsidian uses the heading text after `#`
as the heading target. The two systems do not agree, and section-fragment
links that look right in one tool will fail or drift in the other.

The typed-edge fields (`linked_decisions`, `linked_research`,
`linked_pushes`, `linked_outcomes`, `linked_docs`, `linked_issues`,
`linked_bets`, `linked_playbooks`, etc.) point at files, not headings.
That is intentional. If you need to point at a specific section of the
target file, name the section in body prose rather than encoding it in
a link fragment:

```markdown
## Related links
- [Markdown link conventions](markdown-link-conventions.md) — see the
  "Body mirrors" section.
```

Treat heading anchors as brittle unless the heading is deliberately
stable.

## Wikilinks

Wikilinks are valid in Obsidian and are accepted by `mb graph` and
`mb validate --cross-refs` as body-link edges. Use them when the file is
written for an Obsidian-only audience and GitHub readability is not a
constraint.

When you do use a wikilink, prefer the path form over a bare stem:

```markdown
See [[decisions/2026-05-04-pricing-model|pricing decision]].
```

Bare stems like `[[pricing-model]]` rely on Obsidian's basename resolver
and can collide silently when two folders have the same stem.

For files that mix audiences (PR reviewers on GitHub plus operators in
Obsidian), use Markdown relative links per the rule above.

## Entity Tags

`mb graph` recognizes typed entity tags in markdown bodies:

```markdown
#company/example-co
#person/jane-doe
#offer/main-branch
#channel/github
#competitor/status-quo
#metric/activation-rate
```

Use these for durable entities that should appear in graph output. Keep
values lowercase and hyphenated. Do not use entity tags for secrets,
private customer names, account numbers, or legal/finance identifiers
that should not be visible to the repo audience.

Obsidian's native graph view can also surface tags as nodes when toggled.
Nested tags (`#parent/child`) display as a hierarchy in Obsidian's Tags
pane but do not draw parent-child edges in core Graph view.

## Cross-Repo Links

A business repo may link to another repo, but a cross-repo link is not
the same as access.

Use public URLs when the target is public:

```markdown
See [Main Branch issue #274](https://github.com/dmthepm/mainbranch/issues/274).
```

Use a plain-text repo/path reference when the target may be private and
the link should not imply broad access:

```markdown
Private finance source: finance-repo/core/finance/ledger/
```

Do not commit private local machine paths. If a local-only path is
needed for an operator, keep it in local config, a private repo, or
local scratch space rather than public docs.

## Obsidian Setup

Opening a business repo as an Obsidian vault is optional. The viewer
story is browsing files, following links, and reading the Backlinks pane
and Graph view. That is the whole claim.

1. Open the repo root as the vault.
2. Keep attachments and exports in existing repo folders only when they
   are safe for the repo audience.
3. Do not rely on an Obsidian plugin for Main Branch correctness. `mb`
   validates and indexes the same files without any plugin.
4. Keep `.obsidian/` local. `workspace.json` and `workspace-mobile.json`
   contain machine-specific pane state and should not be committed
   shared.

Main Branch should not require Obsidian, replace Obsidian, or add
Obsidian as a runtime dependency. See
[the Obsidian viewer decision](../decisions/2026-05-09-obsidian-first-class-viewer.md).

## Validation

Run:

```bash
mb validate --cross-refs
```

This checks known frontmatter link fields and warns when important
links are missing, when frontmatter links are not mirrored in
`## Related links`, and when wikilinks point to missing markdown files or
match multiple files by stem. Standard Markdown relative links are
validated as body-link edges in the same pass.

Use strict mode in CI or branch cleanup when warnings should fail:

```bash
mb validate --cross-refs --strict
```

Validation does not prove a user can access a private cross-repo
target. It only checks the current repo and safe external references.
