---
date: 2026-05-13
status: accepted
tags: [ads, creative, media-generation, providers, skills]
---

# Creative Media Generation Rails

## Decision

Treat creative media generation as an optional Ship rail, not a core `mb`
provider integration yet.

Main Branch can help operators plan, prompt, review, and record static ad
images, landing-page visuals, organic assets, and simple motion exports. It
should not claim first-class image, video, motion, model-routing, or
platform-creative generation support until the exact provider path has current
docs, setup detection, approval gates, smoke evidence, and reproducibility
metadata.

The product direction is not a prompt library. The deeper loop is:

1. the agent understands the business context;
2. the agent generates or helps produce the creative asset;
3. the agent records the sources, references, prompt, model, and storage
   location it used;
4. the operator reviews and approves the asset before publishing or spending;
5. the system can later connect creative assets to outcomes.

The first readiness rail should be:

1. **Prompt and output record first.** Store the creative brief, prompts,
   source files, claim/proof context, provider/model, output dimensions,
   post-processing settings, cost, retries, review state, and safe logical
   media references.
2. **OpenAI GPT Image 2 first for provider smoke.** Use a direct OpenAI
   Image API or thin CLI wrapper for fixture-safe static image generation and
   editing. Record the exact model, snapshot when available, docs-checked date,
   prompt, dimensions, quality, usage/cost facts, and output path.
3. **Configurable media storage.** Commit the durable asset record by default,
   not the generated image binary. Store media in a configured local/private
   media location, external media folder, or explicitly approved site/public
   folder, and record a safe logical media reference.
4. **Prompt-only/manual fallback when no approved provider is configured.**
   Prompt-only mode is a safe fallback, not the target rail. The agent may save
   prompts and an asset record for manual provider use, but must not ask the
   operator to paste provider secrets into chat or committed files.
5. **Deterministic local motion before raw AI video.** Use inspectable
   Remotion/FFmpeg-style render settings before accepting raw AI video
   providers as a supported rail.
6. **No broad model router until one rail is boring.** Google Gemini / Nano
   Banana, BFL FLUX.2, xAI Imagine, Ideogram, Runway, Kling, Luma, and similar
   tools remain candidate or reference rails until each has its own setup,
   smoke, cost, and artifact-record evidence.

## What This Changes

This decision supersedes the earlier Google-first image guidance in
`/mb-ads` references. Google remains a candidate provider, but the next
implementation slice should validate the narrower OpenAI rail first because
it has a direct official API surface, clear model docs, familiar SDK/CLI
patterns, and strong community skill references for Claude Code and Codex-style
agent workflows.

This does not mean Main Branch supports OpenAI image generation today. It means
OpenAI GPT Image 2 is the first provider path to smoke for MAIN-362.

## Runtime Boundary

Claude Code does not provide native image generation as a Main Branch runtime
claim. It can call external tools through skills, Bash scripts, MCP servers, or
other configured integrations. Main Branch may ship Claude Code skill guidance
that invokes an approved image rail only after the rail has setup detection,
approval language, and smoke evidence.

Claude Design is a separate Anthropic Labs product. It can be useful
inspiration for design/prototype workflows, but it is not evidence that Claude
Code natively generates image assets for Main Branch.

Codex and other runtimes may expose their own image tools or install community
skills, but Main Branch should not depend on runtime-native image generation
until compatibility docs and runtime smoke evidence cover that exact surface.

## Repository Placement

Do not create a new top-level `brandkit/`, `outputs/`, or `artifacts/` folder
as the first rail.

Use current business-repo vocabulary:

- brand source context lives in `core/brand/visual-style.md` and related
  `core/brand/` files;
- coordinated ad, launch, site, organic, or creative work lives under
  `pushes/<YYYY-MM-DD-slug>/`;
- the durable committed record for a batch is `image-index.md` or another
  explicitly named push artifact that maps prompts, references, metadata,
  review state, and final media references;
- generated image binaries are not committed by default;
- media storage is configurable. Acceptable first options include a local
  gitignored media cache such as `.mb/media/`, a private operator folder such
  as `~/MainBranchMedia/<business>/`, an external media folder, or a site
  repo/public folder only after explicit approval;
- committed records should store safe logical media references such as
  `mb-media://pushes/2026-05-ad-test/images/hero-001.png`, not private
  absolute paths;
