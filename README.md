<p align="center">
  <img src="docs/assets/main-branch-logo.png" alt="Main Branch logo" width="100" />
</p>

# Main Branch

Run your business with an AI agent that reads your business files before it
advises you, then saves the work you approve for the next session.

Main Branch keeps your offers, audience, research, decisions, bets, and lessons
in a folder you own. Claude Code or Codex helps you work with those files.
The `mb` command checks the folder, reports current facts, and saves readable
checkpoints in git history.

[Set up your business folder](docs/beginner-setup.md) ·
[Follow a working day](docs/working-day.md) ·
[Browse the docs](docs/README.md) ·
[Check runtime support](docs/compatibility.md)

## What you can do

Start with a question about your business. For example:

> People keep asking what my service includes. Read my offer and audience
> files, show me what is unclear, and propose one change before writing.

The agent reads your files and Main Branch's health and status facts. It
compares options, explains the evidence and uncertainty, and proposes work.
You choose what to accept. Approved decisions and lessons become files that
future sessions can read.

Use this loop to clarify an offer, turn research into a decision, plan a bet,
draft content, review a page, or save a lesson from completed work. The
[working-day walkthrough](docs/working-day.md) shows a fictional example from
first question to the next morning.

Claude Code supports the bundled production workflows within each workflow's
limits. Codex supports the daily start, status, setup, think, repair, update,
help, and close routes. Its bet, ads, organic, site, and books routes remain
read-only planning. Wiki and skill-authoring workflows are outside current
Codex support. Check [compatibility](docs/compatibility.md) or run
`mb workflow list --runtime codex --json` for exact route status.

## Get started

You need Python, git, and Claude Code or Codex CLI. The
[setup guide](docs/beginner-setup.md) covers tool installation and guided setup.
If those tools and pipx are already installed:

```bash
pipx install mainbranch
mb onboard --name "My Business" --path my-business
cd my-business
mb doctor
```

"My Business" and `my-business` are example names. Choose your own.
Keep this business folder separate from a clone of the Main Branch engine.

Open the business folder in Claude Code and run `/mb-start`. In Codex CLI,
ask it to use the global `mb-start` skill. Tell the agent what you want help
with. Main Branch prepares runtime guidance during onboarding. If a skill is
missing, follow the [setup repair steps](docs/beginner-setup.md#common-issues).

For guided setup, paste the [setup prompt](docs/beginner-setup.md#setup-with-an-agent)
into your runtime. It asks about your business and proposes the first files
for your review. Local-only setup is valid. GitHub backup is recommended and
requires a signed-in account and your approval.

## Work with it each day

1. Open your business folder. Use `/mb-start` in Claude Code or the global
   `mb-start` skill in Codex to read current facts.
2. Describe the question or work. Ask the agent to cite the files and
   observations behind its recommendation.
3. Choose the next move. Review proposed file changes and approve the work
   you want it to do.
4. Ask for a checkpoint preview, then approve the save. A checkpoint records
   accepted files in local history. Syncing that history to GitHub is separate.
5. Use `/mb-end`, or the global `mb-end` skill in Codex, to review what changed,
   what you learned, and what remains open.

The [four operating loops](docs/operator-loops.md) describe this method as
Sense, Decide, Ship, and Reflect. You can use them within one short session.
You do not need a separate agent or document for every step.

## Your files and authority

Your business memory stays in plain Markdown and git history. You can read it
in a text editor without Main Branch. Credentials, caches, and raw sensitive
data have separate storage boundaries.

The agent proposes and explains work within the authority you give it.
Publishing, spending, customer contact, and account changes require explicit
approval and a tested execution path. Installing Main Branch does not authorize
those actions.

`mb` runs checks and commands when called. It does not host a model or keep an
agent running in the background. The local read-only dashboard is a view over
your files, not a hosted business database.

## Supported setups

| Setup | Scope |
| --- | --- |
| macOS and Linux | Supported CLI paths. Install your agent runtime separately. |
| Claude Code | Bundled skills with plugin wiring and project-local command bridges. |
| Codex CLI | Global Main Branch skills and generated repo guidance for the daily loop, with the workflow limits above. |
| Native Windows | Experimental. WSL2 is the closest path to the supported Linux setup. |
| Other agent runtimes | Compatibility targets until an adapter and smoke evidence exist. |

See [compatibility](docs/compatibility.md) for the full contract. Updates,
older layouts, and repairs are covered in [setup](docs/beginner-setup.md#updating-main-branch)
and [migration](docs/migrating.md).

## For contributors and power users

The agent normally runs `mb` for you. These commands let you inspect its facts
and proposals directly:

| Need | Command |
| --- | --- |
| Read the daily briefing | `mb status` |
| Read usage and weekly role caps | `mb usage` |
| Check folder and runtime health | `mb doctor` |
| Preview repairs | `mb doctor repair --plan` |
| Check business files and relationships | `mb validate` |
| Inspect the relationship graph | `mb graph` |
| Preview a saved checkpoint | `mb checkpoint --plan --json` |
| Inspect workflow support | `mb workflow list` |
| Inspect connected-tool readiness | `mb connect status --json` |
| View the local dashboard | `mb dashboard build` |

Run `mb --help` for the command list. See the [docs index](docs/README.md) for
Google reads, books, provider connections, playbooks, and other references.

Main Branch also carries read-only `mb-homelab-*` skills for securing the
machines that run your agents; they do not touch business data. See
[homelab skills](docs/homelab-skills.md).

New contributors should read [CONTRIBUTING.md](CONTRIBUTING.md). Agents working
on the engine follow [AGENTS.md](AGENTS.md) and the
[cold-start contract](docs/agent-cold-start.md).

## Help and community

Ask for `mb-help` in your runtime, read [support](SUPPORT.md), or report a
public-safe problem through [GitHub Issues](https://github.com/dmthepm/mainbranch/issues).
Review an issue draft before submitting business context.

The optional [Skool community](https://skool.com/main) follows businesses using
Main Branch. Membership is not required to use the open-source tool.

## License

[MIT](LICENSE) (c) 2026 Noontide
