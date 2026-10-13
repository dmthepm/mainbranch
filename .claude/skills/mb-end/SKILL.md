---
name: mb-end
description: "Session-closing skill that helps users wrap up intentionally. Use when: user says done, wrapping up, end my day, closing out, call it a day, goodnight, that's it for today, checkpoint, pause. Bookend to /mb-start. Scans git activity, surfaces what happened, spawns a crystallize agent for deep analysis, offers to save an approved checkpoint, and closes with a brief summary. Works for end-of-day, end-of-research-batch, end-of-decision-sprint, or mid-work checkpoints."
loops: [reflect, ship]
---

# End

Close your session intentionally. The bookend to `/mb-start`.

**You only run this when you choose to.** It is never auto-invoked.

**Shared source:** The portable workflow contract lives in
`workflows/mb-end/workflow.md`. This Claude skill is the Claude Code shell over
that source.

**CLI facts first:** After finding the business repo, run
`mb status --json --peek` and `mb checkpoint --plan --json` before summarizing
the session or offering to save. Use status `journal`, `since_last_check`,
dirty-work, readiness, and checkpoint facts as the primary source. Raw git is
fallback/detail only when `mb` facts are unavailable or a crystallize step needs
site-code history the CLI does not expose.

**Shared contract markers:** Keep these aligned with the shared source.

Required commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb checkpoint --plan --json`
- `mb validate --json`

Required fact paths:

- `money_path`
- `money_path.objects.proof.quality`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `relationship_health.gaps`
- `update`
- `readiness`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `journal`
- `since_last_check`
- `checkpoint.pending`
- `checkpoint.pending.changed_files`
- `checkpoint.pending.blockers`
- `checkpoint.pending.proposed_subject`
- `summary.changed_files`
- `safety.blocks`
- `proposal.message`
- `validation`

Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`,
`provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`,
`destructive_operations`, and `public_issue_or_proposal`.

Public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, and `no_raw_finance_legal_records`.

Core closeout flow: status scan, checkpoint plan, session summary, final
thought capture, crystallize, approval-gated save, owner-facing save states,
and warm close.

---

## Philosophy

The end of a session is the highest-leverage reconnection point. All session you were doing -- researching, deciding, generating. Now you step back and see what actually happened. Accumulated doing becomes conscious understanding.

`/mb-end` is not just end-of-day. It closes any significant session:

- **End of day** -- wrapping up, done for today
- **End of a research batch** -- crystallize before deciding
- **End of a decision sprint** -- step back and see what decisions mean together
- **Mid-work checkpoint** -- pause deep work, crystallize, then continue

The crystallize moment does not assume the user is leaving. It assumes the user wants to step back from doing and see what happened.

This is not an audit. It is a thoughtful friend helping you close the session.

---

## The Flow

```
1. Find the business repo
2. Scan today's activity
2b. Decision lifecycle reconciliation (shared audit script)
3. Session summary
4. Final thought capture (optional)
5. Crystallize (spawns dedicated agent if meaningful activity detected)
   5a. Check for meaningful activity
   5b. Gather file contents for the agent
   5c. Spawn crystallize agent (Task tool)
   5d. Present output to user as-is
   5e. If user engages: stay with it (engagement protocol)
   5f. Propose saving crystallize output as a research file
6. Checkpoint & close
```

Step 4 is optional. Step 5 is required when meaningful activity happened
(decisions, research, core changes) unless the user explicitly asks for a quick
close or the runtime cannot support it. In Claude Code, use the Task subagent
for deep crystallize. In runtimes without that surface, the shared workflow
still requires crystallize-lite instead of silently skipping the ritual.

A quick `/mb-end` (user says "just commit and close") can be steps 1-3 and 6. But if there is meaningful activity and the user did not explicitly skip, always run Step 5.

**Mid-session save vs session close.** When the operator only wants to save
progress and keep working -- "save", "save my progress", "checkpoint this", "yes
save" mid-flow, "should we checkpoint everything" -- this is a save, not a close.
Run `mb checkpoint --plan --json`, show the planned save, save on approval through
`mb checkpoint`, and return them to their work. Do not run the crystallize/summary
closeout, and never save with raw `git add`/`git commit` -- the save always goes
through `mb checkpoint`. Reserve the full flow (crystallize, final thought, warm
close) for an actual end or pause of the session.

---

## Step 1: Find the Business Repo

**CWD-first:** If current Main Branch markers exist in CWD, use it. If CWD looks like an old Main Branch repo, run `mb status --json --peek` and `mb doctor repair --plan` before saved config or discovery. Do not write to old repo structure; tell the operator to follow the repair/migration plan. Otherwise, read `~/.config/vip/local.yaml` for `default_repo` only as a legacy machine-local fallback.

