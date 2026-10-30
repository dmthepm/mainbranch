# Beginner Setup Guide

Setup guide for people new to Claude Code, Codex, Git, or the terminal. Plan
on under 30 minutes.

---

## Read this first

Main Branch turns one folder on your computer into the business brain your AI
reads before it helps. That folder holds your offer, proof, research, decisions,
launches, pages, ads, bets, notes, and lessons in files you own.

Most of this page is one-time setup. After that, your normal flow is simple:

1. Open or select the business folder in Claude Code or Codex.
2. In Claude Code, run `/mb-start`. In Codex, use the global `mb-start` skill.
3. Tell the agent what you want help with.

You will use a few terminal commands during setup because Main Branch creates
real files on your machine. You do not need to make terminal commands your daily
workflow.

---

## What you need

- **A folder on your computer** - this becomes your business brain.
- **Main Branch (`mb`)** - creates the folder, checks it, updates it, and
  repairs it when something drifts.
- **Claude Code or Codex** - the app where you talk to the agent.
- **GitHub CLI (`gh`)** - strongly recommended for backup, sync, shared tasks,
  proposals, and AI tools that can read GitHub repos.

GitHub does not need to cost anything. Main Branch can start locally before
GitHub is ready, but most users should connect GitHub during first setup so the
business brain has cloud backup and readable saved history.

Before using GitHub-backed setup, confirm GitHub is signed in on your computer:

```bash
gh auth status
gh api user --jq .login
```

If that account is wrong, stop before creating the GitHub-backed setup and run
`gh auth login` or `gh auth switch`.

---

## Setup with an agent

This is the same prompt as the README's "Set up with AI (recommended)"
section — the same prompt, two doors. Open your strongest model
(Claude Fable with the 1M context window works great; on Codex, pick the
strongest model with extra reasoning) and paste this:

```text
I want Main Branch: AI business memory I own as files in one folder
(https://github.com/dmthepm/mainbranch). First read the entire README (fetch the raw file if your tools summarize),
then explore the repo enough to understand the architecture (the mb CLI is
the deterministic control plane; skills are the judgment layer; my business
lives in its own folder, never in the engine; bets, research, decisions,
pushes, playbooks, outcomes, and checkpoints are the primitives; writing
files, publishing, spending, and customer contact stay my call). Then
interview me briefly about my business, my offer, and my audience. Then:
install the engine, run `mb onboard` to create my business folder,
then run `mb doctor` inside that folder and fix anything it flags, seed my
core files from the interview using the templates the folder ships with,
save the first checkpoint, and teach me the daily loop — /mb-start to
open, /mb-end to close. If I decline GitHub, treat local-only as a valid
choice, not something to repair. Get me to a business folder with offer,
audience, and voice drafted and a clean `mb status`, then stop and show me
what you set up.
```

Do not save that prompt as a markdown document. It tells the agent to start
setup. The agent keeps the safety rails regardless of the prompt: writes are
explained and approved first, GitHub-backed setup checks `gh auth status`
and the signed-in account, and setup ends with read-only health checks in
plain business language.

---

## Step 1: Install the tools

### Mac

```bash
# 1. Install pipx, the Python app installer Main Branch uses
brew install pipx
pipx ensurepath

# 2. Install Main Branch
pipx install mainbranch

# 3. Strongly recommended for backup/sync/collaboration
brew install gh
gh auth login
```

Install Claude Code, Codex, or both from their official instructions. Main
Branch works from the same business folder in either app. In Claude Code, Main
Branch installs as a plugin that works in both the Claude Desktop app and the
terminal — `mb onboard` (next step) wires it for you, so you usually do not
install it by hand.

### Linux

Use `apt install pipx` on Debian/Ubuntu or `dnf install pipx` on Fedora, then:

```bash
pipx ensurepath
pipx install mainbranch
```

