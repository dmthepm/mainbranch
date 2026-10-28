# Website — Build Flow

The website shape: full multi-section site, often with a build step (Next.js, Astro, etc.), possibly with a blog, multi-offer support, knowledge base, course area. Larger surface area than a minisite; warrants component reuse and a structured site-config.

V1 status: per-offer Website generation is not yet wired (a future companion to `minisite-generation-system.md`). For now, this flow uses the legacy Next.js templates (`saas` and `high-ticket` — Devon-specific examples) as starting points. They work via Netlify deploy or Cloudflare Pages with a build step.

When per-offer Website generation ships, this file gets a sibling section for the static-or-Next.js LLM-generated path.

---

## Hosting decision (default: Cloudflare Pages)

For new Website builds, Cloudflare Pages is the default — better CLI, better domain integration, git auto-deploy, supports Next.js/Astro/React with build steps via build presets. Netlify works too and is documented in [`deployment.md`](deployment.md) as the legacy path; pick it only if you have specific Netlify-only needs.

For Cloudflare Pages with a build step:
```bash
python3 .claude/skills/mb-site/scripts/pages.py create-project <name> \
  --repo-owner <owner> --repo-name <repo> --branch main
# Build settings configured in CF dashboard once: Build command (e.g., `pnpm build`), Output dir (`out` or `dist`)
```

For Netlify legacy path: see [`deployment.md`](deployment.md).

---

## setup (Next.js website)

**1. Choose template.** Two pre-V1 examples:
- **SaaS / Product** — Hero → Demo → Value Prop → Workflow → Examples → Integrations → CTA. Best for software, e-commerce, product companies.
- **High-Ticket Services** — Hero → Solution → Pain → Process → Competitive → Objections → Proof → Qualification → FAQ → CTA. Best for coaching, consulting, agencies, $3k+ services.

These are Devon-specific examples, not the broader Website tier. Future per-offer Website generation will produce fresh output per offer like the minisite shape.

**2. Name + location.**
- Site name (e.g., "my-landing-page")
- Location (default: `~/sites/[name]`)

**3. Check prerequisites.**
```bash
node --version          # Need 18+
pnpm --version          # Package manager
mb connect doctor --json # GitHub/provider readiness
```
If anything missing, install before proceeding:
- Wrong Node version → `nvm use 18`
- pnpm not found → `npm install -g pnpm`
- GitHub not ready → use the repair command from `mb connect doctor --json`

**4. Create GitHub repo.**
```bash
gh repo create [name] --private --clone --directory [location]
cd [location]
```

**5. Add template as upstream.**
```bash
git remote add upstream https://github.com/dmthepm/mainbranch-site-template-[saas|high-ticket].git
git fetch upstream
git merge upstream/main --allow-unrelated-histories -m "Initial template merge"
```

**6. Install dependencies.**
```bash
pnpm install
```

**7. Verify build.**
```bash
pnpm build
```
If build fails, troubleshoot before proceeding. Don't deploy a broken build.

**8. Initial commit and push.**
```bash
git add -A
git commit -m "[add] Initial site from template"
git push -u origin main
```

**9. Deploy.**
- **Cloudflare Pages (default):** `python3 .claude/skills/mb-site/scripts/pages.py create-project <name> --repo-owner <owner> --repo-name <repo> --branch main` — git-connected, auto-deploys on push. Configure build command (`pnpm build`) + output directory (`out` or `dist`) in the CF dashboard once.
- **Netlify (legacy):** see [`deployment.md`](deployment.md). Key settings: Build command = `pnpm build`, Publish directory = `out`, NODE_VERSION = `20`.

**10. Detect business repo.** Ask: "Where is your business repo with current business files?" Confirm the path has current Main Branch markers. If CWD looks like an old Main Branch repo, treat it as migration input and run `mb status --json --peek` and/or `mb doctor repair --plan` before relying on it. If the business repo has multiple offers, ask which offer this site is for.

**11. Save config.** Prefer repo-local `.mainbranch/repo.json`:

```json
{
  "schema": "mb.child_repo.v0",
  "role": "site",
  "display_name": "Website",
  "github_owner": "example-co",
  "repo_name": "example-site",
  "safe_purpose": "Public website for Example Business.",
  "parent": {
    "display_name": "Example Business",
    "github_owner": "example-co",
    "repo_name": "example",
    "remote": "github:example-co/example",
    "local_checkout": "../example"
  },
  "linked": {
    "offers": ["core/offers/flagship/offer.md"]
  },
  "return_to_hub_command": "cd ../example && claude",
  "safe_to_share": true
}
```

Use real GitHub handles and an optional relative `parent.local_checkout`; do not
commit absolute local paths. Treat `~/.mainbranch/sites.json` as a legacy
fallback only when no repo-local descriptor exists:
```json
[
  {
    "name": "<site-name>",
    "site_repo": "/absolute/path/to/site-repo",
    "business_repo": "/absolute/path/to/business-repo",
    "shape": "website",
    "template": "saas",
    "hosting": "cloudflare",
    "domain": "<your-cf-pages-or-custom-apex>"
  }
]
```

Create `~/.mainbranch/` directory if it doesn't exist.

**Exit:**
> "Site deployed at https://<url>. Run `/mb-site configure` to apply your brand, or `/mb-site build` to start customizing sections from your core business files."

---

## configure (Next.js website)

Apply brand identity from business context files to the site's visual system.

**What it reads:**
- `voice.md` — Aesthetic direction, tone, personality
- `offer.md` — Headline copy, value proposition
- `soul.md` — Mission text, credibility elements

