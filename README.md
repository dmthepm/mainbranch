<p align="center">
  <img src="docs/assets/main-branch-logo.png" alt="Main Branch logo" width="100" />
</p>

<h1 align="center">Main Branch</h1>

<p align="center"><strong>Give your AI the business brain it was missing.</strong></p>

<p align="center"><em>One folder for your offers, proof, research, decisions, launches, ads, pages, bets, and lessons, readable by Claude Code, Codex, and you.</em></p>

<p align="center">
  <a href="https://github.com/dmthepm/mainbranch/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/dmthepm/mainbranch?style=social"></a>
  <a href="https://pypi.org/project/mainbranch/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mainbranch?label=PyPI"></a>
  <a href="https://github.com/dmthepm/mainbranch/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/dmthepm/mainbranch/ci.yml?label=CI"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-supported-black">
  <img alt="Codex" src="https://img.shields.io/badge/Codex-supported-blue">
</p>

<p align="center">
  <a href="#set-up-with-ai-recommended"><strong>Set up with AI</strong></a> &middot;
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#what-changes">What changes</a> &middot;
  <a href="#what-it-actually-does">What it does</a> &middot;
  <a href="#named-workflows">Workflows</a> &middot;
  <a href="#works-with">Works with</a> &middot;
  <a href="docs/beginner-setup.md">Beginner setup</a>
</p>

---

<!--
  HERO VISUAL - ADD BEFORE PUBLISHING
  Best README conversion asset:
    1. Open a sample business folder.
    2. Open the folder in Claude Code and run `/mb-start`, or open it in Codex
       and use the global `mb-start` skill.
    3. Show the agent reading Main Branch facts and naming the next business move.
    4. Flash to `mb checkpoint --plan` or `mb graph --open`.
  Save to docs/assets/hero.gif and uncomment the image below.
-->
<!-- <p align="center"><img src="docs/assets/hero.gif" alt="Main Branch in action" width="780" /></p> -->

## Why this exists

Your business context is probably scattered: a Notion page for the offer, Looms
for voice, Google Docs for research, a few chats with good ideas, a launch plan
somewhere, and decisions no one can find when the next AI session starts.

Main Branch turns one folder on your computer into business memory your agent
reads before it answers, then saves approved decisions, launches, bets, pages,
ads, research, and lessons back into files you own.

It is built for revenue-producing work: sharpening offers, building proof,
planning launches, writing ads, creating organic content, checking pages,
tracking bets, and turning what you learn into the next decision.

Open the folder. In Claude Code, run `/mb-start`. In Codex, use the global
`mb-start` skill. Tell the agent what you want help with. Main Branch checks
what changed, what matters, and what to do next.

| Step | What you do | What happens |
| --- | --- | --- |
| **01** | Open the business folder | Your offer, audience, voice, proof, research, bets, pushes, logs, and documents live there. |
| **02** | Start Main Branch | Claude Code uses `/mb-start`; Codex uses the global `mb-start` skill. The agent checks current Main Branch facts before giving advice: status, MoneyPath, recent work, connected tools, drift, checkpoints, and next actions. |
| **03** | Pick the next move | The agent routes the work into an offer, bet, decision, push, playbook, research note, outcome, or checkpoint. |
| **04** | Approve the work | Writing files, publishing, spending, account changes, and customer contact stay your call. |
| **05** | Keep the lesson | Approved work becomes durable memory for the next session. |

If you want AI business memory that stays yours, star this repo so more
business owners find it.

---

## Set up with AI (recommended)

Open your strongest model — Claude Fable with the 1M context window works
great; on Codex, pick the strongest model with extra reasoning — and paste
this:

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

Prefer to drive it yourself? Everything below is the manual path.

## Quickstart

Start with the folder that should become your business brain:

Tell the agent what you are setting up. It should create or connect the business
folder, not save your note as another document.

