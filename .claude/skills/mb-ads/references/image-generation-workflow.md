# Image Generation Workflow

Optional image-generation workflow for producing ad images from approved
prompts and provider access. The durable product rail is the prompt, source
context, output index, approval state, and safe logical media reference.
Provider support is run-scoped until `mb` owns detection and smoke evidence.

Prompt-only/manual mode is a fallback, not the target. The product direction is
fixture-safe generation/editing plus strong artifact records and storage
boundaries.

---

## Ad Readiness Gate

Do not generate final ads when required business context is missing.

Hard-stop fields for final ad generation:

- offer;
- audience;
- current campaign goal;
- claim/proof boundary.

Soft-warning fields:

- proof;
- customer language or reviews;
- brand visual style;
- prior outcomes;
- Meta summary;
- reference images.

If a hard-stop field is missing, output an intake/source-bite plan instead of
finished ads:

```text
I do not have enough offer context to make ads yet. I can help create the
missing offer, audience, and claim-boundary files first.
```

Allowed low-context actions: intake questions, repo/source audit, ad strategy
outline, missing-info checklist, and placeholder concepts clearly marked as
placeholders. Blocked low-context actions: final ad package, provider image
generation, campaign-ready claims, and Meta-informed recommendations.

Use CLI facts first:

```bash
mb status --json --peek
mb start --json
mb connect doctor --json
mb ads meta summary --json   # only if ready and operator approved
```

If a stable readiness check emerges from this experiment, propose
`mb ads readiness --json` as a future command. Do not invent facts in skill
prose.

---

## Creative Direction Contract

Before any provider call, turn the push brief and business context into 3 to 6
reviewable Facebook image-ad concepts. The useful artifact is the creative
decision, not merely the generated file. A concept should pass this litmus test:
could this image have come only from this business repo? If it could fit a
generic productivity app, coaching offer, or accounting tool, do not generate it
unless the operator is intentionally testing broad top-of-funnel imagery.

Read available context before drafting concepts:

- resolved offer and audience files;
- proof and typicality context;
- `core/brand/visual-style.md` when present;
- the push brief or static-ad batch;
- compact Meta summary only when the operator approved a read-only account
  summary and `mb` reports it is ready;
- reference images already represented by safe `mb-media://...` handles.

First extract 5 to 10 source bites from the repo, then choose the 3 strongest
ones to visualize. Source bites can come from customer language, the offer,
proof, research, founder notes, a push brief, prior outcomes, visual style, or
operator-provided inspiration. A source bite proves what the concept latched
onto before any image prompt exists.

If there is no source bite, mark the concept `source_light: true` and do not
generate unless the operator explicitly approves broad exploration.

MAIN-374 treats creative playbooks as emerging metadata for a router
experiment, not a full official schema. Use `creative_playbook_id` on every
candidate and keep the list small until generated candidates prove which
patterns work:

- `native_problem_scene`
- `specific_object_metaphor`
- `proof_artifact`
- `myth_vs_fact`
- `with_without_transformation`
- `crossed_out_problem_list`
- `founder_pov`
- `high_contrast_poster`
- `simple_chart_comparison`
- `testimonials_with_artifact`
- `us_vs_them_split`
- `simple_list_framework`

Use `conversion_informed`, not `high_converting`, unless the business has live
result data.

Each concept must record:

- `concept_id`;
- `status`: `planned`, `generated`, `rejected`, or `needs_revision`;
- `creative_playbook_id` and optional `creative_playbook`: playbook-router
  candidate metadata, not a canonical library;
- `router_inputs`: offer type, audience, source-bite type, proof availability,
  brand style, platform, and niche when known;
- `router_reason`: why the playbook fits this source bite and audience;
- `playbook_fit`: 1 to 5 scores for source-bite fit, offer fit, audience fit,
  visual distinctiveness, and conversion-pattern fit;
- `source_bite`: source file, type, phrase, insight, and visual translation;
- `genericness_check`: whether the idea could fit generic adjacent products and
  a 1 to 5 `specific_to_this_offer` score;
- `avoidance_strategy`: what generic or unsafe creative patterns the concept
  avoids, any soft-avoid pattern it intentionally uses, and why;