**If no repo found:** Skip to a simple close. No business repo means no git activity to scan.

**Do not ask the user to pick a repo.** /mb-end is a quick close, not a triage. Use CWD or the default. If the user worked in a different repo today, they can say so.

---

## Step 2: Scan Today's Activity

Run these in the user's business repo first:

```bash
mb status --json --peek
mb checkpoint --plan --json
```

Before the checkpoint, compare changed bets, pushes, decisions, and research
files with `relationship_health.gaps` evidence or records. If a gap names one,
offer one link fix with the field and file; ask at most one question. Otherwise skip.

**Parse what you find into categories:**

| Category | How to Detect |
|----------|---------------|
| Research files created | `journal.events[].files` and checkpoint changed files under `research/` |
| Decisions made | `journal.events[].files` and checkpoint changed files under `decisions/` |
| Core files updated | Status/checkpoint changed files under `core/` |
| Push artifacts generated | Status/checkpoint changed files under `pushes/` |
| Unsaved work | Status dirty-work facts and `mb checkpoint --plan` changed files/blockers |

**Pulse check (skip if no `core/operations/pulse/`):** If today's
`log/<date>-*-pulse.md` exists, compare its ONE recommended action against
today's activity — done, moved into a lane (bet/issue/decision), or untouched
— and say which in the session summary. If the scaffold exists but today's
paper was never written, note it at close so tomorrow opens with a fresh pulse.

**Multi-offer detection (skip if no `core/offers/` folder — single-offer mode,
everything reads from `core/`):** Use status/checkpoint file paths under
`core/offers/` to note which offers changed. If those facts are unavailable,
use a raw git fallback:
```bash
git diff --name-only HEAD@{midnight}..HEAD -- core/offers/ 2>/dev/null | head -20
```
Report: "Offers affected: community, newsletter" (or "Brand-level changes only" if only core/ changed)

**If status/checkpoint facts are unavailable** (repo issues or an older CLI):
fall back to `git status`, `git log`, and `ls -lt` only to avoid blocking the
close.

**If nothing happened today:** Say so briefly. "Quiet day -- no changes detected. Want to close out?" Skip to Step 6.

---

## Step 2b: Decision Lifecycle Reconciliation

Run the shared lifecycle audit script so `/mb-end` uses the same decision buckets as `/mb-start` (`needs_review`, `action_needed`, `stale_orphaned`, `invalid_or_missing`).

**Manual confirmation rule (non-negotiable):** Never auto-flip to `codified` from evidence alone. If `needs_review > 0`, offer to review with the user; require explicit confirmation per file before editing `status: accepted` -> `status: codified`. If declined, leave statuses unchanged and continue.

For the full bash (vip script resolution + fallback strict status counter), expected buckets, and confirmation protocol, see [references/decision-lifecycle-audit.md](references/decision-lifecycle-audit.md).

---

## Step 3: Session Summary

Present a brief, warm summary. Not a report -- a reflection.

**Offer context:** If a future `mb` JSON active-offer field or explicit session context identifies an active offer, include in summary:
"Worked on: **[offer]**"

**Format (adapt to what actually happened):**

