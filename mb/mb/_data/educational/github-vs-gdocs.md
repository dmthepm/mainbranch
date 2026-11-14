---
type: educational
topic: github-vs-gdocs
status: draft
last-updated: 2026-05-08
---

# GitHub vs. Google Docs: why your business repo lives in files

Main Branch is not asking you to become a developer. It is asking you to put
the important parts of the business record in a place that you, your team,
and your agent can inspect later.

Google Docs is good for live writing. GitHub plus markdown is better for
durable operating memory.

## The beginner version

Think of Google Docs as a whiteboard and GitHub as the business filing cabinet
with a built-in change log.

When you run `mb onboard`, Main Branch creates a business folder on your
computer. Inside it are plain markdown files for offers, audience notes,
research, decisions, pushes, logs, documents, and outcomes. Git records how
those files change over time. GitHub can back up and share that history.

You do not need to manage the plumbing every day. The normal loop is:

```bash
cd /path/to/your-business
claude
/mb-start
```

`/mb-start` reads the files and the repo facts before it gives advice.

## Why not just use Google Docs?

**Docs are easy to write in, but hard to operate from.** A business usually
starts with scattered documents: a brand doc, an offer doc, research notes,
meeting notes, maybe a spreadsheet. Six months later, nobody knows which doc is
current or why the old decision changed.

**Git keeps the story.** A commit is a saved checkpoint. It says what changed,
when it changed, and what the operator meant to preserve. That matters when an
agent asks, "what did we decide last time?" or "what changed since this offer
worked?"

**Markdown is easy for agents to read.** Claude Code, future adapters, and
power-user tools can read files directly. They do not need to export a Doc,
guess at formatting, or lose comment context before reasoning about the
business.

**GitHub gives shared work threads.** Issues can be tasks, blockers, requests,
or follow-ups. Pull requests can be proposals and review conversations. You can
use friendlier words in the daily loop, but the durable layer remains
inspectable.

## What still belongs in Google Docs?

Use Google Docs when live multiplayer editing is the job: a call agenda that
three people are typing in at once, a client-facing collaborative draft, or a
source doc someone already gave you in Workspace.

When the doc becomes business truth, summarize or move the durable part into
the repo:

- a decision goes in `decisions/`;
- research goes in `research/`;
- an operating note goes in `log/`;
- offer, audience, voice, proof, and strategy updates go in `core/`;
- coordinated launches, drops, promos, or challenges go in `pushes/`.

## The safe setup path

Start with the shipped beginner command:

```bash
mb onboard --name "My Business" --path my-business
cd my-business
claude
/mb-start
```

Do not start by hand-writing git commands. Let `mb onboard`, `mb status`,
`mb doctor`, and `/mb-start` tell you what is ready and what needs repair.

## What Main Branch does not claim

Main Branch does not replace Google Workspace. It gives the business a durable
operating repo. Google Docs, Sheets, and Drive can still be useful source
material when a workflow needs them.

Main Branch also does not claim broad runtime support yet. Claude Code is the
supported runtime today; other runtimes are roadmap targets until adapter code
and smoke evidence exist.
