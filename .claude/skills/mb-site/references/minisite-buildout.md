# Minisite Build-Out

Load this for step 9 of the minisite flow: generating the remaining pages after the operator picks a home-page concept.

## Build Subagent

Spawn the minisite generation subagent in the foreground with the picked concept as the design seed.

The subagent generates the rest of the pages:

- `how-it-works/`;
- picked supporting pages;
- `privacy/`;
- `terms/`;
- `start/thanks/`.

The supporting pages must stay consistent with the picked concept's design language.

## Inputs

Pass the build subagent:

- picked `index.html` and `styles.css` from the raw published concept;
- locked brief from `decisions/YYYY-MM-DD-minisite-brief-<slug>.md`;
- conversion endpoint URL from `.mainbranch/conversion.json`;
- resolved `offer.md`;
- resolved `audience.md`;
- `voice.md`;
- optional `soul.md`;
- [`minisite-generation-system.md`](minisite-generation-system.md) as the system prompt.

Anti-patterns to avoid in the user message: [`anti-patterns.md`](anti-patterns.md).

## Validation After Build-Out

Required files must be present:

- `index.html`;
- `how-it-works/index.html`;
- at least two more supporting page directories with `index.html`;
- `privacy/index.html`;
- `terms/index.html`;
- `start/thanks/index.html`;
- `_headers`;
- `_redirects`;
- `robots.txt`;
- `sitemap.xml`;
- `og.svg`;
- `favicon.svg`.

Each missing file is a fix request to the subagent.

Footer presence:

```bash
# ENTITY = `entity:` from offer.md frontmatter
[ -n "$ENTITY" ] && [ "$ENTITY" != "<legal entity from offer.md>" ] || { echo "no entity: ask the owner"; exit 1; }
find . -name '*.html' -exec grep -L -F "$ENTITY" {} +
find . -name '*.html' -exec grep -l -F "&lt;legal entity" {} +
```

Stop if `ENTITY` is empty or still the placeholder. Both `find` commands must print nothing; any file listed is a fix request to the subagent.

OG render:

```bash
python3 .claude/skills/mb-site/scripts/og_render.py render <repo>/og.svg <repo>/og.png
```

The envelope must return `status: ok` with `width: 1200` and `height: 630`.

Conversion URL substitution:

- Every CTA href on every page should match the URL in `<repo>/.mainbranch/conversion.json`.
- No `https://CONVERSION-PLACEHOLDER` should remain.

## Variance Test

Running the full flow twice on the same offer must produce visually distinct sites: different palettes, hero artifacts, page choices, and microcopy.

Concept variations enforce this at the home-page level. Build-out inherits the picked concept's seed but still has aesthetic latitude in the supporting pages.

If two full runs produce identical output, the brief was over-specified or the concept-variations soft brief was too prescriptive. Re-read [`anti-patterns.md`](anti-patterns.md).

## Not In The Minisite Shape

- No `pnpm install`, no `pnpm build`. Static HTML only.
- No `site-config.ts` pattern. Each minisite generates its own one-off structure.
- No section-types menu; each minisite picks its own sections.
- No Anthropic API key. Generation runs inside the operator's Claude Code session through the `Agent` tool.
- No multi-endpoint conversion. One minisite has one conversion endpoint; graduate to website shape if you need both.

After validation passes, move to [`minisite-publish.md`](minisite-publish.md).
