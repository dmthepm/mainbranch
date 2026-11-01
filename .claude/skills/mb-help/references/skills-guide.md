# Skills Guide: When to Use What

Skills are specialized workflows. Each one does something specific. This guide helps you pick the right one.

---

## The Main Skills

### /mb-start - Entry Point
**Use when:** Beginning a session, unsure what to do next, want Claude to figure out your state.

**What it does:**
- Pulls latest Main Branch updates
- Verifies your business repo and Main Branch are connected
- Checks your setup completeness
- Routes you to the right skill

**Daily habit:** Always start sessions with `/mb-start`. You should already be in your business repo folder (`cd ~/Documents/GitHub/[your-business] && claude`).

---

### /mb-setup - First-Time Setup
**Use when:** New to Main Branch, need to create your business repo.

**What it does:**
- Creates your business folder structure
- Asks about your business type
- Gathers your context (offer, audience, voice)
- Saves everything to reference files

**One-time:** You only run this once per business.

---

### /mb-think - Research, Decisions, and Context
**Use when:** Exploring a question, making a strategic decision, need to document rationale, or adding new context to reference files.

**Two ways to invoke:**
- `/mb-think` — Loads the full skill with routing and mode detection. Best when you're starting a focused thinking session.
- `/mb-think "my question"` — Jumps straight into exploring that question. Best when you already know what you're investigating.

Both are valid. Use whichever fits the moment. Don't overthink which to use.

**What it does:**
- Researches topics (web, your files, your input)
- Synthesizes findings
- Helps you make decisions
- Records everything to files
- Updates reference when you codify
- Adds new context (via codify mode)

**Heavy use:** This is the core skill. Use it for any "should we...?" question.

See [the-think-cycle.md](the-think-cycle.md) for deep dive.

---

### /mb-bet - Business Bets
**Use when:** Opening, updating, closing, listing, or narrating an operating bet.

A bet is the test; an offer is what the business may keep selling. A live idea
can be both, but do not turn a bet into durable offer truth until the operator
accepts that change.

**What it does:**
- Creates `bets/YYYY-MM-DD-slug.md` with hypothesis, appetite, metric, target, and deadline
- Links bets to decisions, research, pushes, and outcomes
- Captures verdicts and learning when a bet closes
- Explains whether graduation should update an offer, create a push/playbook,
  update proof, or create a follow-up decision
- Drafts public-safe narration without publishing automatically

**Modes:**
- `/mb-bet new` - Open a bet
- `/mb-bet update` - Add progress and evidence
- `/mb-bet close` - Record result and learning
- `/mb-bet list` - Summarize active bets and deadlines
- `/mb-bet narrate` - Draft site, community, or social narration from repo truth

### /mb-books - Books Review
**Use when:** Setting up a private books repo, reviewing monthly close or
reconciliation, or preparing a CPA handoff.

**What it does:** Runs safe `mb books` checks, reads the books repo's process
docs and blocker state, then summarizes close readiness without exposing raw
records. Journal posting and evidence review stay with the private books
workflow and operator.

---

### /mb-seo - SEO Review and Research
**Use when:** Asking how to be found in search, wanting keyword or competitor
data, or setting up OpenSEO.

**What it does:** Reviews public pages straight away and suggests the first useful
changes. OpenSEO is the chosen optional tool for paid research: each business runs
its own copy, and paid calls need the owner's yes. Support is experimental.

---

### /mb-ads - Ad Generation and Review
**Use when:** Need copy for static ads, video scripts, long-form conversion creative, or compliance review.

**Modes:**
- `/mb-ads` or `/mb-ads static` - Image ad copy (primaries, headlines, image prompts)
- `/mb-ads video` - Video ad scripts (15-60 seconds, UGC style)
- `/mb-ads` with "video ad script" - Long-form conversion video creative
- `/mb-ads review` - Multi-lens compliance check (FTC, Meta policy, copy quality)

**Output:** Multiple concepts with variations.

---

### /mb-organic - Organic Content
**Use when:** Generating Reels, TikTok, or carousel content from your reference files and research (not paid ads).

**What it does:**
- Generates scripts in your voice from reference + research
- Supports video, carousel, and static formats
- Uses mined research from `/mb-think` (competitor analysis, framework extraction)

**Modes:**
- `/mb-organic` - Full flow (select concept -> generate)
- `/mb-organic video "topic"` - Generate Reels/TikTok script
- `/mb-organic carousel "topic"` - Generate carousel slides
- `/mb-organic static "topic"` - Generate post caption