- `external_pattern_signal`: optional scratch/source signal only, with
  `primary_source_verified: false` unless primary research has been checked;
- `reference_influence_test`: `none`, `text_traits`, or `image_reference`,
  plus specificity, native-feed-fit, and AI-slop-risk effects;
- `reference_influence`: lean future hook with `mode`, `influence_score:
  null`, and `copy_risk`;
- `viewer_scroll_context`;
- `first_second_read`;
- `audience_state`;
- `visual_job`;
- `visual_metaphor` or scene;
- `composition`;
- `visual_hierarchy`;
- `camera_language`;
- `style_strength`;
- `emotional_tone`;
- `placement`;
- `text_overlay_plan`;
- `source_files`;
- `claim_boundary`;
- `references`;
- `prompt`;
- `negative_constraints`;
- `review`.

External creative research, including Grok or ad-research synthesis, is only a
source signal until verified against primary sources. Do not commit raw Grok
dumps, screenshots, provider payloads, or unverified claims.

Use this shape inside push-local `image-index.md` (a full worked example lives
in the image-rail test fixtures; omit fields you have no value for):

```yaml
schema: mainbranch.image_index.v0
push_slug: 2026-05-ad-test
conversion_language: conversion_informed
review_rule: Beautiful but no click reason = reject.
ad_readiness_gate:
  state: ready            # hard-stop fields: offer, audience, campaign_goal, claim_proof_boundary
  hard_stop_missing: []
  soft_warning_missing: [proof, customer_language, brand_visual_style, prior_outcomes, meta_summary, reference_images]
image_generation_gate:
  required_before_provider_generation:
    - selected_concept
    - prompt_record
    - safe_media_storage
    - image_index_target
    - credential_state
    - operator_approval_for_live_provider_call
post_processing_plan:
  resize_target: 1440x1800
  overlay_method: deterministic_overlay_step
  validation: Preview in Meta Ads Manager before launch.
placement_presets:       # sizes and safe zones: see ad-media-specs.md; verify current Ads Manager specs
  facebook_feed_portrait_4x5: {aspect_ratio: "4:5", recommended_generation_size: 1440x1800, final_export_size: 1440x1800, safe_zone: {top: 10%, bottom: 10%, sides: 10%}}
  facebook_feed_square_1x1: {aspect_ratio: "1:1", recommended_generation_size: 1440x1440, final_export_size: 1080x1080, safe_zone: {top: 10%, bottom: 10%, sides: 10%}}
  facebook_story_reels_9x16: {aspect_ratio: "9:16", recommended_generation_size: 1440x2560, final_export_size: 1080x1920, safe_zone: {top: 14%, bottom: 35%, sides: 6%}}
reference_roles: [logo, product_photo, style_reference, screenshot_reference, background, mask_source]
concepts:
  - concept_id: lost-thread-branch-map
    status: planned
    prompt_key: lost-thread-branch-map.v1
    creative_playbook_id: specific_object_metaphor
    router_inputs: {niche: founder_tool, offer_type: open_source_business_os, audience: solo founder or operator, source_bite_type: customer_language, proof_available: false, platform: facebook_feed}
    router_reason: The source bite is emotional and abstract, so a specific object metaphor beats chart proof.
    playbook_fit: {source_bite_fit: 5, offer_fit: 5, audience_fit: 4, visual_distinctiveness: 5, conversion_pattern_fit: 4}
    source_bite:
      source_file: research/customer-language.md
      source_type: customer_language
      extracted_phrase: I keep losing the thread
      insight: Continuity breaks across tools.
      visual_translation: tangled red thread becoming one clean branch map
    genericness_check: {could_fit_generic_productivity_app: false, could_fit_any_coaching_offer: false, could_fit_accounting_software: false, specific_to_this_offer: 5, reason: "..."}
    avoidance_strategy: {avoids: [stock-photo business imagery, fake dashboard, generic SaaS gradient], intentionally_uses: [], reason: "..."}
    reference_influence: {mode: none, influence_score: null, copy_risk: pass}
    viewer_scroll_context: cold Facebook feed
    first_second_read: lost business thread becomes one durable branch map
    audience_state: resuming work after context switching
    visual_job: make continuity loss visible before showing the fix
    visual_metaphor: tangled red thread resolving into a clean branch map
    composition: one clear branch path, upper-right overlay space
    visual_hierarchy: {primary_focal_point: red thread becoming a branch map, text_zone: upper right}
    camera_language: slight top-down editorial
    style_strength: specific metaphor, restrained polish
    emotional_tone: relief after broken continuity
    placement: facebook_feed_portrait_4x5
    text_overlay_plan: text-free base image; deterministic overlay later, max 4 words
    source_files: [core/offer.md, core/audience.md, pushes/2026-05-ad-test/push.md]
    claim_boundary: do not imply guaranteed revenue or Meta partnership
    references: [{id: style-001, role: style_reference, path: "mb-media://references/style-001.png", safe_to_share: false, use_for: color mood, do_not_copy: exact subject, logos, text}]
    prompt: Create a Facebook image ad base scene with a clear focal point, mobile-safe whitespace, no rendered text, no real logos, no private data.
    negative_constraints: [no real Meta UI, no real logos, no tiny text, no revenue screenshots, no before/after income claim]
    likely_click_reason: A founder who feels context slipping away recognizes the lost-thread problem before reading the overlay.
    review:                # rubric: see Creative Review Rubric below
      status: accepted
      scores: {one_second_clarity: 5, visual_hook_strength: 5, specificity: 5, brand_fit: 5, source_bite_fit: 5, specific_to_this_offer: 5, native_feed_fit: 5, ai_generic_risk: 1}
      decision: accept
assets:
  - asset_id: lost-thread-branch-map-001
    concept_id: lost-thread-branch-map
    provider: openai
    model: gpt-image-2
    prompt_key: lost-thread-branch-map.v1
    state: blocked
    blocker_code: missing_openai_api_key
    output_reference: mb-media://pushes/2026-05-ad-test/images/lost-thread-branch-map-001.png
    committed_binary: false
```

