# mainbranch (`mb`)

Engine umbrella for [Main Branch](https://github.com/dmthepm/mainbranch) — scaffolds, validates, and graphs business-as-files repos.

This package is the Python entry point. Workflows, playbooks, educational
content, and consumer-repo templates ship as bundled package data. Today, the
day-to-day "do work" surfaces are Claude Code skills and global Codex `mb-*`
skills grounded in the same deterministic `mb` facts. The `mb` CLI stays
runtime-agnostic by design so future adapters can operate against the same
business-as-files repo.

The source tree keeps the engine payload in one place: repo-root `.claude/`. During sdist/wheel builds, `setup.py` copies that tree into `mb/_engine/.claude/` inside the build artifact so installed wheels can resolve skills, playbooks, reference materials, lenses, and educational prompts without a source checkout.

## Install

```bash
pipx install mainbranch
```

That puts `mb` on your PATH. Verify:

```bash
mb --version
```

## Subcommands

| Command | What it does |
|---|---|
| `mb onboard` | Human setup flow. Creates or connects a business repo, explains the local files/git/GitHub model, wires Claude Code and Codex guidance, verifies discovery, and prints the next start step. Supports `--yes` and `--json` for smoke tests. |
| `mb init` | Scaffold a new business repo (business folders, CLAUDE.md, AGENTS.md, CODEOWNERS, `git init`) and wire bundled runtime guidance. One question only: business name. |
| `mb doctor` | Diagnostic. Checks Claude Code, gh auth, network, librsvg, runtime wiring, and package freshness. Warns on cloud-backed finance paths and offers educational triage. |
| `mb status` | Daily briefing. Summarizes repo shape, install/runtime readiness, recent brain files, recent git activity, and GitHub tasks/proposals when `gh` is authenticated. Supports `--json`. |
| `mb start` | Runtime handoff. Verifies the current business repo, git, Claude Code, Codex guidance, and start-skill wiring, then prints the exact next step. Supports `--json`. |
| `mb validate` | Frontmatter shape check across current business repo folders, with compatibility reads for old migrated surfaces where needed. Exit 1 on any fail. |
| `mb graph` | Walk linked_research / linked_decisions / supersedes; emit Graphviz DOT to stdout. `--open` shells to `dot` + `open`. |
| `mb similar-bets` | Find similar past bets and offer outcomes from repo truth. |
| `mb checkpoint` | Plan or save a business-readable git checkpoint. |
| `mb update` | Refresh the Main Branch engine according to install mode and repair skill links. `pipx` and clone installs upgrade automatically; a `uv` tool install upgrades only after an explicit yes; any other wheel install gets the upgrade command printed. `--check` dry-runs; `--json` emits an envelope. |
| `mb pulse install` | Install an operator-owned daily pulse wrapper. |
| `mb leads grade` | Grade lead batches and calculate eligible-lead CPL beside raw CPL. |
| `mb ledger init` | Create the what's-working creative ledger structure. |
| `mb automation init` | Create an inspectable steered-loop automation contract. |
| `mb production plan` | Inspect launch/production readiness without mutating providers or repos. |
| `mb migrate` | Inspect and apply numbered repo schema migrations. `status`, `--check`, and `--apply` support `--json`; `--check` prints privacy-safe summaries by default, with full diffs behind `--diff`. |
| `mb connect` | Connect provider credentials without committing secrets, test provider health, inspect hygiene/identity, and report repair-safe integration status. |
| `mb site` | Inspect site readiness for launch-adjacent workflows. |
| `mb issue` | Draft and open privacy-safe GitHub issues from local friction. |
| `mb think <topic>` | Print the /mb-think workflow invocation hint for the currently supported runtime. |
| `mb resolve <key>` | Resolve a reference key from the curated library, local core files, or bundled stubs. |
| `mb skill path <name>` | Print the on-disk path to a bundled skill. |
| `mb skill validate <name>` | Validate bundled skill frontmatter, local references, and line-count gates. |
| `mb skill link --repo <path>` | Wire or repair Claude Code skill discovery for a business repo. Future runtime adapters should get equivalent wiring commands. |
| `mb skill repair --repo <path>` | Detect personal Claude Code skills that shadow Main Branch and safely back up stale Main Branch symlinks with `--apply`. |
| `mb educational <topic>` | Print an educational triage file. Powers `mb doctor`'s "tell me more" prompts. |

Users on early `0.1.x` installs must bootstrap once with
`pipx upgrade mainbranch` before `mb update` exists locally. Existing business
repos should run `mb skill link --repo .`, then `mb skill repair --repo .` after
upgrading.

If you installed Main Branch as a Claude Code plugin, package updates do not
change the plugin that Claude Code has already loaded. After updating, re-add the
Main Branch plugin (`claude plugin marketplace add dmthepm/mainbranch`) and
restart Claude Code.

## Status

Main Branch is **Claude Code first** with supported Codex CLI guidance through
generated `AGENTS.md` and global `mb-*` skills. `mb onboard`, `mb status`,
`mb start`, and `mb update` are public package surfaces. Cursor, OpenClaw,
Hermes, and local runtimes remain roadmap work. The schema is v1 and will
evolve. The runtime boundary decision lives at
`decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md`; the engine master
decision lives at `decisions/2026-04-29-mb-vip-v0-1-0-master.md`.

## License

MIT.
