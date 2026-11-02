# Website — Build Flow

The website shape: a multi-section site past about 10-15 pages, possibly with a blog, several offers, a knowledge base or a course area. Deploys to Cloudflare Pages with git auto-deploy, like every other shape.

The legacy Next.js templates (`saas`, `high-ticket`) and the Netlify path are retired. A website is built the way a minisite is, then grown.

---

## Start static, add a build step only when it pays

1. **Setup.** Follow [`minisite-setup.md`](minisite-setup.md): site repo, `.mainbranch/repo.json` descriptor, business repo link, offer pick, Cloudflare Pages project ([`cloudflare-pages-link.md`](cloudflare-pages-link.md)).
2. **Content.** Run research, brief, conversion and build-out through [`minisite-build.md`](minisite-build.md), using [`minisite-generation-system.md`](minisite-generation-system.md) and [`anti-patterns.md`](anti-patterns.md). Add pages as directories; update `sitemap.xml`, `_headers` and nav.
3. **Build step (optional).** When component reuse or taxonomy needs it, use Astro, 11ty or a similar generator. Ask the owner first; do not scaffold a framework unasked. Check `node --version` (18+) and the package manager, run the build locally before any push, and fix a failing build before publishing.
4. **Pages project with a build step:**

```bash
python3 .claude/skills/mb-site/scripts/pages.py create-project <name> \
  --repo-owner <owner> --repo-name <repo> --branch main
```

Set the build command and output directory once in the Cloudflare dashboard. Moving a minisite onto a generator: see [`graduation.md`](graduation.md).

---

## Brand and copy

Read `voice.md`, `offer.md`, `audience.md`, `soul.md` and `core/proof/testimonials.md` through [`site-context.md`](site-context.md).

| Voice trait | Design implication |
|---|---|
| Warm, personal | Rounded corners, warm palette, serif or humanist sans display |
| Direct, authoritative | Sharp corners, high contrast, geometric sans or strong serif |
| Playful, energetic | Bold colors, larger type scale, personality fonts |
| Premium, refined | Restrained palette, ample whitespace, thin weights, serif display |
| Technical, expert | Monospace accents, structured grids, muted palette with signal color |

- Pull language directly from business context files. Don't invent marketing speak.
- Headlines come from `offer.md`: the transformation, not the feature. Pain points come from `audience.md`, in their words.
- Testimonials come from `testimonials.md` only. Never fabricate.
- CTAs are specific actions from `offer.md`, not "Learn More". One CTA color, shared by nothing else.
- If the site sends traffic to Skool, cross-check `skool-surfaces.md` so the page and the Skool about page agree.
- No generic default fonts (Inter, Roboto, Arial). Mobile-first. Respect `prefers-reduced-motion`.

**Section order for a conversion page:** hero, trust strip, problem, solution, how it works, examples, proof, why this vs alternatives, objections, pricing or value stack, FAQ, final CTA. Minimum: hero, problem, solution, proof, CTA. Briefs may name a `copy_framework_tag`; see [`minisite-brief.md`](minisite-brief.md).

---

## Preview and publish

Preview locally (static server, or the generator's dev command). Iterate until the owner is happy.

Publish: run the local build if there is one, `git status && git diff --stat`, commit, `git push origin main`. Cloudflare Pages auto-deploys in about 1-2 minutes. Ask before the first push to a public site, and follow the visibility and approval rules in [`SKILL.md`](../SKILL.md). Then run `mb site check` per [`site-measurement.md`](site-measurement.md).

---

## Growing further

Past about 10 pages or with non-developer editors, bolt on a CMS: see [`graduation.md`](graduation.md).
