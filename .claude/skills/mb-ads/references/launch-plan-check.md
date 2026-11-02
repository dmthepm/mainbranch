# Launch Plan And Check Modes

Use this when the operator asks to launch/check paid traffic, especially Google
Ads traffic for a lander or minisite. For Google Ads campaign structure,
account-history, keyword, negative-list, policy-fit, and approval sequencing,
load [`google-ads-campaign-plan.md`](google-ads-campaign-plan.md).

This mode prepares a reviewable plan and checks recorded readiness. It does not
mutate Google Ads, GTM, Meta Ads, Stripe, or analytics providers unless a future
adapter ships with approval gates and smoke evidence.

## Launch-Plan Inputs

From the business repo:

- active offer and audience;
- offer-sharpening facts from
  `.claude/reference/conversion/offer-sharpening.md`, especially mechanism,
  proof, risk reversal, objections, reason to act, and next step;
- the launch push at `pushes/<push>/push.md`;
- keyword-gate research, especially ready-to-buy terms and negative seeds;
- site record or linked site repo;
- existing ad account/campaign exports or read-only Google Ads facts when the
  operator explicitly provides them, or when an approved runtime tool, sidecar,
  MCP server, or future `mb` adapter proves read-only access for this business;
- `docs/google-ads-gtm-conversion-rubric.md`;
- `mb status --json --peek`;
- `mb connect plan` or `mb connect doctor --json`;
- when a site repo exists:

```bash
mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json
```

## Readiness States

Use the returned `mb site check` state:

- `missing`: measurement setup has not been declared; draft strategy only and
  route setup through `/mb-site` or the measurement rubric before traffic.
- `blocked`: stop launch planning after listing blockers and next commands.
- `ready_for_preview`: draft ads only; operator still needs GTM Preview/Tag
  Assistant and provider metadata.
- `ready_for_operator_review`: prepare campaign materials and approval list.
- `ready`: local checks passed; still require explicit operator approval before
  provider mutation or spend.

Never say `ready_for_launch`.

## Output

Write a provider-safe plan under the launch push, for example:

```text
pushes/<YYYY-MM-DD-slug>/ads.md
```

Sections:

- `## Source Facts`
- `## Offer And Policy Fit`
- `## Existing Account/Campaign Decision`
- `## Readiness`
- `## Budget And Review Window`
- `## Market Intent Research`
- `## Core Updates From Research`
- `## Campaign Structure`
- `## Campaign Settings And Forks`
- `## Keyword Targets`
- `## Negative Strategy`
- `## RSA Assets`
- `## Sitelinks`
- `## Callouts`
- `## Structured Snippets`
- `## Skipped Assets And URL Options`
- `## Lander And Sitelinks`
- `## Measurement Checklist`
- `## Manual Provider Steps`
- `## Approval Gates`
- `## Review Loop`

If the work includes repeatable provider setup, resource delivery, or approval
state, draft a `type: playbook` file under `pushes/<push>/playbooks/` instead
of hiding the plan in prose. For a reusable Google Ads Search proof
run, route through the `playbooks/google-ads-search-launch/playbook.md` source
or the `.claude/playbooks/google-ads-search-launch/` Claude shell and
instantiate its push-playbook template.
For B2B local-services lead-form campaigns, apply that playbook's field notes
before launch review.

## Policy Preflight

Before preparing launch copy:

- run the normal ad compliance review flow;
- apply the offer-sharpening rubric; stop when proof, guarantee, urgency,
  mechanism, buyer, outcome, or next step is too thin for paid traffic;
- check for regulated verticals: medical, finance, credit, employment,
  housing, legal, social issues/politics;
- decide whether the request needs `/mb-think` first for offer/policy research,
  keyword-gate work, competitor mapping, or a separate-product decision;
- compare claims against offer proof and Skool/site surfaces when present;
- stop on unsupported guarantees, "cures/treats/heals" claims, impossible
  outcomes, or provider-specific disallowed phrases.

## Existing Campaign Guidance

When account history exists, do not default to a new campaign. Prefer keeping an
existing campaign when the same offer, conversion event, goal, budget structure,
and useful search/negative history still apply. In that case, plan to pause bad
or disapproved assets, add clean assets inside the existing campaign or ad
group, keep the campaign paused until review approval, and record the old
assets as audit context.

Recommend a new campaign only when the goal, offer/service line, conversion
event, budget model, geography, or campaign settings materially change.

## Check Mode

Use check mode when the operator asks "how are the ads doing" or "should we
continue/kill this launch."

Because live provider metrics are not yet a supported mutation/read adapter by
default, use one of these sources:

1. `mb status --json --peek` and relationship/outcome health.
2. Existing push outcome/review files.
3. Operator-provided Ads/GTM/Stripe screenshots or CSV exports.
4. Read-only provider context only when an approved runtime tool, sidecar, MCP
   server, or future `mb` adapter proves it can inspect that provider account.

Output a concise continue/change/stop recommendation and write findings to the
push review or outcome file when the operator approves.

For a recurring read, use the scored checks:

- Meta packs: the daily read, stop rules, day-14 verdicts and retro in
  [meta-pack-loop.md](meta-pack-loop.md).
- Google Ads: the daily money and tracking check and the Monday deep read in
  [google-ads-check.md](google-ads-check.md).

Both prepare pauses and proposals for the operator; neither mutates an
account.

## Approval Boundary

Do not:

- upload campaigns;
- publish GTM containers;
- change budgets;
- start spend;
- upload conversions;
- ask for OAuth secrets, API keys, customer records, or raw account exports in
  chat.

Do:

- prepare the plan;
- cite exact manual steps;
- record approval requirements;
- checkpoint approved artifacts.
