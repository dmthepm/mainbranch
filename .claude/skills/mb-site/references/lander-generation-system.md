# Lander Generation Profile

Use this as the system profile for a one-page offer lander. The skill, not a
Python LLM wrapper, gives this profile to the active Claude Code session or a
foreground subagent.

## Inputs

- resolved offer and audience files;
- keyword-gate research when present;
- voice, proof, testimonials, visual style, and named enemies when present;
- linked launch push path;
- conversion endpoint choice;
- optional taste references or existing URLs.

## Files To Produce

For a static Cloudflare Pages-compatible site repo:

```text
index.html
_headers
og.svg
favicon.svg
README.md
```

Render `og.png` from `og.svg` after generation when the render tool is
available. Do not generate `og.png` directly from the model.

## Page Contract

One page, no nav dependency, mobile-first:

- hero with keyword-aligned promise and one primary CTA;
- recognition/problem section using audience language;
- mechanism/process section;
- proof or credibility section;
- offer/logistics section;
- FAQ or objections section;
- final CTA;
- privacy/terms links or clear hosted equivalents;
- footer with the `entity` and `contact` from `offer.md` (if missing, ask the owner and, with their OK, record them in `offer.md`).

The page can link to a hosted checkout, booking, or form, but it must not assume
provider setup that `mb site check` or operator approval has not verified.

## OG Image Rules

`og.svg` is the page-as-thumbnail. It should be readable at roughly 200px wide:

- hero text or tighter H1 echo, two lines max;
- one signature visual object that fits the offer;
- small wordmark;
- no body copy, pricing, CTAs, logo bars, stock photos, grids, or collages;
- include `og:image:alt` and `twitter:image:alt` in page metadata.

## Paid-Traffic Readiness

For paid traffic, the generated HTML must support the measurement rubric:

- leave room for GTM snippet insertion without hardcoding secrets;
- use `mb_*` dataLayer event names from
  `docs/google-ads-gtm-conversion-rubric.md` when instrumentation is selected;
- include privacy/consent posture in the page or linked docs;
- run `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
  before any ad launch recommendation.

## Quality Gate

Before calling the lander ready for operator review:

- all required files exist;
- footer/entity is present: `ENTITY` (from `offer.md`) is non-empty and not the `<legal entity from offer.md>` placeholder, `grep -c -F "$ENTITY" index.html` is at least 1, and `grep -l "&lt;legal entity" index.html` prints nothing;
- CTA links are real or explicitly marked as placeholders;
- page has title, description, canonical URL when known, OG/Twitter metadata;
- keyword cluster appears naturally without stuffing;
- no unsupported provider claims or unsafe regulated claims;
- `mb site check` state is reported when paid traffic is in scope.
