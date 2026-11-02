# Ad Review Workflow

Review ads through 6 compliance and quality lenses before shipping. Reviews are read-only until proposed changes are shown and explicitly approved.

## The 6 Lenses

| Lens | Location | What It Checks |
|------|----------|----------------|
| FTC Compliance | `references/lenses/ftc-compliance.md` | Federal regulations, earnings claims |
| Meta Policy | `references/lenses/meta-policy.md` | Platform triggers, Personal Attributes |
| Copy Quality | `references/lenses/copy-quality.md` | Schwartz, Hormozi, Suby frameworks |
| Visual Standards | `references/lenses/visual-standards.md` | Safe zones, OCR, prohibited visuals |
| Voice Authenticity | `references/lenses/voice-authenticity.md` | AI tells, brand voice |
| Substantiation | `references/lenses/substantiation.md` | Claims inventory, proof matching |

Severity: **P1** blocks launch (legal/platform risk); **P2** fix before launch; **P3** nice to have.
Status: **BLOCKED** any P1; **REVIEW REQUIRED** multiple P2 or borderline P1; **CLEAR** no P1, minimal P2.

## Phase 0: Pre-Review Checkpoint

Preserve the original after operator approval; show the planned files, message and any blockers before saving:

```bash
mb checkpoint --plan --json
mb checkpoint --validate "[drafted] {type} ad batch" --json
mb checkpoint --message "[drafted] {type} ad batch" --yes
```

## Phase 1: Gather Input

A single ad concept (copy + visual description), a full campaign batch, or one component (headlines, hooks).

## Phase 2: Run Lenses in Parallel

Spawn one `general-purpose` Task agent per lens, all in a single message. Each agent gets the ad content inline (not just a file path), reads its lens file from this skill's bundled `references/lenses/` directory (never cwd-relative), and only the business context that lens needs (FTC and Substantiation: offer.md, testimonials.md, typicality.md; Meta Policy: offer.md; Copy Quality: offer.md, audience.md, skool-surfaces.md if present; Voice Authenticity: voice.md; Visual Standards: none). Agents are read-only: they report, never write or fix.

```
You are reviewing ad copy through the [LENS NAME] lens.
Read: [path to lens file]
Review this content: [AD CONTENT]
For each checklist item: Pass or Fail; if Fail cite the specific violation.
For each issue return:
  - severity: P1 | P2 | P3   (P1 blocks, P2 fix before launch, P3 improve if time)
  - item_ref: which ad/line
  - issue: what's wrong
  - evidence: exact text that violates
  - rule: which check this violates
  - fix: specific rewrite based on the lens's "Safe" examples
Return "NO ISSUES" explicitly if everything passes.
Do NOT write any files. Do NOT fix anything. Report only.
```

## Phase 3: Synthesize Report

Combine all lens findings into one report, deduplicating where lenses overlap (FTC and Substantiation often flag the same issue):

```markdown
# Ad Review Report

**Date:** YYYY-MM-DD
**Reviewed:** [Campaign/Ad name]
**Status:** [BLOCKED / REVIEW REQUIRED / CLEAR]

---

## Summary

| Lens | P1 | P2 | P3 |
|------|----|----|----|
| FTC Compliance | X | X | X |
| Meta Policy | X | X | X |
| Copy Quality | X | X | X |
| Visual Standards | X | X | X |
| Voice Authenticity | X | X | X |
| Substantiation | X | X | X |
| **Total** | X | X | X |

---

## P1 Issues (Must Fix Before Launch)

### [Issue Title]
**Lens:** [Which lens caught this]
**Evidence:** [Specific text/visual]
**Why it's P1:** [Explanation from lens]
**Fix:** [Specific correction]

---

## P2 Issues (Should Fix)

[Same format]

---

## P3 Issues (Nice to Have)

[Same format]

---

## What's Working Well

[Positive findings from lenses]
```

## Phase 4: Propose Fixes and Gate Writes

**Compliance gate: Reviews never rewrite user-provided copy until the proposed changes are shown and explicitly approved.**

For each P2/P3 issue:
1. Add the finding to `proposed-compliance-fixes.json` with:
   - `severity`
   - `item_ref`
   - `issue`
   - `evidence`
   - `rule`
   - `fix`
2. Run the gate in dry-run mode:

   ```bash
   python -m mb.ads_compliance_gate pushes/YYYY-MM-DD-{type}-{campaign}/{batch-file}.md pushes/YYYY-MM-DD-{type}-{campaign}/proposed-compliance-fixes.json
   ```

3. Show the resulting diff to the user.
4. Ask: "Apply these compliance copy changes? (y/n)"
5. Only if the user says yes, run:

   ```bash
   python -m mb.ads_compliance_gate pushes/YYYY-MM-DD-{type}-{campaign}/{batch-file}.md pushes/YYYY-MM-DD-{type}-{campaign}/proposed-compliance-fixes.json --approve --review-log pushes/YYYY-MM-DD-{type}-{campaign}/review-log.md
   ```

If the user says no, stop with the source file unchanged. Do not apply partial edits unless the user gives a narrower approval.

**review-log.md format:**

```markdown
## Review: YYYY-MM-DD

**Status:** BLOCKED | REVIEW REQUIRED | CLEAR TO SHIP

### Fixes Applied

| Line | Original | Fixed | Reason |
|------|----------|-------|--------|
| #5 | "tired of juggling..." | "juggling..." | Meta Personal Attributes |
| #22 | "drowning in..." | "overwhelmed by..." | Meta Personal Attributes |

### P1 Issues (Manual Fix Required)

[Any P1 issues that need human decision]
```

`review-log.md` is written only after approval. The proposed JSON file is safe to write before approval because it is a separate review artifact, not a rewrite of the user's copy.

For P1 issues:
- Do NOT auto-fix (requires human decision)
- Document in the unified report and keep source copy unchanged until the user gives a specific fix approval
- Status: BLOCKED until P1s resolved

## Phase 5: Post-Review Checkpoint

After fixes are approved and applied:

```bash
mb checkpoint --plan --json
mb checkpoint --validate "[updated] {type} ad batch after review" --json
mb checkpoint --message "[updated] {type} ad batch after review" --yes
```

**To see what review changed:** `git diff HEAD~1`

## Context Files

**Bundled with this skill:**
- `references/lenses/` — the 6 review lenses
- `references/compliance/` — shared compliance frameworks

Resolve these paths relative to the `mb-ads` skill directory. Do not resolve them
against the business repo's cwd or a sibling engine directory.

**From business repo:**
- `core/proof/testimonials.md` — Available testimonials for substantiation check
- `core/proof/typicality.md` — Outcome data for claim validation
- `core/offer.md` — To verify claims match actual offering

## Quick Review (Single Lens)

If you only need one lens (e.g., "just check FTC compliance"):

1. Read the specific lens file
2. Apply only that checklist
3. Return findings for that domain
