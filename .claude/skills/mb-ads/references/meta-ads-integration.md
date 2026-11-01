# Meta Ads Account Access

Meta ad account awareness is additive. `/mb-ads` and `/mb-think` should use
live account context only after deterministic `mb` provider facts say the Meta
path is ready and the current runtime exposes verified read-only account tools.

Main Branch no longer supports third-party Meta MCP setup or detection as a
fallback. The official Meta Ads CLI is real and installable, and `mb connect
meta` owns setup guidance, safe token capture, and read-only smoke. Until `mb`
reports Meta as `ready`, skills must work from repo reference files and manual
Ads Manager input.

---

## Current Support State

Meta Ads AI Connectors has two surfaces:

- **Meta Ads CLI**: local Python package `meta-ads`, binary `meta`. This is the
  Main Branch target because Claude Code-first workflows can call Bash.
- **Meta-hosted MCP**: remote server at `https://mcp.facebook.com/ads` for
  supported chat clients. Treat it as forward-looking for Claude Code until the
  OAuth handshake is proven there.

Meta's package metadata classified `meta-ads` 1.0.1 as Alpha and requires
Python 3.12+. A dogfood business ran 1.2.0 (Graph v24.0) in September 2026.
Expect setup and command details to keep moving; what Meta did to real objects
is recorded in [meta-api-behaviours.md](meta-api-behaviours.md).

Main Branch support level is read-only readiness: the official path and setup
requirements are known, and `mb connect test meta` can validate local token,
metadata, auth, and read-only account smoke. Therefore:

- do not tell users Meta account access is ready unless `mb` says it is `ready`;
- do not ask users to configure third-party Meta connector fallbacks;
- do not ask users to paste Meta tokens into chat or repo files;
- do not run live campaign mutations from this skill.

Official docs:

- https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli/
- https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/setup/get-started
- https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/command-reference

---

## Official CLI Setup Facts

The setup path follows Meta's CLI docs:

1. Install the package as `meta-ads`; the binary is `meta`.
2. Use a Meta Developer App and a system user access token for the CLI path.
3. Use `mb connect meta --token-stdin --metadata ad_account_id=<act_id>` so
   `ACCESS_TOKEN` lands in `SecretStore` and only safe metadata lands in
   `.mb/connect.yaml`.
4. Verify with `mb connect test meta --json`.

The CLI uses this precedence: CLI flag, environment variable, project `.env`,
then user-level `~/.config/meta/`.

For user setup, prefer an isolated tool install when available:

```bash
pipx install meta-ads
meta --version
meta auth status
```

If the user's default Python is too old, quote the Python 3.12+ repair command
from `mb connect plan` or `mb connect doctor --json`. Do not recommend `meta auth login`,
`meta-ads-cli`, `npm install -g @meta/ads-cli`, or `mcp.meta.com/ads`.

Meta's documented baseline token scopes are:

- `business_management`
- `ads_management`
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_ads`
- `catalog_management`
- `read_insights`

Some Business Manager configurations require a second admin to approve system
user token generation. Surface that as conditional repair copy, not a universal
rule.

When the user is in Meta's business info page, the UI label "Business portfolio
ID" is the optional `business_id` metadata value. The ad account metadata should
be the `act_` ad account ID.

---

## Provider Facts

Provider metadata and repair state come from the CLI:

```bash
mb status --json --peek
mb connect plan
mb connect doctor --json
```

Use the CLI's `summary`, `next_command`, and `repair_command` fields. Do not
write provider readiness into business-repo config from this skill.

If `mb connect` reports Meta as anything other than `ready`, mention the account
context once, quote the repair or setup command, and continue from reference
files.

---

## Readiness Flow

Triggered lazily at `/mb-think` or `/mb-ads` when the topic is ads-related:

```
1. Read `mb status --json --peek`.
2. If the operator needs setup choices, run `mb connect plan`.
3. If provider facts are degraded, missing, invalid, waiting for admin approval,
   or otherwise not `ready`, run
   `mb connect doctor --json` and quote the repair/setup guidance.
4. Only if `mb` reports Meta account context `ready`, ask whether to pull a
   compact read-only account summary before generating.
