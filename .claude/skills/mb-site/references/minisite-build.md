# Minisite Build

The minisite shape is ~4-6 pages of static HTML, no build step, deployed to Cloudflare Pages with git auto-deploy. It is designed fresh per offer by a generation subagent; no template inheritance.

V1 target. This is the default for paid-ad lander tests, single-offer first deploys, lead-form funnels, and conversion-gateway flows.

The source-of-truth contract for what a minisite is (page list, per-page content, conversion endpoint, tracking, walkthrough UX) lives at [`minisite.md`](minisite.md). This file is the `/mb-site` minisite router. Load the step reference needed for the current step instead of loading the whole flow at once.

## Progressive Loading Map

| Step | Purpose | Load |
|---|---|---|
| 1 | Research | [`minisite-research.md`](minisite-research.md) |
| 2-4 | Brief draft, review, lock | [`minisite-brief.md`](minisite-brief.md) |
| 5 | Domain, DNS, repo, Pages setup | [`minisite-setup.md`](minisite-setup.md) |
| 6 | Conversion endpoint | [`minisite-conversion.md`](minisite-conversion.md) |
| 7 | Home-page concept variations | [`concept-variations.md`](concept-variations.md) |
| 8 | Publish raw concept | [`minisite-publish.md`](minisite-publish.md) |
| 9 | Build out remaining pages | [`minisite-buildout.md`](minisite-buildout.md) |
| 10-11 | Pre-publish review, final push | [`minisite-publish.md`](minisite-publish.md) |
| After launch | Targeted edits, regeneration, graduation | [`minisite-iterate.md`](minisite-iterate.md) |

## Flow At A Glance

The minisite is built in one continuous flow. Brief and site are not separate skills; `/mb-site` walks all of it:

```text
1. Research      - parallel foreground subagents record findings to research/
2. Brief draft   - composed from research + core business files
3. Review        - quality gates run in parallel; operator addresses or proceeds
4. Brief lock    - committed as the first durable artifact
5. Setup         - domain, DNS, repo, Cloudflare Pages
6. Conversion    - endpoint kind and URL captured to .mainbranch/conversion.json
7. Concepts      - N home-page variations on localhost; operator picks
8. Publish raw   - picked concept committed and pushed
9. Build out     - remaining pages generated with picked concept as seed
10. Review       - pre-publish quality gates
11. Publish      - final push, then iterate
```

Every step that produces durable work commits to git before moving on. Git history is the durable memory; chat compaction cannot be trusted.

## Step Notes

**Research:** use [`minisite-research.md`](minisite-research.md) to spawn foreground subagents and persist findings.

**Brief:** use [`minisite-brief.md`](minisite-brief.md) for dial, archetype, headline formulas, schema, pre-lock review, and the lock commit.

**Setup:** use [`minisite-setup.md`](minisite-setup.md) only when creating or repairing the domain, repo, DNS, Cloudflare Pages project, source link, or local site record.

**Conversion:** use [`minisite-conversion.md`](minisite-conversion.md) only when choosing, creating, or repairing the CTA target and `.mainbranch/conversion.json`.

**Concepts:** use [`concept-variations.md`](concept-variations.md). Concept subagents generate only home pages. The picked concept seeds the rest of the site.

**Build-out:** use [`minisite-buildout.md`](minisite-buildout.md) for subagent inputs, required files, validation, and variance checks.

**Publish:** use [`minisite-publish.md`](minisite-publish.md) for raw publish, final review, and git push behavior.

**Iterate:** use [`minisite-iterate.md`](minisite-iterate.md) for targeted edits, regeneration, and graduation signals.

## Cross-References

- [`../SKILL.md`](../SKILL.md) - top-level `/mb-site` router.
- [`site-context.md`](site-context.md) - active offer and required `core/...` context.
- [`site-repo-workflow.md`](site-repo-workflow.md) - business repo vs site repo boundaries.
- [`site-measurement.md`](site-measurement.md) - paid-traffic readiness checks.
- [`review.md`](review.md) - dial-gated quality gates.
- [`minisite-generation-system.md`](minisite-generation-system.md) - load-bearing generation prompt.
- [`anti-patterns.md`](anti-patterns.md) - what not to bake into prompts.
- [`graduation.md`](graduation.md) - when to move beyond minisite shape.
- [`examples.md`](examples.md) - examples.
- [`troubleshooting.md`](troubleshooting.md) - common fixes.
