---
type: educational
topic: markdown-vs-notion
status: draft
last-updated: 2026-05-08
---

# Markdown vs. Notion: why Main Branch writes plain files

Notion is useful for pages, databases, and team notes. Main Branch uses
markdown because the business record needs to stay portable, searchable, and
easy for agents to read without a private app API.

## The beginner version

Markdown is plain text with light formatting:

```markdown
# Offer

This is who we serve, what we sell, and why it matters.
```

That file can be opened in any text editor. Claude Code can read it directly.
Git can show how it changed. GitHub can render it nicely.

## Why markdown works for the business record

**It is durable.** Plain text survives tool changes better than proprietary
workspace pages.

**It is easy to inspect.** You can search the whole business repo, compare
versions, and ask an agent to read a folder without exporting anything.

**It keeps structure close to the words.** Frontmatter can record status,
links, dates, providers, bets, pushes, and outcomes without turning every note
into a hidden database row.

**It works with git.** Git can diff text well. That makes decisions, offer
changes, and research updates easier to review.

## What still belongs in Notion?

Use Notion when it is already the team's collaborative scratch space, public
wiki, lightweight CRM, or source material. Main Branch does not require a
purge.

Move the durable part into the repo when the note becomes operating truth:

- a decision in `decisions/`;
- research in `research/`;
- a playbook or launch plan in `pushes/`;
- a durable operating lesson in `log/` or `core/`;
- a long-form artifact in `documents/`.

## What Main Branch does not claim

Markdown is not the best live multiplayer writing surface. If three people
need to type into the same paragraph during a call, use the tool that fits that
moment, then bring the durable result back into the repo.

Main Branch is not trying to clone Notion. It is trying to make the business
memory readable by the owner, the agent, git, GitHub, and future tools.
