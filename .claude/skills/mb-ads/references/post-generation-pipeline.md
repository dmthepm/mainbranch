# Automatic Post-Generation Pipeline

**Every generation mode (Static, One-Liner, Video) runs this pipeline automatically after saving output.** Do not ask the user whether to run compliance review -- it is automatic.

## Step 1: Checkpoint Pre-Review

Phase 0 of [review-workflow.md](review-workflow.md): plan, show, save only after operator approval.

## Step 2: Select Lens Tier

| Output Type | Tier | Lenses |
|-------------|------|--------|
| One-liners (text only) | Copy Review | FTC, Meta Policy, Copy Quality, Voice Auth, Substantiation (5) |
| Video scripts (spoken word) | Copy Review | FTC, Meta Policy, Copy Quality, Voice Auth, Substantiation (5) |
| Static ads (copy + image prompts) | Full Review | All 5 above + Visual Standards (6) |

Visual Standards evaluates image prompt composition and safe zones -- skip it for text-only outputs.

## Step 3: Check Optional Image Provider Availability

If an approved image provider was detected at Step 0d AND the mode produces
images (Static or One-Liner):

1. Calculate cost estimate:
   - **Static ads:** N angles x 3 styles x current provider price
   - **One-liners:** 8 background clusters x current provider price
2. Ask ONE question: "Compliance review will run automatically. Also generate images with {provider/model}? Est. cost: ~$X for N images. (y/n)"
3. If yes -> include image gen agent in the parallel spawn
4. If no -> skip image gen, run compliance only
5. If no provider is available -> skip image gen silently, compliance runs alone

**Video scripts:** No image generation. Skip this step.

## Step 4: Spawn Parallel Agents (Single Message)

Spawn ALL agents in a single message for parallel execution. Use `subagent_type: "general-purpose"` for all agents.

**Compliance agents:** brief and context per lens as in Phase 2 of [review-workflow.md](review-workflow.md) (ad content inline, read-only, lens files from this skill's `references/lenses/`).

**Image generation agents (write-with-fallback pattern -- if user approved):**

Spawn ONE subagent PER IMAGE (or per 2-3 images if generating 15+). All image agents launch in the SAME message as compliance agents.

Each agent receives its prompt(s), visual-style.md context, output path, and target filenames. Agents generate via Python SDK, post-process, verify on disk, and return path + status + cost.

**IMPORTANT:** Main conversation writes `prompts.json` to disk BEFORE spawning agents (Python file I/O -- not affected by Write tool durability bug). Failed images get retried with a fresh single-image agent.

See [image-generation-workflow.md](image-generation-workflow.md) -> "Parallel Agent Spawning" for batching strategy, rate limiting, agent prompt template, and failure handling.

## Step 5: Synthesize Results and Gate Copy Changes

When all agents return:

1. **Compliance synthesis:** deduplicate lens findings into a unified P1/P2/P3 report. P1 goes to the user for decision (never auto-fixed; status BLOCKED). P2/P3 go through the dry-run compliance gate, diff and explicit approval in Phase 4 of [review-workflow.md](review-workflow.md). If the user declines, leave the batch file unchanged, keep `proposed-compliance-fixes.json`, and summarize the declined changes in chat. `review-log.md` is written only when the user approves source copy changes.

2. **Image synthesis (if applicable):**
   - Collect results from all image agents, retry any failures, write a local
     ignored review board/contact sheet, and write `image-index.md`
   - The review board answers: "Which playbook produced the best actual ad
     candidate?" It is visual-comparison scratch, not committed proof.
   - Commit only safe `image-index.md` records and distilled findings, not raw
     images, private paths, provider payloads, or screenshots.

## Step 6: Present Unified Report

```
Pipeline complete:
  Review: [STATUS] (P1: N, P2: N fixed, P3: N noted)
  Images: [N generated / N/A]
  Cost: [$X / N/A]

  [If P1 exists: show blocking issues with suggested fixes]
  [If P2/P3 exists: show proposed diff before applying]
  [If P2/P3 approved: show summary of applied fixes]
  [If P2/P3 declined: say source copy was left unchanged]

  Files:
    pushes/YYYY-MM-DD-{type}-{campaign}/
    |- {batch-file}.md (copy, unchanged unless approved)
    |- proposed-compliance-fixes.json
    [|- review-log.md]
    [|- image-index.md]
    [|- .mb/media/.../review-board.md (ignored scratch)]
    [|- .mb/media/.../images/ (ignored media)]

  Save reviewed copy [+ images] as a checkpoint? (y/n)
```

## Step 7: Checkpoint Post-Review

If the user approves, run Phase 5 of [review-workflow.md](review-workflow.md) (`[updated] {type} ad batch after review`). Do not run raw `git add` or `git commit`.

## Pipeline Timing

Compliance review (5-6 agents, read-only) typically completes in 30-60 seconds.
Image generation (parallel agents, one per image) typically completes in 30-90 seconds for 15 images.
All agents -- compliance + image -- run in parallel, so total time = max(slowest compliance agent, slowest image agent).

## One-Liner Image Generation Details

One-liners use **Template 4 (background-only)** from [image-prompt-templates.md](image-prompt-templates.md).

After creative variations are generated, cluster them by hook category:

| Cluster | Scene Type | Approx Lines |
|---------|-----------|--------------|
| Problem agitation | Dark, moody atmospheric | 4-6 |
| Emotional state | Warm, intimate | 3-5 |
| Transformation | Aspirational, bright lifestyle | 4-6 |
| Contrarian | Bold, stark, max contrast | 3-5 |
| Identity callout | Person-centered, relatable | 3-5 |
| Social proof | Clean, authoritative abstract | 2-4 |
| Curiosity/reframe | Two-tone, conceptual | 2-4 |
| Overflow | Versatile, brand-forward | 2-3 |

Generate 1 background per cluster (8 total) using **parallel subagents -- one agent per cluster**. Each agent generates its background, post-processes it, and returns the path + status. All 8 agents spawn in the same message as compliance agents. Map each variation to its cluster. Text overlay composited via Pillow post-processing (separate from Gemini generation).

Estimate cost from the current provider/model pricing at run time and record
the provider, model, docs-checked date, estimated cost, retries, and final cost
if available. User can choose 8 recommended background clusters, 15
backgrounds, or 30 unique backgrounds. At 15+, batch agents into groups of 2-3
images each to limit agent count.

See [image-generation-workflow.md](image-generation-workflow.md) for provider
selection, metadata, and fallback details.