**What it changes:**
- `app/globals.css` — CSS custom properties (colors, fonts)
- `app/layout.tsx` — Font imports, metadata
- `site-config.ts` — Brand name, tagline, metadata

**Voice-to-aesthetic derivation:**

| Voice Trait | Design Implication |
|---|---|
| Warm, personal | Rounded corners, warm palette, serif or humanist sans display font |
| Direct, authoritative | Sharp corners, high contrast, geometric sans or strong serif |
| Playful, energetic | Bold colors, larger type scale, bouncy motion, personality fonts |
| Premium, refined | Restrained palette, ample whitespace, thin weights, serif display |
| Technical, expert | Monospace accents, structured grids, muted palette with signal color |

See [`frontend-design.md`](frontend-design.md) for font pairings, color systems, and motion guidelines.

**Steps:**
1. Read `voice.md` — determine aesthetic direction
2. Read `offer.md` — extract headline, tagline, CTA text
3. Choose font pairing based on voice (see frontend-design reference)
4. Choose color palette based on brand positioning
5. Update CSS variables in `globals.css`
6. Update font imports in `layout.tsx`
7. Update metadata (title, description, OG tags) in `layout.tsx`

**Checkpoint:**
> "Preview the brand changes? Run `/mb-site preview` to see them locally, or continue to `/mb-site build` to generate sections."

---

## build (Next.js website)

The core generation mode. Reads business context files and generates page sections.

**How it works:**
1. Resolve offer context — use offer-specific `offer.md` and `audience.md` when available
2. Read business context files from the business repo (resolved paths)
3. Generate or update `site-config.ts` — the single source of all brand-specific content
4. Generate or edit component files in `components/`
5. Update page composition in `app/page.tsx`

**The site-config.ts pattern:**

All brand-specific content lives in one file. Components import from it:

```typescript
// site-config.ts
export const siteConfig = {
  brand: {
    name: "Your Business",
    tagline: "Your tagline from offer.md",
    email: "you@example.com",
  },
  hero: {
    eyebrow: "DERIVED FROM AUDIENCE.MD",
    headline: "Derived from offer.md headline",
    subhead: "Derived from offer.md value proposition",
    ctaText: "Derived from offer.md CTA",
    ctaUrl: "#pricing",
  },
  // ... sections populated from business context files
}
```

**Section types available:**

| Section Type | Purpose | Reference Source |
|---|---|---|
| `hero` | Headline, subhead, CTA, badge | offer.md, audience.md |
| `reasons-grid` | Pain point cards | audience.md |
| `process-stepper` | How it works timeline | offer.md (mechanism) |
| `credibility` | Stats, testimonials, trust | testimonials.md |
| `competitive-positioning` | Why you vs alternatives | offer.md, audience.md |
| `objection-handling` | FAQ-style objection reframes | audience.md |
| `faq` | Standard Q&A accordion | offer.md, audience.md |
| `cta-simple` | Headline + button + microcopy | offer.md |
| `cta-application` | Multi-step qualification form | audience.md, offer.md |
| `examples-grid` | Use case cards | offer.md |
| `trust-strip` | Logo bar | testimonials.md |
| `interactive-explorer` | Clickable detail showcase | offer.md (features) |
| `integration-river` | Scrolling logo marquee | offer.md (integrations) |
| `footer` | Brand, contact, legal | brand info |

See [`section-patterns.md`](section-patterns.md) for detailed generation rules per section.

**Build flows:**
- **Full rebuild:** Read all business context files → regenerate `site-config.ts` → regenerate all components.
- **Add section:** Ask which section type → read relevant reference → generate component → add to `page.tsx`.
- **Edit section:** Read current component → read relevant reference → update content and copy.

**Copy guidelines:**
- Pull language directly from business context files. Don't invent marketing speak.
- Headlines from `offer.md` — the transformation, not the feature.
- Pain points from `audience.md` — their words, not generic.
- Testimonials from `testimonials.md` only — never fabricate.
- CTAs from `offer.md` — specific action, not generic "Learn More."
- If site drives traffic to Skool, cross-reference `skool-surfaces.md` for messaging consistency between the landing page and the Skool about page.

**Design guidelines:** Follow [`frontend-design.md`](frontend-design.md):
- No generic fonts (Inter, Roboto, Arial banned)
- Bold color commitment (not safe grays)
- Hero animation is mandatory (GSAP stagger reveal)
- CTA color is sacred — nothing else shares it
- Mobile-first responsive
- `prefers-reduced-motion` respected

**Checkpoint:**
> "Section generated. Want to preview it, add another section, or publish?"

---

## preview (Next.js website)

Start local dev server for immediate feedback.

```bash
cd <site_repo> && pnpm dev
```

Server starts at `http://localhost:3000`. User reviews in browser, requests changes. Iterative — stay in preview until satisfied, then route to publish.

**Checkpoint:**
> "Looking good? Make changes, or publish when ready."

---

## publish (Next.js website)

Ship changes to production.

```bash
cd <site_repo> && pnpm build       # Verify build passes; fix before proceeding
git status && git diff --stat       # Review changes
git add -A
git commit -m "[update] Description of changes"
git push origin main
```

Cloudflare Pages auto-deploys on push (per the git-connected project from setup step 9). Netlify legacy path also auto-deploys on push.

**Exit:**
> "Pushed to GitHub. Cloudflare will auto-deploy in ~1-2 minutes (or Netlify if you set up legacy). Live URL: https://<domain>."

---

## Graduating to a website with CMS

When the website grows past ~10 pages or content needs to be edited by non-developers, `/mb-site` supports bolting on a CMS. See [`graduation.md`](graduation.md) for the Sanity / Contentful / Notion-as-CMS / etc. paths.