- large binaries are optional business-repo content, not required source of
  truth. Store large assets in the configured media location that fits the
  operator's repo boundary.

The legacy `outputs/` vocabulary should not be used for new generated work.

## Credential And Secret Boundary

OpenAI image generation remains a creative playbook rail for now, not a full
`mb connect` provider. But any provider credential used by the rail must follow
the existing Main Branch secret boundary:

- never ask the operator to paste provider secrets into chat;
- never commit provider keys, raw tokens, private environment files, or local
  credential paths;
- prefer existing `SecretStore` / Keychain-style storage when a CLI setup path
  exists;
- allow environment variables only as local runtime input, not as committed
  configuration;
- artifact records may include safe credential metadata such as
  `credential_ref: openai:image-generation` or
  `credential_state: configured`, but never the secret value;
- if no approved credential is available, fall back to prompt-only/manual mode.

Safe metadata:

```yaml
provider: openai
model: gpt-image-2
credential_ref: openai:image-generation
credential_state: configured
output_reference: mb-media://pushes/2026-05-ad-test/images/hero-001.png
```

Unsafe metadata:

```yaml
api_key: sk-...
token_path: /Users/<operator>/.config/provider/token
env_file: ~/.config/provider/.env
private_absolute_media_path: /Users/<operator>/PrivateMedia/hero-001.png
```

Only introduce `mb connect openai` or `mb connect image openai` later if Main
Branch needs stable provider readiness facts in `mb status --json --peek`.
Until then, keep this playbook-first with a shared artifact/media contract.

## Artifact Metadata Contract

Every generated, edited, manually produced, or template-rendered creative asset
record should include the fields below. A batch can store this as one
`image-index.md` with structured entries instead of one sidecar file per image.

Required for all assets:

- `asset_id` or stable filename key;
- `rail`: `provider`, `manual`, or `template`;
- `provider`: provider name, or `manual`;
- `model` or tool label;
- exact model snapshot/version when available;
- docs-checked date when provider/model guidance affects the run;
- source files read, such as offer, audience, proof, voice, content strategy,
  visual style, push, playbook, or operator-provided references;
- source file public/private status when relevant to sharing;
- prompt text and negative constraints;
- dimensions, aspect ratio, format, compression, crop, and safe-zone rules;
- quality or generation setting when applicable;
- cost estimate, provider usage details when available, and actual cost when
  known;
- failure, retry, and timeout count;
- post-processing notes;
- safe logical output reference for each final asset;
- storage backend label, such as `mb-media`, `site-public`, `external-media`,
  or `manual`;
- approval/review status;
- `safe_to_share` status;
- generated-at or manually-produced-at timestamp;
- operator notes.

Optional when useful:

- reference image paths and roles;
- mask path;
- seed or deterministic render settings;
- prompt-template name;
- provider request ID when safe to record;
- watermark/provenance notes;
- manual provider URL or account label when public-safe;
- supersedes/replaces link to a prior asset.

Do not store secrets, raw private account IDs, customer/member data, private
provider exports, or unapproved brand/customer assets in public examples,
fixtures, committed docs, or issue comments.

Reference images should preserve roles without leaking private paths:

```yaml
references:
  - id: logo
    role: logo
    path: mb-media://brand/logo.png
    safe_to_share: false
  - id: product
    role: product_photo
    path: mb-media://pushes/2026-05-ad-test/references/product.webp
    safe_to_share: false
```

## Cost / Benefit Notes

Costs below were checked on 2026-05-13 and are decision context, not durable
pricing guarantees. Any generation run that recommends a provider must recheck
current provider docs or console pricing when the cost matters to the operator.