For GitHub backup/sync/collaboration, install GitHub CLI from
[cli.github.com](https://cli.github.com/) and run `gh auth login`.

### Windows

> **Windows is experimental.** It may work, but it is not tested in CI. For the
> closest supported path, use WSL2. See [compatibility](compatibility.md).

```powershell
# 1. Install pipx
python -m pip install --user pipx
python -m pipx ensurepath

# 2. Install Main Branch
pipx install mainbranch

# 3. Strongly recommended for backup/sync/collaboration
# Download GitHub CLI from https://cli.github.com/
gh auth login
```

After install, verify:

```bash
mb --version
```

---

## Step 2: Create your business folder

Local setup:

```bash
mb onboard --name "My Business" --path my-business
```

GitHub-backed setup, after `gh auth status` shows the expected account:

```bash
mb onboard --name "My Business" --path my-business --github your-gh-username/my-business --github-visibility private --push
```

`mb onboard` creates or connects the folder, prepares Claude Code and Codex,
and shows the next step.

The folder will include places for core business context, research, decisions,
bets, logs, launches, documents, playbooks, and saved lessons. You may also see
a `.mb/` folder. That is normal. It stores local Main Branch state for this
business, such as onboarding progress, safe connected-account metadata, backups,
and issue drafts.

You do not need a `.mb-vip/` folder. That name comes from the old setup.

### What gets saved

- Saving a file writes it on your computer.
- A checkpoint is an approved saved point in the business history.
- GitHub backup/sync means approved history is also available from GitHub, where
  AI tools with GitHub connectors can read the business brain.
- Main Branch updates change the engine and skills. They do not rewrite your
  business files without an approved repair, migration, or edit.

Use one business folder when brand, team, voice, access, and operating history
are shared. Use separate folders for separate entities or independent operating
histories. Use linked child repos for sites, products, finance/legal, client
work, or private ops when access or lifecycle differs. The full model lives in
[system architecture](system-architecture.md#repo-topology).

---

## Step 3: Start the first session

Open or select the business folder in Claude Code or Codex.

In Claude Code, run:

```text
/mb-start
```

Claude Code supports the production workflows below. Codex supports the daily
loop; bet, ads, organic, site, and books routes are read-only planning. See
[runtime compatibility](compatibility.md) and run
`mb workflow list --runtime codex --json` for exact route status.

`/mb-start` checks what changed, what matters, and what to do next. It can route
you into setup, thinking, ads, organic content, site work, bookkeeping checks,
repairs, updates, or closing a session.

In Codex, use the global `mb-start` skill instead of typing the slash command.

If `/mb-start` does not appear in Claude Code, the Main Branch plugin may not be
installed or enabled yet, or the project-local bridge may need repair. Add the
plugin with `claude plugin marketplace add dmthepm/mainbranch`, enable it,
and restart Claude Code from this folder. The plugin works in both the Claude
Desktop app and the terminal. For direct plugin diagnostics, use
`/mainbranch:mb-start`.

Daily use is:

1. Open or select the business folder in Claude Code or Codex.
2. In Claude Code, run `/mb-start`. In Codex, use the global `mb-start` skill.
3. Tell the agent what you want help with: an offer, page, ad, launch, research
   question, decision, bookkeeping check, or cleanup.

You do not need to run `mb status` first. `/mb-start` reads those facts for you.

---

## Connected tools

You do not need to connect every account during first setup. Main Branch chooses
tools carefully so each one has a clear job and a safe boundary.

| Tool | Why it is included |
| --- | --- |
| **GitHub** | Backup, saved history, shared tasks/proposals, and a copy of the business brain AI tools can read. |
| **Cloudflare** | Domains, DNS, websites, ad landing pages, Cloudflare Pages, and future Workers for small always-on business tasks. |
| **Google / Workspace** | Read-only Search Console and GA4 commands through `mb google` after setup. Broader Workspace source ingestion remains planned; durable summaries belong back in the folder. |
| **Google Ads / GTM** | Checks whether a site is ready to measure paid traffic. Publishing tags, creating conversions, changing budgets, or launching campaigns requires separate approval. |
| **Meta Ads** | Read-only account summaries after setup. No campaign editing, budget changes, or launch claim. |
| **Bookkeeping** | Plain-file bookkeeping for owners who want to stop depending on QuickBooks-style software. Uses hledger under the hood and keeps raw ledgers private. |
| **Apify** | Optional read-only research path for web research where scraping is appropriate. |
| **Postiz** | Future path for scheduling and automatically posting approved content to social channels. Today, treat social posting as draft-and-approve, not automatic publishing. |

Secrets stay outside saved business files. Publishing, spend, customer contact,
account changes, Google Ads changes, Meta campaign changes, and DM automation
stay approval-gated or out of scope until there is tested support.

Power users can inspect setup choices from the business folder:

```bash
mb connect plan
```

---

## Updating Main Branch

When Main Branch says an update matters, run this in Claude Code:

```text
/mb-update
```

In Codex, use the global `mb-update` skill. The update path figures out which
install you have and refreshes the supported surfaces it owns. `/mb-start` also
checks for important updates at the beginning of a Claude Code session.

If you installed Main Branch as a Claude Code plugin, package updates do not
change the plugin that Claude Code has already loaded. After updating, re-add the
Main Branch plugin (`claude plugin marketplace add dmthepm/mainbranch`) and
restart Claude Code.

Power users can run the same update path from a business folder:

```bash
mb update --repo .
```

If you installed an early `0.1.x` version, `/mb-update` or `mb update` may say
the install is too old to update itself. The fallback command is:

```bash
pipx upgrade mainbranch
```

---

## Already using the old setup?

Read [migrating.md](migrating.md) before repairing old clone-era installs,
`reference/core/` layouts, or stale skill links. You usually do not need to
move files immediately. Update Main Branch first, then let the agent walk you
through the confirmation-gated migration prompt from that doc.

Open Claude Code or Codex and paste:

```text
I want to migrate my existing Main Branch setup to the current pipx workflow.
If we are in Claude Code, use `/mb-start` after repair. If we are in Codex, use
the global `mb-start` skill after repair. Please run read-only checks first,
find my likely business folders, show me the exact changes you recommend, and
ask before running anything that writes files. If an old `reference/` layout is
present, run `mb migrate --check` first and do not run `mb migrate --apply` until
I approve the dry run. Use docs/migrating.md as the source of truth.
```

The agent may ask you to restart in the business folder after it repairs setup.
That is normal.

---

## What you can ask for

You can ask naturally. In Claude Code, you can also use slash commands when you
know them. In Codex, use the matching global skill names without the slash.

| Ask for | What Main Branch does |
| --- | --- |
| `/mb-start` | Starts from current business facts and routes you to the next safe move. |
| `/mb-status` | Gives a briefing over current facts and ranked next actions. |
| `/mb-think` | Turns research, transcripts, market context, or messy ideas into decisions and business files. |
| `/mb-bet` | Opens, updates, closes, lists, and narrates business bets. |
| `/mb-ads` | Drafts paid creative and reviews it for compliance before approval. |
| `/mb-organic` | Drafts Reels, TikToks, carousels, static posts, and sales-video repurposing. |
| `/mb-site` | Helps plan, write, check, and launch landing pages, minisites, websites, and Cloudflare Pages work. |
| `/mb-books` | Reviews private books setup, monthly close, reconciliation, and CPA handoff readiness. |
| `/mb-seo` | Reviews public pages for SEO, with optional OpenSEO research (experimental). |
| `/mb-wiki` | Builds a personal wiki with atomic notes. |
| `/mb-end` | Closes a session with summary, crystallization, and checkpoint options. |
| `/mb-help` | Answers questions and helps troubleshoot. |
| `/mb-update` | Updates Main Branch. |

---

## Terminal commands for support

The agent normally runs `mb` for you. These are useful when you want to inspect
or repair something yourself.

| Command | What it does |
| --- | --- |
| `mb onboard` | Creates or connects a business folder and shows the next `/mb-start` step. |
| `mb status` | Shows a terminal-only briefing. `/mb-start` reads these facts internally. |
| `mb start` | Checks handoff readiness for Claude Code and Codex. |
| `mb connect plan` | Shows connected-tool setup choices. |
| `mb issue draft` | Drafts a privacy-safe GitHub issue from a bug, confusing step, or feature gap. |
| `mb checkpoint` | Plans or saves a readable checkpoint during long work. |
| `mb similar-bets` | Finds similar past bets and outcomes before starting a new one. |
| `mb update` | Updates Main Branch. |
| `mb doctor` | Checks setup and walks through fixes. |
| `mb validate` | Checks your business files. |
| `mb graph` | Shows how business files, decisions, bets, launches, and connected tools relate. |
| `mb skill list` | Shows which skills your installed Main Branch ships. |

For the full list, run `mb --help`.

---

## Common issues

**`/mb-start` does not appear in Claude Code:** ask the agent to repair Main
Branch setup in this folder. Power users can run:

```bash
mb doctor repair --plan
```

Apply only after reviewing the plan.

If you use the Claude Code plugin, re-add the Main Branch plugin and restart
Claude Code after updating. If you use Codex, start a fresh Codex thread after
updating so refreshed global skills are loaded.

**I only see `.mb/`, not `.mb-vip/`:** good. `.mb/` is current. `.mb-vip/` was
old setup language and is not required.

**`mb` not found after install:** run `pipx ensurepath`, close your terminal
completely, reopen it, then try `mb --version`.

**Output sounds generic:** add more detail to your core files, especially the
files about your offer, audience, voice, proof, and current bets.

**You hit a 404:** the repo is public; no access request is needed. Double-check
the URL spelling.

---

## Help

- **In Claude Code:** run `/mb-help` or describe the issue in plain English.
- **In Codex:** use the global `mb-help` skill or describe the issue in plain
  English.
- **In the community:** post with a screenshot of the exact error.
- **For contributors:** open an issue at
  [https://github.com/dmthepm/mainbranch/issues](https://github.com/dmthepm/mainbranch/issues).
- **Platform support:** see [compatibility](compatibility.md).

---

## After setup

You do not need to memorize the commands.

Open or select your business folder in Claude Code or Codex. In Claude Code, run
`/mb-start`; in Codex, use the global `mb-start` skill. Then tell the agent what
you want help with. Main Branch keeps the useful work in files you own so the
next session does not start from scratch.

### Get your first useful result

Ask the agent:

> Read my offer, audience, and voice drafts. Show me one unclear promise and
> propose a clearer version. Explain what supports it and what you still need
> to ask me. Wait for my approval before writing.

Review the proposal, correct any assumptions, and approve only the changes you
want. Then ask for a checkpoint preview and approve the save separately. You
have a useful first result when you can read an accepted offer draft and name
one next business task. Optional account connections can wait.

Continue with [a working day](working-day.md) to see how an approved decision
becomes a lesson the next session can use.
