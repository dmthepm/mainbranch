# Main Branch System Model

Main Branch is the system of record for businesses run with AI agents. Agents
run the work. You keep the business record and the keys. Session logs show what
an agent did; the business record shows what you decided. `mb` starts and
checks the agents you define. It hosts no model and schedules nothing.

Main Branch has three user-visible pieces:

- **Your business folder** -- the business record Claude reads and writes:
  offer, audience, voice, proof, team context, research,
  decisions, bets, pushes, logs, and outcomes.
- **The `mb` CLI** -- the deterministic control plane. It checks setup,
  status, validation, graph links, provider readiness, updates, repairs, and
  checkpoints.
- **The skills** -- the judgment layer Claude uses for routing, writing,
  review, and explanation.

Normal operators should not need to think in terms of a package or source
checkout. They open the business folder, start Claude Code, and run
`/mb-start`. The CLI and skills do the setup and repair work underneath.

---

## How The Pieces Work

```text
business folder
├── core/                 # offer, audience, voice, proof, team, strategy
├── research/             # source notes and investigations
├── decisions/            # choices the business made
├── bets/                 # time-boxed operating hypotheses
├── pushes/               # coordinated shipping work
├── log/                  # what happened
├── .mb/                  # local Main Branch state
└── .claude/skills/mb-*   # Claude Code skill discovery links
```

`mb onboard` or `/mb-setup` creates and repairs this wiring. `mb update` keeps
the installed Main Branch package and skill links current. `/mb-start` reads
the folder through CLI facts before routing the operator into a workflow.

---

## Where Files Live

| Content | Location | Why |
|---|---|---|
| Offer, audience, voice, proof | Business folder | Business-specific durable truth |
| Research, decisions, bets, pushes, logs | Business folder | Operating memory the next session can read |
| Local setup state | `.mb/` | Repairable machine-local state |
| Claude Code skill links | `.claude/skills/mb-*` | Runtime discovery |
| Main Branch implementation | Installed package or source checkout | Shared software, not the business record |

If the operator asks where to edit, point them to the business folder. If they
ask how to repair, route to `/mb-start`, `/mb-setup`, `/mb-update`, or the
underlying `mb` command named by status or doctor output.

For old clone-era installs, stale skill links, or old repo layouts, use
`docs/migrating.md` as the source of truth. Normal help should teach the
current business-folder, CLI, and skills model. Migration is readiness work:
current skills depend on `mb` CLI facts, so old wiring and reported repair
errors should be fixed before serious skill use.
