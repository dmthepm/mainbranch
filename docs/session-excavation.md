# Session Excavation

Use this workflow when a customer call, setup session, exported chat log,
runtime transcript, or agent session export should improve Main Branch.

The goal is to turn real usage into a prioritized, public-safe backlog. Raw
sessions are source material, not product truth. Durable outputs should be
sanitized GitHub issues, docs, decisions, tests, skill updates, or evidence
reports.

## When To Use This

Use session excavation for:

- first-run setup calls;
- customer onboarding calls;
- exported Claude Code, Codex, or other agent-runner sessions;
- webinar transcripts and chat logs;
- runtime dogfood transcripts that are not release validation;
- generated business-repo history after a live session;
- repeated support conversations that expose the same friction.

When the goal is to mine transcripts, authenticated community content,
connected-provider recordings, cloud-drive files, or mixed private/business
sources into business memory, use [`source-ingestion.md`](source-ingestion.md)
before reading source content. Session excavation turns a session into public
product follow-ups; source ingestion controls whether and how source material
may be read and routed.

For release-bearing runtime validation, use
[`release-simulations.md`](release-simulations.md) and
[`release-agent-contract.md`](release-agent-contract.md) first. This document
is for product excavation from real usage, not for replacing release evidence.

## Privacy Boundary

Raw transcripts, chat logs, customer/member data, local paths, account details,
private business strategy, proof assets, screenshots, and credentials stay out
of public docs and GitHub comments.

Public artifacts may include:

- sanitized summaries;
- generic reproduction steps;
- category and priority tables;
- short sanitized excerpts only when needed;
- public-safe links to existing docs, issues, or decisions;
- decisions about what surface should change.

Private artifacts may include:

- raw transcript paths;
- exact local file paths;
- customer names, customer repo names, and member names;
- sensitive proof/legal details;
- internal operator notes;
- screenshots or logs that contain private context.

Keep private evidence in ignored local scratch space such as `.agent/`, an
agent-runner scratch directory, or OS temp, or in Linear-only comments when the
tool clearly supports keeping the note private. Do not copy private Linear
evidence into public GitHub comments or PR bodies.

This follows [where data lives](../.claude/skills/mb-setup/references/where-data-lives.md):
a team's private business repo may hold real material for the team and its
agents (recordings, reviews, real examples), media goes on the team's own
tracker issue, and large datasets stay out because commits are never deleted.
The line this page draws is the public one: this engine repo, its public
issues and its docs get sanitized summaries only. Raw session material that
would not suit the private hub goes in ignored scratch or OS temp.

## Source Inventory

Start by listing the evidence set before analysis:

| Source | Private location | Public-safe description | Use |
|---|---|---|---|
| Transcript or chat export | local scratch path | Customer setup transcript | User questions, confusion, language, trust risks |
| Runtime/session export | local scratch path | Agent session export | Actual commands, tool errors, runtime behavior |
| Generated business repo | local or private repo | Resulting business repo history | File quality, checkpoint quality, privacy boundaries |
| Existing issue/PR | public URL | Work thread | Prior scope, open questions, linked follow-ups |

Do not commit this inventory if it names private paths or customers. Commit
only a sanitized version when it is useful as a public report.

## Analysis Passes

Read the session in passes. Do not start with broad product wishes.

1. **Actual errors:** setup failures, wrong commands, broken skill discovery,
   failed validation, accidental files, dirty repos, bad commits, tool crashes,
   or confusing recovery paths.
2. **Trust and safety:** private data exposure, proof permission gaps,
   credential risks, money-spend/publish/contact actions, runtime overclaims,
   or customer-visible statements the product cannot support.
3. **User experience:** questions the user had to ask, points where the
   operator translated technical terms, places where the agent needed a rescue
   phrase, and moments where the next step was unclear.
4. **Language:** git, terminal, provider, and runtime terms that should be
   translated into business language first.
5. **Saved history:** checkpoint quality, commit grouping, accidental cleanup
   commits, stale source material, and whether the final history tells a useful
   business story.
6. **Workflow gaps:** missing source-ingestion flows, review gates, repo
   boundary decisions, provider readiness, dashboards, or other repeated
   operator loops.