| Provider / rail | Current cost signal | Benefit | Cost / risk |
| --- | --- | --- | --- |
| OpenAI GPT Image 2 | Official pricing lists GPT Image 2 examples at about `$0.005` to `$0.211` per generated image depending on size and quality, with 1536x1024 medium around `$0.041`, plus input token costs for prompt/reference images. | Strong first rail for ad/static creative because the official API supports generation, editing, flexible sizes, quality controls, `b64_json` output, SDK and CLI paths, and a dated snapshot (`gpt-image-2-2026-04-21`). Community Claude Code/Codex skill references are unusually aligned with this workflow. | May require API organization verification. Pricing is token/resolution/quality based, exact text placement can still fail, and Main Branch still needs setup detection, approval copy, fake-asset smoke, and artifact records before support claims. |
| Google Gemini / Nano Banana image models | Official Gemini pricing lists image generation examples around `$0.039` per image for output images up to 1024x1024, with batch discounts in some tiers. | Strong comparison candidate for fast image iteration and Google ecosystem workflows. | Model names and preview labels move quickly. Earlier Google-first guidance became stale, so Main Branch should not make this the first rail without fresh smoke and exact model pinning. |
| BFL FLUX.2 / ComfyUI | BFL lists FLUX.2 API pricing from roughly `$0.014` to `$0.07+` per image depending on model and resolution; some FLUX.2 Klein weights are local/open or non-commercial. | Best candidate for local/private, high-volume, heavy-reference, or ComfyUI-style workflows after the metadata contract is stable. | Heavier setup, licensing distinctions, local GPU/runtime burden, and more moving parts than the first direct OpenAI rail. |
| xAI Grok Imagine | Official xAI pricing lists flat image generation at `$0.02`, `$0.05`, or `$0.07` per image depending on model tier, plus input-image charges for editing. | Credible low-friction experimentation rail, and flat per-image pricing is easy to explain. | Needs separate policy, moderation, setup, URL-expiration, and artifact-record smoke before support language. |
| Deterministic Remotion / FFmpeg | Local compute and storage rather than per-image generation fees. | Best first motion/export rail because source, timing, captions, crops, and variants are inspectable and reproducible. | Requires template work and local render dependencies. It does not solve novel image generation by itself. |
| Raw AI video providers | Often priced per second, credit, tier, or model and usually more expensive than static images. | Useful for future creative exploration when the operator accepts cost and lower reproducibility. | Higher policy, latency, cost, account-access, and reproducibility risk; keep out of the first MAIN-362 implementation. |

### OpenAI First-Rail Ad-Volume Math

Use this table as a first implementation planning aid, not as a billing
guarantee. It is based on OpenAI pricing examples checked on 2026-05-13 and
excludes prompt/reference-image input tokens, retries, edits, storage,
post-processing, and any provider-side pricing changes.

| OpenAI `gpt-image-2` example | Per-image example cost | 100 images | 500 images | 1,000 images | 5,000 images |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1024x1024 `low` | `$0.006` | `$0.60` | `$3.00` | `$6.00` | `$30.00` |
| 1024x1024 `medium` | `$0.053` | `$5.30` | `$26.50` | `$53.00` | `$265.00` |
| 1024x1024 `high` | `$0.211` | `$21.10` | `$105.50` | `$211.00` | `$1,055.00` |
| 1536x1024 `low` | `$0.005` | `$0.50` | `$2.50` | `$5.00` | `$25.00` |
| 1536x1024 `medium` | `$0.041` | `$4.10` | `$20.50` | `$41.00` | `$205.00` |
| 1536x1024 `high` | `$0.165` | `$16.50` | `$82.50` | `$165.00` | `$825.00` |

The first rail should make the cost visible before generation and record both
estimated and actual cost when the provider exposes usage. For testing, default
to low or medium quality. Use high quality for final typography, packaging, or
identity-sensitive assets only after approval.

## Recommended Rails

| Rail | State | Why |
| --- | --- | --- |
| Static image prompts plus output records | Recommended | Fits current `/mb-ads`, `/mb-site`, and `/mb-organic` workflows without claiming provider support. Prompts, source context, and final assets can be reviewed and saved as push artifacts. |
| OpenAI GPT Image 2 direct API/CLI | First readiness target | Official OpenAI docs expose `gpt-image-2` for generation/editing, flexible image sizes, quality controls, and both Image API and Responses API paths. Community skill/CLI references are strong, but Main Branch should implement a thin direct rail and smoke it with fake assets before claiming support. |
| Remotion plus FFmpeg for deterministic motion/export | Recommended design rail | Remotion gives code-backed, parameterized video rendering; FFmpeg gives durable resizing, overlay, concatenation, captions, encoding, and platform export. This is a better first motion rail than raw AI video because the brief and render settings are inspectable. |

## Candidate Rails

