# The four operating loops

Use Main Branch to read what is happening, choose a next move, produce approved
work, and keep the lesson. The four names for that sequence are Sense, Decide,
Ship, and Reflect.

For a complete example, follow [a working day](working-day.md). For the product
contract, read [ethos](ethos.md).

## Loops are workflow phases, not categories

A loop describes the work you are doing. It is not a folder, an agent role, or
a required ceremony. A short conversation can pass through all four loops.
An ad, a decision, or a bookkeeping question can involve several loops.

| Loop | Owner's question | Useful result |
| --- | --- | --- |
| Sense | What is happening, and what do we know? | Facts with sources, freshness, and gaps. |
| Decide | What should we do next? | A choice with its reason, uncertainty, and review condition. |
| Ship | What work should we produce or release? | An approved artifact or action, with evidence of what happened. |
| Reflect | What did we learn, and what should change? | A recorded outcome or lesson that future work can use. |

## The daily loop in loop terms

1. Start Main Branch in your business folder. The agent reads `mb` facts and
   relevant business files. This is Sense.
2. Describe the question and choose a proposed next move. This is Decide.
3. Review the proposed work and authorize the actions you want. This is Ship.
4. Compare the result with the intent and save the useful lesson. This is Reflect.

In Claude Code, start with `/mb-start`. In Codex CLI, use the global `mb-start`
skill. Codex supports the daily loop, but production routes have narrower
limits. Check [compatibility](compatibility.md) or
`mb workflow list --runtime codex --json` before choosing a production route.

## 1. Sense

Read the facts before giving advice. `mb status` reports folder health,
readiness, recent work, and ranked next actions. The agent reads the relevant
business files and distinguishes recorded evidence from an owner's observation
or its own inference.

For example, an owner says buyers ask whether a planning service includes
furniture. The offer file names a planning session. That mismatch supports a
clarity question; it does not prove that changing the wording improves sales.

Missing provider data is a gap to name, not permission to invent performance
numbers. Folder health and business performance answer different questions.

## 2. Decide

Choose a next move and record why it is worth doing. Use the think route to
compare options, examine research, or sharpen an offer.

A decision should say what you chose, what supports it, what remains uncertain,
and what would make you reconsider. A bet adds a bounded hypothesis, appetite,
metric, target, and review point. An offer describes something you sell; a bet
records an attempt to learn or achieve something within a limit.

In the planning-service example, the owner chooses clearer wording and plans
to review future buyer questions. That is a wording experiment, not a proven
sales result.

## 3. Ship

Produce the work the owner approved. This can mean updating an offer draft,
writing content, preparing a launch plan, completing fulfillment work, or
saving an accepted checkpoint.

| Work | Example route | Boundary |
| --- | --- | --- |
| Paid creative | `/mb-ads` | Draft and review creative and launch plans. Publishing and spend need separate approval and tested support. |
| Organic content | `/mb-organic` | Draft content from business context. A draft does not imply automatic posting. |
| Pages | `/mb-site` | Plan, create, or check a site within runtime and provider limits. Deployment needs authority. |
| Public search | `/mb-seo` | Review public pages and check AI search access. Paid research asks first, and OpenSEO setup is optional and experimental. Claude Code only. |
| Business records | `mb-think`, `mb-bet` | Review proposed file changes before saving accepted work. Codex bet support remains read-only planning. |
| Saved history | `mb checkpoint` | Preview included files and the message before approving a local save. Remote sync is separate. |

Slash commands in this table name Claude Code routes. Codex uses global skills,
with the support limits in the [workflow matrix](compatibility.md#workflow-coverage-today).

## 4. Reflect

Compare what happened with what you expected. Keep evidence, uncertainty, and
one useful next check. Use the end route to review a session, or review a bet
when its deadline or evidence calls for a verdict.

An approved artifact proves that you produced something. It does not prove a
business outcome. Record a sales improvement only when you have evidence for
it. If the useful lesson is already in a decision, closing a session need not
create another file.

Reflection feeds the next session's Sense step. In the example, tomorrow's
agent reads the wording experiment and asks about new buyer questions before
recommending another offer change.

## Loops chain together

Research can lead to a decision, an approved offer edit, and a saved lesson.
A launched page can lead to measurement checks and a revised bet. Revisit an
earlier loop whenever new evidence changes the question.

Use a [playbook](playbooks.md) when a repeated task needs a reusable method.
Keep the method separate from the record of what happened during one run.

## Skills are journeys; loops are stations

A skill can pass through several loops. `/mb-think`, for example, can read
research, compare choices, and write an approved decision. Its name does not
add a fifth loop.

Bundled `SKILL.md` files declare their loops in frontmatter:

```yaml
loops: [sense, decide, ship]
```

Only `sense`, `decide`, `ship`, and `reflect` are valid. `mb skill validate`
checks this metadata. Runtime and status grouping do not yet use it for product
behavior; do not infer a UI grouping from the declaration.

## Applying the loops

For owners, use the four questions to identify what is missing. If you have a
proposal with no evidence, return to Sense. If you have evidence with no next
move, Decide. If you have completed work with no recorded result, Reflect.

For contributors, describe which owner loop a change improves. Keep deterministic
facts in `mb`, judgment in skills, and business memory in the business repo.
Follow [AGENTS.md](../AGENTS.md) for changes to commands or runtime behavior.

## Channels (the four pillars)

Paid, Organic, Pages, and Ops describe areas of work. They are not additional
loops. Each can involve Sense, Decide, Ship, and Reflect. Bookkeeping and
fulfillment, for example, are Ops work that still needs evidence, choices,
authorized execution, and outcomes.

## See also

- [A working day](working-day.md) for a synthetic owner example.
- [Product principles](ethos.md) for ownership and authority.
- [Taxonomy decision](../decisions/2026-05-05-operator-loops-taxonomy.md) for the original rationale.
- [Roadmap](roadmap.md) for direction beyond the current loop.
