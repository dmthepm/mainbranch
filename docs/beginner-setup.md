# Set up your business folder

Create a folder your agent can read, draft your core business context, and save
one useful result. Keep the business folder separate from the Main Branch
engine repository.

After setup, open that folder in Claude Code or Codex CLI and describe what
you need. The agent runs Main Branch's checks for you.

## What you need

- Python 3.10 or newer and git.
- pipx to install the `mb` command.
- Claude Code or Codex CLI, installed and signed in separately.
- Optional GitHub CLI, `gh`, for remote backup and shared work.

macOS and Linux are the supported CLI paths. Native Windows is experimental;
use WSL2 for the closest Linux path. See [compatibility](compatibility.md) for
runtime details and limitations.

## Setup with an agent

If you want the agent to guide setup, open your runtime and paste this prompt.
It is an example request, not a required business configuration.

```text
Help me set up Main Branch using the current README and setup guide at
https://github.com/dmthepm/mainbranch. Ask briefly about my business, offer,
and audience. Check which tools are installed. Propose a business folder
separate from the engine, then install Main Branch and run mb onboard with
my approval. Local-only setup is valid if I decline GitHub.

Inside the business folder, run mb doctor and explain any findings. Propose
offer, audience, and voice drafts using the folder's templates. Ask me to
review assumptions before writing. Preview the first checkpoint and ask
before saving or syncing it. Finish by showing the accepted drafts, any
unresolved setup findings, and one next business task. Teach me how to start
and close a session in my chosen runtime.
```

Do not save that prompt as a markdown document. It tells the agent to start
setup.

You can follow the steps below yourself instead. The agent should not need to
study the engine's architecture to help you create a business folder.

## Step 1: Install the tools

On macOS with Homebrew:

```bash
brew install pipx
pipx ensurepath
pipx install mainbranch
```

On Debian or Ubuntu, install pipx with `apt install pipx`. On Fedora, use
`dnf install pipx`. Then run:

```bash
pipx ensurepath
pipx install mainbranch
```

Open a new terminal if `mb` is not found. Check the installation:

```bash
mb --version
```

Install and sign in to Claude Code or Codex CLI before the first session.
Main Branch prepares its own runtime guidance during onboarding; it does not
provide the runtime or its subscription.

GitHub is recommended, and it does not need to cost anything. Main Branch can
start locally, but with GitHub the business brain has cloud backup and readable
saved history, and AI tools with GitHub connectors can read the business brain.
If you want GitHub backup, install GitHub CLI and confirm the account before
creating a remote business folder:

```bash
gh auth status
gh api user --jq .login
```

Use `gh auth login` to sign in or `gh auth switch` to change accounts.

## Step 2: Create your business folder

For local setup:

```bash
mb onboard --name "My Business" --path my-business
cd my-business
mb doctor
```

These names are examples. Choose your own business name and folder path.
Onboarding creates or connects the folder, prepares supported runtime guidance,
and shows the next action. Review any existing-folder changes before approving.

If you choose a private GitHub backup, use your account and repository name in
place of the example below. This command can create a remote repository and
push the initial history:

```bash
mb onboard --name "My Business" --path my-business --github your-gh-username/my-business --github-visibility private --push
```

Keep the folder local if you prefer. A local folder is not a remote backup.

The folder includes `core/` for your offer, audience, voice, and other business
context. Research, decisions, bets, coordinated work in `pushes/`, and lessons
have their own places. `.mb/` holds explicit Main Branch operational state.
Secrets and raw sensitive records stay outside tracked business files.