| Rail | State | Boundary |
| --- | --- | --- |
| Google Gemini image generation | Candidate provider | Official docs identify Nano Banana image-model families, but exact model IDs and preview status move quickly. Main Branch should avoid shipping hard-coded Gemini image model IDs until a run checks current primary docs and pins the exact model used. |
| BFL FLUX.2 | Candidate provider/reference local rail | Official BFL docs and repos cover FLUX.2 [pro], [max], [flex], [klein], API pricing, multi-reference editing, typography, and open-weight/local paths. Useful for future local/private or ComfyUI workflows, but heavier than the first Main Branch rail. |
| xAI Grok Imagine | Candidate provider | Official xAI docs expose image generation/editing and video generation with flat image/video pricing. It is credible for experimentation, but should not be a first rail until setup, moderation, cost, and artifact metadata are smoked. |
| Ideogram | Candidate typography specialist | Official API docs expose image-generation and editing surfaces. It remains a candidate for text-heavy creative, but exact pricing and setup details should be rechecked before any support claim. |
| Google Veo | Candidate video provider | Useful for short social/video ad generation, but paid/provider setup, temporary output storage, preview model churn, and low reproducibility keep it out of core until smoked. |
| OpenAI Sora | Candidate video provider | Official API docs expose asynchronous video generation/edit/extend flows. Treat as optional video generation only after account access, cost, moderation, approval, and artifact recording are proven. |
| Runway | Candidate video provider | Strong premium AI video surface with primary API docs, SDKs, moderation, tiers, and pricing. Higher maintenance burden than OpenAI/Google; needs a separate provider decision before adoption. |
| Luma / Kling | Candidate video references | Useful tools in the market, but public API/CLI/pricing evidence needs separate primary-source validation before Main Branch records support language. |
| ComfyUI | Reference local rail | Strong local workflow ecosystem and useful CLI-harness patterns exist. Treat as a future local/private rail after a deterministic harness, setup docs, model availability checks, and fixture-safe smoke exist. |
| Shotstack-style hosted JSON render | Candidate hosted template rail | Good hosted template-render option if local Remotion/FFmpeg is too heavy. Not a generative rail and adds cloud billing/lock-in. |
| MoviePy | Reference helper | Useful for simple Python-native assembly, but FFmpeg is the better primitive for predictable transforms and Remotion is stronger for reusable motion systems. |
| TikTok Symphony Creative Studio | Manual platform rail | Useful free business-owner workflow inside TikTok Ads Manager, but not a reproducible API/CLI rail for Main Branch today. |

## Refused For Core

| Rail | Reason |
| --- | --- |
| Vendoring community GPT Image skills into Main Branch core | Community skills are useful references, but vendoring them would create dependency, security, update, and runtime-support obligations. Main Branch should implement only the narrow behavior it can smoke and maintain. |
| A generic model router as the first implementation | Routing across OpenAI, Google, BFL, xAI, Ideogram, and video providers multiplies setup, cost, policy, and validation paths before one rail is proven. |
| Top-level `brandkit/` as a new business-repo primitive | Brand context already belongs in `core/brand/`, especially `core/brand/visual-style.md`. New top-level folders need a separate repo-shape decision. |
| `outputs/` for new generated work | `outputs/` is legacy generated-work language. New coordinated creative work should route through `pushes/<push>/` or approved document/media locations. |
| Committing generated image binaries by default | The durable source of truth is the asset record, not every generated binary. Binary commits require explicit operator approval and a clear repo/storage reason. |
| `mb connect` provider state before one rail is smoked | Provider state should wait until direct OpenAI image generation/editing has fixture-safe smoke evidence and the metadata/storage contract is stable. |
| Meta Advantage+ Creative as the generator | It is an in-platform optimization layer, not a reproducible asset generator. Main Branch can record whether the operator used it, but should not treat platform-side resizing, background generation, or animation as source-of-truth creative production. |
| TikTok Symphony API automation | No public primary API/CLI rail was verified. Keep it as a manual handoff until official automation docs and smoke evidence exist. |
| Raw AI video as the first creative system | Video generation is slower, more expensive, less reproducible, and higher policy risk than static images plus deterministic motion/export. Start with briefs, static assets, and renderable templates. |

## External References

Use external repositories as references, not vendored product code.

Useful references checked during the MAIN-362 research pass:

| Repo | Direct API or wrapper | Pattern to borrow | Do not copy |
| --- | --- | --- | --- |
| `wuyoscar/gpt_image_2_skill` | Direct/OpenAI-oriented skill and CLI reference | Prompt gallery shape, CLI-first skill structure, reference-image edit examples, size/quality flags, install/update cautions | Do not vendor the full skill, prompt library, showcase claims, or local install workflow |
| `dshark3y/gpt-image-2-skill` | Direct OpenAI scripts | Clean `generate.py` / `edit.py` split, PEP 723 / `uv run` script ergonomics, up-to-10 reference image input shape, size validation notes | Do not copy code without license review; do not inherit omissions such as limited logging or no explicit mask support |
| `Wangnov/gpt-image-2-skill` | Agent-first CLI with OpenAI, OpenAI-compatible, and Codex-auth provider paths | JSON stdout, JSONL progress events, retries/timeouts, provider config inspection, masks, custom size validation, transparent-asset verification patterns | Do not inherit its broader provider abstraction, desktop app, Codex-auth support claim, release machinery, or `auth.json` dependency |
| `robonuggets/gpt-image-2-skill` | Fal-backed wrapper around GPT Image 2 endpoints | Structured prompt shape, explicit generate-vs-edit endpoint distinction, optional mask field, cost-tier defaults | Do not use Fal as the first dependency, copy Fal-specific auth/header behavior, or inherit wrapper pricing claims |
| `EvoLinkAI/gpt-image-2-gen-skill` | EvoLink/OpenAI-compatible wrapper | One-command installer ergonomics, agent-facing setup docs, multi-runtime packaging notes | Do not add wrapper dependency, auto-installer behavior, or support claims for runtimes Main Branch has not smoked |
| `YouMind-OpenLab/gpt-image-2-prompts-search` | Prompt-search skill, not generation rail | Token-efficient prompt search, category manifests, prompt-gallery indexing, remix workflow | Do not copy prompt corpus, viral/source claims, or treat prompt search as generation support |
| `lansespirit/image-gen-mcp` | MCP server, multi-provider wrapper | Future MCP server boundary, storage/resource URI ideas, local metadata and cleanup patterns | Do not make MCP or multi-provider routing the first implementation |
| `openai/codex` imagegen sample skill | Runtime-native sample and built-in-tool boundary | Generate/edit decision tree, reference-role labeling, batch-vs-variant distinction, transparent-background fallback cautions | Do not claim Codex image-generation parity for Main Branch without compatibility docs and runtime smoke |

These references do not create Main Branch support claims.

## Implementation Patterns To Borrow From References

Borrow patterns, not code:

- repeated reference image inputs;
- reference roles such as `logo`, `product_photo`, `style_reference`,
  `background`, and `mask_source`;
- optional mask path for targeted edits;
- generate vs. edit vs. mask-edit decision tree;
- retries, timeouts, and clear failure records;
- JSON/events or artifact logs that can be inspected after a run;
- deterministic output naming conventions;
- prompt galleries as inspiration for templates, not as product truth;
- CLI-first skill invocation that keeps runtime prose thin.

Wrapper/provider repos can inform input shape and workflow ergonomics, but the
first Main Branch rail should not depend on them.

## Generate / Edit / Mask Decision Tree

- No image input: generate.
- Image input plus broad natural-language change: edit.
- Image input plus exact region change: mask edit.
- Many prompts, many variants, or repeated reference combinations: batch later,
  after the single-image rail is stable.

## Video / Motion CLI Boundary

Video research stays useful as source discovery, but MAIN-362 should not become
a raw generative-video provider branch. The first video-shaped CLI work should
be deterministic motion/export around already-approved media.

| Need | First CLI shape to prefer | Why | Do not do in MAIN-362 |
| --- | --- | --- | --- |
| Resize/crop/compress/static-to-platform exports | `mb media export` or `mb video export` over FFmpeg-style settings | Deterministic, inspectable, low cost, easy to validate in fixture repos | Do not call raw video models just to make platform crops |
| Branded motion templates | `mb video render --template ... --data ... --out mb-media://...` over Remotion-style templates | Fits git-backed templates, exact text, captions, timing, safe zones, and repeatable variants | Do not put Remotion/Node dependencies in core without a separate dependency decision |
| Short animated ad variants | Template render from approved image assets plus deterministic overlays | Lets the image rail, metadata record, and media URI contract stay shared | Do not add Kling/Runway/Luma/Sora/Veo/xAI provider routing here |
| AI-generated video exploration | Follow-up provider decision and smoke issue | Higher cost, policy, latency, and reproducibility risk | Do not claim support from market sentiment or social examples |

## Recommended CLI Shape

