# Research Phase

Detailed workflow for research mode in `/mb-think`.

**See also:** [research-routing-quick-ref.md](research-routing-quick-ref.md) for full routing and tool selection logic.

---

## Offer Context Resolution

When researching an offer-specific topic, load:
- `core/offers/[active]/offer.md` (if exists) for offer-specific context
- `core/offer.md` for brand-level context
- Both may be relevant — offer-specific for details, core for brand positioning

Use `.claude/reference/business-primitives/offer-bet-push-proof.md` before
starting research. If a future `mb` JSON field exposes active offer state, use
it. Otherwise, if `core/offers/` exists but no active offer is selected, ask
which offer this research relates to or whether it is brand-level work; do not
silently route from `.vip/local.yaml`. If old `reference/*` paths appear without
`core/`, run `mb doctor repair --plan` before relying on them.

---

## Workflow

1. **Define the question** — What specifically are you trying to learn?
2. **Recommend depth** — For offer, audience, proof, CTA, content strategy,
   ads/pages, and positioning work, choose the smallest useful depth with
   [research-depth-ladder.md](research-depth-ladder.md)
3. **Detect intent & route** — Determine which research tools to use (see [research-routing-quick-ref.md](research-routing-quick-ref.md))
4. **Check capabilities** — Are preferred tools available? Offer setup or fallback if not
5. **Gather findings** — Execute with token management and cost awareness
6. **Synthesize** (required) — Distill findings into actionable insight
7. **Save** — Write to `research/YYYY-MM-DD-topic-[source].md`
8. **Checkpoint** — Ask whether to make the research batch durable before the
   next decision or codify pass

If the operator passes `--brief-format=grok-8`, asks for a researched brief,
or wants research to feed a site, ads, organic content, or a push playbook,
load [grok-8-brief-format.md](grok-8-brief-format.md) before gathering. Save
the output with `brief_format: grok-8` and include all eight categories.

---

## Defining Good Questions

**Good research questions:**
- "What pricing tier structure should we use?"
- "Which messaging angle resonates with cold traffic?"
- "Should we add a guarantee? What kind?"

**Bad questions (too vague):**
- "How do I grow?"
- "What should I do next?"

---

## Source Suffixes

| Suffix | Source |
|--------|--------|
| `-gemini.md` | Gemini deep research |
| `-gpt.md` | ChatGPT research |
| `-claude-code.md` | This Claude Code session |
| `-claude-web.md` | Claude.ai web interface |
| `-x-social.md` | X/Twitter social research (Grok MCP) |
| `-yt-mining.md` | YouTube transcript mining (Apify) |
| `-competitor-mine.md` | Competitor content mining (Instagram, sites, videos; Apify or manual). `/mb-organic` reads this name |
| `-customer-mining.md` | Customer calls, surveys, support, onboarding, cancellation language |
| `-review-mining.md` | Public reviews and rating-backed customer language |
| `-winning-ad-research.md` | Competitor gap maps, ad/script teardown, winning blueprint research |
| `-content-comment-mining.md` | TikTok, YouTube, Instagram, or X comment language mining |
| `-local-mining.md` | Local video/audio transcription |
| `-voice-mining.md` | Voice memo transcription |
| `-internal-mining.md` | Internal data (emails, DMs, reviews) |
| `-source-mining.md` | Authenticated/private source synthesis after manifest-first review |
| `-audit.md` | Site or system audit |
| (none) | General or mixed sources |

### Multi-Offer Research Naming

Multi-offer research can optionally include the offer name in the slug for clarity:

```
research/YYYY-MM-DD-[offer]-topic-[source].md
```

**Example:** `research/2026-02-04-community-pricing-analysis-gemini.md`

This is optional — standard naming without the offer prefix works fine. Use the offer prefix when researching a topic specific to one offer to make it easy to find later.

### Which Repo Gets the Research File

Research lives where its conclusions codify — not where the session happened
to run:

- Conclusions change `core/` (offer, audience, pricing, positioning, bets) →
  the **business repo's** `research/`.
- Conclusions land in one product repo's code or docs → **that product
  repo's** `research/`.
- Mixed → default **up** to the business repo, and fold the build-specific
  notes into the product repo's docs in the same pass.

Quick test: *if we rebuilt the product from scratch tomorrow, would this
research still matter?* Yes → business repo. No → product repo.