Concepts and assets must be linkable through `concept_id`. `image-index.md`
can contain planned concepts even when no provider generated an image.

---

## Prompt Strategy

Use source bites and the concept brief before writing provider prompts. A small
fixture-safe comparison for this contract favored "creative-director brief
first" because it makes the reviewer answer what repo fact the image latched
onto, who the image is for, what job the image does, which placement it serves,
and what it must not claim before generation.

Keep these reusable patterns:

- direct prompts are acceptable for quick fixture smoke only;
- creative-director briefs are the default for real ad concepts;
- reference-aware prompts should say what to borrow and what not to copy;
- no-text base images are the default when final ad text needs control;
- text-in-image prompts are testable, but should be marked for readability
  review and not become the default final-ad path.

Creative direction principles to encode in each concept:

- Native but specific beats generic polish. Use feed-native or UGC-like scenes
  when the brand allows it, but still specify the subject, environment,
  lighting, camera language, and emotional state.
- Build a small brand world before prompting: mood, palette, environment,
  texture/material cues, and style strength.
- Design the visual hierarchy explicitly: primary focal point, secondary
  support, and text zone.
- Use concept diversity before micro-variants: different audience states,
  metaphors, funnel emotions, and placements.
- Treat AI output as raw material that needs human review, compliance checks,
  and final overlay/polish.

Default flow:

```text
repo facts -> ad readiness -> source bites -> playbook router -> concepts ->
review/genericness checks -> prompt records -> generation or fallback ->
review board -> image-index
```

Creative playbooks are optional overlays, not the base system. Suggest one only
when it fits the repo's source bites, offer, audience, and brand context. Do not
make any one metaphor universal across businesses.

The review board should answer: "Which playbook produced the best actual ad
candidate?" Do not reduce review to "Which image looked best?"

Write the prompt record before provider generation. If the selected provider is
prompt-only or cannot accept image references, convert approved references into
explicit `reference_trait_extraction` fields such as palette, composition,
lighting, identity/persona constraints, and `do_not_copy`; do not imply image
reference support when the provider path cannot use it.

