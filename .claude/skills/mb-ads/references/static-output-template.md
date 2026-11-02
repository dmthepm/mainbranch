# Static Ad Output Template

Use this structure for campaign batch outputs.

## Contents

- **Part 1: Image Prompts** - Generate all images first (line 25)
- **Part 2: Ad Copy** - Copy for Ads Manager (line 70)
- **Naming Conventions** - File and image naming (line 174)
- **Format Pair: 4:5 + 9:16** - One composition per placement

---

```markdown
---
type: output
format: static-ad
date: YYYY-MM-DD
status: draft
platform: meta
---

# Campaign Batch {number} — {Campaign Name}

Generated: {date}
Target: {Offer name and price}
Destination: {CTA URL}

**Workflow:** Generate all images first (Part 1), then copy ad text (Part 2)

---

# PART 1: IMAGE PROMPTS

Generate all images first. Make a 4:5 for Feeds and a 9:16 for Stories and Reels, each composed for its placement.

---

## Ad 1: {Angle Name} — {batch#}.1

**Angle:** {description}
**Avatar:** {target persona}

---

### {batch#}.1_IMG_01 — {Descriptive Name}

**Concept record** (fields and playbook IDs: the `concepts:` schema in [image-generation-workflow.md](image-generation-workflow.md); `creative_playbook_id` optional):
```yaml
prompt_key: "{descriptive-concept-id}.v1"
prompt_file: "pushes/{push}/prompts/{descriptive-concept-id}.md"
creative_playbook_id: "{playbook id or omit}"
router_reason: "{why this playbook fits this candidate}"
source_bite: {source_file: research/customer-language.md, source_type: customer_language, extracted_phrase: "{phrase}", insight: "{why sharper than generic}", visual_translation: "{one-second visual}"}
genericness_check: {specific_to_this_offer: 4, reason: "{why this image could only come from this business context}"}
avoidance_strategy: {avoids: [stock-photo business imagery, fake dashboard, generic SaaS gradient], intentionally_uses: [], reason: "{...}"}
```

**Feed (1440×1800, 4:5):**
```text
{Full prompt for the 4:5 feed image. Whole product in frame with margin; words on a flat area.}
```

**Vertical (1080×1920, 9:16):**
```text
{Full prompt for 9:16 vertical. Product, headline and key visual between 14% and 65% of the height. Fill top/bottom with the scene's own background, not a flat block.}
```

---

### {batch#}.1_IMG_02 — {Descriptive Name}

[Repeat structure]

---

### {batch#}.1_IMG_03 — {Descriptive Name}

[Repeat structure]

---

## Ad 2: {Angle Name} — {batch#}.2

[Repeat full structure for each ad]

---

# PART 2: AD COPY FOR ADS MANAGER

Copy and paste into Ads Manager after images are ready.

---

## Ad 1: {Angle Name} — {batch#}_IMG_01

---

### Primary 1 — Deep Ad (~500 words)

**Hook:** {complete first sentence, 44 chars or fewer}

```text
{Full primary text}

{CTA URL}
```

---

### Primary 2 — UGC/Native (~200 words), Primary 3 — Direct Response (~300), Primary 4 — Pattern Interrupt (~80), Primary 5 — Testimonial (~300)

Same block as Primary 1: `**Hook:** {hook}`, then a text block with the primary text and `{CTA URL}`.

---

### Headlines — {batch#}_IMG_01

Headlines 1-5, each in its own text block: Proof-led, Mechanism-led, Outcome-led, Curiosity-led, Benefit-led.

---

[Repeat for Ad 2, Ad 3, etc.]
```

---

## Naming Conventions

Folder `pushes/YYYY-MM-DD-static-ads-{campaign}/` (campaign name lowercase with dashes, required); batch file `static-ads-batch-{###}.md` (for example `pushes/2026-01-15-static-ads-january-launch/static-ads-batch-001.md`); `review-log.md` in the same folder; images `{batch}.{ad#}_IMG_{image#}` (`001.1_IMG_01` is the first image for Ad 1). Ad and Meta object names: [naming-and-utm.md](naming-and-utm.md).

---

## Format Pair: 4:5 + 9:16

For Meta static creative, the default pair is **4:5** (Feeds, 1440×1800
minimum) and **9:16** (Stories and Reels, 1080×1920). Compose each for its
placement rather than cropping one from the other. Keep product, words and
disclosures between 14% and 65% of the 9:16 height. Full specs, composition
rules and the media gate: [ad-media-specs.md](ad-media-specs.md).

### Post-Processing (When Using An Image Provider)

If a provider generated the image:
- Record the raw output dimensions and format
- Resize to 1440×1800 (4:5) and 1080×1920 (9:16); never upscale product detail
- Convert PNG → JPEG, compress under 300KB
- Name files by ad name plus `-45` / `-916` once the ad is named ([naming-and-utm.md](naming-and-utm.md))
- See `image-generation-workflow.md` for full pipeline

---

## Image Index

When planning or generating images, create `image-index.md` in the batch folder, holding planned concepts and generated assets linked by `concept_id`. Also write a local ignored review board/contact sheet under configured media storage that answers "Which playbook produced the best actual ad candidate?"; commit only safe `image-index.md` records and distilled findings. Schema: [image-generation-workflow.md](image-generation-workflow.md). Header fields: docs checked, provider, model, source files, review board path, estimated and actual cost, post-processing, approval state.
