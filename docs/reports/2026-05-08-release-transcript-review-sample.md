# Release Transcript Review Sample

This is a public-safe fixture review for the rubric in
[Release Simulations](../release-simulations.md#transcript-review). It uses
sanitized excerpts modeled on the packaged release simulation prompts. It is
not a private Claude transcript and does not claim interactive TUI smoke.

## Evidence Set

- Date: 2026-05-08
- Issue: [#379](https://github.com/dmthepm/mainbranch/issues/379)
- Source: sanitized fixture review, not raw runtime output
- Fixture identity: Dogfood Studio sample business repo
- Evidence level: sanitized fixture review
- Public/private boundary: no secrets, customer/member data, account IDs, raw
  business transcript, or local machine paths

## Review Summary

| Simulation | Severity | Categories | Result |
|---|---|---|---|
| `fresh_first_day` | Hard failure | skill discovery, evidence quality | Block release-bearing slash-command claim until repaired or rerun. |
| `messy_morning_thought_dump` | Quality concern | CLI grounding, business-language return, conversation shape | Route to skill/generated-instruction follow-up if repeated. |
| `checkpoint_discipline` | Pass | checkpoint discipline, write discipline, evidence quality | Accept as reviewed fixture behavior. |

## Finding 1: Fresh First Day

Simulation: `fresh_first_day`
Tier: PR smoke, pre-release candidate, and release acceptance
Expected: Claude recognizes `/mb-start`, uses `mb status --json --peek` or
`mb start` facts, names the fixture business repo, and returns with a business
next action.
Sanitized excerpt:

```text
Unknown command: /mb-start
```

Severity: hard failure
Categories: skill discovery, evidence quality
Likely fix types: `runtime_behavior`, `generated_claude_md`, `docs_gap`,
`harness_gap`

Review:

- The transcript reports an observed slash-command discovery failure.
- There is no evidence that the intended Main Branch skill ran.
- A release-bearing slash-command claim cannot rely on print-mode proxy output
  or generic repair advice after this failure.

Issue route:

- Use open [#356](https://github.com/dmthepm/mainbranch/issues/356) when
  the miss is a ghost route or docs naming unavailable slash commands.
- Open a focused runtime smoke issue if the repaired flow still fails in the
  interactive Claude Code TUI.

## Finding 2: Messy Morning Thought Dump

Simulation: `messy_morning_thought_dump`
Tier: PR smoke, pre-release candidate, and release acceptance
Expected: Claude treats fuzzy input as triage, maps options to a business
primitive, uses deterministic `mb` facts before advice, and asks before durable
writes.
Sanitized excerpt:

```text
You could update onboarding or draft content. I recommend making a list, then
checking the files and committing your work when done.
```

Severity: quality concern
Categories: CLI grounding, business-language return, conversation shape
Likely fix types: `skill_prose`, `generated_claude_md`, `user_education`

Review:

- The answer gives generic productivity advice before `mb status --json --peek`
  or `mb start --json` facts.
- It does not route the choice to Main Branch primitives such as a bet,
  research note, decision, push, playbook, outcome, or checkpoint.
- It makes the operator think about commits before translating the moment into
  business progress.

Issue route:

- Use open [#350](https://github.com/dmthepm/mainbranch/issues/350) when
  the miss exposes unclear push/playbook routing.
- Open a focused `/mb-start` or generated-instructions follow-up if the same
  weak routing appears after closed
  [#353](https://github.com/dmthepm/mainbranch/issues/353).

## Finding 3: Checkpoint Discipline

Simulation: `checkpoint_discipline`
Tier: pre-release candidate and release acceptance
Expected: Claude runs or recommends `mb checkpoint --plan --json`, validates a
proposed business-readable message, and asks before saving.
Sanitized excerpt:

```text
I will first show the checkpoint plan, then validate the proposed message. I
will not save the checkpoint until you approve it.
```

Severity: pass
Categories: checkpoint discipline, write discipline, evidence quality
Likely fix types: none

Review:

- The response separates planning, validation, and saving.
- It frames the checkpoint as approved saved progress rather than defaulting to
  raw git commands.
- The review would still need command artifacts or a post-run git check before
  claiming an actual checkpoint was created correctly.

Issue route:

- No new issue from this fixture pass.

## Follow-Up Recommendations

- Keep closed [#364](https://github.com/dmthepm/mainbranch/issues/364) as
  historical harness context only; open a new focused harness issue if manual
  review findings need a structured generated artifact beyond the current
  `evidence-template.md`.
- Use open [#357](https://github.com/dmthepm/mainbranch/issues/357) and
  [#358](https://github.com/dmthepm/mainbranch/issues/358) when a transcript
  shows Claude lacked deterministic relationship or status facts.
- Do not paste raw transcripts into public issues. Post short summaries,
  sanitized excerpts, severity, category, likely fix type, and the minimal
  reproduction needed for the follow-up.
