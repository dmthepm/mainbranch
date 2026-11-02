# Graduation — Site Shape Transitions

When an offer pulls more traffic, the site that supports it often needs more. `/mb-site` ships three site shapes (lander, minisite, website) and a fourth posture (website with a CMS bolted on for non-developer content editing). Sites can graduate up the ladder; this file documents the paths and when to take each.

V1 doesn't ship an automated graduation tool — these are operator-decision moments triggered by real signal. The skill recognizes the signal, surfaces the option, walks through the change. Future versions may script more of it.

---

## When to graduate

| Signal | Suggests graduating from → to |
|---|---|
| 1-page lander pulls traffic that lingers on hero but doesn't convert; people want more proof or process detail before deciding | **Lander → Minisite** |
| Minisite paid-ad funnel gets meaningful conversions; offer is validated; team wants to add blog, case studies, multiple offer pages, course/community area | **Minisite → Website** |
| Website grows past ~10 pages OR non-developers (marketing, ops, founder partner) need to edit content without git access | **Website → Website + CMS** |
| Website needs structured content (case studies, courses, products, locations) with relationships and queries | **Website → Website + CMS** |
| Site outgrows static; needs auth, gated content, dashboards, complex forms | (out of scope for /mb-site — use a separate app skill or upgrade to a full SPA) |

Don't graduate prematurely. Each tier costs operational complexity. Graduate when the *current* tier is failing — not because a future tier sounds neat.

---

## Lander → Minisite

**What changes:**
- 1 page → ~4–6 pages (home + how-it-works + 2–4 LLM-picked + privacy/terms/start-thanks)
- Single hero focus → distributed proof + how-it-works + faq across pages
- Same domain, same Cloudflare Pages project (no infra change)

**Mechanics:**
1. Run `/mb-site` against the existing project. The minisite generation subagent reads the same offer.md / audience.md and produces a ~4–6 page version. The home page stays focused (linking directly to the conversion endpoint); supporting pages get the proof, mechanism, and faq content.
2. Confirm `/start/thanks/` is present (minisite shape requires it as the post-conversion landing).
3. Update the `shape` field in the repo-local `.mainbranch/repo.json` (or legacy `~/.mainbranch/sites.json`): `lander` → `minisite`.
4. `git push` — Cloudflare auto-deploys.
5. (Optional) Re-run `og_render.py` if the og.svg changed.

**Gotcha:** if the lander had a meta description / OG image tuned for the single-page funnel, the minisite generation may produce different OG content. Either accept the new content or pass `--reference <old-lander-url>` to the subagent's reference list to anchor toward continuity.

---

## Minisite → Website

**What changes:**
- ~4–6 pages → 10+ pages (blog, multiple offers, knowledge base, course area, etc.)
- Static HTML → likely Astro or similar with a build step (component reuse pays off past ~6 pages)
- Possibly: deeper navigation (header nav, footer site map), search, taxonomy

**Two paths:**

### A. Stay static, expand

Keep the static HTML, add more directories. Simple, no build step. Works for ~10–15 page sites without taxonomy.

1. Add new pages directly in the project repo (`/about/`, `/blog/`, `/case-studies/<slug>/`, etc.)
2. Update `sitemap.xml`, `_headers`, internal nav by hand or with a small subagent prompt
3. `git push` — Cloudflare auto-deploys

### B. Migrate to Astro / similar

Past ~10–15 pages, component reuse + a build step pays off. Use a static-site generator (Astro, 11ty, similar); ask the owner before scaffolding one.

**Mechanics:**
1. Create a parallel repo for the generator. The minisite repo's content gets copied or adapted into components or templates.
2. Configure the Cloudflare Pages project's build settings (dashboard): build command and output directory for the generator. Or create a fresh Pages project pointed at the new repo.
3. Test on a `*.pages.dev` URL before flipping the apex domain.
4. When ready, detach the apex domain from the old project and re-attach to the new one (use the `pages.py set-domain` tool).
5. Update the repo-local `.mainbranch/repo.json` (or legacy `~/.mainbranch/sites.json`) with `shape: website`, and optionally archive the old minisite repo.