Two invariants hold regardless of where the raw file sits: durable
conclusions always codify up into the business repo's `core/`, and research
files carry `offer:` frontmatter in multi-offer repos.

---

## Content Strategy Research Routing

When the user's research topic involves content pillars, platform selection,
content cadence, account strategy, founder/person voice, distribution, channel
rules, or content performance, start from `mb status --json --peek` and use
`content_strategy` to see whether the simple file and optional layers are
healthy, stale, disconnected, or missing. Then read `core/content-strategy.md`
and the relevant `core/marketing/` or `core/people/` files when the question
names a channel, account, or person.

**Trigger topics:** content pillars, recognition target, which platforms,
content plan, cadence, content mix, repurposing, hooks, content frameworks,
content metrics, newsletter strategy, channel strategy, account strategy,
founder voice, weekly content plan

**Research flow for content strategy topics:**
1. Read `content_strategy` facts from status, then read existing
   `core/content-strategy.md` when present
2. Read `core/soul.md` + resolved `offer.md` + resolved `audience.md` for pillar derivation context
3. Conduct research (web, mining, competitor analysis)
4. Synthesize into a research file as usual
5. In the **Implications for Reference Files** section, note which sections of
   `core/content-strategy.md`, `core/marketing/...`, or `core/people/...`
   should be updated, and whether `linked_strategy_layers` needs repair

If `content-strategy.md` does not exist, the research output should recommend
creating it as an action item. See `mb-setup/references/templates.md` for the
content strategy templates, and `mb-help/references/content-strategy-help.md`
for user-facing FAQ.

---

## Winning-Ad Research Routing

When the research topic involves ad creative, customer language, competitor
ads, reviews, scripts, or comments, load
[winning-ad-research.md](winning-ad-research.md) and choose the smallest useful
bundle:

1. **Customer language mining** — sales calls, surveys, support tickets,
   onboarding forms, cancellation notes.
2. **Competitor gap map** — competitor ads, landing pages, product pages,
   pricing, reviews, and mechanism stories.
3. **Review mining** — public reviews with platform, rating, date, and source
   link where possible.
4. **Winning script teardown** — own winners or inferred competitor winners
   with transcripts.
5. **Content/comment mining** — TikTok, YouTube, Instagram, or X comments and
   replies.

Do not skip from mined data straight to ad generation. The loop is:

```
Mine sources -> synthesize -> codify reference -> generate with /mb-ads or /mb-organic
```

### Source Handling

Use public or operator-provided evidence only. Raw prompt libraries, scraped
comment dumps, customer records, full tweet threads, and copyrighted page
copies do not belong in committed research files. Cite source URLs and keep
only concise excerpts needed to support the synthesis.

For transcripts, authenticated community content, connected-provider
recordings, cloud-drive files, call notes, exported chats, or mixed
private/business sources, use the source-ingestion privacy rail before reading
content: [`source-ingestion.md`](source-ingestion.md).
Inventory sources, review a manifest, apply allow/skip filters, then read only
the smallest approved slice. Commit synthesized findings, not raw provider
payloads or transcripts.

### Provider Routing

- Use Apify only as optional read-only enrichment, preferably through MCP for
  now: YouTube transcripts, Instagram mining, public web scraping, and public X
  profile/post/reply samples when actor metadata, operator-accepted terms,
  access/permission boundaries, and a small smoke run support the source. Treat
  public X actors as sidecar research, not an official X integration. Treat
  Apify MCP as an agent-side research tool surface, not automatically as an
  `mb connect` provider.
- Use Grok/xAI or web search for topic-level X/social sentiment when
  configured; otherwise ask for screenshots, public embeds, or manual exports.
- Treat Postiz as planned scheduling/publishing support only where current docs
  and connected-channel smoke evidence exist. The 2026-05-07 API smoke proved
  reachability/auth, but not draft or scheduling support.
- Do not recommend comment/DM automation through X API, Postiz, Typefully,
  Apify, browser automation, or ManyChat-style providers as a supported Main
  Branch path.

---

## Sources to Check