```bash
pipx install mainbranch
mb onboard --name "My Business" --path my-business
```

`mb onboard` creates the folder, prepares Claude Code and Codex, and shows the
next step. Claude Code uses `/mb-start`; Codex uses the global `mb-start` skill.
Both read the folder and Main Branch facts before telling you what to do.

### Daily use

1. Open or select the business folder in Claude Code or Codex.
2. In Claude Code, run `/mb-start`. In Codex, use the global `mb-start` skill.
3. Tell the agent what you want help with: an offer, page, ad, launch, research
   question, decision, or cleanup.

You do not need to make terminal commands your daily workflow.

Use either Claude Code or Codex. Both start from the same business folder.
Step-by-step walkthrough: [docs/beginner-setup.md](docs/beginner-setup.md).

### Backup and sync

GitHub backup/sync is strongly recommended. It gives the business brain cloud
backup, readable saved history, shared tasks/proposals, and a repo that AI tools
with GitHub connectors can read. Before using the GitHub-backed path, confirm
GitHub is signed in on your computer:

```bash
gh auth status
gh api user --jq .login
```

To create the folder, save the first scaffold, create a private GitHub repo,
and push it in one pass:

```bash
mb onboard --yes --name "My Business" --path my-business --github owner/my-business --github-visibility private --push
```

Tested on macOS and Linux. Windows is experimental; use WSL2 for the closest
supported path.

---

## What changes

| Just AI | Main Branch + Agent |
| --- | --- |
| Context lives in chats, projects, docs, and memory you manage manually. | Business truth lives in a folder the agent reads every session. |
| Output can drift away from your offer, voice, proof, or latest decision. | The agent reads current files and Main Branch facts before acting. |
| Decisions disappear into conversation history. | Decisions become plain files future sessions can cite. |
| Long workflows are hard to pause and resume. | Checkpoints preserve approved progress in readable history. |
| Tool setup breaks silently. | Main Branch checks health and shows repair paths. |
| Connected accounts can leak secrets or blur authority. | Secrets stay outside tracked files, and account changes stay approval-gated. |

---

## What it actually does

The short version: Main Branch makes AI business work durable, inspectable, and
grounded in the business you are actually running.

### 1. Starts every session from business facts

`/mb-start` is the daily entry point. It checks:

- what changed since last time;
- what is unsaved or needs a checkpoint;
- whether offer, proof, CTA, page, channel, push, playbook, and outcome
  feedback are connected;
- whether content strategy, bookkeeping setup, connected tools, updates, or
  folder health need attention;
- the ranked next actions with the signals behind them.

You ask the agent. Main Branch runs the checks underneath the conversation.

### 2. Saves long AI sessions as readable history

Pause a four-hour research, offer, ad, or site session. Come back Monday. Scan
your history in plain English.

When you ask to save progress, Main Branch previews the changed files, proposes
a readable checkpoint, blocks obvious secrets and scratch files, and waits for
approval. `/mb-end` uses the same save path to close a session.

This is not noisy autosave and not blanket automatic pushing. It is approved
business memory at meaningful boundaries.

### 3. Runs real business workflows

Main Branch skills run multi-step workflows, not prompt snippets:

- **`/mb-think`** researches, sharpens offers, turns source material into
  decisions, analyzes sales videos, and cleans up stale claims.
- **`/mb-ads`** creates paid creative: hooks, static ads, image prompts, video
  scripts, long-form paid creative, launch plans, optional read-only account
  checks, and 6-lens P1/P2/P3 compliance review.
- **`/mb-organic`** creates Reels, TikToks, carousels, static posts, and
  sales-video repurposing drafts from your voice and content strategy.
- **`/mb-site`** supports landers, minisites, websites, Cloudflare Pages,
  concept variations, pitch scripts, VSL-style work, and paid-traffic
  measurement checks.