7. **Provider and connector boundaries:** connector setup friction, bridge or
   restart requirements, OAuth scope confusion, direct provider writes, secret
   handling, account mutation, and whether a provider path is `mb`-native,
   runtime-native, plugin-based, CLI/API-key-based, or unsupported.
   Provider smoke evidence should record presence, exit status, and readiness
   facts, never credential values or token prefixes.
8. **Roadmap signal:** useful future direction that should not become an
   immediate support claim.

Separate facts from inferences. A fact is visible in the transcript, logs, repo
history, or generated files. An inference is a likely product implication that
needs a follow-up issue, decision, or test.

## Priority Ladder

Use this severity ladder by default:

| Priority | Meaning | Typical action |
|---|---|---|
| P0 | Actual failure, safety risk, privacy risk, or trust-breaking output | Open or attach a concrete issue; add tests or smoke plan |
| P1 | Adoption blocker, repeated confusion, stale workflow, or user-facing quality gap | Open a scoped issue or document an explicit defer |
| P2 | Important workflow improvement or validated product pull | Add to backlog or fold into an existing issue |
| P3 | Education, polish, roadmap signal, or optional enhancement | Record only if it helps future prioritization |

Actual observed errors outrank attractive roadmap ideas. Do not let connector
wishes bury setup, privacy, proof, save, or language failures.

## Public Issue Table

Use a compact table for the public issue or public report:

```md
| Priority | Area | Finding | Why it matters | Candidate follow-up |
|---|---|---|---|---|
| P0 | Setup | The pasted setup prompt did not trigger the intended setup flow. | First-run setup should not require an expert rescue phrase. | Add a fixture/runtime smoke for full-guide paste recognition. |
| P1 | Language | The operator had to translate `cd` and commit language live. | Beginner users need folder/save/checkpoint language first. | Audit generated setup and status copy for owner-language leakage. |
```

Keep the table sanitized:

- say "customer", "operator", "business repo", or "member proof" instead of
  naming the person or business;
- use generic local paths such as `<business-repo>`;
- avoid exact raw quotes unless they are short, necessary, and public-safe;
- cite private evidence only in private notes.

## Private Evidence Note

When a public issue needs private backing, add a private note outside public
GitHub with this shape:

```md
Private evidence note. Do not copy into public GitHub.

| Source | Private location | What it showed |
|---|---|---|
| Transcript | <local scratch path> | Setup recovery, user questions, cost concerns |
| Session export | <local scratch path> | Runtime metadata, command output, logs |
| Generated repo | <private repo/path> | Commit history, scratch files, proof status |

| Priority | Evidence | Notes |
|---|---|---|
| P0 setup | Transcript around <time> shows the operator restated the setup intent. | Public issue should describe the failure generically. |
```

## Follow-Up Routing

After the table is drafted, route each P0 and P1 row.

| Finding type | Durable home |
|---|---|
| Reproducible CLI or setup failure | GitHub issue with command, expected behavior, actual behavior, validation target |
| Runtime discovery or skill behavior | GitHub issue with runtime, adapter/support boundary, and smoke plan |
| Public/private leak risk | GitHub issue if generic; private note only if the evidence itself is sensitive |
| Generated repo guidance gap | Skill prose, template, docs, and a fixture/runtime smoke if first-run behavior changes |
| Stale business source handling | Workflow issue, skill update, or decision if it changes repo primitives |
| Provider write or secret handling risk | Provider mutation, approval-gate, or secret-redaction issue with a validation target |
| Connector bridge confusion | Connector-readiness issue or shared-workflow source issue; do not claim runtime support from directory availability alone |
| Transcript or authenticated-community ingestion | Use `source-ingestion.md`; open or link an ingestion/privacy issue when the rail itself needs product work |
| Connector/provider request | Provider-readiness issue only after support claim and smoke boundary are clear |
| Roadmap pull | Roadmap note or backlog issue; do not claim support |

For each P0/P1, either:

- open or link a concrete issue;
- attach it to an existing active issue; or
- write a short defer note explaining why it is not being worked now.

## Repeatable Output

End every excavation with:

- public-safe issue/report link;
- P0/P1 routing table;
- private evidence location, if any;
- validation needed for the next implementation branch;
- artifact left behind, if the session taught a repeatable process.

The last bullet matters. If the session reveals a workflow that future agents
will repeat, leave behind a reusable doc, decision, fixture, test, template, or
skill reference instead of only filing another backlog item.
