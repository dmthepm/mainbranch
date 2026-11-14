---
type: educational
topic: cli-vs-dashboard
status: draft
last-updated: 2026-05-08
---

# CLI vs. dashboard: why Main Branch starts with `mb`

`mb` is a command-line tool because Main Branch needs a deterministic control
plane before it needs a prettier screen.

That does not mean the product is "for developers only." It means the setup,
status, repair, validation, graph, provider, update, and checkpoint facts should
be scriptable and inspectable before any dashboard becomes a view over them.

## The beginner version

The terminal is just the place where you run exact commands.

For normal setup:

```bash
mb onboard --name "My Business" --path my-business
cd my-business
claude
/mb-start
```

For the daily loop:

```bash
cd /path/to/my-business
claude
/mb-start
```

You do not need to memorize hidden repair commands. `mb` and the skills should
tell you the next exact command when something needs attention.

## Why not start with a SaaS dashboard?

**Dashboards can hide the source of truth.** If a dashboard becomes the place
where the business record lives, the repo becomes a stale export. Main Branch wants
the opposite: the repo is truth, and dashboards are views.

**Commands are testable.** `mb status --json --peek` either reports the facts or
it does not. Agents, scripts, tests, and future dashboards can all read the same
contract.

**Repair needs exactness.** When a repo needs migration, skill relinking,
provider readiness, or validation, a vague UI message is not enough. The user
needs to know what broke, why it matters, and which command fixes the next
step.

**Power users and beginners share one rail.** Beginners get guided copy and
numbered choices. Power users get quiet commands and JSON output. The control
plane stays the same.

## Where dashboards fit

Main Branch has a local, read-only dashboard today: `mb dashboard build` writes
an HTML file and `mb dashboard open` shows it. A richer or hosted dashboard is
future work. Any dashboard should show existing truth:

- repo health from `mb status`;
- graph relationships from `mb graph`;
- provider readiness from `mb connect`;
- tasks and proposals from GitHub;
- saved checkpoints from git history;
- business files from the repo.

It should not become a second database that the files have to chase.

## What Main Branch does not claim

Main Branch does not ship a hosted SaaS dashboard today. Any richer dashboard
must stay optional, local-first or self-hostable, and honest about which files,
GitHub threads, commits, and provider facts it is reading.