1. **Codebase** — Existing reference files, past decisions, research
2. **Web** — Competitors, industry benchmarks, expert perspectives
3. **X/Twitter** — Real-time sentiment, trending topics (see [grok-social.md](grok-social.md))
4. **User input** — "What else do you know about this?"
5. **YouTube transcripts** — When researching topics with video content (see below)
6. **Local video/audio** — User's own recordings, voice memos, Loom exports (see [local-transcription.md](local-transcription.md))
7. **Customer/review/comment evidence** — When researching ad or organic angles,
   use [winning-ad-research.md](winning-ad-research.md)
8. **Authenticated/private source sets** — Use `source-ingestion.md` first for
   manifest-first review, skip filters, proof-permission gates, and private
   evidence handling

---

## YouTube Transcript Research

When user wants to research video content, use **Apify** (`starvibe/youtube-video-transcript`).

**IMPORTANT:** Never fall back to browser automation for transcripts. If Apify fails, troubleshoot the MCP — don't open Chrome. Browser automation for transcripts is slow, unreliable, and defeats the purpose of having MCPs.

**Trigger phrases:**
- "pull down this YouTube video"
- "transcribe this video"
- "what does [creator] say about..."
- "research this YouTube link"

**How to use:**

```
mcp__apify__call-actor
  actor: "starvibe/youtube-video-transcript"
  input: {
    "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "language": "en",
    "include_transcript_text": true
  }
```

Then fetch results with `mcp__apify__get-actor-output` using the returned datasetId.

**Cost:** ~$0.005 per video (~200 videos for $1, regardless of length)

---

### Best Practices

**Token management:**
- Full transcripts can be 10-30K tokens for long videos
- Always use `include_transcript_text: true` to get plain text (not timestamped array)
- When fetching output, use `fields` parameter to get only what you need:
  ```
  fields: "title,channel_name,transcript_text"
  ```
- Don't dump raw transcripts into research files — synthesize first

**Efficient workflow:**
1. Call actor → get datasetId
2. Fetch with specific fields (title, transcript_text, view_count)
3. Synthesize immediately — extract frameworks, quotes, patterns
4. Save synthesis, not raw transcript

