# A working day with Main Branch

Turn a question about your offer into a reviewed decision, save it, and use
that lesson tomorrow. Start with a business folder from the
[setup walkthrough](beginner-setup.md).

This example uses a fictional business, Clear Desk Studio, which offers a
one-session workspace planning service for freelancers. Every exchange and
result below is synthetic. The short agent responses illustrate the method;
they are not captured runtime output or promised results.

The example uses the daily start, think, and end routes. In Claude Code, use
`/mb-start`, `/mb-think`, and `/mb-end`. In Codex, ask for the corresponding
global `mb-start`, `mb-think`, and `mb-end` skills. Other production routes
have different limits; see [runtime compatibility](compatibility.md) or run
`mb workflow list --runtime codex --json`.

## Open the day with a question

Open Clear Desk Studio's business folder in your runtime and start Main Branch.
Then give the agent the question you actually need answered:

> I keep describing the service as a workspace transformation. People ask
> whether that means buying furniture. Help me make the offer clearer. Read
> our current files first and propose a change before writing anything.

The agent reads Main Branch facts and the relevant business files before
advising. A useful response distinguishes evidence from a guess:

> Your offer says "workspace transformation," but the service description
> promises a planning session and a written layout plan. Your audience file
> names freelancers who work in small spaces. You have no saved evidence that
> buyers want furniture recommendations. I suggest testing wording that names
> the planning session and its deliverable. I cannot tell whether it improves
> sales from these files.

If the response sounds generic, ask which file or observation supports it.
You can correct the business facts before choosing a direction.

## Choose one change

Use the think route to compare wording and make the decision explicit:

> Use mb-think to compare "workspace transformation" with "a workspace
> planning session with a written layout plan." Use only our files and my
> observation today. Show the tradeoff. Don't change files yet.

The agent might answer:

> The second version tells a buyer what they receive and avoids implying that
> you supply furniture. It is less aspirational, and we have not tested whether
> buyers prefer it. I recommend the clearer version as a wording experiment.
> Keep the service itself unchanged and record what would make us reconsider.

Choose the change and authorize its scope:

> Use the clearer version. Update the offer draft and record the decision,
> including my observation and the uncertainty. Show me the proposed files
> first. Don't publish the wording or contact anyone.

For this single-offer business, the agent proposes an edit to `core/offer.md`
and a dated decision in `decisions/`. It checks the folder's templates and
conventions before choosing the filename. The decision links back to the
offer and records the reason, uncertainty, and next check.

Review the proposed wording. Then approve the file changes:

> Approved. Write those two changes.

The agent shows what it wrote. Read the actual offer and decision, or ask for
the changed passages. You should see the new deliverable wording and a note
that this is an experiment, not evidence of better sales.

## Save the accepted work

Writing a file and saving a checkpoint are separate actions. Ask:

> Preview a checkpoint for the changes I just approved. Explain anything else
> that would be included.

The agent uses `mb checkpoint --plan --json` to inspect pending files. If the
preview includes unrelated work, resolve that before saving. Ask it to propose
and validate a business-readable checkpoint message with
`mb checkpoint --validate "..." --json`.

For this example, the proposed message describes clarifying the offer and
recording the wording experiment. After reviewing the file list and message:

> Approved. Save this checkpoint locally. Don't sync it yet.

The agent saves with `mb checkpoint --message "..." --yes` after the safety
gates pass, then confirms the result. If a gate blocks the save, ask it to
explain and resolve the flagged files before trying again. A local checkpoint
preserves accepted work in saved history; remote backup needs a separate
approved sync.

## Close with what you learned

At the end of the session, use the end route:

> Close the session with mb-end. Summarize what changed and what's still
> unknown. Propose any lesson worth keeping before you write it.

A useful close distinguishes the decision from its outcome:

> We clarified what the session delivers and saved the wording experiment.
> We learned that the old phrase prompted a furniture question, based on your
> observation. We have not learned whether the new wording improves sales.
> Next time, review any new questions before changing the service itself.

If that next check is missing from the decision, approve adding it. Preview
and approve another checkpoint if the close creates further file changes.
If everything is already recorded, closing need not create another file.

## Start tomorrow with the saved lesson

Open the same folder in a new session and start Main Branch again:

> Use mb-start. What did we decide about the offer, and what should we check
> before changing it again?

The agent should read the saved offer and decision, rather than rely on the
previous conversation:

> The saved decision replaced "workspace transformation" with the planning
> session and written layout plan. It records a clarity experiment, not a
> proven sales improvement. The next check is whether new questions still
> suggest that buyers expect furniture. Do you have any observations to add?

You can now add evidence, keep the wording, or revisit the decision. If the
agent misses the lesson, point it to the saved decision and ask it to read the
linked offer before recommending work.

## Who handles what

| Responsibility | Who handles it |
| --- | --- |
| Inspect folder health, report deterministic facts, and guard checkpoint saves | `mb` |
| Read context, compare choices, draft changes, and propose lessons | Main Branch skills |
| Correct facts, choose the next move, and approve writing, saving, syncing, or external action | You, the owner |
| Run the conversation and tools within its permissions | Claude Code or Codex |

Try the same sequence with one question about your business. Ask the agent to
read the relevant files, propose one change, and show what tomorrow's session
will read after you approve and save it.
