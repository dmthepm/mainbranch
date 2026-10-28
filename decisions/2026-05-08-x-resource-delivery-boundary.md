---
type: decision
date: 2026-05-08
status: accepted
topic: X resource delivery boundary
linked_decisions:
  - decisions/2026-05-01-mb-cli-vs-agent-workflows-boundary.md
  - decisions/2026-05-04-sidecar-enrichment-cli-contract.md
  - decisions/2026-05-07-growth-automation-playbook-addons.md
  - decisions/2026-05-07-postiz-scheduling-rail.md
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/351
participants: [Devon, Codex]
tags: [v0-3, integrations, social, provider-boundary, x, playbooks]
---

# X Resource Delivery Boundary

## Decision

Main Branch should not support X/Twitter interaction-triggered resource
delivery today. That includes comment-to-DM, auto-reply, keyword-triggered DM,
bulk DM, auto-like, auto-follow, follower-gated giveaway, and browser-automation
workflows.

Main Branch may support X as:

- a planning surface for public resource playbooks;
- a drafting surface for posts, threads, public CTAs, and reply/link copy;
- a future scheduling/publishing surface through Postiz, Typefully, or the
  official X API only after focused smoke evidence;
- a read-only Sense surface through official X API reads, Grok/xAI X Search,
  public web/manual exports, or carefully bounded optional sidecars.

The default Main Branch recommendation for X resource delivery is:

1. publish the useful resource or proof publicly;
2. use a public link, repo link, landing page, or explicit opt-in CTA;
3. keep fulfillment manual or provider-native until a tested adapter exists;
4. record the plan, approval state, provider boundary, and outcome under the
   relevant push or research artifact.

This is a refusal of X interaction-triggered execution, not a refusal of X as a
channel. Operators can still use X for build-in-public work, giveaway-in-post
experiments, public resource drops, public reply/link playbooks, and approved
scheduling.

## Strategy Classification

When a skill or playbook analyzes an X growth example, classify the pattern
before recommending action:

| Pattern | Main Branch stance | Notes |
|---|---|---|
| Full-value public post | Recommend | The post itself teaches, proves, or ships enough value to earn trust, saves, stars, follows, or profile visits. |
| Resource-in-post | Recommend | Link to a repo, landing page, document, or signup path directly in the post when the operator accepts the tradeoff. |
| Public reply/link playbook | Draft only today | Main Branch can draft reply copy and resource links, but execution is manual or provider-native until a smoke-tested write adapter exists. |
| Build-in-public | Recommend | Public process, metrics, decisions, and lessons create trust without inbox automation. |
| Build-cool-stuff-publicly | Recommend | Ship a useful artifact in public, then invite opt-in follow-up through a public link or repo. |
| Giveaway-in-post | Proceed carefully | Avoid follow/retweet gates and engagement manipulation. Prefer non-engagement entry paths and real delivered value. |
| Comment-to-resource | Draft/manual only | A keyword comment can express interest, but Main Branch should not automate reply or DM fulfillment. |
| Comment-to-DM or keyword DM | Refuse execution | X DM rules require clear prior intent to be contacted by DM, opt-out handling, and privacy care; Main Branch has no accepted adapter or smoke evidence. |
| Browser automation or scraper-driven mutation | Refuse | Non-API automation, session-token workflows, and browser scripting are not Main Branch product guidance. |

A concrete creator specimen can inform the research, but the durable artifact
should stay generic. Do not encode one creator's bookmarks, private strategy,
raw comments, or scraped funnel data as product doctrine.

## Provider Boundary

### Postiz

Postiz remains a candidate scheduling rail, not an X resource-delivery rail. Its
public docs describe an MCP endpoint for agent access and X as a posting
provider, which makes it plausible for scheduling/drafting smoke. It does not
make comment monitoring, DMs, auto-replies, auto-likes, or inbox workflows a
supported Main Branch surface.

### Typefully

Typefully is a plausible operator-facing drafting and scheduling tool. Its API
docs describe programmatic draft, schedule, publish, media, tags, and webhook
workflows across X and other platforms. Main Branch may mention Typefully as a
manual/provider-native scheduling option, but should not wrap it as a supported
adapter before smoke evidence and should not treat Typefully as a DM/resource
delivery provider.

### Official X API And XMCP

The official X API is the only acceptable future mutation path for X write
automation inside Main Branch, including posts, replies, and DMs. Even then,
Main Branch would need an accepted adapter, operator-visible approval gates,
OAuth/user authority, safe credential storage, rate-limit and billing handling,
tests, docs, and mutation smoke in a safe account.

The official XMCP server is promising because it exposes X API operations to
MCP clients and supports allow-listing. Until Main Branch has a tested adapter,
XMCP should be described as a candidate future provider surface, not support.

