# CLAUDE.md Guide

How to draft an effective CLAUDE.md for a business repo.

---

## Purpose

Your entire repo is a precision instrument for LLM context quality. Every file should earn its place. CLAUDE.md is the lightest layer — summaries and pointers, not full content.

CLAUDE.md is the **always-loaded business brain**. Claude reads this file at the start of every session. It should contain:

- Enough context to work effectively
- Pointers to deeper reference files
- Current state and key decisions

**Not too much** — keep it scannable. Put deep details in reference files.

---

## Structure

```markdown
# [Business Name]

[One sentence: What this business is]

---

## Main Branch

This folder contains your **business files**. Main Branch adds the `mb` CLI
and skills around those files.

**Setup:**
1. Start Claude in THIS folder (your business folder) and run `/mb-start`
2. Main Branch is linked via `.claude/settings.local.json` (with bridge links as compatibility fallback)

**How it works:**
- `mb` CLI: Checks setup, status, readiness, repairs, and updates.
- Skills: Read `core/`, `research/`, and `decisions/`, then write coordinated work to `pushes/`.
- This folder: Contains the business context you own and edit.

**If `/mb-start` isn't available:** Run `mb skill link --repo .`, then restart
Claude. For old clone-era installs, use `docs/migrating.md`.

---

## Folder Structure

```
[business-name]/
├── CLAUDE.md              # Always loaded - business brain
├── README.md              # Human-readable overview
│
├── core/                  # Evergreen business brain
│   ├── offer.md
│   ├── audience.md
│   ├── voice.md
│   ├── content-strategy.md
│   ├── brand/             # Deep brand systems
│   ├── proof/
│   │   ├── testimonials.md
│   │   └── angles/
│   └── operations/        # Business-type specific
│
├── research/              # Dated investigations
├── decisions/             # Dated choices with rationale
└── pushes/                # Coordinated work records and generated output
```

---

## The Business ([Month Year])

**What it is:** [Brief description]

**Current state:**
- [Key metric 1]
- [Key metric 2]
- [Current situation/phase]

**Key assets:**
- [Asset 1]
- [Asset 2]

---

## The Customer

[2-3 sentences about who buys]

**Who they are:**
- [Characteristic 1]
- [Characteristic 2]

**Full profile:** `core/audience.md`

---

## Voice (Quick Reference)

**Tone:** [Primary tone]
**Cadence:** [How it flows]
**Key phrases:**
- "[Phrase 1]"
- "[Phrase 2]"

**Full system:** `core/voice.md`

---

## Key Decisions

| Decision | File |
|----------|------|
| [Decision 1] | `decisions/YYYY-MM-DD-topic.md` |
| [Decision 2] | `decisions/YYYY-MM-DD-topic.md` |

---

## Reference Tiers

| Tier | What | When Loaded |
|------|------|-------------|
| **Always** | This CLAUDE.md | Every session |
| **Core** | core/*.md | When generating content |
| **On-demand** | research/, decisions/ | When reasoning about choices |
| **Deep reference** | core/brand/, core/proof/ | When writing copy |
| **Domain** | core/operations/ | When business-type matters |

---

## Work Continuity

- Active bets: `bets/`
- Active pushes: `pushes/`
- Decisions that explain direction: `decisions/`
- Team handoffs and daily records: `log/`
- Use GitHub issues only when work needs a durable thread across sessions,
  proposals, releases, or team visibility.

This gives `/mb-start` business-language routing hints without creating a
separate work-management surface.
```

---

## What to Include

### Must Have
- Business one-liner
- Engine reference
- Folder structure
- Current state summary
- Customer quick reference
- Voice quick reference
- Reference tiers

### Should Have (if exists)
- Key decisions index
- Work-continuity routing hints
- Best sellers / top products
- Current strategy
- Known gaps
- Tools in use

### Avoid
- Full testimonials (put in `proof/testimonials.md`)
- Complete product catalog (put in `core/operations/products/`)
- Deep voice system (put in `core/brand/voice-system.md`)
- Research content (put in `research/`)

---

## Progressive Disclosure

CLAUDE.md is **Tier 1** — always loaded, so keep it lean.

Pattern:
1. **Summary in CLAUDE.md** — Quick reference
2. **Pointer to full file** — "Full system: `core/voice.md`"
3. **Claude loads on-demand** — When actually needed

Example: the "Voice (Quick Reference)" block above (tone and key phrases here, `Full system: core/voice.md` as the pointer).

---

## Length Guidelines

- **Ideal:** 100-300 lines
- **Maximum:** 500 lines
- **If longer:** Move content to reference files

CLAUDE.md shares context window with everything else. Keep it tight.

---

## Update Cadence

Update CLAUDE.md when:
- Business state changes significantly
- New major decisions are made
- Strategy shifts
- Key metrics update (quarterly)

Don't update for:
- Every small change
- New research (goes in `research/`)
- New testimonials (goes in `proof/`)
