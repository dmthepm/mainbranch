# The /mb-think Cycle

The heart of Main Branch: research, decisions and reference files preserve the business reasoning future sessions need.

```
RESEARCH → DECIDE → CODIFY → GENERATE → LEARN
    ↑                                      │
    └──────────────────────────────────────┘
```

Investigate, choose with documented rationale, update reference files, let skills generate outputs, feed results back into research. Each loop makes your reference more accurate and outputs more effective.

## How it works

`/mb-think "What pricing tier should we use?"` researches (web, your files, your context), synthesizes a clear summary, presents options with pros/cons, helps you decide, saves research and decision as files, and optionally updates reference.

| Mode | What it does |
|------|--------------|
| `/mb-think "topic"` | Full flow inline: research, decide, codify. Best for a specific question. |
| `/mb-think research "topic"` | Investigate and save findings |
| `/mb-think decide "topic"` | Document a decision (research already done) |
| `/mb-think` | Loads the full skill with routing; asks what you want to work on. Best when exploring. |

| Type | Location | Purpose |
|------|----------|---------|
| Research | `research/2026-01-19-topic-claude-code.md` | Dated investigations |
| Decisions | `decisions/2026-01-19-topic.md` | Choices with rationale |
| Reference | `core/offer.md` | Evergreen truth skills consume |

Research is any investigation that informs a decision: web research, data mining, transcript analysis, competitor mining, internal audits. Every research output needs a one-sentence summary (20 words max), 5-10 key findings, implications for reference files, and open questions. If you can't summarize it, you don't understand it yet.

Use it for pricing, positioning and messaging decisions, turning data dumps into insights, and any "should we...?" question. Don't use it for quick factual questions, simple file edits, or content generation (use `/mb-ads`, `/mb-organic`, `/mb-site`).

## Why record everything

Context windows are limited and conversation fades; files persist. Come back next week and the research is there; six months later the decision file explains why. Knowledge compounds.

## Working after compaction

Compaction loses conversational context, not your repo: research, decision and reference files are on disk and in git. If an insight only existed in conversation, it is gone, so when in doubt save a research file. To rebuild context, point Claude at recent work ("Look at my last 3 decisions", "Read the commits from today", "Summarize what's in `research/` from this week"), or just run `/mb-start`, which scans your folders and routes you. The files are plain markdown, readable in Cursor, Warp, VS Code or any editor. Context management gets easier after a few sessions: think, capture, move on.

## Decisions as rationale anchors

For substantial work, create the decision file early, even before you have decided: `proposed` (direction drafted, still evaluated) -> `accepted` (operator chose it; describe what changes) -> `codified` (rationale integrated into durable business or engine truth). `## What Changes` lists the reference files affected; `## Review Date` is optional. Rationale maturity is visible in the file, and next session `/mb-start` recovers the view from files, git, GitHub facts, graph links and checkpoints. Follow-up work routes into a push, playbook, log, checkpoint or GitHub issue when it needs a durable thread. For smaller work, just do it.

## Work continuity

Main Branch does not ask operators to pick a task system; see [work-continuity.md](work-continuity.md). **decisions/** hold choices and rationale, **pushes/** coordinated launches, drops, promos or operating pushes, **bets/** wagers, success metrics, verdicts and lessons, **GitHub issues** durable threads that need visibility, **checkpoints** saved progress at meaningful boundaries.

## Closing the loop: /mb-end

`/mb-end` offers a natural crystallize moment ("What did you learn?"), where accumulated doing becomes understanding and often updates reference files. It is also your safety net: it reviews what happened so nothing falls through before you close.

Next step: got a question you've been wrestling with? Run `/mb-think`.