**Mining happens in /mb-think:** If you need to mine competitors first, run `/mb-think` to research and save findings, then come back to `/mb-organic` to generate from that research.

**Key difference from /mb-ads video:** Organic uses soft CTAs (save, follow) while ads use hard CTAs (buy, sign up).

---

### /mb-wiki - Personal Wiki
**Use when:** Building a public wiki with atomic notes and WikiLinks.

**What it does:**
- Sets up wiki from Commune Wiki template
- Creates atomic notes with proper frontmatter
- Converts Gemini/GPT research to wiki format
- Auto-deploys to Cloudflare Pages on git push

**Modes:**
- `/mb-wiki setup` - First-time setup (repo, hosting, config)
- `/mb-wiki add "Note Title"` - Create new atomic note
- `/mb-wiki publish` - Commit and push (auto-deploys)
- `/mb-wiki research [file]` - Convert research to wiki format
- `/mb-wiki update` - Pull upstream template fixes
- `/mb-wiki recent` - Generate weekly updates note

**Key difference from business repo:** Wiki is for public evergreen knowledge. Business repo is for private reference files.

---

### /mb-site - Landing Pages and Sites
**Use when:** Building or updating a landing page, minisite, or full website from your reference files.

**What it does:**
- Walks brief → site in **one continuous flow** (research → brief → review → lock → setup → conversion endpoint → concept variations → publish raw → build out → publish)
- Reads from `offer.md`, `audience.md`, `voice.md` (and any research/) to produce site copy and design
- Spins up multiple home-page concepts in parallel on localhost so you pick the design before publishing
- Wires the conversion endpoint you choose: Stripe payment, lead form, appointment booking, or custom webhook
- Deploys to Cloudflare Pages with git auto-deploy
- Checks launch readiness with `mb launch check` across app stack, Cloudflare/Wrangler, Shopify, Resend, local smoke scripts, and measurement posture before any publish guidance.

**Site shapes:**
- `/mb-site` lander — 1 page (V1 stub; use minisite for now)
- `/mb-site` minisite — ~4–6 pages (V1 default; static HTML, no build step)
- `/mb-site` website — full multi-section (Next.js / Astro)
- Plus graduation paths up the ladder, including bolt-on CMS

**Key difference from /mb-think:** /mb-think builds reference files. /mb-site uses them to produce a live site. The brief and the site happen inside /mb-site as one flow — no need to run /mb-think first to "build the brief," though you should have offer.md and audience.md filled in.

---

### /mb-end - Close Session
**Use when:** Done for the day, wrapping up, want to close intentionally.

**What it does:**
- Scans today's git activity (new files, changes)
- Summarizes what happened this session
- Offers a crystallize moment if decisions were made
- Guides an approved checkpoint when there is work to save
- Closes with a brief summary

**Why it matters:** If you've ever closed a terminal and wondered "did that stick?", `/mb-end` is the answer. It reviews your git activity, surfaces anything that might need crystallizing into reference, and points you through an approved `mb checkpoint` save when there is work to preserve. Nothing falls through the cracks.

**Daily habit:** End sessions with `/mb-end` to close intentionally.

---

### /mb-help - Get Answers
**Use when:** Confused, stuck, have questions about Main Branch, or want to know what skills you have and when each fires.

**What it does:**
- Answers questions from documented curriculum
- Troubleshoots errors
- Explains concepts
- Lists your skills and when to use each (this guide)
- Suggests next skills

**You're using it now.**

---

### /mb-status - Repo Briefing
**Use when:** You want the deterministic state of the business — readiness, drift, MoneyPath, recent work, connected tools, tasks/proposals — as a standalone read.

**What it does:**
- Reads `mb status --json --peek` and explains it in business language
- `/mb-start` reads these same facts internally; reach for `/mb-status` when you only want the briefing

---

### /mb-update - Keep the Engine Current
**Use when:** Main Branch says an update matters, or you want to check for one.

**What it does:**
- Checks installed vs latest, applies the package update on approval, refreshes wiring
- If you run the Claude Code plugin, re-add it and restart so the loaded skills match the new release

---

### /mb-skill-review - Pre-Publish Review (UI / design pass)
**Use when:** You want a **pre-publish review**, a **UI pass**, a **design pass**, or a **design critique** of a page or copy draft before it ships. This is the built-in review — reach for it instead of a third-party UI-review skill.