The first implementation does not have to keep this exact command surface, but
the decision recommends a one-shot, scriptable CLI shape so the next agent does
not design ad hoc commands:

```bash
mb image generate --prompt "..." --out mb-media://pushes/2026-05-ad-test/images/hero-001.png
mb image edit --prompt "..." --ref-image mb-media://brand/logo.png --out mb-media://pushes/2026-05-ad-test/images/hero-002.png
mb image edit --prompt "..." --ref-image mb-media://pushes/2026-05-ad-test/references/product.webp --mask mb-media://pushes/2026-05-ad-test/references/mask.png --out mb-media://pushes/2026-05-ad-test/images/hero-003.png
```

The implementation should resolve logical media URIs to configured storage
locations at runtime, write/update the push-local `image-index.md`, and refuse
private absolute paths in committed records.

## Implementation Order

1. Update `/mb-ads` image guidance so OpenAI GPT Image 2 is the first readiness
   target and Google/BFL/xAI remain candidate rails.
2. Define or tighten the `image-index.md` asset record shape for push-local
   creative assets.
3. Add a minimal `mb image` or equivalent CLI surface only if it remains
   one-shot, scriptable, explicit about provider setup, and fixture-safe.
4. Smoke direct OpenAI generation/editing with fake prompts and fixture-safe
   images only.
5. Wire `/mb-ads` to consume the same artifact record instead of hard-coding
   one provider or one private local path.
6. Open follow-up issues for Google Gemini, BFL FLUX.2/ComfyUI, deterministic
   Remotion/FFmpeg templates, and raw video providers only after the OpenAI
   rail and metadata contract are stable.

## Acceptance Criteria For MAIN-362 Decision Readiness

- OpenAI `gpt-image-2` is the first readiness target, not a support claim.
- Prompt-only/manual mode is a fallback, not the main product target.
- Generated images are not committed by default.
- `image-index.md` or equivalent is the durable committed record.
- Media storage is configurable or explicitly follow-up scoped.
- Safe logical media URIs are preferred over private absolute paths.
- Reference image roles are supported in the metadata contract.
- Community repos are references only, not vendored dependencies.
- No top-level `brandkit/`, `outputs/`, or `artifacts/` folder is introduced.
- No generic model router is introduced.
- No `mb connect` provider state is added until one rail is smoked and boring.
- `scripts/check.sh` passes before PR.

## Source Notes

Primary/current sources checked on 2026-05-13:

- OpenAI GPT Image 2 model docs:
  https://developers.openai.com/api/docs/models/gpt-image-2
- OpenAI image generation docs:
  https://developers.openai.com/api/docs/guides/image-generation
- OpenAI pricing:
  https://developers.openai.com/api/docs/pricing
- Google Gemini image generation docs:
  https://ai.google.dev/gemini-api/docs/image-generation
- Google Gemini pricing:
  https://ai.google.dev/gemini-api/docs/pricing
- BFL FLUX.2 docs:
  https://docs.bfl.ai/flux_2
- BFL pricing:
  https://docs.bfl.ai/quick_start/pricing
- xAI Grok Imagine image docs:
  https://docs.x.ai/developers/model-capabilities/images/generation
- xAI pricing:
  https://docs.x.ai/developers/pricing
- Anthropic Claude Code MCP docs:
  https://docs.anthropic.com/en/docs/claude-code/mcp
- Anthropic Claude Design announcement:
  https://www.anthropic.com/news/claude-design-anthropic-labs
- Remotion docs:
  https://www.remotion.dev/docs/
- FFmpeg docs:
  https://ffmpeg.org/ffmpeg.html
- Runway API docs:
  https://docs.dev.runwayml.com/
- Shotstack docs:
  https://shotstack.io/docs/guide/
- MoviePy docs:
  https://zulko.github.io/moviepy/
- Meta Advantage+ Creative:
  https://www.facebook.com/business/ads/meta-advantage-plus/creative
- TikTok Symphony Creative Studio:
  https://ads.tiktok.com/help/article/about-symphony-creative-studio

## Follow-Ups

- Add the combined creative asset generation readiness rail before any `mb
  connect` provider state or motion/template support claim:
  https://github.com/dmthepm/mainbranch/issues/569
- The standalone deterministic motion-template follow-up was superseded by the
  combined readiness rail so provider images and deterministic templates share
  one artifact metadata contract:
  https://github.com/dmthepm/mainbranch/issues/568