One folder usually fits products that share brand, team, voice, and access.
Separate entities or access boundaries may need separate folders. See
[repo topology](system-architecture.md#repo-topology) when that question arises.

## Step 3: Start the first session

Open the business folder in your runtime.

In Claude Code, run:

```text
/mb-start
```

In Codex CLI, ask:

```text
Use the global mb-start skill for this business folder.
```

The start route reads current Main Branch facts before advising. It can find
unfinished setup and route you to the next step. Ask the agent to read your
business files before proposing work.

Claude Code supports the bundled production workflows within their limits.
Codex supports the daily loop, including think and close. Its bet, ads,
organic, site, and books routes remain read-only planning. Wiki and
skill-authoring workflows are outside current Codex support. See
[compatibility](compatibility.md), or inspect exact route status with
`mb workflow list --runtime codex --json`.

### Get your first useful result

Ask the agent:

> Read my offer, audience, and voice drafts. Show me one unclear promise and
> propose a clearer version. Explain what supports it and what you still need
> to ask me. Wait for my approval before writing.

Correct assumptions and approve the changes you want. Then ask for a checkpoint
preview. Review the files it includes and approve the save separately.

You have a useful first result when you can read an accepted offer draft and
name one next business task. Missing optional account connections can wait.
Unresolved health findings should be named, with an explanation of whether they
block your next task.

## After setup

Open the same business folder each day. Use `mb-start`, describe one question,
review the proposal, and approve the work you want. Use `mb-end` when you want
to close the session and keep the lesson.

A checkpoint is an approved saved point in the business history. Writing files,
saving a local checkpoint, and syncing to GitHub are distinct
actions. Ask the agent to show what each action includes. The next session
reads saved business files; it does not need the previous chat to remember an
accepted decision.

Follow [a working day](working-day.md) for a fictional example of this sequence.
The [operating loops](operator-loops.md) explain the method behind it.

## Connected tools

Connect an account when a task needs it. You do not need every integration to
start working with your offer and audience files.

| Task | Reference and boundary |
| --- | --- |
| Run commands with stored credentials | [Connections](connect.md). Use `mb connect exec`; keep secret values out of prompts and saved files. |
| Read search or analytics data | [Google](google.md). Search Console and GA4 reads need setup; broader Workspace ingestion remains planned. |
| Review bookkeeping readiness | [Books](books.md). Keep raw ledgers private; sample monthly reports use fake data. |
| Check paid-traffic measurement | `mb site check`. Readiness checks do not authorize tag publishing or ad spend. |
| Inspect Meta Ads context | `mb ads meta summary`. Read-only account context after setup. |

Publishing, spending, customer contact, and account changes require your
explicit approval and a tested execution path. A connection alone grants no
such authority. Social content drafts do not imply automatic posting.

## Updating Main Branch

In Claude Code, use `/mb-update`. In Codex, ask for the global `mb-update`
skill. You can also run this inside your business folder:

```bash
mb update --repo .
```

Main Branch updates change the engine and skills. They do not rewrite your
business files without an approved repair, migration, or edit.

The update path detects your install mode. If an early install cannot update
itself, use `pipx upgrade mainbranch`.

Restart the runtime or open a fresh thread after updating so it loads refreshed
skills. Claude Code plugin users also need to refresh plugin wiring as described
in [compatibility](compatibility.md#updating).

## Already using the old setup?

Read [migration](migrating.md) before moving old folders or repairing old skill
links. Ask the agent to run read-only checks and show a plan before applying
changes. `.mb-vip/` and `reference/core/` belong to older layouts; they are not
required for a new folder.

## Common issues

If `mb` is missing, run `pipx ensurepath`, reopen the terminal, and try
`mb --version`.

If a start skill is missing, ask the agent to inspect runtime wiring from the
business folder. A repair preview is read-only:

```bash
mb doctor repair --plan
```

Review the plan before applying it. For Claude Code plugin diagnostics, use
`/mainbranch:mb-start`. The friendly `/mb-start` command uses the project-local
bridge. [Compatibility](compatibility.md) describes plugin and global-skill
setup. Start a fresh runtime session after repairs that change loaded skills.

If advice sounds generic, ask which business files and observations support
it. Correct the offer, audience, or evidence before accepting the recommendation.

For unfinished onboarding, ask `mb-start` to resume setup. The
[onboarding progress reference](onboarding-progress.md) describes the saved
progress facts for agents and tool authors.

## Help

Ask for `mb-help` in your runtime or describe the problem in plain language.
See [support](../SUPPORT.md) for reporting options and
[the docs index](README.md) for task references. Review logs and screenshots
for private business details before sharing them.