**Before a large Apify mining run** (many posts, several competitors, or a hashtag sweep): show the owner an estimated cost (posts × the actor's per-post price) and get their OK first. Offer a quick scan as the cheaper option.

**If MCP fails:**
1. Check Apify account has credits
2. Verify video has captions (some don't)
3. Try different language code
4. Check if video is age-restricted or private
5. **Never** fall back to Chrome — fix the root cause

---

### Use Cases

**Best for:**
- Mining competitor messaging from their videos
- Extracting frameworks from educational content
- Researching what experts say about a topic
- Getting exact quotes for proof/angles

**After transcription:**
1. Synthesize key findings (don't dump raw transcript)
2. Extract quotable moments
3. Note messaging patterns
4. Save competitor content to `research/YYYY-MM-DD-[topic]-competitor-mine.md` (other sources: the suffix table above)
5. For private or authenticated sources, keep raw output in ignored scratch and
   record proof candidates with permission fields before public use

**Example workflow:**
> User: "Research what Alex Hormozi says about pricing"
> 1. Search YouTube for relevant Hormozi videos
> 2. Transcribe 2-3 key videos via Apify
> 3. Extract pricing principles and frameworks
> 4. Synthesize into actionable findings

---

## X/Twitter Social Research

When user wants to know what people are saying about a topic in real-time.

**Trigger phrases:**
- "what are people saying about..."
- "sentiment on X"
- "what's trending in..."
- "social proof research"

**How to use:** prefer the xAI Python SDK path in
[grok-social.md](grok-social.md). A Grok X Insights MCP may work if configured,
but test that it returns actual X data before relying on it.

**Setup:** See [grok-setup.md](grok-setup.md)
**Full workflow:** See [grok-social.md](grok-social.md)

**Quick example:**
```
User: "What are people saying about Skool communities?"

1. Check if Grok MCP available
2. grok_search_posts with query "Skool communities" timeWindow "7d"
3. Synthesize findings
4. Save to research/YYYY-MM-DD-skool-sentiment-x-social.md
```

**Fallback:** If no Grok MCP, use web search or ask user to share X screenshots manually.

---

## Public X Post/Profile Mining

When the user provides a specific public X/Twitter post or profile and asks
what the post, comments, or nearby profile pattern is doing, use Apify as
optional read-only enrichment only when configured and when the operator
accepts the source, terms, cost, and reliability tradeoffs. Otherwise use
Grok/xAI, web search, public embeds, screenshots, or manual exports.

**Trigger phrases:**
- "mine this X post"
- "what are the replies saying"
- "what is this Twitter strategy"
- "look at this profile and nearby posts"
- "is this comment-to-DM or full-value"

**How to use:**

1. Search Apify actors by source and task, for example `X post replies`,
   `Twitter profile posts`, `tweet scraper`, or `quote posts`.
2. Fetch actor details and inspect input/output shape. Treat actor names as
   examples, not a stable Main Branch adapter contract.
3. Run the smallest useful public scrape:
   - one post URL, `resultsLimit` 20-100, include original post when available;
   - one profile URL, `resultsLimit` 20-50 for nearby post context;
   - quote posts or nested threads only if the research question needs them.
4. Fetch only necessary dataset fields when output is large.
5. Synthesize immediately. Save the pattern, not the raw scrape.

**Synthesize:**
- funnel mechanic;
- proof pattern;
- CTA pattern;
- reply quality split between keyword comments and substantive audience
  language;
- source limitations and conversion claims that public data cannot prove.

**Limits:**
- Do not assume complete reply-tree coverage, ordering, hidden replies, quote
  posts, retweets, or conversion data.
- Do not treat public comments as buyer proof. Keyword comments can prove the
  mechanic, but they are weak audience language unless replies are substantive.
- Do not claim Apify can access DMs, private analytics, protected accounts, or
  account mutation.
- Do not ask for X session cookies or use browser automation as product
  guidance. Those belong outside Main Branch-supported X workflows.
- Durable outputs go to `research/YYYY-MM-DD-[topic]-x-public-mining.md` or
  into synthesized strategy files; raw scrape dumps stay out of committed repos.

---

## Local Video/Audio Transcription

When user wants to mine their OWN recordings (not YouTube), use local transcription.

**Trigger phrases:**
- "transcribe this video"
- "I have a recording to mine"
- "transcribe my Loom"
- "process this voice memo"
- User shares a local `.mp4`, `.mov`, `.m4a`, `.wav` file path

**How to use:**

See [local-transcription.md](local-transcription.md) for full workflow.

**Quick version (CLI — check config `tools.whisper.notes` for which variant):**
```bash
# mlx_whisper (Apple Silicon, preferred — handles video directly):
mlx_whisper --model mlx-community/whisper-large-v3-turbo --language en --output-format txt --output-dir /tmp/whisper-out "video.mp4"

# whisper-cli (Homebrew fallback — needs ffmpeg conversion first):
# ffmpeg -i "video.mp4" -ar 16000 -ac 1 /tmp/audio.wav -y
# whisper-cli --model ~/.whisper/ggml-base.en.bin --file /tmp/audio.wav --output-txt
```

**With whisper-mcp:** Use `transcribe_audio` tool directly.

**After transcription:**
1. Synthesize key findings (don't dump raw transcript)
2. Extract quotable moments
3. Note messaging patterns
4. Save to `research/YYYY-MM-DD-[topic]-mining.md`

---

## Writing Good Synthesis

Every research output MUST have a synthesis section. This forces distillation.

**The rule:** If you can't synthesize it, you don't understand it.

---

## Content Mining: Framework Extraction (Human Work)

When mining competitor content, AI collects data. YOU extract the frameworks.

> "AI can show WHAT worked. Human must judge WHY." — Koston Williams

**Three dimensions to extract:**

| Dimension | What AI Observes | What YOU Determine |
|-----------|------------------|-------------------|
| **Visual** | Format, production style, patterns | Does this fit MY setup/skills? |
| **Audible** | Energy, pacing, delivery | Can I match this energy authentically? |
| **Emotional** | Primary emotion triggered | Does this align with MY audience's identity? |

**The skill is framework transfer.** A competitor's video worked for THEM — their audience, their personality, their offer. Your job is to see the framework beneath the content, judge whether it transfers to your context, and adapt it to your voice.

**Don't skip to content.** Mining → Framework Extraction (human) → Reference Update → THEN Generate.

This methodology comes from Koston Williams, who used it to create a 6M view video. The insight: copying content doesn't work. Extracting and transferring frameworks does.

---

### One-Sentence Summary

The hardest part. Forces clarity.

**Constraints:**
- **20 words maximum** — Not 21. Not "about 20."
- **One sentence** — Period at the end. No semicolons connecting two thoughts.
- **Actionable insight** — Not a description of what you researched.

**Bad:**
> "We researched competitor pricing strategies and found various approaches."

Problems: Describes research, not finding. Says nothing actionable.

**Good:**
> "Three-tier pricing with free/paid/premium maximizes reach while creating natural upgrade paths."

Why it works: Specific structure, specific benefit, 14 words.

### Key Findings

**Constraints:**
- **5-10 bullets** — Not 4. Not 11.
- **15 words each maximum** — Forces precision.
- **Facts, not opinions** — "Competitors charge $47-147" not "Competitors are reasonable."

Each finding should stand alone. Someone reading just the bullets should understand the research.

**Include:** Data points with numbers, patterns across sources, surprises, direct quotes.
**Exclude:** Background information, methodology details, tangential findings, speculation.

### Implications for Reference Files

Makes research actionable. Without it, research becomes orphaned knowledge.

For each finding, ask: "Does this change anything in my reference files?"

In multi-offer mode, use offer-qualified paths:

| File | Potential Update |
|------|------------------|
| `core/offers/community/offer.md` | Add tier structure, update pricing |
| `core/offer.md` | Update brand-level positioning |
| `core/audience.md` | Segment by tier |
| `core/proof/angles/` | Add durable emotional or competitive angles |
| `core/proof/typicality.md` | Add aggregate outcome and average-case context |
| `core/content-strategy.md` / `core/marketing/...` / `core/people/...` | Add hooks, frameworks, platform strategy, comment insights, or layer links |
| `core/product-ladder.md` | Update ascension logic |

In single-offer mode, paths stay standard:

| File | Potential Update |
|------|------------------|
| `core/offer.md` | Add tier structure, update pricing |
| `core/audience.md` | Segment by tier |
| `core/proof/angles/` | Add durable emotional or competitive angles |
| `core/proof/typicality.md` | Add aggregate outcome and average-case context |
| `core/content-strategy.md` / `core/marketing/...` / `core/people/...` | Add hooks, frameworks, platform strategy, comment insights, or layer links |

**Bad:** "Update offer.md"
**Good:** "Update core/offers/community/offer.md — Add three-tier pricing with benefits per tier"

### Open Questions

Research rarely answers everything. Document what you still don't know.

**Good:** "What should the free tier include to create desire for paid?"
**Bad:** "How do we make more money?" (too vague)

Each open question is a potential next research session.

---

## Synthesis Checklist

Before marking research as complete:

- [ ] One-sentence summary is under 20 words
- [ ] Summary states an insight, not a description
- [ ] 5-10 key findings, each under 15 words
- [ ] Findings are facts, not opinions
- [ ] Each finding could stand alone
- [ ] Implications section maps to specific reference files
- [ ] Open questions identify follow-up research needs
- [ ] Someone could read just the synthesis and understand the research

---

## Exit Criteria

Research is complete when:

- [ ] Research question answered
- [ ] Synthesis section completed
- [ ] Key findings extracted (5-10 bullets)
- [ ] Open questions documented
- [ ] File saved to `research/`

---

## Template

See [templates/research-template.md](templates/research-template.md) for full file structure.

---

## Parallel Research Agents

When research needs 2+ sources (YouTube + web, X + codebase, competitor mining + deep research), spawn one Task agent per source in a single message with `subagent_type: "general-purpose"` (has Write, Edit, Bash, MCP access). Do not use `run_in_background: true`: background agents cannot access MCP tools (Apify, etc.) or prompt for permissions.

Each agent:
- gets a focused prompt: one source, one research question, no full business context;
- writes its own dated file (for example `research/YYYY-MM-DD-topic-yt-mining.md`);
- verifies the write (Read or `ls`) after writing;
- returns the file path, write status and a 5-bullet summary;
- on write failure, returns the full research content so the main conversation can write it (works around a known Claude Code subagent write persistence bug).

After all agents return, check the files landed, write any that failed from the returned content, then synthesize across summaries. Heavy raw content stays in subagent contexts. For authenticated or private sources, run the source-ingestion rail first and keep raw transcripts and provider payloads out of committed files by default.

Multi-source output example: `research/2026-01-26-guarantee-x-social.md`, `-competitors.md`, `-psychology-gemini-deep.md`, plus `-synthesis.md` that references the individual files.