> "Here's what happened today:
>
> - Researched [topic] (research file saved)
> - Made a decision on [topic]
> - Updated offer.md with [what changed]
> - Generated a batch of [type] outputs
>
> [1 sentence connecting the dots -- what theme ties today's work together?]"

**Guidelines:**

- Keep it to 3-6 bullet points max. Summarize, don't list every file.
- If reference files were updated, highlight that -- it is the most valuable work.
- If decisions were made but not codified, note it gently: "Decision on [topic] is ready to codify when you're back."
- The connecting sentence should feel like an observation, not a judgment. "Lot of foundation work today" or "Focused session -- pricing is locked in now."

---

## Step 4: Final Thought Capture (Optional)

Ask once:

> "Any final thoughts before we close?"

**If the user shares something:**

- If it is brief (a sentence or two), acknowledge it and include it in the checkpoint summary or suggest adding it to an existing research file.
- If it is substantial (a paragraph or more), offer to save it: "Want me to save that as a quick research note? `research/YYYY-MM-DD-end-of-day-thoughts.md`"
- Use today's date. Source suffix: `-end-of-day.md`

**If the user says no, nothing, or skips:** Move on. No friction.

**After Step 4 -- whether the user engaged or not -- proceed to Step 5.** Do not stop here. Do not wait for permission. If meaningful activity happened today, the crystallize agent runs next.

---

## Step 5: Crystallize

**YOU MUST SPAWN A SUBAGENT FOR THIS STEP.** Do not attempt the crystallize analysis in the main conversation. The main conversation has been burning tokens all session. The crystallize agent gets a fresh context window and spends 50-100K tokens reading the actual files from today -- decisions, research, soul.md, core diffs. That depth is what makes the question good. Without the subagent, you will default to generic questions like "What did you learn?" which is the exact failure this architecture was built to prevent.

A dedicated subagent performs deep analysis of the session's work and generates one crystallize output -- context plus questions that make the user stop and think.

**Core purpose:** Enrich data and help the user fill in the gaps and find the why.

### 5a. Check for Meaningful Activity

Check if decisions, research, or significant core changes happened today. Use
the `mb status --json --peek` and `mb checkpoint --plan --json` file lists from
Step 2 first. If they are unavailable, use these raw git fallbacks:

```bash
# Decisions created or modified today
git log --since="6am" --name-only --diff-filter=AM -- decisions/ 2>/dev/null

# Research created today
git log --since="6am" --name-only --diff-filter=A -- research/ 2>/dev/null

# Core changes
git diff --name-only HEAD@{6am}..HEAD -- core/ 2>/dev/null
```

**When to skip crystallize entirely:**
- No decisions, research, or core changes (truly nothing happened)
- Context window critically low (under 30K remaining)
- User explicitly asked for a quick close ("just commit and close")

**Light days:** If only minor activity (one small edit, no decisions), the agent still runs but shifts focus to core gaps. See [references/crystallize-agent.md](references/crystallize-agent.md) for light-day behavior.

### 5b. Gather File Contents

Before spawning the agent, read and collect:

| Content | How | Always/Conditional |
|---------|-----|-------------------|
| Today's saved-work summary | From Step 2 output | Always |
| Today's decision files (full text) | Read each file detected in 5a | Always |
| Today's research files (full text) | Read each file detected in 5a | Always |
| Core file diffs | `git diff HEAD@{6am}..HEAD -- core/` | If core changed |
| `core/soul.md` | Read full file | Always |
| `content_strategy` from `mb status --json --peek` | Use health state and findings | Always |
| `core/content-strategy.md` and indexed `core/marketing/` / `core/people/` layers | Read full files | If status says they changed, are stale, or are relevant |
| Past crystallize outputs | Read `research/*-end-of-day-crystallize.md` | If any exist |

**Heavy-day adaptation:** If more than 5 research files exist for today, pass commit messages + file names for all research, but full text only for the 3-5 most recent or most connected to today's decisions.

### 5c. Spawn the Crystallize Agent

Use the Task tool to spawn a dedicated subagent with a full context window:

```
Task(
  subagent_type: "general-purpose",
  description: "Crystallize agent: analyze today's session work and generate
    a crystallize output (context block + questions) that surfaces unnamed
    tensions, connects tactical work to existential purpose, and identifies
    core gaps."
)
```

**Agent prompt construction:** Build a structured prompt containing all gathered content from 5b, plus the agent instructions. See [references/crystallize-agent.md](references/crystallize-agent.md) for the complete agent prompt template, analysis process, anti-patterns, and question design criteria.

**Pass to crystallize agent:** Include active offer from a future `mb` JSON field or explicit session context if present, so the agent can analyze offer-specific core changes and ask offer-relevant questions. Do not silently restore offer context from `.vip/local.yaml`.

**The agent is read-only.** It reads files and returns findings. It does not write files. The main conversation handles all file writes.

**The agent returns:** A crystallize output block -- 2-4 sentences of context followed by 1-3 questions. The main conversation presents this to the user exactly as returned, without editing or summarizing.

### 5d. Present to User

Show the crystallize output exactly as the agent returned it. Do not summarize, reword, or add commentary.

### 5e. Engagement Protocol

If the user engages with the crystallize question, the main conversation handles the dialogue (the agent's job is done).

**Rules:**

1. **Let them go deep.** Never redirect to "pick this up with /mb-think." If someone is having an insight at session's end, that is the highest-value moment. Stay with it.
2. **Listen and reflect.** Reflect back what they said in one sentence. Give them space to refine their thinking.
3. **Name what they are doing.** If they articulate a new belief: "That sounds like a new entry for soul.md." If they resolve a tension: "That is a decision waiting to be written."
4. **If insight updates reference, offer to do it.** Don't push -- just offer.
5. **Never push.** If they say one sentence and stop, let them stop. The question was planted. The insight might arrive tomorrow.

See [references/crystallize-agent.md](references/crystallize-agent.md) for the full engagement protocol with examples.

### 5f. Propose Saving the Crystallize Output

Crystallize output can help future sessions see what keeps coming up, but it is
still a business-file write. Offer to save it as a research file and wait for
explicit operator approval before writing.

```markdown
---
type: research
date: YYYY-MM-DD
source: crystallize
status: complete
---
# End-of-Day Crystallize

## Question Asked
[The crystallize question as presented]

## User Response
[What the user said, or "No engagement" if they skipped]

## Insight Captured
[Any insight that emerged, or empty if none]

## Reference Updated
[Which files were updated as a result, or "None"]
```

Proposed save target: `research/YYYY-MM-DD-end-of-day-crystallize.md`

If an insight is substantial enough to update reference directly (`core/soul.md`,
`core/offer.md`, etc.), name the proposed target and ask for approval before
editing. If approved, note the updated file in the crystallize file.

---

## Step 6: Checkpoint & Close

Run `mb checkpoint --plan --json` from the business repo. Summarize the changed
surfaces/files, proposed message, and any blockers.

Lead with owner-facing save state before technical detail:

- `drafted` -- work exists but is not yet saved as durable business memory.
- `saved locally` -- work is saved in local business history.
- `ready to send up` -- work is saved locally and ready for shared backup or
  review.
- `sent for review` -- work has been sent to the shared proposal/review lane.
- `landed in main` -- work is accepted in the main business area.
- `blocked by unrelated cleanup` -- session work is ready, but separate cleanup
  or drift blocks a clean save or handoff.

Use these states when the user asks "is that it?" Put branch, pull request,
merge, and working-tree detail second unless the user asks for plumbing.

**If there are unsaved changes:**

> "You have unsaved work:
>
> - [summarize changed surfaces/files from the plan]
>
> Want me to save a checkpoint before we close?"

If yes:
- Validate the intended subject with `mb checkpoint --validate "..." --json`; use
  a verb it lists (repair `[fixed]`, migration or update `[ran]`, move `[updated]`), not a coined one.
- After approval, save with `mb checkpoint --message "..." --yes`.
- Use beginner-safe language: "saved checkpoint," not "ran git commit."
- Include the crystallize research file in the checkpoint if the operator
  approved creating one.
Do not run raw `git add` or `git commit`.

If no: Leave the work unchanged. Some people prefer to checkpoint at the start
of next session.

If safety is unclear, do not save a checkpoint. Explain the block and leave the
work unchanged.

### The Close

End with a brief, warm close. Not a performance review -- a goodbye.

**Pattern:**

> "Good session. [1 sentence summary of the most important thing that happened]. See you next time."

**Examples:**

> "Good session. Pricing is locked in and your offer is stronger for it. See you next time."

> "Good session. Three new angles ready for ads whenever you are. See you next time."

> "Quiet day, but that research on [topic] will pay off when you decide. See you next time."

> "Solid work. Reference files are updated and everything downstream just got better. See you next time."

**Do not:**
- List everything again (the summary was Step 3)
- Suggest what to do tomorrow (that is /mb-start's job)
- Be overly enthusiastic or performative
- Use emojis

---

## Handling Edge Cases

### User says /mb-end but hasn't done anything

> "Nothing to close out -- no changes detected today. See you next time."

### User says /mb-end mid-task

> "You have work in progress -- [describe what's open]. Want to finish that first, or close out and pick it up next time?"

If they want to close: run `mb checkpoint --plan --json`, summarize what exists,
and save only after operator approval.

### Context window is nearly full

Keep it ultra-brief. Scan, offer a checkpoint if needed, close. Skip Steps 4 and
5.

### Multiple repos in session

Only scan the primary business repo (from config). If the user worked across repos, they can mention it.

### No git repo / no business repo

> "No business repo found. If you want session tracking, run `/mb-setup` next time to create one. See you next time."

---

## What /mb-end Is NOT

- **Not a daily standup.** No plans for tomorrow.
- **Not a task manager.** No to-do lists or assignments.
- **Not a journal.** The final thought capture is optional and brief.
- **Not an audit.** The summary is observational, not evaluative.
- **Not /mb-think** -- but if someone is having an insight, stay with it. The crystallize moment can go deep. That is the point.

---

## Tone

Same as the rest of Main Branch: a thoughtful friend. Brief. Warm. Not performative.

The close should feel like the end of a good conversation -- not a report card, not a ceremony. Just: "Here's what happened. Anything else? Good. See you."

---

## References

- [references/crystallize-agent.md](references/crystallize-agent.md) -- Agent prompt template, analysis process, anti-patterns, question design, engagement protocol, examples
- [references/decision-lifecycle-audit.md](references/decision-lifecycle-audit.md) -- Step 2b shared audit bash, expected buckets, manual confirmation rule