### Grok/xAI

Grok/xAI X Search can support Sense work when configured: topic sentiment,
current public post discovery, user/thread lookup, and cited synthesis. It
should not be treated as a complete dataset, compliance system, scheduler,
publisher, or resource-delivery provider.

### Apify And Scrapers

Apify and similar scraper actors may help bounded, read-only public research
when the operator deliberately chooses that sidecar and accepts the terms,
privacy, reliability, and cost tradeoffs. Main Branch should not describe Apify
as an official X integration, a guaranteed reply-tree source, a private inbox
source, or any kind of X write provider.

Do not ask users to paste X session cookies, bearer tokens, raw scrape dumps,
DMs, customer records, or private analytics into committed files or public
issue comments.

### X-Focused Growth Tools

Tools such as Hypefury, Tweet Hunter, browser-extension products, and X-focused
DM tools may offer auto-DM, giveaway, reply, or scheduling features. Their
existence is not Main Branch support. If an operator uses one directly, Main
Branch can draft the public-safe playbook and record the provider boundary, but
should not recommend high-volume inbox automation as a safe default.

## Policy And Product Rationale

Current X public docs support a narrow distinction:

- automated public posts can be acceptable when compliant, non-spammy, and
  authorized;
- automated replies and mentions are sensitive, especially when unsolicited or
  keyword-driven;
- automated DMs require clear prior user intent to be contacted by DM, easy
  opt-out, and privacy care;
- being able to technically send someone a DM does not mean they requested
  automated DMs;
- non-API automation, scraping, and browser automation are explicitly risky in
  X developer guidance;
- current X API access is pay-per-use, endpoint-priced, rate-limited, and
  requires developer-console cost monitoring.

That makes auto-DM and interaction-triggered delivery a poor default for Main
Branch. It mutates customer conversations, depends on shifting provider policy,
creates privacy and opt-out obligations, and needs operational state that the
engine does not yet own.

The safer product path is public proof plus explicit opt-in:

- put the resource in the post, thread, repo, or landing page;
- make the CTA visible and honest;
- use provider-native scheduling only after smoke evidence;
- record the push/playbook/outcome in files and git;
- open follow-up implementation issues only for accepted, testable provider
  surfaces.

## Skill Guidance

`/mb-think` should:

- classify the X strategy before recommending tactics;
- separate visible participation from substantive audience language;
- use Grok/xAI, official X API reads, public web, screenshots, manual exports,
  or bounded optional sidecars for Sense work when configured;
- codify the decision, research, or playbook in public-safe markdown.

`/mb-organic` should:

- draft full-value posts, build-in-public updates, resource-in-post CTAs, and
  public reply/link copy;
- label DM/comment-keyword CTAs as draft strategy only;
- avoid telling operators that Main Branch can execute X DMs, replies, follows,
  likes, or comment-triggered fulfillment.

Future playbook/schema work may model:

- `platform: x`;
- `delivery: public_link`, `resource_in_post`, `manual_reply`,
  `manual_dm`, or `provider_native`;
- `provider: manual`, `postiz`, `typefully`, `x-api`, or another accepted id;
- approval, opt-in, opt-out, smoke evidence, rate-limit notes, and retirement
  criteria.

Those schema names are design guidance, not shipped CLI behavior.

## Follow-Up Issues

Useful future slices:

- Postiz X scheduling smoke, already tracked by #352.
- Push playbook schema, already tracked by #350.
- Official X API/XMCP read-only proof: list allowed read tools, prove
  credentials stay outside the repo, and record cost/rate-limit behavior.
- Official X API/XMCP write proof, only if an operator-approved safe account
  and explicit mutation smoke criteria exist.

Do not open implementation for X auto-DM/comment-to-DM until a later decision
accepts the policy, privacy, provider, testing, and support burden explicitly.

## Sources

- X automation rules: https://help.x.com/en/rules-and-policies/x-automation
- X developer policy: https://docs.x.com/developer-terms/policy
- X developer guidelines: https://docs.x.com/developer-guidelines
- X API pricing: https://docs.x.com/x-api/getting-started/pricing
- X API usage and billing: https://docs.x.com/x-api/fundamentals/post-cap
- X API rate limits: https://docs.x.com/x-api/fundamentals/rate-limits
- X Direct Messages API: https://docs.x.com/x-api/direct-messages/manage/introduction
- X MCP servers: https://docs.x.com/tools/mcp
- Postiz providers: https://docs.postiz.com/providers/overview
- Postiz MCP introduction: https://docs.postiz.com/mcp/introduction
- Typefully API: https://support.typefully.com/en/articles/8718287-typefully-api
- xAI X Search: https://docs.x.ai/developers/tools/x-search
- Apify Actor terms: https://docs.apify.com/legal/actor-terms-and-conditions
