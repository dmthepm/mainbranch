# Meta Text Slots and Hooks

How to write the words for one Meta ad when it carries several text options:
up to 5 primary texts, 5 headlines and 5 descriptions. Use it in a pack
([meta-pack-loop.md](meta-pack-loop.md)) or any time an ad needs text slots.
The static-ad styles in [mode-static-ads.md](mode-static-ads.md) stay the menu
of angles and lengths; this page is how they fit Meta's slots.

Source: a live ecommerce dogfood business, September 2026. The slot plan and
edit loop were used on its first packs, which passed Meta review. Whether Meta
serves all five variants per placement is not yet proven
([meta-api-behaviours.md](meta-api-behaviours.md)); write all five anyway, and
make slot 1 of each kind the one that must stand alone.

---

## Meta Pairs Anything With Anything

Meta rotates the slots freely: any primary text can show with any headline and
any description. So:

- every line must stand alone;
- every pairing must pass policy and read sensibly;
- no headline repeats its own ad's hook (the card could show the same words
  three times);
- two lines that fight each other when paired are a defect, even if each is
  fine alone. Change the new line, not an already-approved one.

Read each headline and description next to the primary text that makes it
riskiest: the one with the strongest claim, the one that says "you", the one
that names the most sensitive subject.

## The Slot Plan (Per Ad)

| Slot | Length | Job |
|------|--------|-----|
| Primary 1 | medium, 200-300 characters | the pack's core text |
| Primary 2 | **short, under 125 characters** | the hook plus one line; shows whole in the feed |
| Primary 3 | long, 500-700 characters | the story: what it is, how it works, where it comes from, who makes it |
| Primary 4 | medium | a second angle on the concept |
| Primary 5 | medium | a third angle on the concept |
| Headlines 1-5 | 40 characters or fewer (about 27 show whole on Facebook Feed) | the product name, approved anchors, the pack's hooks, overlay lines, page phrases |
| Descriptions 1-5 | 30 characters or fewer | plain facts from the page; fewer than 5 is fine, never pad |

- **Angles, not rewordings.** Primaries 4 and 5 each prove a different
  one-sentence angle (an objection answered, how it's made, what's inside, how
  it works). A variant that only swaps words is not a variant.
- **Split risky material.** If a sensitive subject is allowed at all, keep it
  to some slots and leave others without it, so the read shows which carried.

## Hooks

A hook is the first line of every primary text **and** frame one of the image
or video with its overlay: one package.

- **Hook-first.** Every primary opens with its ad's own hook. The body after
  the hook is shared by the h1 and h2 ads (except the short slot, written per
  hook), which keeps the hook test clean. Read each body after **both** hooks.
- **Reels shows about 44 characters.** The hook is a complete sentence inside
  44 characters; it may be all anyone reads.
- **Name the thing first.** Cold traffic often doesn't know the product
  category exists. The plainest true name is usually the strongest first line;
  clarity beats cleverness.
- **Show what it does in frame one.** Pair the hook with a frame that shows the
  product's moment (it opening, working, being used).
- **One angle, one sentence.** Write the ad's angle as one sentence before the
  hook; the hook and every line after it prove that sentence.
- **Buyers' words.** Take nouns and verbs from the audience file's customer
  language, not agency phrasing.
- **Two hooks per concept that differ in kind** (a name versus a reveal, a
  ritual versus an outcome), not two phrasings of one idea.
- **Questions.** A question is fine when it is about the product or is the
  buyer's own first-person question. It never asks the viewer about their
  beliefs, health, finances, losses or other personal attributes
  ([lenses/meta-policy.md](lenses/meta-policy.md)).

## Facts Come From the Page

- Every fact in an ad is on the live product or offer page on the day the line
  is written, in the page's own words (its dimension word, its material word,
  its uniqueness claim).
- Check the source of a fact before the copy ships, not just the page: a page
  can overstate. The dogfood business had to pull a live claim the product card
  overstated.
- Some words on the page never go in an ad (claims the category's policy
  forbids, promises, "ships in 2 days" lines that go stale). Keep that list in
  the business's `core/` voice or offer files and check every slot against it.

## Words on Images

Overlays, captions and callouts are copy. A caption baked into a video shows on
every impression whatever text runs, and fixing it costs a re-render.

- Keep them in their own words file for the pack: idea, frame, words, status
  (approved, candidate, blocked), page source.
- They pass the same checks as the slots, plus a check of shape, size and
  material words against the product's real specs.
- They get their own fresh-agent edit before anything is rendered.
- The media uses the words file character for character, copied by value.

## The Fresh-Agent Edit

A self-edit is not the copy pass. A separate agent that did not write the lines
edits them, read-only, and returns verdicts:

```text
slot id | PASS / EDIT / CUT | exact replacement if EDIT | one-line reason citing the page or the rule
...
pairing risks
VERDICT: PASS | PASS WITH EDITS | FAIL
```

- The editor checks every line against the live page, the business's
  never-list, the lengths above, the pairing rule, and the lenses in
  [review-workflow.md](review-workflow.md).
- The writer applies each EDIT or declines it with a reason, and records the
  verdict and every edit in the slots file's "Copy pass record".
- FAIL means a rewrite and a new fresh edit, never a patch-and-ship.
- **Any line added or changed after a fresh edit gets a new fresh edit** before
  hand-off. A second edit on the dogfood business changed lines the first had
  passed.
- Lines already live are not changed without the operator's yes.

## Slots File Shape

One file per pack: `pushes/<push>/packs/p<NN>-text-slots.md`.

````markdown
## p01 <avatar> x <angle>

Hooks: h1 **<hook 1>** · h2 **<hook 2>**

### Primary text 1: medium

h1 ads
```
<hook 1>

<body>
```
h2 ads: the same text with the first line replaced by <hook 2>

### Primary text 2: short
...

### Headlines

| Slot | Line | Source |
|------|------|--------|
| 1 | ... | page quote or approved line |

### Descriptions

| Slot | Line | Source |
|------|------|--------|

## Copy pass record
VERDICT: ...
````

Fenced blocks keep line breaks exactly for pasting into Ads Manager; a table
cell can't. If a tool will parse the file, keep this shape stable and change it
only with that tool.

## Copy Retro

At the pack's day-14 close ([meta-pack-loop.md](meta-pack-loop.md#retro-every-pack)):
which hook carried (numbers), which slots took the spend and which Meta never
served, each line Meta rejected or the editor cut and the rule it broke, and
new customer words with their source. Each lesson becomes a change to the
business's `core/` files, playbook or this pack's template, or "no change,
because ...".