### Avoidance Layer

Hard no items are unsafe or misleading and should be rejected before generation:

- fake Meta, Facebook, or Instagram UI;
- fake dashboards with performance numbers;
- fake revenue screenshots;
- real logos or brand marks without approval;
- readable customer or member data;
- private screenshots;
- fake testimonials;
- before/after income proof;
- tiny unreadable text when text is part of the output.

Soft avoid items are not forbidden, but require an intentional reason in
`avoidance_strategy.intentionally_uses`:

- clean desk productivity scene;
- coffee, notebook, plant, and laptop still life;
- split-screen chaos/order composition;
- centered product on a white or gradient background;
- polished stock-photo business people;
- blue or purple SaaS gradient;
- hologram dashboard;
- glossy 3D icons;
- generic growth chart;
- overly cinematic lighting for everyday products;
- "professional photoshoot", "modern minimalist aesthetic", and similar prompt
  language;
- website hero composition.

Use safe wording in public docs and review notes. Do not claim a platform or
algorithm penalizes a pattern unless current primary-source evidence supports
that exact claim. Prefer: "This has high genericness risk, weak native-feed fit,
and should be revised before generation."

Prompt rewrite example:

```text
Bad: Professional photoshoot of a clean modern productivity desk with laptop,
coffee, notebook, and plant.

Better: A tactile visual metaphor: tangled red thread and business decision
cards forming a maze, with one clear branch path emerging through it. No text,
no logos, no fake UI, high-contrast feed-native still life.
```

Do not commit raw provider payloads, raw generated images, private paths,
credentials, or raw research dumps. Summarize only the reusable workflow
pattern in committed docs or fixtures.

---

## Provider Choice

Use the provider and model verified for this run. Do not hard-code a private
environment file, assume a provider is configured, or claim Main Branch supports
image generation because this reference exists.

Current provider notes checked 2026-05-13 (fal.ai row checked 2026-06-10)
against the accepted creative media generation decision:
`decisions/2026-05-13-creative-media-generation-rails.md`.

| Provider | Model family | Use |
| --- | --- | --- |
| OpenAI Image API / Responses API | `gpt-image-2` | Default smoked rail for fixture-safe static image generation/editing. Use only when configured for the run and record the exact model/snapshot. |
| fal.ai sync API (`fal.run`) | `fal-ai/flux/dev` (FLUX) | Explicitly selected alternative smoked rail with the same approval, credential, review, and `image-index.md` boundary as the OpenAI rail. Selection is explicit config; a local `FAL_KEY` never auto-selects fal.ai. |
| Google Gemini API | Nano Banana image-model family | Candidate comparison rail for future work. Do not treat it as proven ad-grade output until a smoke/test run records the current exact model ID, prompt, output, review notes, and final asset quality. |
| BFL FLUX.2 / ComfyUI | FLUX.2 family | Candidate local/private or heavy-reference rail beyond the smoked fal.ai FLUX endpoint, after the metadata contract proves out. |
| Manual provider use | `manual` | Safe fallback when no approved provider is configured. Save prompts and asset records for the operator to use manually. |

If model names or pricing matter to the recommendation, check the provider's
current docs before generating and record the docs-checked date in
`image-index.md`.

Do not hard-code exact candidate-provider model IDs from memory. OpenAI
`gpt-image-2` is the first readiness target; other provider/model IDs must be
checked against current primary docs and pinned per run.

---

## Detection

At triage use `mb status --json --peek` / `mb connect doctor --json` for provider readiness; those may not prove a media API key exists, so check environment variables only when the selected mode needs generation. If a provider is available, show provider/model, estimated cost, output path and required approval before generating. If not, output text prompts only: "Image prompts saved. Paste them into your chosen image tool, or configure an approved provider before asking Main Branch to generate files directly."

---

## Media Storage Boundary

Commit the push-local `image-index.md` record by default, not generated image
binaries. Generated or edited media should resolve through configured storage:

- local gitignored media cache, such as `.mb/media/`;
- private operator media folder, such as `~/MainBranchMedia/<business>/`;
- external media folder;
- site repo/public folder only after explicit approval.

