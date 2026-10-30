---
name: mb-help
description: "Answer questions about Main Branch and Claude Code. Use when: user asks how/what/why questions, is confused about the business folder, CLI, skills, setup, errors, workflow, or what to do next."
loops: [sense, decide]
---

# Help

Answer questions, troubleshoot issues, explain philosophy, suggest next steps.

**CLI facts first:** For "what should I do?", setup, provider, skill wiring, or
troubleshooting questions, run `mb status --json --peek` and use `mb doctor`
for repair facts before giving prose-only advice.

---

## Workflow

1. **Triage** — Parse user's question/brain-dump
2. **Detect business type** — Check current business files (Skool? Ecommerce?). If CWD looks like an old Main Branch repo, treat it as migration input and run `mb status --json --peek` and/or `mb doctor repair --plan` before relying on it.
3. **Load reference** — Find topic in references/ table below
4. **Answer** — Explain "why" not just "what"
5. **Route** — End with next skill or action

---

## Topic Router

| Keywords | Reference |
|----------|-----------|
| Terminal, drag files, cd, business folder vs site folder | [terminal-basics.md](references/terminal-basics.md) |
| Business folder, CLI, skills, linked site folder, system model | [system-model.md](references/system-model.md) |
| Where should this go, real data, code repo, screenshots | `references/where-data-lives.md` in `/mb-setup` |
| Philosophy, why, compound, passive memory | [philosophy.md](references/philosophy.md) |
| /mb-think, research, decide, codify | [the-think-cycle.md](references/the-think-cycle.md) |
| /mb-bet, bet, hypothesis, deadline, public narration, bet vs offer | [skills-guide.md](references/skills-guide.md) |
| Work continuity, where left off, GitHub issues | [work-continuity.md](references/work-continuity.md) |
| Error, command not found, MCP, Apify setup, GitHub issue | [troubleshooting.md](references/troubleshooting.md) |
| Provider readiness, GitHub setup, Cloudflare, Google Workspace, Meta Ads, Apify | [provider-readiness.md](references/provider-readiness.md) |
| Getting started, setup | Route to `/mb-setup` or `/mb-start` |
| Which skill, when to use, list skills, what skills do I have, skills inventory, what can you do, which skills are we using | [skills-guide.md](references/skills-guide.md) |
| Pre-publish review, UI pass, design pass, design critique, review the page before publish | Route to `/mb-skill-review` (see [skills-guide.md](references/skills-guide.md)) |
| Create skill, Notion export, custom | [skills-guide.md](references/skills-guide.md) |
| Migrate from GPT, ChatGPT | [gpt-migration.md](references/gpt-migration.md) |
| Reels, TikTok, organic, /mb-organic | [organic-help.md](references/organic-help.md) |
| Skool, community | [skool-help.md](references/skool-help.md) |
| SEO, search rankings, keyword data, site audit, AI visibility, OpenSEO | Route to `/mb-seo` |
| Wiki, atomic notes, publish, WikiLinks | Route to `/mb-wiki` |
| Books, bookkeeping, monthly close, reconciliation, CPA handoff | Route to `/mb-books` after `mb books check` |
| Launch readiness, Cloudflare, Wrangler, Shopify, Resend, smoke test, form test, booking link | Route to `/mb-site`; run `mb launch check` before launch-readiness advice |
| Site, landing page, lander, minisite, website, about page video, deploy site, publish site, conversion endpoint, concept variations | Route to `/mb-site` (see [skills-guide.md](references/skills-guide.md) for the full one-flow walkthrough) |
| Done, wrapping up, closing, end session, end of day | Route to `/mb-end` |
| multi-offer, product ladder, offers, switch offer | Multi-Offer FAQ (below) |
| Better outputs, quality, what next | [making-outputs-better.md](references/making-outputs-better.md) |
| Content strategy, pillars, platforms, newsletter, channel strategy, account strategy, founder voice, weekly content plan | [content-strategy-help.md](references/content-strategy-help.md) |
| Subagents, parallel, agents, context window, tokens | [working-with-agents.md](references/working-with-agents.md) |
| workspace-isolated tools, sandboxed workspace, skills not showing | [workspace-setup.md](references/workspace-setup.md) |
| Contribute, contributor | [becoming-contributor.md](references/becoming-contributor.md) |

