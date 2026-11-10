# Newer CLI surfaces — the business question each one answers

Operators never browse the CLI; they ask business questions and the agent
runs the right command. This map keys each newer surface to its question
and to the *moment* it should be offered. If an operator's question matches
a row, answer with the row — do not make them learn the command catalog.

| Business question | Surface | Offer it when |
| --- | --- | --- |
| "Where do my customers/leads actually live? Can my agent see them?" | `mb spine declare --store <provider>` records the position as a repo fact; `mb spine show` reads it back; `mb doctor` grades it (queryability, declared gaps, revisit trigger). | Any whose-data question, or when status/doctor shows no spine declaration. |
| "We deliberately keep no customer list — is that okay?" | `mb spine declare --store none --intentional` — a declared stance, not a gap. | Local-first / privacy-stance products. |
| "My platform can't answer X about my people." | `mb spine init --owned` scaffolds the owned contact+event schema (the *triggered* build path — declare first; see decisions/2026-06-12-spine-levels.md). | Only when a real unanswerable question exists — never as a default migration. |
| "How do I know my checkout/forms still work while I sleep?" | `mb canary init` scaffolds the golden-path smoke harness + alert doctrine (FAIL pages, WARN never). | The moment real money or real leads flow unattended. |
| "Give me a daily read on the business — what happened, what do I do today?" | `mb pulse init` scaffolds deterministic per-source collectors plus a repo-local pulse skill: scorecard, anomalies, exactly ONE recommended action, sub-60-line daily log. Read-only; it consumes `mb status` facts rather than re-ranking them. | When the operator wants a recurring morning picture — typically once real traffic, leads, or sends exist to report on. |
| "Run the daily pulse on a schedule, not by hand." | `mb pulse install` emits an operator-owned `run-pulse.sh` (assembles the collector JSON bundle for a date) and prints the exact cron line. It never enables a schedule for you — activation is yours. | After `mb pulse init`, once collectors are real and the operator wants the numbers ready each morning. |
| "We're taking real money now — is the repo protected?" | `mb production plan` reports the money-taking branch-protection gap (require PR, CI + canary as status checks, block force-push/deletion) and prints the exact `gh` apply commands. Read-only; applying is a provider mutation you run (`--solo` records a deliberate skip). | When an offer goes live / real money or leads start flowing. |
| "This ad set looks cheapest per lead — but are the leads real?" | `mb leads grade --file leads.json [--spend N]` grades each lead deterministically (plausible email, valid URL, owner/qualifying answer) and shows ELIGIBLE-lead CPL beside raw CPL, so budget calls use the honest metric. Read-only; no lead data stored. | Comparing lead sources / paid sets, or whenever raw CPL is about to drive a budget decision. |
| "Which of my ad creatives are actually working — keep or kill?" | `mb ledger init` scaffolds the what's-working creative ledger (one row per asset: spend, raw vs ELIGIBLE CPL, downstream event, KEEP/KILL/WATCH). An asset isn't working until it produces an eligible lead, not a cheap one; graduate to the owned spine past ~50 assets. | When verdicts on creatives start scattering across push logs and briefs. |
| "Turn this decision into a card I can send as an image." | `mb card render <spec.json> <out.jpg>` renders a title, numbered sections and lettered options to one JPEG under 2 MB; the tool enforces the layout rules. | When a decision or summary is going to a phone. |
| "I want an overnight agent loop, but I can't tell what it's doing." | `mb automation init` scaffolds the steered-loop contract (`core/operations/loop-state.md`): one inspectable file the loop reads first, appends to Shipped each run, and renders handoffs from. Unattended deterministic jobs pair with `mb pulse install`. | When you run (or want to run) an unattended/steered loop and need its state visible to anyone, not hand-written in someone's head. |
| "How do my scheduled tasks read credentials safely?" | `mb connect exec <provider> -- <command>` — the command gets the credential in its environment (default: the provider's own variable, e.g. `STRIPE_API_KEY`; `--env NAME` overrides); nothing is printed. `mb connect token <provider> --print > file` only when a script must capture the raw value. | Any cron/automation wiring. Never echo the value. |
| "Are any of my API keys sitting in plaintext where an agent could leak them?" | `mb connect hygiene` — read-only scan of `~/.claude.json` + project MCP/settings for plaintext credentials; reports surface, location, length-only mask, and a keychain/env remediation. Never prints the value. | After wiring MCP servers, before sharing a machine, or any credential-hygiene worry. |
| "What's deployed across all my sites, and is any behind or failing CI?" | `mb fleet refresh` reads GitHub and Cloudflare into a local snapshot; `mb fleet status [--json]` reads only that snapshot. Read-only; needs Python 3.11+. | Any question that spans more than one repo. |
| "What's my ad account / pixel / page / sender-domain id? (so agents don't guess from live state)" | `mb connect identity` — aggregates the recorded identity metadata across connected providers and names what's still unrecorded. Read it from facts; record gaps with `mb connect <provider> --metadata <field>=<value>`. Operator-facing (business identifiers — not safe to paste publicly). | Whenever an agent needs page/pixel/account identity; before any ads/email work that would otherwise infer it. |
| "My tool isn't in the provider list." | `mb connect <id> --custom` — operator-named provider on the same secure rails. | When `mb connect` says unknown provider. |
| "Did my key rotation actually take everywhere?" | Rotation sweeps sibling refs automatically and warns loudly about any it could not update. | After any credential rotation. |
| "An `mb` command refused me / confused me / was missing a check — where does that go?" | `mb feedback "<what happened>" --command "<mb command name>"` appends one line to a local file; nothing is sent. Write a credential-free summary in your own words and pass only the command name (for example `mb connect test`), never the arguments, tokens, keys, URLs with credentials or file paths you used. The scrubber is a backstop, not permission to paste. Credential and safety refusals log themselves (`MB_FEEDBACK_LOG=0` turns that off). `mb feedback rollup` drafts the week for a maintainer; reproducible bugs still go through `mb issue draft`. | The moment an agent is about to work around `mb` instead of using it. |
| "Validate just what I changed, not the whole repo's history." | `mb validate --paths <file-or-dir>` (repeatable). | Agents validating their own work in repos with legacy debt. |
| "Show me the business visually." | `mb dashboard build` / `mb dashboard open` — local, read-only, never committed. | "What's the state of things" moments. |
| "I changed my offer — did the ads/pages catch up?" | `core_propagation` drift in `mb status` flags identity files newer than active push records. | Automatic; explain it when it appears. |
| "We decided that weeks ago — did anything actually change?" | `uncodified_decisions` drift flags accepted decisions never codified; repair with `/mb-think codify`. | Automatic; explain it when it appears. |
| "What can my agents actually access?" | `core/operations/agent-access-dossier.md` (scaffolded at setup); `mb doctor` runs the safe rows of its verify column. | Access/capability questions; after connecting providers. |

Two rules when using this map:

- **Lead with the business answer, command second.** "Your customers live
  in your commerce platform; let's record that so every agent knows" — then
  the command.
- **Triggered surfaces stay triggered.** Never push `spine init --owned` or
  a canary on a business whose trigger hasn't fired; the doctrine pages say
  when (decisions/2026-06-12-spine-levels.md, the canary README it
  scaffolds, docs/delivery-truth.md, docs/traffic-reconciliation.md).