Committed records should use safe logical references such as
`mb-media://pushes/2026-05-ad-test/images/hero-001.png`, not private absolute
paths.

Reference images should carry roles. The important fields are what to borrow
and what not to copy. If the operator provides inspiration, ask what should be
borrowed before using it; inspiration is a role-tagged instruction, not vague
permission to copy the source image.

```yaml
references:
  - id: inspo-001
    role: style_reference          # also: logo, product_photo, screenshot_reference, background, mask_source
    path: mb-media://pushes/2026-05-ad-test/references/inspo-001.png
    safe_to_share: false
    approval_required: true
    privacy_level: private
    use_for: [composition tension, gritty lighting, scroll-stopping object metaphor]
    do_not_copy: [exact subject, exact layout, text, brand marks]
    operator_note: I like how specific and hard to ignore this feels.
```

Logo references use brand-mark placement only after explicit approval and must not copy private file paths or unapproved lockup variants.

---

## Generate / Edit / Mask Decision Tree

- No image input: generate.
- Image input plus broad natural-language change: edit.
- Image input plus exact region change: mask edit.
- Many prompts, many variants, or repeated reference combinations: batch later,
  after the single-image rail is stable.

Recommended implementation shape:

```bash
mb image generate --prompt "..." --out mb-media://pushes/2026-05-ad-test/images/hero-001.png
mb image edit --prompt "..." --ref-image mb-media://brand/logo.png --out mb-media://pushes/2026-05-ad-test/images/hero-002.png
mb image edit --prompt "..." --ref-image mb-media://pushes/2026-05-ad-test/references/product.webp --mask mb-media://pushes/2026-05-ad-test/references/mask.png --out mb-media://pushes/2026-05-ad-test/images/hero-003.png
```

This generate/edit shape is a decision recommendation, not a shipped command
claim. The first shipped smoke surface is narrower:

```bash
mb image smoke-openai --repo "$BUSINESS_REPO" --json
mb image smoke-openai --repo "$BUSINESS_REPO" --generate --json
mb image smoke-fal --repo "$BUSINESS_REPO" --json
mb image smoke-fal --repo "$BUSINESS_REPO" --generate --json
```

Run without `--generate` to create a safe blocked record. Add `--generate` only
after the operator approves one fixture-safe provider call and local provider
credentials are available outside chat and tracked repo files.

Provider selection is explicit: each smoke command names exactly one provider,
and the OpenAI rail stays the default. `mb image smoke-fal` uses the fal.run
sync endpoint with a local `FAL_KEY` (environment-first); the presence of a
`FAL_KEY` never switches the OpenAI surfaces to fal.ai.

---

## Generation via Python SDK

The `mb image smoke-openai` command owns the default fixture-safe smoke path;
`mb image smoke-fal` follows the same record and storage boundary over the
fal.run REST endpoint without an extra SDK dependency.
When generation is approved, the OpenAI rail uses the Python SDK shape below and
writes the binary to configured media storage while committing only the
push-local `image-index.md` record. MCP servers, runtime-native image tools, or
another SDK can be used only when they are configured for the run and the
artifact metadata records the provider/model.

```python
import base64
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

response = client.images.generate(
    model=os.environ.get("MB_IMAGE_MODEL", "gpt-image-2"),
    prompt=prompt_text,
    size=os.environ.get("MB_IMAGE_SIZE", "1024x1536"),
    quality=os.environ.get("MB_IMAGE_QUALITY", "medium"),
)

image_bytes = base64.b64decode(response.data[0].b64_json)
with open("output.png", "wb") as f:
    f.write(image_bytes)
```

---

## Post-Processing Pipeline (MANDATORY — Never Skip)

**Raw provider output is not automatically the final deliverable.** Post-process
every ad image immediately after generation. Never save raw provider files as
final output unless the operator explicitly approves that exact file as the
final asset.

### Steps (run on EVERY generated image)

1. **Resize** to target dimensions (LANCZOS resampling)
2. **Convert** PNG → JPEG
3. **Compress** to under 300KB (quality stepping: 85 → 75 → 65 → 55 → 45)
4. **Delete the raw PNG** after both formats are saved
5. **Verify** final JPEG is under 300KB and at correct dimensions

