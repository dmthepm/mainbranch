---
name: mb-setup
description: "Bootstrap a new business folder with Main Branch structure, or migrate an existing single-offer folder to multi-offer. Use when: (1) New user needs Claude Code environment configured (2) User says \"set up\", \"get started\", \"initialize\", \"bootstrap\", \"create my repo\", \"new business\" (3) User is new to Main Branch and needs full onboarding (4) Migrating existing business context into the Main Branch structure (5) User wants to add a second offer to an existing repo. Creates CLI and skill wiring, a business folder with full structure, and bounded context until core files are useful. Applies business setup patterns. Teaches concepts during setup."
loops: [sense, decide, ship]
---

# Repo Setup

Get a new user fully configured with Claude Code and their business repo. Use
shipped `mb` commands for setup facts before teaching concepts or reading
reference prose.

**CLI facts first:** Run `mb doctor`, `mb start --json`, and
`mb status --json --peek` when a repo exists or can be identified. Use
`mb onboard status --json` as the read-only progress check for existing repos.
Use `mb onboard plan` only after the operator approves writing setup progress;
do not keep onboarding state only in chat prose. If there is no repo yet,
inspect `mb onboard --help`, explain the target folder, ask for approval, then
use `mb onboard` to create one instead of hand-rolling repo-shape checks.

For provider setup, use `mb connect plan` and `mb connect doctor --json` as the
durable readiness contract. Explain providers as business capabilities, not
developer config, and end with exact commands.