- **`/mb-bet`** opens, updates, closes, lists, and narrates business bets with
  appetite, metrics, deadlines, evidence, kill/double-down thinking, and
  graduation paths.
- **`/mb-end`** closes a session with summary, crystallization, and approved
  checkpoint options.

Playbooks and push records turn repeatable work into durable business memory.
They record plans, approval gates, connected-account boundaries, manual steps, and
outcomes without giving the agent hidden authority to publish, spend, DM, or
mutate accounts.

### 4. Builds a graph of your business

Main Branch can map how decisions, research, bets, launches, pages, files, and
connected tools relate. Use the graph to see what the agent is reading from
instead of trusting a black box.

### 5. Keeps the business folder healthy

Main Branch checks structure, links, setup, updates, connected tools, saved
history, and business relationships so the agent does not have to guess.

It can show what changed, what needs repair, what is ready to ship, what still
needs approval, and where the next useful action is.

### 6. Connects real tools safely

Main Branch is not a connect-every-SaaS hub. It connects to real tools only
where that makes daily business work clearer and safer.

The choices are deliberate. GitHub is for saved history and proposals.
Cloudflare is the launch rail for domains, DNS, websites, ad landing pages, and
small always-on tools. Bookkeeping uses plain files so owners have an exit path
from QuickBooks-style software. Social and ad tools stay narrow until posting,
spend, or account changes can be handled safely.

| Tool | What Main Branch does |
| --- | --- |
| **GitHub** | Backup, saved history, tasks/proposals, folder detection, and privacy-scrubbed public issue drafting. First-run setup can create and push a GitHub repo when you choose that path. |
| **Cloudflare** | The default web launch path: domain and DNS work, websites, ad landing pages, Cloudflare Pages, and future Workers for small always-on business tasks. Tokens stay out of saved files, and deploys or account changes require approval. |
| **Google / Workspace** | Planned optional connection for source material and metadata; durable summaries belong back in the folder. |
| **Google Ads / GTM** | Checks whether a site is ready to measure paid traffic. Publishing tags, creating conversions, uploading data, changing budgets, or launching campaigns requires separate approval. |
| **Meta Ads** | Read-only account summaries after setup. No campaign editing, budget changes, or launch claim. |
| **Bookkeeping** | Plain-file bookkeeping for owners who want to stop depending on QuickBooks-style software. Uses hledger under the hood, keeps raw ledgers private, tracks bet exposure, and can show sample monthly reports. |
| **Apify** | Optional read-only research path. No official X integration, no posting, no DMs, no guaranteed scrape coverage. |
| **Postiz** | Future path for scheduling and automatically posting approved content to social channels. Today, treat social posting as a draft-and-approve workflow, not an automatic publishing promise. |

Secrets stay out of saved business files. Publishing, spend, customer contact,
account changes, GTM publication, Google Ads changes, Meta campaign changes, and
DM automation stay approval-gated or out of scope until there is tested support.

---

## The operating loop

Main Branch is built around four loops every business owner runs whether they
name them or not.

**Sense -> Decide -> Ship -> Reflect.**

| Loop | The question | What it looks like |
| --- | --- | --- |
| **Sense** | What's true right now? | `/mb-start` and `/mb-status` read folder health, recent work, MoneyPath, content strategy, connected-account status, and tasks/proposals. |
| **Decide** | What do we do next? | `/mb-think`, bets, decisions, and ranked actions help choose the next business move. |
| **Ship** | What goes out the door? | `/mb-ads`, `/mb-organic`, `/mb-site`, `/mb-bet`, pushes, playbooks, issue drafts, updates, and checkpoints move work forward. |
| **Reflect** | What sticks? | `/mb-end`, bet close/narrate, outcomes, retros, decisions, and checkpoint history turn lessons into future context. |

Each loop reads your folder before it speaks. Each loop writes back only when
you approve.

---

## Named workflows

Things you can ask for this week:

