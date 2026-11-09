# Handoffs to OpenSEO's skills

Upstream owns each procedure. Names are as published in `plugins/openseo/skills/`
at the pinned release. Loose skills may appear under their own names; the hosted
plugin namespaces them as `/openseo:<name>`. Check which names this runtime shows,
and whether any collide, before telling the owner what to type.

The business repo is the record. OpenSEO project context is a working copy.
Read prior `research/` and `decisions/` findings before buying data again.

Every return is saved with: source, observation date, market, actual or unknown
cost, coverage, and uncertainty. Owner choices go to `decisions/`. Keep secrets and
raw exports out. A report link alone is not a record.

| Upstream skill | Before: Main Branch adds | After: Main Branch adds | Playbook |
|---|---|---|---|
| `seo-coach` | Current goal, owner capacity, unresolved decisions. | Pick the next useful action within that capacity, not a generic checklist. | [costs](playbooks/costs.md) |
| `seo-project-setup` | Fill context from business files; ask only for missing facts. Do not invent competitors or pay to find them without a yes. | Reconcile owner-confirmed facts into the repo; note which OpenSEO fields are working copies. | [project-context](playbooks/project-context.md), [search-console-insights](playbooks/search-console-insights.md) |
| `keyword-research` | Buyer, offer, market, exclusions, prior keyword gates, approved budget. | Reject high-volume terms that do not fit real buyers or the owner's voice. Save accepted and rejected terms with reasons. Offer choices go to the `/mb-think` keyword gate. Volume is an estimate. | [keyword-research](playbooks/keyword-research.md) |
| `keyword-clustering` | Offer boundaries, existing pages, approved keyword set. | Reject clusters needing duplicate pages or unsupported offers. Save page intent and ownership. | [keyword-research](playbooks/keyword-research.md) |
| `seo-audit` | Public review first; key selling pages, honest claims, affordable effort, allowed audit options. | Separate crawl failures from page faults. Prioritize fixes that help the business sell honestly. Route approved changes to `/mb-site`. Save findings even if an HTML report exists. | [site-audit](playbooks/site-audit.md), [rank-tracking](playbooks/rank-tracking.md) |
| `competitor-analysis` | Owner-confirmed competitors, geography, positioning, approved data spend. | Separate observed competition from inferred strategy. Keep differences consistent with the business's proof. | [domain-overview](playbooks/domain-overview.md) |
| `competitive-landscape` | Same as `competitor-analysis`. | Same. | [domain-overview](playbooks/domain-overview.md) |
| `link-prospecting` | Audience fit, reputation limits, outreach permission. | Reject irrelevant or dubious prospects. Save a shortlist. Research permission is not permission to contact. | [backlinks](playbooks/backlinks.md) |
| `ai-prompt-research` | Actual audience language, buying questions, paid-call limits. | Keep prompts tied to buying or service decisions. Save rejected assumptions. Do not buy the same research twice. | [prompt-research](playbooks/prompt-research.md) |
| `ai-visibility-audit` | Real buyer questions, relevant engines, named competitors, baseline, approved cost. Schedules need a separate yes. | Distinguish a sampled mention, a citation, a referral, and a sale. Reject guaranteed-visibility or causal claims. Save prompt, engine, date, and sample limits. | [ai-visibility-tracking](playbooks/ai-visibility-tracking.md) |
| `local-seo` | Verified location, service area, hours, real availability, permission to use business details. Local-data calls may spend. | Reject invented locations, reviews, and thin city pages. Save evidence and proposed changes for approval. | [local-seo](playbooks/local-seo.md) |
| `seo-report` | The owner's decision question, goal, prior actions, windows, source coverage, sharing permission. | Judge progress against the business goal. Label organic versus all-channel figures and missing data. Public sharing needs approval. | [reports](playbooks/reports.md) |

## Limits that sit above every handoff

- Playbooks hold the business layer, worked costs and what to save:
  [playbooks/](playbooks/). Two have no upstream skill:
  [indexnow](playbooks/indexnow.md) and [agent-setup](playbooks/agent-setup.md).
  Spend rules shared by all are in [costs](playbooks/costs.md).
- Spend, schedules, and owner-run steps: [daily-use.md](daily-use.md).
- A weekly Search Console review needs no OpenSEO: [search-review.md](search-review.md).
- Public AI-search checks and `llms.txt` stay here: [ai-agents.md](ai-agents.md).