**Gotcha:** SEO continuity. The minisite's URLs (`/how-it-works/`, `/proof/`, etc.) should map cleanly to the new site's URLs. Use `_redirects` for any path changes.

---

## Website → Website + CMS

**Why bolt on a CMS:**
- Non-developers need to edit content (blog posts, case studies, product info) without touching git
- Content has structure that benefits from queries (filter case studies by industry, list courses by topic)
- Multi-language or multi-region content needs centralization
- Editorial workflow (drafts, review, publish) needs explicit status

**Common CMS options for static sites:**

| CMS | Strength | When to pick |
|---|---|---|
| **Sanity** | Real-time, structured content with relationships, GROQ queries, customizable Studio editor | Most flexible; preferred for complex content models |
| **Contentful** | Mature, enterprise-y, broad ecosystem | When team wants a polished editor and doesn't need infinite custom schema |
| **Notion as CMS** | Use existing Notion workspace as content source via API | Lowest friction if team already lives in Notion; trade-off: Notion's API is rate-limited and not built for high traffic |
| **Markdown in repo** (no CMS) | Files in git, edited via PR, all version-controlled | Best when content editors are comfortable with git or willing to use the GitHub web UI |
| **Decap CMS** (formerly Netlify CMS) | Git-backed, self-hosted, free | When you want a CMS UI but don't want a third-party SaaS bill |

**Bolt-on mechanics (Sanity example, as the most common):**

1. Create a Sanity project at https://sanity.io. Define schema for the content types (blog posts, case studies, etc.) — schema lives in code, deploys to Sanity hosted Studio.
2. Add `@sanity/client` to the website repo. Page templates fetch content from Sanity at build time (for static sites) or runtime (for SSR sites).
3. Migrate existing markdown / hand-written content into Sanity via the Studio or import script.
4. Configure rebuild webhooks: Sanity content publish → triggers Cloudflare Pages rebuild (CF Pages supports deploy hooks).
5. Editor team uses Sanity Studio (sanity.studio/{project}) to add/edit content; on publish, the website rebuilds and deploys automatically.

**The deploy target stays the same.** The Cloudflare Pages project doesn't care about the CMS; it just sees a git push or a deploy hook fire and rebuilds.

**Gotchas:**
- Build time grows as content grows. For a static site with hundreds of CMS items, build can take 5+ minutes. Consider on-demand revalidation (Next.js ISR) or chunked builds at that point.
- Editor permissions: Sanity has roles, but coordinate with the team on who can publish vs. draft.
- Asset hosting: Sanity hosts images by default with a CDN. If you want assets on your own CDN, configure Sanity's asset URL to proxy or use a transform.

---

## Anti-patterns when graduating

- **Skipping tiers.** Lander → Website + CMS in one move is usually a sign the team wants to "do it right the first time." That's almost always premature. Each tier validates whether the next is needed.
- **Graduating before the offer is validated.** A minisite that's not converting doesn't need more pages — it needs a better offer or a different message. Graduating won't fix the upstream problem.
- **Bolting a CMS on too early.** A 5-page website with infrequent content updates doesn't need Sanity overhead. Edit pages directly via git PRs until the team's velocity demands a CMS.
- **Re-platforming because the team is bored.** If the current tier works, leave it alone. Engineering inertia is a feature when conversion data says you're winning.

---

## What V1 ships vs. what's automated later

V1 ships these graduation paths as **documented manual flows** — `/mb-site` recognizes the signal, surfaces the option, but the operator does the work (with Claude Code's help via `/mb-site` modes).

Future versions might add `/mb-site graduate <new-shape>` as a skill mode that automates the bulk of the transition (creates the new repo, ports content, swaps the apex domain). That ships only after the manual flow has been run on real graduations and the patterns are stable enough to script.