- **Start the business day from facts.** Main Branch reads status, MoneyPath,
  recent work, drift, connected tools, and ranked actions before advice.
- **Turn research into a decision.** Ask it to turn source material,
  transcripts, market context, and business files into research, decisions,
  offer updates, proof context, or stale-source cleanup.
- **Create paid creative with review gates.** Ask it to draft hooks, static ads,
  image prompts, video scripts, long-form paid creative, and launch plans, then
  run 6-lens P1/P2/P3 compliance review before approval.
- **Create organic content in your voice.** Ask for Reels, TikToks, carousels,
  static posts, and sales-video repurposing from your content strategy and
  source material.
- **Plan and check a landing page.** Ask for a lander, minisite, site pass,
  pitch script, or paid-traffic measurement check.
- **Open a bet with a real exit path.** Record the hypothesis, appetite, metric,
  target, deadline, evidence, and linked work.
- **Save a long session as readable history.** Close the session, review what
  happened, preview the checkpoint, and save only after approval.
- **Draft a public GitHub issue safely.** Turn confusing friction into a scrubbed
  issue draft you review before anything posts.
- **See your business as a graph.** Map how decisions, research, bets, pushes,
  and connected tools relate.
- **Repair a folder that drifted.** Ask for a repair plan before changing files.

---

## Who it is for

Main Branch is for solo founders, small agencies, course creators,
productized-service owners, indie SaaS founders, small ecom teams, and
small teams that want AI help without surrendering their operating memory to
another SaaS.

It is a good fit if:

- your offer, voice, research, proof, and launch context are scattered;
- you want AI help with offers, pages, ads, content, launches, and decisions;
- you want history you can inspect instead of chat output you have to trust;
- you want private business truth to stay in files you own;
- you want the system to get sharper the longer you use it.

---

## Common objections

| Objection | Reality |
| --- | --- |
| "I'm not technical enough." | Install once. Then open the folder in Claude Code and run `/mb-start`, or open it in Codex and use the global `mb-start` skill. Answer plain-language questions. |
| "I'll set it up wrong." | Main Branch checks the folder, explains what is wrong, and shows the repair path. |
| "I'll lose work." | Approved checkpoints and GitHub backup give you readable history and reviewable changes. |
| "I need someone to walk me through it." | Open the folder in Claude Code and run `/mb-start`, or open it in Codex and use the global `mb-start` skill. The agent explains the next step. |
| "I won't maintain it." | Run `/mb-update` when asked. Repair checks tell you if anything needs fixing. |

---

## Works with

| App | Current support |
| --- | --- |
| **Claude Code** | Open or select the business folder in the Claude Desktop app or the terminal, run `/mb-start`, and use the bundled Main Branch skills. They install as a plugin that works on both surfaces; `mb onboard` wires it for you. |
| **Codex** | Open or select the business folder and use the global Main Branch `mb-*` skills. |

Account writes, publishing, spend, customer contact, and account changes remain
approval-gated everywhere.

Cursor, OpenClaw, Hermes, Paperclip-adjacent orchestration, Windows native, and
local-only agent setups are not documented as supported until the exact path is
tested.

See [docs/compatibility.md](docs/compatibility.md) for the current support list.

---

## What Main Branch is not

| | |
| --- | --- |
| **Not a chat app.** | Use it inside Claude Code or Codex. Main Branch gives them durable context to read from. |
| **Not a SaaS dashboard.** | Your business does not live on our servers. It lives in your folder. |
| **Not a connect-every-tool hub.** | We pick boring, inspectable connections: GitHub, Cloudflare, Meta Ads, bookkeeping, and a few optional tool paths. Curated, not sprawl. |
| **Not an ad manager or publisher.** | Paid creative and site checks are supported; spend, publishing, account changes, and customer contact require explicit approval and tested support. |
| **Not a model host.** | `mb` does not run models. It gives the agent the right context so the model you already use is sharper. |
| **Not magic.** | The work is still real. Main Branch makes the memory and workflow durable. |