5. Never block generation on missing account access.
```

---

## First Account Summary Surface

The first product surface is a compact read-only account summary, not a raw
reporting import:

```bash
mb ads meta summary --repo <BUSINESS_REPO> --window 7d --json
```

Use `mb connect` for setup, credential storage, readiness, repair, and smoke
tests. Use the future `mb ads` family for paid-channel read-only summaries and
any later approval-gated account work.

Before calling a live summary, ask:

```text
Meta appears connected for read-only checks. Do you want me to pull a compact account summary before making recommendations?
```

If approved, say:

```text
I'll pull a read-only summary and avoid saving raw account data.
```

The summary should default to account readiness, safe label, currency/timezone,
active campaign count, recent spend presence or bounded total, broad direction,
dataset/pixel readiness, creative counts or naming patterns when safe, findings,
and next actions. Campaign names require current-run approval.

Do not save raw provider payloads, account IDs, business IDs, full campaign
dumps, performance caches, or private paths into tracked files.

## Account Context Uses

When read-only account context is verified, use it for these workflows:

| Workflow | Purpose |
|----------|---------|
| Account overview | See readiness, active campaign count, current spend context, and broad direction |
| Creative audit | Find winning angles, hooks, offers, formats, and naming conventions |
| Performance check | Compare recent CPA, ROAS, spend, and volume trends |
| Performance iteration | Generate variants that build on known winners |
| Pixel/event survey | Inspect datasets/pixels and conversion-source readiness |

Keep account data in conversation context only. Do not write raw account
exports, customer data, tokens, account IDs, or sensitive performance details
into public files.

---

## Graceful Degradation

Ad account context is optional. The entire `/mb-ads` skill works without it.

| With Account Context | Without Account Context |
|----------------------|-------------------------|
| Ask whether to pull a compact read-only account summary before generating | Skip to generation |
| Use winning patterns before generating | Generate from reference files |
| Match account naming conventions | Ask the operator for naming conventions if needed |
| Suggest where new creative fits | Operator decides placement in Ads Manager |

If live account access is missing, mention the option once per session and move
on. Use this framing:

> "I do not have live Meta account context yet. I can still work from your repo, exported screenshots, or manual Ads Manager notes."

---

## Mutation Boundary

Read-only account context may inform recommendations. It does not authorize
campaign changes.

Before any future write operation exists, Main Branch needs:

1. a `pushes/<push>/playbooks/<playbook>.md` plan with preview, approval
   state, safe provider state, validation evidence, and outcome links;
2. explicit preview of every account change;
3. explicit operator approval in chat;
4. PAUSED-by-default campaign/ad/ad-set creation preserved;
5. no budget changes without a separate approval gate.

Until those conditions are met, write operations are roadmap only. The rails
any future write adapter must keep, and the read-back checklist, are in
[meta-api-behaviours.md](meta-api-behaviours.md#adapter-rails). The operating
loop around a build is [meta-pack-loop.md](meta-pack-loop.md).

---

## CLI Sharp Edges

Preserve these constraints in setup and repair copy:

- `meta auth status` is the documented auth check. There is no documented
  `meta auth login`.
- Global output flags belong before the subcommand: use `meta -o json ads ...`.
- Campaign and ad set creation default to PAUSED. Activation remains a separate
  operator action.
- The raw `--bodies` / `--images` creative form builds a dynamic creative, and
  `standard_enhancements` is refused; see
  [meta-api-behaviours.md](meta-api-behaviours.md).
- Creating fresh creatives can require the Meta Developer App to be in Live
  Mode; document this because the CLI docs do not surface it clearly.
- Store tokens through `SecretStore`; keep only safe metadata and validation
  summaries in `.mb/connect.yaml`.
- If the operator hits a two-admin token approval gate, explain that it depends
  on the Business Manager's security configuration.

---

## Proactive Suggestions

When account context is verified, suggest it once per context at natural moments: before generating new creative (the pull question above), after a batch ("Want to compare this against what's currently live before you upload it?"), in `/mb-think` with an ad topic, and on Monday reviews. The user can decline; frame it as optional account context and fall back to reference files or manual Ads Manager notes.

---

## See Also

- [entry-points.md](entry-points.md) - how account access composes with other entry points
- [post-generation-pipeline.md](post-generation-pipeline.md) - where account awareness fits in post-generation review
- `/mb-think` SKILL.md - ad-account research routing