### Target Dimensions

| Format | Dimensions | Use |
|--------|-----------|-----|
| 4:5 (feed) | 1440×1800 | Facebook and Instagram feeds |
| 9:16 (vertical) | 1080×1920 | Stories, Reels, full-screen mobile |

### Python Post-Processing

```python
from PIL import Image
import os

def post_process(input_path, output_path, width, height, max_kb=300):
    img = Image.open(input_path).convert('RGB')
    img = img.resize((width, height), Image.LANCZOS)
    for quality in [85, 75, 65, 55, 45]:
        img.save(output_path, 'JPEG', quality=quality, optimize=True)
        if os.path.getsize(output_path) < max_kb * 1024:
            return quality
    return 45  # best effort
```

### Provider Watermarking

Record provider watermarking or provenance metadata when known. Do not promise
that all providers expose the same provenance, watermarking, or C2PA behavior.

---

## Format Pair: 4:5 + 9:16

Plan the default pair as 4:5 (Feeds) and 9:16 (Stories and Reels); 1:1 only via the `facebook_feed_square_1x1` preset when a placement or reused asset needs it. Compose each ratio for its placement rather than cropping one from the other; when one generation must serve both, generate the 9:16 with critical content inside the 4:5 centre band, crop the 4:5, and check both against [ad-media-specs.md](ad-media-specs.md) (safe bands, composition, current Ads Manager specs). Each concept prompt states the aspect ratio, critical content inside its safe band, and atmospheric elements in the margins.

---

## Smart Mix Recommendation

Based on `core/brand/visual-style.md` depth:

| visual-style.md State | Mix |
|----------------------|-----|
| Rich (80+ lines, hex codes, mood, prompts) | 60% on-brand, 40% freestyle |
| Adequate (20-80 lines) | 50/50 |
| Stub (< 20 lines) | 30% on-brand, 70% freestyle |
| Missing | 100% freestyle. Offer to create. |

**On-brand images** use color palette, typography direction, mood, and prompt fragments from visual-style.md.

**Freestyle images** ignore brand constraints. Pattern interrupts, meme-style, lo-fi, native/ugly ads — these intentionally break from brand to stop scrolling.

---

## Cost Estimation

Before generating, show cost estimate and get approval:

```
Image Generation Estimate:
  5 angles × 3 styles × 1 format = 15 images
  Provider/model: OpenAI / gpt-image-2
  Docs checked: 2026-05-13
  Estimated cost: $X from current provider pricing
  Storage: mb-media://pushes/2026-05-ad-test/images/
  Record: pushes/2026-05-ad-test/image-index.md

  Proceed? (y/n)
```

Actual cost depends on prompt complexity and retries.

---

## Text-on-Image: Prefer Deterministic Final Overlays

GPT Image 2 is the first rail to smoke partly because current validation
points to strong text rendering. Still, final paid creative often needs exact
copy, exact safe-zone placement, and predictable export sizes. When exact text
matters, generate the background or composition and apply final text with a
deterministic post-processing step such as Pillow.

### Workflow

1. **Provider generates the background or composition**
2. **Pillow composites text onto the background** — white bold text, drop shadow, centered

### Text Positioning (Critical)

On 9:16 images the bottom ~25-30% is covered by UI (caption, CTA, likes) and the top ~10% by the progress bar and account icon. Place text at 35-40% from the top: Pillow Y = `int(height * 0.38)`, not `height // 2`.

### Prompt Pattern for Text-Free Backgrounds

```
"Generate a [style] background image for a Facebook ad.
9:16 aspect ratio (1080x1920px).
NO TEXT on the image. This is a background for text overlay.
Leave generous clean space in the center-upper area for white text.
[scene/mood/brand directives]"
```

---

## Batch Generation Flow

Order: copy saved -> approved pre-review checkpoint -> main conversation writes `prompts.json` (keyed by target filename) -> compliance agents and image agents spawn in parallel in one message -> synthesize (retry failed images, surface P1s, show the P2/P3 diff, apply copy fixes only after approval, write `review-log.md` if approved, write `image-index.md`) -> approved post-review checkpoint. The pipeline steps live in [post-generation-pipeline.md](post-generation-pipeline.md).

