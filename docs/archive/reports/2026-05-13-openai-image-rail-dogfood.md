# OpenAI Image Rail Dogfood

Date: 2026-05-13
Issue: MAIN-376 / GitHub #600

## Result

Official API generation worked, but the batch did not produce a Facebook image
ad candidate worth showing or testing.

Sanitized evidence:

```text
generated_count=9
provider=openai
model=gpt-image-2
binary_committed=false
review_board_written=true
overlay_tested=false
best_candidate=null
all_rejected=true
main_failure_modes=generic_ai_image_feel, not_native_to_feed, weak_ad_click_reason, overlay_not_tested_no_finalist
```

## Manual Review

The operator reviewed the ignored local contact sheet and image folder. The
batch was rejected because the images still looked like generic AI images, not
native feed ads. No clear best three emerged, so deterministic overlays were
not tested.

## What Worked

- The official OpenAI rail produced the requested 8-12 candidate range.
- Generated binaries stayed in ignored media storage.
- The committed `image-index.md` record uses safe logical media references and
  does not include raw provider payloads, secrets, private paths, or image
  binaries.
- The batch intentionally used one portrait provider size for every asset while
  testing creative direction before per-placement export.

## What Failed

- Pre-generation concept scoring selected a theoretical winner, but the actual
  visuals did not pass manual ad-quality review.
- Per-concept placement plans were not used for provider sizing in this batch.
- The prompts still produced polished, generic GPT-image aesthetics.
- The batch did not create a strong native-feed click reason.

## Next Prompt Direction

- Require real reference or ad-native pattern inputs before the next
  visual-quality test.
- Bias prompts toward ugly, specific, native-feed artifacts rather than polished
  AI illustration.
- Keep automated concept scores separate from manual visual review. A generated
  candidate is not a winner until the operator would actually show or test it.
