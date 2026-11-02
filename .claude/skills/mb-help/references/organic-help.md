# Organic Skill Help

Help for `/mb-organic`: organic content scripts (Reels, TikTok, carousels, static posts) generated from your reference files and saved research. It is for free reach; use `/mb-ads` for paid ads. Mining competitors is research and happens in `/mb-think`, which saves to `research/`; `/mb-organic` then generates from that research.

## What it needs

`core/voice.md` (how you sound), `core/audience.md` (who watches), `core/offer.md` (what you sell, for CTAs). Missing any? Run `/mb-setup`. `research/*.md` is optional input. Recommended when available: `core/content-strategy.md` (recognition target, pillars, asset jobs, non-publishing rules), `core/marketing/channels/<channel>.md` (platform norms), `core/marketing/accounts/<platform>-<account>.md` (audience, CTA path, cadence, allowed topics) and `core/people/<person>.md` (beliefs, stories, fabrication boundaries).

## Modes

- `/mb-organic`: review reference files and saved research, pick winning concepts and angles, generate scripts in your voice.
- `/mb-organic video "topic"`: Reels/TikTok script from a research concept or your topic.
- `/mb-organic carousel "topic"`: 7-10 slides (hook, value, CTA), ready to design.
- `/mb-organic static "topic"`: single-post caption with hook line, body, soft CTA and hashtag suggestions.

## Organic vs paid

| Aspect | `/mb-ads video` | `/mb-organic` |
|--------|-----------------|---------------|
| Purpose | Paid traffic conversion | Organic reach |
| Tone | Direct response, urgency | Value-first, authentic |
| CTA | Hard (buy now) | Soft (save, follow, comment) |
| Framework | AIDA, PAS | Hook-Retain-Reward |
| Goal | Clicks and sales | Views, saves, follows |

Spending money to show it: `/mb-ads video`. Posting to your feed: `/mb-organic`.

## Common questions

- **Research competitors first?** `/mb-think` (3-5 accounts: direct competitors, adjacent creators, aspirational ones), then `/mb-organic`. Top 10-20% by engagement rate ((likes + comments) / followers) are the winners worth studying.
- **Use the exact hooks I find?** No. Adapt the pattern, not the words: "3 things I wish I knew before starting my agency" becomes "3 things I wish I knew before my first launch".
- **How is voice applied?** From `core/voice.md`: tone, vocabulary, "never say" phrases, verbal quirks. More detail in the file means better output.
- **Content feels generic?** Thin voice file (run `/mb-think codify` to add more), topic too broad, or no personal examples or stories in your reference.
- **Save winning angles?** Route to `/mb-think codify` to add them to `core/proof/angles/` for all skills.
- **Don't know what to create about?** Run `/mb-think research "content ideas for [your niche]"`, or mine competitors, then come back.
- **Mining used a lot of tokens?** Each competitor costs about 3-5k tokens in `/mb-think`; mine 2-3 instead of 5, or use "quick scan".
- **Apify isn't working?** Type `/mcp` and look for `apify`; restart Claude (MCPs load at startup: `/exit`, then `claude --continue`); check the token at apify.com under Settings, API & Integrations; or share screenshots manually. Full setup: `mb-organic` `references/apify-setup.md`.

## Typical flow

`/mb-think` (mine competitors, save concepts to `research/`) -> `/mb-organic video "concept from research"` (saved to `pushes/`) -> repeat for carousel or static -> optionally `/mb-think codify` to save the best angles.

Related: `/mb-ads video` and `/mb-ads static` for paid; `/mb-think` for content, channel, account or person-voice strategy; `/mb-think codify` for more voice context.