---

## Parallel Agent Spawning

Image generation uses **one subagent per image** (or per 2-3 images for large batches). This is faster than sequential generation and aligns with how Claude Code handles independent tasks.

### How It Works

Main conversation writes `prompts.json` (key = target filename; value = prompt text, style on-brand/freestyle, brand context) before spawning anything. All agents, compliance and image, spawn in one message as `general-purpose`. Each image agent reads its prompt(s), uses the already-configured provider environment, makes one API call per image, post-processes immediately, verifies the final JPEG in configured media storage, and returns `{output_reference: "mb-media://pushes/2026-05-ad-test/images/001_01_graphic_vertical.jpg", status, provider, model, cost_estimate}` (or `status: "fail"` with the error). Main collects results and retries failures with fresh single-image agents.

### Batching Strategy

| Image Count | Strategy | Agents Spawned |
|-------------|----------|----------------|
| 1-8 | One agent per image | N agents |
| 9-15 | One agent per image | N agents |
| 16-30 | Batch 2-3 per agent | ~10-15 agents |

### Rate Limiting

Each agent adds a `time.sleep(2)` before its first API call. Natural stagger from agent startup timing provides additional spacing. If an agent receives a 429 (rate limit), it retries once after a 5-second sleep. If the retry also fails, it returns `status: "fail"` and main conversation handles the retry.

### Agent Prompt Template

```
You are an image generation agent. Generate the assigned image(s) and return results.

Provider setup:
  Use the provider/model selected by the main conversation.
  Do not ask the operator to paste API keys into chat.

Your assigned image(s) from prompts.json at {output_dir}/prompts.json:
  Key(s): {filename_key(s)}

For EACH assigned image:
1. Read the prompt from prompts.json
2. Resolve the assigned `mb-media://...` reference to configured media storage
3. Run Python: generate via the selected provider/model, save raw PNG in configured media storage
4. Run Python: post-process (resize to target dims, JPEG compress under 300KB, delete raw PNG)
5. Verify final JPEG exists in configured media storage and return the safe logical reference
6. Return the logical media reference, provider, model, cost, and status

If rate-limited (429): sleep 5 seconds, retry once.
If retry fails: return status "fail" with error message. Do NOT keep retrying.
```

### Failure Handling

- Agent returns `status: "fail"` with error details
- Main conversation spawns a new single-image agent for just that prompt
- One retry per image. If second attempt fails, log the failure in `image-index.md` and note which prompts need manual generation.

---

## Output Structure

```
pushes/YYYY-MM-DD-static-ads-{campaign}/
├── static-ads-batch-001.md        ← Copy (Batch 1)
├── proposed-compliance-fixes.json ← Compliance proposals
├── review-log.md                  ← Compliance changes after approval
└── image-index.md                 ← Maps prompts, provider metadata, review
                                      state, and mb-media:// references
```

`image-index.md` stores logical media references that resolve to configured
storage, not generated binaries in the push folder:

Each asset carries `asset_id`, `output_reference: mb-media://pushes/YYYY-MM-DD-static-ads-{campaign}/images/<name>.jpg`, `storage_backend: mb-media` and `committed_binary: false`.

### Image Naming Convention

```
{batch}_{sequence}_{style}_{format}.jpg

Examples:
001_01_graphic_feed.jpg
001_01_graphic_vertical.jpg
001_02_lofi_feed.jpg
001_03_interrupt_feed.jpg
001_04_oneliner_feed.jpg
```

---

## Image Index Metadata

Every generated image batch gets an `image-index.md` carrying the schema above: concepts with playbook IDs, router inputs and fit scores; `concept_id` links to assets; provider and model (or `manual`); docs-checked date; source files read; prompt text or key; placement preset and safe zones; reference roles, safe logical paths, `use_for` and `do_not_copy`; structured review; output dimensions, format and post-processing; estimated and actual cost; failure/retry count; storage backend label; approval state.
