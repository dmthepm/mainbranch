# First Customer Setup Excavation

## Evidence Set

- Date reviewed: 2026-05-16
- Source session date: 2026-05-14
- Issue: [#622](https://github.com/dmthepm/mainbranch/issues/622)
- Linear: MAIN-386
- Evidence level: sanitized review of a real customer setup transcript, agent
  session export, and generated business-repo history
- Public/private boundary: no raw transcript, customer/member names, local
  customer paths, private repo names, account details, proof quotes, or private
  business strategy are included here

Private evidence remains in local scratch space and Linear-only context. Do
not reconstruct customer identity from this public report.

## Summary

The first live customer setup proved the core product shape: a non-technical
operator can watch a business repo appear, see files become useful, and
understand why durable memory matters. It also exposed first-run failures that
matter more than roadmap pull:

- the pasted beginner setup guide initially routed to document-saving instead
  of business setup;
- `mb onboard --push` needed manual repair for generated `.mb/` state;
- status JSON hit a serialization traceback;
- accidental scratch files entered the repo history;
- proof looked strategically valuable while remaining unusable for public
  marketing until permission was collected.

The biggest product lesson is that first-run setup is not just installation.
It is a trust moment. The system has to explain what is being created, what is
saved, what is private, what can be used publicly, what updates later, and why
the next action is safe.

## Timeline

| Phase | What Happened | Product Signal |
|---|---|---|
| Setup intent | The full beginner setup guide was pasted into an empty target folder with a business intent. | Runtime guidance did not reliably infer "set up my business repo" from the guide paste. |
| Recovery | The operator restated the goal and the setup skill launched. | Expert recovery worked; new-user recovery path is too fragile. |
| Onboarding | `mb onboard --push` created the folder and baseline but returned `needs repair`. | First-run GitHub setup still leaks generated-state/git cleanup. |
| Baseline repair | The operator inspected `.mb/`, manually committed a schema marker, and reran onboarding connect mode. | The product should hide this plumbing or provide one Main Branch repair command. |
| Source ingestion | A large mixed source dump fed offer, audience, proof, operations, and tier files. | The system handles messy source material, but stale-source cleanup needs a named workflow. |
| Correction loop | An obsolete offer detail and a tested messaging angle were corrected during the session. | Real onboarding requires "retire this source/claim/angle" as a normal move. |
| Offer/proof pass | The agent sharpened offer, proof, typicality, objections, and transformation context. | MoneyPath-style guidance is useful, but proof permission must gate public marketing readiness. |
| Status check | A status JSON check hit a date serialization error before later status facts were recovered. | Deterministic JSON fact surfaces must fail as structured envelopes, not tracebacks. |
| Checkpointing | Business-readable commits were created, but scratch files were accidentally committed and then removed. | Checkpoint guardrails need stronger suspicious-file detection. |
| Closing reflection | The session produced useful unresolved questions around proof permission, voice/angle tension, and operator adoption. | `/mb-end` surfaced real strategy risks; those risks should route into follow-up issues or decisions. |

## Prioritized Findings

| Priority | Area | Finding | Evidence Type | Route |
|---|---|---|---|---|
| P0 | Setup routing | Full-guide paste plus business intent was misread as "save this guide" before the operator corrected it. | Session export, transcript | [#625](https://github.com/dmthepm/mainbranch/issues/625) |
| P0 | Onboarding/git setup | `mb onboard --push` stalled on generated `.mb/` state and required manual git repair. | Session export, command output | [#626](https://github.com/dmthepm/mainbranch/issues/626) |
| P0 | Checkpoint quality | Accidental scratch files entered the generated business repo history. | Generated repo history | [#627](https://github.com/dmthepm/mainbranch/issues/627) |
| P0 | Status JSON | Status JSON hit a `date` serialization traceback. | Session export, command output | [#628](https://github.com/dmthepm/mainbranch/issues/628) |
| P0 | Proof/legal safety | Strong proof existed but was not permissioned for public marketing; readiness did not make permission collection the hard next action. | Generated files, closing reflection | [#629](https://github.com/dmthepm/mainbranch/issues/629) |
| P1 | Stale-source cleanup | Mixed source material included old offer details and a retired angle that needed cross-file reconciliation. | Transcript, generated decisions | [#630](https://github.com/dmthepm/mainbranch/issues/630) |
| P1 | Repo boundary | The customer needed rules for one business repo vs separate linked repos. | Transcript | [#631](https://github.com/dmthepm/mainbranch/issues/631) |
| P1 | Beginner explanations | Updates, local edits, saved checkpoints, GitHub backup, runtime cost, and support boundaries needed live explanation. | Transcript | [#632](https://github.com/dmthepm/mainbranch/issues/632) |
| P2 | Source ingestion | The customer wanted calls, live chats, video transcripts, SOPs, screenshots, and voice notes routed into durable memory. | Transcript | Backlog; should become separate ingestion issues when scoped by source type. |
| P2 | Provider readiness | The customer asked about video, research, web, email, social scheduling, CRM, banking, and dashboard rails. | Transcript | Backlog; split only when each provider support boundary and smoke plan is clear. |
| P2 | Review gate | The customer wanted final human approval before content leaves the system. | Transcript | Backlog; likely belongs with push/content review queue work. |
| P2 | Dashboard | The customer described a morning view over content, spend, proof gaps, and next actions. | Transcript | Existing dashboard direction; route to dashboard issue when active scope is verified. |
| P3 | Skill/source inspectability | Viewers asked where skills live and how to inspect them. | Transcript/chat | Defer; useful education, not a first-run blocker. |
| P3 | Visual workflow | Rendered markdown, Obsidian, diagrams, and graph views resonated strongly. | Transcript | Defer; support as optional viewer guidance without distracting first-run setup. |
| P3 | Playbook marketplace pull | The session pulled toward niche playbooks and expert-maintained workflows. | Transcript | Roadmap signal only; no support claim. |

## What Worked

- The setup skill recovered once the operator clarified intent.
- The shipped onboarding path created a usable scaffold and private GitHub
  backup after repair.
- Generated repo guidance carried the current business-repo shape: core,
  research, decisions, bets, pushes, logs, and documents.
- The agent created useful decisions when the source material changed.
- Proof typicality and permission metadata were captured rather than silently
  treating all proof as public-ready.
- `/mb-end` produced strategy questions instead of a flattering summary.

## What Failed

### Actual Failures

- The initial user intent was misclassified.
- The first-run push path required manual generated-state cleanup.
- A status JSON path emitted a Python serialization failure.
- Checkpointing allowed accidental scratch files into business history.

### Trust Risks

- Proof permission was visible but not strong enough as a blocker.
- The setup ran in a powerful permission mode, while first-run public guidance
  still has to teach safer defaults.
- Private source material and customer/member proof were close to public issue
  surfaces; the process needs a repeatable redaction habit.

### UX Gaps

- The operator translated git/terminal language live: folder, save, backup,
  checkpoint, update, and sync need to come first.
- The customer asked the right mental-model questions, but those answers live
  mostly in expert explanation rather than first-run product copy.
- Multi-repo boundaries are central to the model and should be introduced as a
  decision helper, not a tangent.

## Follow-Up Routing

P0 and P1 findings now have concrete public issues:

| Issue | Owner Loop | Validation Need |
|---|---|---|
| [#625](https://github.com/dmthepm/mainbranch/issues/625) | Sense / Decide | Runtime or fixture prompt for full-guide paste recognition |
| [#626](https://github.com/dmthepm/mainbranch/issues/626) | Ship | Fixture repo smoke for `mb onboard --github <owner/repo> --push` |
| [#627](https://github.com/dmthepm/mainbranch/issues/627) | Ship / Reflect | Checkpoint plan/hook tests with suspicious scratch files |
| [#628](https://github.com/dmthepm/mainbranch/issues/628) | Sense | Status JSON regression test with date-valued facts |
| [#629](https://github.com/dmthepm/mainbranch/issues/629) | Decide / Ship | MoneyPath/proof fixture plus skill routing review |
| [#630](https://github.com/dmthepm/mainbranch/issues/630) | Sense / Decide / Reflect | Stale-source workflow fixture or manual smoke |
| [#631](https://github.com/dmthepm/mainbranch/issues/631) | Decide | First-run guidance/template review; fixture if generated guidance changes |
| [#632](https://github.com/dmthepm/mainbranch/issues/632) | Sense / Decide | Docs and runtime-guidance review; smoke if slash/guidance changes |

P2/P3 items stay in this report until an active issue can own a narrow slice.
Do not bundle provider rails, dashboards, and playbook marketplace direction
into a first-run repair PR.

## Public/Private Boundary Notes

- Do not publish raw transcript excerpts from this session.
- Do not name the customer, customer business, private repo, local folder, or
  member proof assets in public issue comments.
- Do not use the customer's proof examples as public fixtures.
- Use synthetic businesses for tests.
- Use generic terms: customer, operator, business repo, member proof, source
  dump, generated repo history.

## Process Artifact

This excavation produced
[`docs/session-excavation.md`](../session-excavation.md). Future agents should
use that workflow before creating public issues from transcripts, chat exports,
or session logs.