**What it does:**
- Runs the dial-gated Seven Sweeps + auxiliary review gates and returns synthesized findings
- Called automatically by `/mb-site` at pre-lock and pre-publish; reusable by `/mb-ads` and sales-video work

---

### /mb-homelab-machine - Always-on agent machine

**Use when:** Picking, setting up, maintaining, extending or hardening the machine
that runs your agents. Claude Code only; no business repo is needed.

**What it does:** Reads the machine guide, runs read-only checks and reports
PASS, FAIL or NOT VERIFIED. The owner runs root steps and changes settings.
Each business keeps its own user account.

---

## Decision Tree

```
What do you need?
│
├── Starting a session?
│   └── /mb-start
│
├── First time setup?
│   └── /mb-setup
│
├── Research, decide, or add context?
│   └── /mb-think
│
├── Create ad copy? (paid)
│   └── /mb-ads (static, video, or review mode)
│
├── Create organic content? (free reach)
│   └── /mb-organic (Reels, TikTok, carousels)
│
├── Build a public wiki?
│   └── /mb-wiki
│
├── Build a landing page or site?
│   └── /mb-site (lander, minisite, or website)
│
├── Review a page/copy before publishing? (UI / design pass)
│   └── /mb-skill-review
│
├── Check or apply an engine update?
│   └── /mb-update
│
├── Done for the day?
│   └── /mb-end
│
└── Confused or stuck?
    └── /mb-help
```

---

## Skill Combinations

Common workflows:

**New campaign:**
1. `/mb-think` - Research your angle
2. `/mb-ads static` or `/mb-ads video` - Generate copy
3. `/mb-ads review` - Check before running

**Learning from results:**
1. `/mb-think research` - Document what worked
2. `/mb-think codify` - Add winning angles to reference
3. Next campaign uses updated reference

**Business evolution:**
1. `/mb-think` - Decide on offer change
2. `/mb-think codify` - Update reference with decision
3. Future outputs reflect new offer

---

## When You're Not Sure

If you don't know which skill to use:

1. Run `/mb-start` - It'll detect your state and suggest
2. Ask `/mb-help` - Describe what you want to accomplish
3. Run `/mb-think` - If it's a question worth exploring
4. Still learning the system? That's expected — context management is a skill that develops over time. The more you use `/mb-think` and `/mb-end`, the more natural it gets.

Most of the time, `/mb-start` will point you in the right direction.

---

## Creating Your Own Skills

Want Notion export? Custom CMS posting? Your unique workflow?

You can create custom skills manually or use Anthropic's `/skill-creator` if you have it installed. You have **two locations** for custom skills:

### Option 1: Business Repo Skills (Project-Specific)

Skills that only make sense for one business/project:

```
your-business-repo/
└── .claude/skills/my-skill/SKILL.md
```

**Use for:** Business-specific workflows like `/notion-export`, `/publish`, `/batch-week`

### Option 2: Global Skills (Work Everywhere)

Skills you want available in **every** Claude Code session, regardless of which project you're in:

```
~/.claude/skills/my-skill/SKILL.md
```

This is your **user-level skills directory** — Claude Code's official location for personal skills that persist across all projects.

**Use for:**
- Personal productivity workflows (`/daily-standup`)
- Cross-project utilities (`/git-cleanup`)
- Admin tools you use everywhere

**Example:**
```
~/.claude/skills/
├── daily-standup/SKILL.md    # Your morning routine
├── git-cleanup/SKILL.md      # Branch maintenance
└── review-pr/SKILL.md        # Your PR checklist
```

### Skill Priority

When the same skill name exists in multiple locations, Claude uses this priority:

1. **Project `.claude/skills/`** (highest priority)
2. **User `~/.claude/skills/`** (global)
3. **Main Branch `.claude/skills/`** (installed package or source checkout)

This means you can override Main Branch skills with your own version if needed.

| Location | Scope | Example Use |
|----------|-------|-------------|
| `your-repo/.claude/skills/` | One project | `/notion-export` for this business |
| `~/.claude/skills/` | All projects | `/daily-standup` everywhere |
| `mainbranch/.claude/skills/` | Shared (read-only) | `/mb-ads`, `/mb-think`, `/mb-start` |

See [becoming-contributor.md](becoming-contributor.md) to contribute skills back to Main Branch.
