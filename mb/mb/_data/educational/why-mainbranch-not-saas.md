---
type: educational
topic: why-mainbranch-not-saas
status: draft
last-updated: 2026-05-08
---

# Why Main Branch is not another SaaS dashboard

Start with the daily owner loop:

```bash
cd /path/to/your-business
claude
/mb-start
```

Main Branch's anti-SaaS philosophy exists to make that loop work. Your business
memory should not reset every time you open a new chat or switch tools.

Traditional SaaS tools are useful, but they usually own the database, the
workflow, the pricing, and the export shape. Main Branch puts the durable
operating memory in files you own, then lets `mb`, Claude Code skills, GitHub,
and provider rails work around that repo.

## The beginner version

Main Branch has three layers:

1. **Your business repo** - the durable memory: offers, audience, voice,
   research, decisions, bets, pushes, logs, documents, outcomes, and safe
   provider references.
2. **`mb`** - the deterministic control plane: setup, status, validation,
   graph links, provider readiness, updates, repair, and checkpoints.
3. **Claude Code skills** - the judgment layer: research, decide, write,
   review, ship, and reflect from the files.

A SaaS dashboard usually hides those layers behind one account. Main Branch
keeps them inspectable.

## What this changes for a business owner

**You stop rebuilding context.** The agent can read the repo instead of asking
you to paste the same offer, audience, proof, and decisions every session.

**You can inspect the work.** The files are regular markdown. The history is
regular git. Issues and pull requests are durable work threads and proposals,
not hidden rows in a vendor database.

**You can switch tools later.** Claude Code is the supported slash-skill
runtime today, and Codex CLI is supported for the owner loop. The repo shape is
not trapped inside either runtime. Future adapters should read the same files
and deterministic `mb` commands.

**You keep SaaS tools as rails, not the brain.** GitHub, Cloudflare,
Google/Workspace, ads tools, Apify, Stripe, Cal.com, and other providers can be
useful. Main Branch connects them when the business job needs them. The repo
remains the source of truth.

## What the daily loop should feel like

```bash
cd /path/to/your-business
claude
/mb-start
```

Then:

1. `/mb-start` senses the repo facts.
2. You and Claude decide the next useful business move.
3. A skill ships the artifact or `mb` repairs the rail.
4. `/mb-end` or `mb checkpoint` helps preserve the lesson or saved work.

The words should feel like business work: bets, goals, offers, pushes,
playbooks, outcomes, and checkpoints. The philosophy is there to protect the
loop: files you own, facts `mb` can check, and rails that stay inspectable.

## Why this is harder at first

Files, terminal commands, markdown, git, and GitHub are less familiar than a
web app with a big button. Main Branch should make that safer with `mb
onboard`, numbered choices, readiness checks, exact next commands, and Claude
Code skills that explain the result.

The learning curve exists because the payoff exists: your business record is
portable, inspectable, and compounding.

## What Main Branch does not claim

Main Branch is not a hosted dashboard, chat client, background daemon, vector
database, scheduler, marketplace, or model host today.

Claude Code is the supported slash-skill runtime today. Codex CLI is supported
for the owner loop. Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration,
and local runtimes are compatibility targets until adapter code and smoke
evidence prove support.