---

## Principles

- **Explain "why"** — Not just steps
- **End with action** — Suggest next skill (`/mb-think`, `/mb-setup`, `/mb-ads`, `/mb-site`, `/mb-organic`)
- **Beginner-friendly** — Many never used Terminal
- **Honest about gaps** — The system is new and evolving. Acknowledge what's still being built rather than presenting everything as polished.
- **Public issue safety** — Suggest `mb issue draft` for reproducible Main Branch friction, but never submit issues for the operator.

---

## Quick Answers

| Question | Answer |
|----------|--------|
| Is this a bet or an offer? | If you're testing whether a direction should continue, it is a bet in `bets/`. If it is something the business sells or may sell repeatedly, it is an offer. A live idea can be both: open the bet first, then create or update the offer only when the operator wants durable sellable truth. |
| Start Claude in a folder? | Open the business folder in Claude Code — either the **Claude Desktop app** or the **terminal** (`cd ~/Documents/GitHub/[your-business] && claude`). Claude reads the files in that folder; the Main Branch plugin makes `/mb-start` and the other skills available on both surfaces. |
| Why can't Claude find `/mb-start` (or any `/mb-` command)? | Main Branch ships as a Claude Code **plugin**. Install it once with `claude plugin marketplace add dmthepm/mainbranch`, then enable it. The plugin works in both the **Claude Desktop app** and the **terminal** `claude` CLI, and it survives git worktrees. Cloud/web Claude sessions can't load plugins — use Desktop or the terminal. If it is installed but skills still don't show, run `mb status --json --peek` and `mb doctor repair --plan` from the business repo, apply the approved repair, then restart Claude. |
| I see `.mb/`, not `.mb-vip/`. Is that wrong? | You're good. `.mb/` is the current repo-local Main Branch state folder. `.mb-vip/` was old clone-based setup language and is not required. If slash commands are missing, use `/mb-update` or run `mb update --repo .`, then repair skill links and restart Claude. |
| Do I start Claude in the business folder or site folder? | Start in the business folder for strategy, bets, decisions, offers, and routing. Switch to a linked site folder only for site implementation work. Linked site folders should have `.mainbranch/repo.json`; older site folders may still use `.mainbranch/source.json`. |
| When use skill prompts? | For structured tasks: `/mb-start`, `/mb-think`, `/mb-ads`, `/mb-site`, `/mb-organic` |
| Drag files in? | Drag from Finder into Terminal, path appears |
| Voice input? | [Wispr Flow](https://ref.wisprflow.ai/main) (affiliate link) |
| What is content-strategy.md? | The business-level content strategy and index: what you want to be known for, who content is for, pillars, content jobs, and what not to publish. Use `core/marketing/` and `core/people/` only when you need channel, account, or person-specific layers. |
| How do I build a content strategy? | Run `/mb-think`. Start with offer clarity, recognition target, audience, and 3-5 pillars in `core/content-strategy.md`. Add distribution, channel, account, and person files only when the simple file gets crowded. |
| How do pillars work? | Each pillar is a content theme that passes three tests: Soul test (connects to why), Offer test (leads to mechanism), Audience test (they care). 3-5 pillars cover your content universe. |
| What's the content pipeline? | Strategy first, then distribution. Owned assets, email, social, communities, wiki, changelog, and paid amplification should point at the same offer and recognition target. Specific execution lives in `pushes/`; results land in `log/`. |
| What are subagents? | Claude can spawn parallel agents to research or review simultaneously. You'll see it happen automatically in `/mb-think` (multi-source research) and `/mb-ads review` (6 compliance lenses). Each agent gets its own context window so your main conversation stays clean. |
| How do I manage context/tokens? | Context management is a skill that develops over time. Your files (`core/`, `research/`, `decisions/`) survive compaction — only conversation memory compresses. After compaction, help Claude rebuild by pointing it at recent files or running /mb-start. Save insights to research files early — if it's in a file, it's safe. |
| How do I just save my progress mid-session? | Say "save" or "checkpoint this" — the agent runs `mb checkpoint`, shows the planned save, and saves on your approval, then you keep working. No need to close the session. Saves always go through `mb checkpoint`, never raw git. |
| How do I close a session? | Run `/mb-end`. It summarizes what happened, asks if you have final thoughts, offers a crystallize moment if you made decisions, and guides an approved checkpoint instead of raw git commits. Bookend to `/mb-start`. A quick mid-work save is just `mb checkpoint` (above) — `/mb-end` is the full close. |
| What is multi-offer? | Multiple products under one brand, one business folder. Each offer gets its own `core/offers/[name]/offer.md`. Soul and voice stay in `core/` because they're brand-level. Use when you sell multiple things (community + newsletter + done-for-you). If you have no `core/offers/` folder, you're in single-offer mode — everything reads from `core/` and nothing changes. |
| How do I switch offers? | Say `/mb-start [offer-name]` or answer when /mb-start prompts. The choice is session-scoped unless you explicitly approve saving it as local active-offer state. |
| Where do offer files go? | In a single-offer repo, `core/offer.md` is the durable offer truth. In a multi-offer repo, `core/offer.md` is the portfolio thesis and `core/offers/[name]/offer.md` holds offer-specific details. Use current paths only; if CWD looks like an old Main Branch repo, run the repair/migration plan before relying on it. |
| What stays in core with multiple offers? | `soul.md` (always), `voice.md` (always), `audience.md` (base, with optional per-offer overrides), `content-strategy.md` (business-level content strategy), and optional `core/marketing/` / `core/people/` layers. |
| Where does proof go? | Company-wide testimonials go in `core/proof/testimonials.md`, average-case context in `core/proof/typicality.md`, and angles in `core/proof/angles/`. Offer-specific proof uses matching files under `core/offers/[name]/proof/`. Use structured permission and offer-link fields when proof should be detectable by `mb status`. |
| Can I delete or rename an old offer folder? | Ask first. Offer folders are durable business history. Rename, delete, merge, or move them only after an accepted decision, approved migration plan, or explicit operator instruction. |
| How do I add another offer? | Run `/mb-setup` -- it detects your existing setup and offers a migration path. Or use `/mb-think` to plan the new offer first. |
| Do I need separate folders for separate businesses? | If they share `soul.md` and `voice.md`, use one business folder with `offers/`. If they have different identities, use separate folders. The test: shared soul = shared folder. |
| Do my files disappear when context compacts? | No. Compaction compresses Claude's conversation memory, not your files. Everything in `core/`, `research/`, and `decisions/` is on your hard drive, version controlled with git. If it's in a file, it's permanent. |
| How do I recover after compaction? | Point Claude at recent files: "look at my last 3 decisions" or "read the commits from today." Or just run /mb-start — it scans your folders and rebuilds context automatically. You can also open files yourself in Cursor, Warp, VS Code, or any text editor. |
| Is this system finished? | Still new and actively being tuned. We're building around Claude Code, minimizing commands you need to learn while giving you real power. There's progressive discovery in /mb-think — the more you use it, the more it reveals. You might find workflows we haven't documented yet. Post them in Skool. |
| Where can I see my files? | Open your business repo folder in Finder, Cursor, Warp, VS Code, or any text editor. They're regular .md files on your hard drive. GitHub Desktop also shows them with version history. |
| Where do my customers/leads live? Can my agent see them? | Declare it once: `mb spine declare --store <provider>` records which system holds your people as a repo fact; `mb doctor` then grades it honestly. Full map of newer surfaces: [cli-surfaces.md](references/cli-surfaces.md). |
| How do I know my money path still works overnight? | `mb canary init` scaffolds a smoke harness + alert doctrine the moment real money or leads flow unattended. See [cli-surfaces.md](references/cli-surfaces.md). |
| How do I get a daily read on the business? | `mb pulse init` scaffolds deterministic collectors + a repo-local pulse skill that writes one short daily paper with exactly one recommended action; `mb pulse install` emits the daily run wrapper + cron line (you activate it). See [cli-surfaces.md](references/cli-surfaces.md). |
| We're taking real money — is my repo protected? | `mb production plan` reports the branch-protection gap (PR required, CI + canary gates, force-push/deletion blocked) and prints the exact `gh` apply commands; applying is yours to run. See [cli-surfaces.md](references/cli-surfaces.md). |
| This ad set is cheapest per lead — but are the leads real? | `mb leads grade --file leads.json --spend N` grades each lead (email, URL, owner answer) and shows ELIGIBLE-lead CPL beside raw CPL, so budget calls use the honest number. See [cli-surfaces.md](references/cli-surfaces.md). |
| Which ad creatives are working — keep or kill? | `mb ledger init` scaffolds the creative ledger (per-asset spend, raw vs eligible CPL, downstream event, KEEP/KILL/WATCH) — an asset isn't working until it makes an eligible lead. See [cli-surfaces.md](references/cli-surfaces.md). |
| Is my site ready to launch? | Use `/mb-site`; the agent runs `mb launch check` for app/deploy/commerce/email/smoke posture and `mb site check` for paid-traffic measurement detail. Publishing, spend, provider changes, and customer contact still need your explicit approval. |
| I run an overnight loop but can't see its state. | `mb automation init` scaffolds the steered-loop contract (`loop-state.md`): one inspectable file the loop reads first and updates each run; handoffs render from it. See [cli-surfaces.md](references/cli-surfaces.md). |
| How do scripts read credentials safely? | `mb connect exec <provider> -- <command>` runs the command with the credential in its environment only — built for scheduled tasks and agents, so the raw value is never retrieved into chat; the command itself must not print its environment. `mb connect token` refuses terminals and pipes with exit 3, before any provider lookup; `--print > file` is only for a script that must capture the raw value. Custom tools: `mb connect <id> --custom`. |
| macOS says a credential has a "keychain prompt pending"? | Run `mb connect repair --keychain` once from a terminal in that hub and choose Always Allow. It moves each credential to Apple's `security` tool, so later Python or `mb` updates stop asking; unattended runs never wait on the dialog. Never reset the login keychain. |
| Are any of my keys sitting in plaintext? | `mb connect hygiene` scans agent configs (`~/.claude.json`, project MCP/settings) for plaintext credentials and shows where to move each one (keychain/env). Read-only; never prints the value. |
| What's the state of all my sites across hubs? | `mb fleet refresh` then `mb fleet status`: one read-only row per site (framework, main's CI, deployed commit, last commit), plus a per-repo Dependabot table (alerts by severity, open PRs). Needs Python 3.11+. Detail: `docs/fleet.md` in the engine repo. |
| What's my ad account / pixel / page id? | `mb connect identity` reads the recorded identity facts across connected providers and names what's unrecorded — agents read identity from facts, never infer it from live state. |
| What should I connect first? | Run `mb connect plan` from your business repo. It shows GitHub, Cloudflare, Google/Workspace, Meta Ads, and Apify as numbered choices with readiness and exact next commands. |
| Skills not showing in a workspace-isolated tool? | Run `mb skill link --repo .` from the business repo when possible, then restart Claude. Some tools also support a pre-start script that creates bridge links and `settings.local.json`; see [workspace-setup.md](references/workspace-setup.md) for the generic pattern. |
| What's a pre-start script? | A workspace tool hook that runs before the agent starts. Use it to set up Main Branch bridge links only when `mb skill link --repo .` is not enough. |