---

## FAQ

**Do I need to know how to code?** No. Open the folder in Claude Code and run
`/mb-start`, or open it in Codex and use the global `mb-start` skill. Answer
questions. The beginner walkthrough shows each setup step.

**Do I need to know git?** No. Main Branch uses git as the hidden save/history
layer and speaks in business language: checkpoints, saved history, tasks, and
proposals.

**Does it push to GitHub automatically?** No. Checkpoints save accepted work
into local git history. GitHub backup/sync is recommended, and first-run
onboarding can create and push a GitHub repo when you choose that path.

**What if I have multiple products under one brand?** Use one folder with
`core/offers/` when products share brand, team, voice, and access. Move an
offer into its own folder if it grows its own team, accounts, site, finance
boundary, or operating history.

**What's a bet vs. an offer?** A bet is a time-boxed hypothesis: what you will
try, why, by when, and how you will know. An offer is a durable thing you sell.
A winning bet can graduate into an offer through an accepted decision.

**How do I update?** Type `/mb-update` in Claude Code, or use the global
`mb-update` skill in Codex. If you installed the Claude Code plugin, update the
package, re-add the plugin, and restart Claude Code so the loaded skills match
the new release.

**Can Claude or Codex migrate an old setup for me?** Yes. Open the folder in
Claude Code or Codex and follow the migration prompt in
[docs/migrating.md](docs/migrating.md#recommended-let-an-agent-walk-you-through-it).

**Can I edit the skills?** You can. You usually do not need to.

**What makes this different from ChatGPT or project memory?** Main Branch is
not only memory text. It is a structured folder, health checks, validation,
graphing, repair paths, connected-tool checks, checkpoints, and agent workflows
that write approved business artifacts back into files you own.

**I'm stuck.** In Claude Code, type `/mb-start` again. In Codex, use the global
`mb-start` skill again. If `/mb-start` is not found at all, the Main Branch
plugin may not be installed — add it with `claude plugin marketplace add
dmthepm/mainbranch`, enable it, and restart Claude Code. The plugin-native
diagnostic command is `/mainbranch:mb-start`; the friendly `/mb-start` command
comes from the project-local bridge Main Branch keeps wired for users.

---

## Open source and optional community

The command-line tool, bundled skills, schema, framework, docs, and any future
local dashboard are MIT-licensed and usable without joining anything. The
[Skool community](https://skool.com/main) is the live narration on top: watch
us build companies with Main Branch in real time.

---

## For contributors and power users

The agent runs `mb` for normal users. If you want to inspect, script, debug, or
build on it, here is the command list.

<details>
<summary>CLI commands</summary>

| Command | What it does |
| --- | --- |
| `mb onboard` | Human setup flow: create or connect a business folder, prepare Claude/Codex setup, show next steps. |
| `mb init` | Quiet scriptable primitive underneath `mb onboard`. |
| `mb status` | Local-first daily briefing with ranked next actions, MoneyPath readiness, recent activity, GitHub tasks/proposals, updates, and drift. |
| `mb doctor` | Check environment, repo shape, frontmatter, settings, app setup, provider state, and repair paths. |
| `mb connect` | Register connected-account metadata/credentials, test health where supported, inspect repair-safe integration status without committing secrets. `mb connect exec <provider> -- <command>` runs a command with the stored credential in its environment only, so an agent can use it without retrieving the raw value; the command itself must not print it. See [docs/connect.md](docs/connect.md). |
| `mb fleet` | Read-only status of every site across your hubs (framework, CI, deploy, Dependabot) from one cached snapshot. Needs Python 3.11+. See [docs/fleet.md](docs/fleet.md). |
| `mb books` | Plain-file bookkeeping setup checks, bookkeeping engine health, safe repair plans, bet exposure, and fake-data sample monthly reporting. |
| `mb launch check` | Read-only launch readiness across app stack, deploy rail, commerce, email, local smoke scripts, and measurement posture. |
| `mb site check` | Local paid-traffic measurement readiness: GTM install, dataLayer events, consent posture, Google Ads metadata, approval gates. |
| `mb ads meta summary` | Read-only Meta Ads account context through the official Meta CLI path after setup. |
| `mb issue draft` / `open` | Draft a privacy-scrubbed GitHub issue locally, review it, then submit through `gh`. |
| `mb feedback` | Log mb friction to a local file; refusals log themselves; `rollup` drafts a weekly summary. Nothing is sent. See [docs/feedback.md](docs/feedback.md). |
| `mb validate` | Frontmatter and cross-reference checks across business repo files. |
| `mb graph` | Build a folder graph from links, tags, connected-tool refs, and repo topology. DOT, JSON, and PNG outputs. |
| `mb suggest links` | Suggest likely connections for a file without editing it. |
| `mb checkpoint` | Plan or save a readable git checkpoint during long agent runs. |
| `mb workflow list` | List workflow surfaces by support level (supported, read-only planning, shared-source, pending, unsupported). |
| `mb skill list` / `path` / `validate` / `link` / `repair` | Inspect, validate, link, and repair bundled skills and generated app guidance. |
| `mb update` | Update Main Branch in place. |

</details>

<details>
<summary>Bundled skills</summary>

| Skill | What it does |
| --- | --- |
| `/mb-start` | Daily entry point: figure out what you need and route there. |
| `/mb-status` | Daily briefing facts and ranked next actions. |
| `/mb-setup` | First-time setup with business-type routing. |
| `/mb-think` | Research, decide, codify, keyword-gate, sharpen offers, and source cleanup. |
| `/mb-bet` | Open, update, close, list, and narrate business bets. |
| `/mb-end` | Close the session: summary, crystallization, checkpoint options. |
| `/mb-ads` | Paid creative: hooks, ads, image prompts, video scripts, launch plans, compliance review. |
| `/mb-organic` | Organic content: Reels, TikToks, carousels, static posts, and sales-video repurpose. |
| `/mb-site` | Lander, minisite, website, Cloudflare Pages, pitch scripts, and measurement checks. |
| `/mb-books` | Private books setup, monthly close and reconciliation review, and CPA handoff prep. |
| `/mb-wiki` | Specialty personal atomic-notes wiki on Cloudflare Pages. |
| `/mb-update` | Update Main Branch. |
| `/mb-help` | Q&A, troubleshooting, and system help. |

</details>

Full list: `mb --help`. JSON output contract:
[docs/json-output-contract.md](docs/json-output-contract.md). Connected-tool
choices: [docs/dependency-choices.md](docs/dependency-choices.md).

### Reading order

- [AGENTS.md](AGENTS.md) - shared operating contract for Codex, Claude Code, and other agents
- [CLAUDE.md](CLAUDE.md) - Claude Code-specific guidance
- [CONTRIBUTING.md](CONTRIBUTING.md) - branch, commit, and validation discipline
- [docs/ethos.md](docs/ethos.md) - product principles
- [docs/operator-loops.md](docs/operator-loops.md) - Sense -> Decide -> Ship -> Reflect taxonomy
- [docs/roadmap.md](docs/roadmap.md) - release direction
- [docs/compatibility.md](docs/compatibility.md) - runtime support matrix

---

## Community

- [Skool community](https://skool.com/main) - watch us build with Main Branch
- [GitHub Issues](https://github.com/dmthepm/mainbranch/issues) - bugs, feature requests and ideas
- [Good first issues](https://github.com/dmthepm/mainbranch/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) - small, scoped issues for a first pull request

---

## License

[MIT](LICENSE) (c) 2026 Noontide

<p align="center">
  <sub>Open source. Built for people who want to own their business memory, not rent it.</sub>
</p>