**Pasted setup guide = setup intent.** If the user pastes this guide, the
beginner setup guide, its prompt ("Help me set up Main Branch using the current
README and setup guide..."), the older "I want Main Branch: AI business memory
I own as files..." prompt, or any bootstrap prompt with business/folder intent, treat it as setup intent, not as a document to save.
Do not offer to save it as a document. Check `mb --version`; if missing, stop
with `pipx install mainbranch`. If present, inspect `mb onboard --help`,
explain the target folder, and ask before any write. When the pasted prompt
carries its own arc (brief interview, then install → doctor → onboard → seed
core files → teach the daily loop), follow that arc: interview first, stop at
the named first win, and show what was set up.

**GitHub-backed setup preflight.** GitHub is strongly recommended because it
gives Main Branch a free cloud backup, shared history, task/proposal layer, and
connector-friendly copy of the business brain. Main Branch can start locally
without GitHub. If the user wants backup, sync, collaboration, or `mb onboard
--github <owner/repo> --push`, check `gh auth status` and
`gh api user --jq .login` first.
Confirm the account is the one they expect before running a writing setup
command.

---

## Before We Begin

**Need help?** Type `/mb-help` + your question anytime. If conversation compacts (gets summarized), `/mb-help` reloads fresh context.

---

## Workflow

### CRITICAL: Write Boundaries in Sandboxed Environments

Some workspace-isolated tools may only allow direct file writes inside the current workspace folder. If you see:

> "Cannot edit files outside allowed directories"

In a regular terminal `claude` session, this is less common because Claude can often request permission and continue. In restricted workspace tools, limits are usually stricter.

Do **not** silently switch strategies. Ask the user first, in beginner language:

> "This app is only letting me edit files in this one workspace folder.
>
> Since this is first-time setup, switching workspaces mid-chat can be confusing. The easiest options are:
> 1. Continue here and I use terminal commands to create/update files in your target repo path
> 2. Stop here, open Terminal in the target repo folder, run `claude`, then run `/mb-setup` again
>
> If you already have a workspace open for that repo, we can use that too. Which option do you want?"

For first-time setup, do not default to "switch workspace now." Prefer option 1 or 2 unless the user already has the target repo workspace ready.

### Check Main Branch Updates and Detect CWD (FIRST)

**Repair Main Branch wiring + detect CWD before context gathering.** Four cases: CWD is the business folder (happy path), CWD is an old Main Branch repo needing repair/migration, CWD is the Main Branch source checkout (engine migration), or CWD is neither (ask user).

See **[references/cwd-detection.md](references/cwd-detection.md)** for the full repair path and all four cases (Case 1 happy path, Case 2 old repo repair, Case 3 engine migration, Case 4 ask). This must happen BEFORE any context gathering — if conversation compacts later, the essential config is already saved.

---

### 0. Check Chrome Extension (Optional, Helpful for Skool)

**Before gathering context, mention the Chrome extension:**

> "The Claude in Chrome extension lets me read your sales pages, Skool community, and web content directly. It's optional but helpful.
>
> To check if it's installed: open Chrome, go to `chrome://extensions`, and look for 'Claude'. If you don't have it: https://claude.ai/chrome"

**If not installed or user declines:** Proceed with URL fetching, Playwright, or manual screenshots. The extension is convenient but not required.

### 1. Confirm Repo + Working Directory

```bash
mb doctor
mb start --json
mb status --json --peek
pwd
```

If no business repo exists yet:
```bash
mb onboard --help
```

If the operator wants the folder created, saved, synced to GitHub, and ready
for Claude Code in one first-run pass, prefer the first-class onboarding path
over hand-rolled `git` / `gh` glue:

```bash
mb onboard --yes --name "[Business Name]" --path "[repo-path]" --github "[owner/repo]" --github-visibility private --push
```

End setup answers in owner language first: created, saved, synced to GitHub
when requested, and ready to open in Claude Code. Put git, remote, branch,
validation, and wiring details second as the technical receipt.

**Visibility default for business repos: private.** A business repo holds
offer experiments, strategy, drafts, client work, screenshots, and
operating notes. Default to a private repo and only switch to public when
the source itself is intentionally public (open-source tool, template,
demo, or build-in-public project). See
[references/repo-visibility-rubric.md](references/repo-visibility-rubric.md).
Use `references/where-data-lives.md` for the hub and child repo data boundaries.
Where the repo lives — local-only, personal GitHub, free GitHub
organization, or paid org — is a separate question from visibility. GitHub
organizations can be free; do not imply that "org" means paid. Default to
"personal GitHub or free GitHub organization" if the operator is unsure.

### 1a. Check Optional Tools (Inform, Don't Block)

**Local transcription (for mining your own recordings):**
```bash
which mlx_whisper 2>/dev/null || which whisper-cli 2>/dev/null; which ffmpeg
```

If missing, note for later:
> "Optional: For transcribing your own videos/voice memos, you'll want a whisper variant. `pip3 install mlx-whisper` is fastest on Apple Silicon. We can set that up later with `/mb-think`."

Don't block setup on this. Continue and mention it at the end.

### 2. Ask Business Type

> What type of business is this?

| Type | Setup Pattern |
|------|---------------|
| **Community/Skool** | Classroom, membership, funnel |
| **E-commerce** | Products, fulfillment, materials |
| **Coaching/Services** | Offers, delivery, packages |
| **Agency** | Services, clients, processes |
| **Other** | Core only, no extra operating folders |

**IMPORTANT:** If user has a Skool community, choose **Community/Skool** even if they also do coaching, courses, or services outside Skool. The community is the hub — other offerings feed into it.

Read `.claude/reference/business-primitives/setup-patterns.md` in the Main
Branch engine for the current setup patterns. Read
`.claude/reference/business-primitives/slug-conventions.md` before naming
offer folders, pushes, bets, or topology entries.

### 2.5: Offer Structure

After business type, determine offer structure:

> "How many distinct products or services do you sell?"

**If one:** "Single offer — clean and simple. All your details go in `core/`. Most people start here."

**If multiple:** "Multiple offers under one brand. You share the same soul and voice, but each offer has its own specifics."
- Ask: "What stable noun should name each offer? Use lowercase kebab-case slugs like `community`, `newsletter`, or `done-for-you`; do not rename later without a decision."
- Ask: "How do these relate? Is there a natural progression — like a free tier that feeds into a paid one?" (This builds `product-ladder.md`)
- Store offer names for Step 4 folder creation
- Note: The multi-offer rules live at
  `.claude/reference/business-primitives/offer-bet-push-proof.md` in the Main
  Branch engine; read it if the user has multiple offers

**Multi-business check (brief, not interrogating):**
> "Are any other business repos relevant right now? If you run completely separate brands, they each get their own repo. We're setting up this one."

This check is simple and non-intrusive. If they say yes, note it and move on — they can run `/mb-setup` again in the other repo later.

### 3. Gather Bounded Context

Your job is to collect enough to create useful core files, not every fact
possible. Users provide context in batches. Keep the first pass bounded by
`mb onboard status --json` and its missing inputs.

Before asking for data, run:

```bash
mb onboard status --repo "$REPO_PATH" --json
```

If business type, team size, success stage, or desired outcome are missing, ask
briefly. After the operator approves saving setup progress, write the plan:

```bash
mb onboard plan --repo "$REPO_PATH" --team-size solo --success-stage working
```

Do not ask for full finances, credentials, raw customer/member exports, or
exhaustive operations details during first-pass onboarding.

See **[references/context-gathering.md](references/context-gathering.md)** for:
- URL fetching fallback chain (WebFetch → Chrome → Playwright → manual)
- Business-type specific checklists (Skool, E-commerce, Coaching)
- Completeness criteria

**Opening prompt:**
> Share the essentials for the core files: what you sell, who it helps, why
> it works, proof you can share, and a few voice samples.
>
> **Pro tip:** You can drag screenshots directly into this terminal window and I'll read them. If you have a Skool community, screenshot your about page, classroom, pricing — drag them all in. Fastest way to get me up to speed.
>
> Paste text, share file paths, give me URLs to fetch, or drag in images. I'll sort it all into the right files.

**After each batch, assess gaps:**
> "Got it. I still need [X, Y, Z] to complete your core files. Can you share those?"

**Only say "we have enough" when you can fill:**
- offer.md (price, mechanism, deliverables, guarantee)
- audience.md (who, pains, desires, objections)
- voice.md (tone, phrases, personality)
- testimonials.md (3-5 with specific outcomes)
- core/operations/ (business-type specific structure)

### 4. Create Folder Structure

```bash
# Always create:
mkdir -p core core/offers core/finance core/brand core/proof/angles core/operations
mkdir -p research decisions bets log pushes documents
```

Do not create old repo structure in new repos. If an existing folder looks like
an old Main Branch repo, treat that structure as migration input and run
`mb doctor repair --plan` before relying on it. Write user context once under
current business files.

**Multi-offer only (if user has multiple offers from Step 2.5):**

```bash
# Create offer folders for each offer
for offer in [offer-names]; do
  mkdir -p "core/offers/$offer"
done

# Ask before persisting active-offer state. Offer choice can stay session-scoped.
# Do not write .vip/local.yaml as the active-offer mechanism.
# Keep the choice session-scoped unless a future mb command exposes an explicit
# session-state contract and the operator confirms persistence.

# Create product-ladder.md placeholder at core/product-ladder.md
touch core/product-ladder.md
```

Full structure (single-offer):
```
{business-name}/
├── CLAUDE.md              # Always loaded - business brain
├── README.md              # Human-readable overview
├── .env                   # Secrets (gitignored)
├── .gitignore             # Include .env
│
├── core/                  # Evergreen business brain
│   ├── soul.md            # Why you exist
│   ├── offer.md           # What you sell / brand thesis
│   ├── audience.md        # Who buys
│   ├── voice.md           # How you sound
│   ├── content-strategy.md # Business-level content strategy and layer index
│   ├── marketing/          # Optional distribution, channel, account layers
│   ├── people/             # Optional founder/person voice source material
│   ├── proof/
│   │   ├── testimonials.md
│   │   └── angles/        # Proven messaging entry points
│   ├── brand/             # Visual identity and brand systems
│   ├── operations/        # Business-type specific operating context
│   ├── finance/           # Ledger and tax artifacts
│   └── offers/            # Per-offer specifics when multi-offer
│
├── research/              # Dated investigations
│   └── YYYY-MM-DD-topic-[source].md
│
├── decisions/             # Dated choices with rationale
│   └── YYYY-MM-DD-topic.md
│
├── bets/                  # Operating bets with target, deadline, and result
│   └── YYYY-MM-DD-topic.md
│
├── log/                   # Running activity log
│
└── pushes/                # Coordinated pushes and their artifacts
    └── YYYY-MM-DD-push-name/
```

Full structure (multi-offer — adds offer folders and `product-ladder.md`):
```
{business-name}/
├── ...                    # Same as above, plus:
├── core/
│   ├── product-ladder.md  # How offers relate
│   └── offers/            # Offer-specific overrides
│       ├── community/
│       │   └── offer.md   # Offer-specific details
│       └── course/
│           └── offer.md
```

### 4a. API Key Environment, Config, and .gitignore

See **[references/repo-scaffolding.md](references/repo-scaffolding.md)** for:
- API key environment setup (`~/.config/vip/env.sh`)
- Legacy `.vip` cleanup guidance
- `.gitignore` creation

Run these steps in order: create env.sh when needed, add shell source line when
approved, and create `.gitignore`. Do not create `.vip/config.yaml` for new
repos.

### 5. Sort Content into Files

**The repo is a precision instrument, not a dumping ground.** Not everything the user provides makes it into core files. Filter for what helps LLMs produce great outputs.

Use templates from `references/templates.md`.

**Teach WHY each file matters as you create it.** Don't just scaffold — explain. This is the user's first encounter with the system. The act of writing these files IS the learning.

See **[references/file-education.md](references/file-education.md)** for the educational blurbs to present before writing each core file (team, soul, offer, audience, voice, multi-offer additions), the priority order, and the visual style scaffolding questions.

When the operator asks how the business should build and operate day to day, point at the engine's `docs/operating-principles.md` — the twelve principles, the decision rule, and the subagent operating contract, proven on a live business.

### 6. Apply Business Setup Pattern

Based on business type, create useful operating folders:

**E-commerce:** `core/operations/products/`, `core/operations/fulfillment/`
**Community/content-led:** `core/operations/classroom/`,
`core/operations/membership/`, `core/operations/funnel/`,
`core/content-strategy.md`, optional `core/marketing/` and `core/people/`
layers, `core/operations/funnel/skool-surfaces.md`

See `.claude/reference/business-primitives/setup-patterns.md` in the Main
Branch engine for current setup patterns. Historical engine builds may still
contain older compatibility notes under paths that use the word "domain"; treat
those as migration notes only, not the current product model.

Also scaffold `core/operations/agent-access-dossier.md` from
`references/templates.md` — the capability map (storage doctrine, provider
verify table, never-print rules); fill rows from what the operator connects.

### 7. Draft CLAUDE.md

See `references/claude-md-guide.md` for structure.

**Key sections:**
- One-line description
- Engine reference (Main Branch)
- Folder structure diagram
- Business summary
- Quick reference (audience, voice, offer)
- Key decisions/research index
- Reference tiers

### 8. Create README.md

Simple human-readable overview:
- What the business is
- How to use the repo with Main Branch
- Quick stats

### 9. Initial Saved Checkpoint

```bash
mb checkpoint --plan --json
mb checkpoint --validate "[added] initial business repo foundation" --json
mb checkpoint --message "[added] initial business repo foundation" --yes
```

Summarize the plan first, including changed surfaces/files and any blockers.
Save only after operator approval. Use `mb checkpoint --plan`'s proposed
subject when it is good; otherwise use a business-readable checkpoint subject
from `references/git-workflow.md`.

### 10. Report Gaps

| File | Status |
|------|--------|
| core/soul.md | [OK] Complete / [WARN] Missing [X] |
| core/offer.md | [OK] Complete / [WARN] Missing [X] |
| core/audience.md | [OK] Complete / [WARN] Missing [X] |
| core/voice.md | [OK] Complete / [WARN] Missing [X] |
| core/proof/testimonials.md | [OK] Has content / [FAIL] Empty |
| core/proof/angles/ | [OK] [N] angles / [WARN] None yet |
| core/operations/ | [OK] Populated / [WARN] Needs [X] |

**Multi-offer additional checks (if applicable):**

| File | Status |
|------|--------|
| core/offers/[name]/offer.md | [OK] Complete / [WARN] Thin (< 20 lines) / [FAIL] Missing |
| core/product-ladder.md | [OK] Complete / [WARN] Placeholder |
| active offer | [OK] Selected for session / [INFO] Not persisted |

Ask user for missing pieces or note for later.

---

## Save And Review Workflow

Use `mb checkpoint --plan`, `mb checkpoint --validate`, and
`mb checkpoint --message ... --yes` for business-repo saves. Use lower-case,
past-tense checkpoint verbs such as `[added]`, `[updated]`, `[decided]`,
`[connected]`, `[ran]`, or `[fixed]`. Pull requests are proposals or review conversations.
The planned `mb publish --plan` command and packaged publish
skill are not shipped yet, so do not promise them.

See `references/git-workflow.md` for the full guide.

---

## References

- **Repo Visibility Rubric:** `references/repo-visibility-rubric.md` — Private-by-default, the one visibility question for site repos, and what visibility does not decide
- **CWD Detection:** `references/cwd-detection.md` — Check Main Branch updates + Case 1/2/3/4 flows for detecting where the user is
- **File Education:** `references/file-education.md` — What to teach the user about each core file, priority order, visual style scaffolding
- **Context Gathering:** `references/context-gathering.md` — Checklists by business type, completeness criteria
- **Templates:** `references/templates.md` — All file templates
- **CLAUDE.md Guide:** `references/claude-md-guide.md` — How to draft a good CLAUDE.md
- **Save and Review Workflow:** `references/git-workflow.md` — Checkpoint-first saves, sync language, and proposal/review guidance
- **Repo Scaffolding:** `references/repo-scaffolding.md` — API keys, config.yaml, .gitignore
- **Multi-Offer Migration:** `references/migration-multi-offer.md` — Single to multi-offer migration

---

## Recovering from Compaction

If conversation compacts mid-setup:

**For the user:** Type `/mb-setup` again and describe where you were:
- "We're in the middle of gathering context for my Skool community"
- "I was giving you screenshots, you hadn't created files yet"
- "You created the folder structure but we haven't sorted content"

**For Claude:** When resuming:
1. Check if business repo exists (look for current markers; if CWD looks like an old Main Branch repo, run `mb status --json --peek` and `mb doctor repair --plan` from CWD before fallback)
2. If exists, check which files are populated vs empty
3. Resume from the appropriate step based on what's done
4. Confirm with user: "I see [business-name] with [X] files. Looks like we're at step [N]. Continue?"

---

## Migration: Single-Offer to Multi-Offer

When an existing user wants to add another offer (says "I want to add another offer", "I have a second product", or similar), follow the migration guide.

See **[references/migration-multi-offer.md](references/migration-multi-offer.md)** for the complete migration flow: detection, naming, atomic execution, brand-level offer.md creation, product-ladder.md, and the saved checkpoint.

---

## After Setup: What's Next

Once setup is complete, tell the user:

> "Your business repo is ready! Here's what to do next:
>
> **Daily workflow:**
> ```
> cd ~/Documents/GitHub/[business-name]
> claude
> /mb-start
> ```
> Main Branch loads as a Claude Code plugin (Desktop or terminal); setup also writes a `settings.local.json` + bridge-link fallback — no need to touch the Main Branch package or source-checkout folder.
>
> **Key skills to try:**
> - `/mb-think` — Research topics, make decisions, update reference
> - `/mb-think` — Build your content strategy (known-for target, pillars, channels, accounts, cadence) — start here after core files are solid
> - `/mb-ads` — Generate image ads, video scripts, or review for compliance
> - `/mb-site` — Build pages and owned-surface sales videos/VSLs
> - `/mb-organic` — Create organic content aligned to your content strategy
> - `/mb-help` — Get answers anytime you're stuck
>
> **The core loop:** Use `/mb-think` regularly. Research → Decide → Codify. This is how your core files get smarter over time.
>
> **Remember:** Type `/mb-help` + your question anytime. It has answers about Terminal basics, the business folder, CLI, skills, troubleshooting, and more."

**If whisper-cpp was missing during setup:**

> "One more thing: To transcribe your own videos and voice memos, install whisper-cpp:
> ```bash
> brew install whisper-cpp ffmpeg
> mkdir -p ~/.whisper
> curl -o ~/.whisper/ggml-base.en.bin -L \
>   'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'
> ```
> Then `/mb-think` can mine your recordings directly."

**If the user wants image generation:**

> "Want to generate actual images for ads and content? See `references/nano-banana-setup.md` for Nano Banana setup (uses your existing Google API key)."
