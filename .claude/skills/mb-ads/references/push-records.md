# Push Records for Ads Work

This skill writes new coordinated work to `pushes/<YYYY-MM-DD-slug>/` (the
engine primitive). Examples below say "push" for the wrapping
record; this is the engine's word. If `core/vocabulary.md` defines a
display word — for example `terms.push.singular: drop` — speak the
operator's word ("drop") in conversation while still writing current
files (`pushes/...`, `type: push`, `linked_pushes`). Never rename folders,
frontmatter, link fields, JSON keys, or commands based on vocabulary.

If the repo still has legacy `campaigns/` records, preview the migration
**before** creating new push work:

```text
mb doctor                       # confirms legacy campaigns/ drift
mb migrate campaigns --plan     # read-only preview of moves
```

The word "campaign" elsewhere in this skill refers to Meta Ads campaigns
(the provider's term for its object) — not the Main Branch primitive.

When creating `push.md`, include the validator-required frontmatter and fill
the values from repo truth or operator answers. When finished creative
already exists outside git (a Drive folder, an export), ask "where do the
finished files live?" and record `media_location` plus a `media_backend`
hint (google-drive, r2, local, mb-media):

```yaml
---
type: push
slug: YYYY-MM-DD-slug
kind: launch
status: planned
health: unknown
goal: { metric: "", target: "", by: YYYY-MM-DD }
owner: ""
audience: ""
offer: core/offers/<offer>/offer.md
promise: ""
media_location: ""   # optional — where binary creative lives
media_backend: ""    # optional hint; requires media_location
---
```

The once-asked bet/decision/research question and typed-link rules live in SKILL.md.

When an ad-adjacent workflow needs a resource-delivery plan, provider setup
recipe, launch checklist, or external automation approval record, draft it
as `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` with `type: playbook`
— plans and approval records only. Do not publish, schedule, DM, reply,
mutate ad accounts, or claim a provider is supported unless `mb` and a
shipped provider adapter prove that path with docs, tests, approval gates,
and smoke evidence.
