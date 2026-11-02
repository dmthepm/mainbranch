# Google Ads Campaign Plan Workflow

Load this when the operator asks for a Google Ads campaign plan, campaign
rescue, search launch, paid-traffic launch, or launch check. This workflow
turns business context and account facts into a reviewable plan. It does not
publish campaigns, change budgets, upload conversions, publish GTM, or mutate
provider accounts.

## Route

Use this route:

1. `/mb-think` when the offer, audience, policy fit, keywords, competitor terms,
   or lander argument needs research before campaign work.
2. `/mb-site` when the landing page, conversion endpoint, GTM/dataLayer events,
   consent posture, sitelinks, or measurement readiness is missing.
3. `/mb-ads launch-plan` when the operator needs campaign structure, keywords,
   negatives, ad assets, budget, manual provider steps, and approvals.
4. `/mb-ads check` when the operator asks whether to continue, change, or stop
   after a review window.

If the work is repeatable or has approval state, write a plan-only playbook at
`pushes/<push>/playbooks/google-ads-launch-plan.md` with `type: playbook`.
When the operator wants the reusable paid-search recipe, use the
`google-ads-search-launch` source under `playbooks/` or its Claude shell under
`.claude/playbooks/`; that playbook instantiates the push playbook run record
and calls this skill for campaign planning.
For B2B local-services lead-form launches, load that playbook's field notes for
GA4/GTM/Ads import order, Search-only defaults, UI gotchas, negative categories,
and volume calibration.

## Required Inputs

Read or ask for:

- active offer, audience, promise, proof, and current lander;
- offer-sharpening style choice and rubric state from
  `.claude/reference/conversion/offer-sharpening.md`;
- launch push at `pushes/<push>/push.md`;
- geography shape: single-city radius, multi-city service area, statewide,
  national, or multi-location;
- conversion path: call/booking, Stripe/deposit, lead form, trial, or another
  concrete action;
- provider readiness from `mb status --json --peek` and `mb connect doctor --json`;
- site readiness from `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`
  when a site repo exists;
- market-intent research: buyer/search-intent clusters, competitor offers,
  SERP/ad examples when available, customer language, reviews, sales-call
  notes, testimonials, objections, proof, and bad-fit exclusions;
- Google Ads account state if the operator provides a sanitized export or an
  explicitly approved read-only provider tool is already available;
- historical winners: search terms, keywords, CPC/CPA, conversions, landing
  pages, and disapproval or policy history;
- existing negative keyword lists and campaign-level exclusions;
- budget cap, review window, geographic scope, and launch objective;
- regulated-category risks such as healthcare, finance, credit, employment,
  housing, legal, politics/social issues, alcohol, supplements, or claims that
  need proof.

Do not ask the operator to paste OAuth tokens, API keys, customer records,
raw account exports with PII, conversion uploads, or screenshots that expose
private account details. Ask for sanitized exports or manual answers instead.

## Source And Documentation Boundary

Treat official Google Ads documentation as the source of truth for platform
facts. Before locking a plan, verify current limits, policy behavior, and
feature mechanics against official docs when a claim is load-bearing.

Useful official starting points:

- Responsive Search Ads and asset limits:
  <https://support.google.com/google-ads/answer/7684791>
- RSA pinning and field limits:
  <https://support.google.com/google-ads/answer/12159014>
- Search ad effectiveness guidance:
  <https://support.google.com/google-ads/answer/6167122>
- Google Ads assets overview:
  <https://support.google.com/google-ads/answer/7331111>
- Structured snippet assets:
  <https://support.google.com/google-ads/answer/6280012>
- Location targeting:
  <https://support.google.com/google-ads/answer/2453995>
- Preventing clicks outside targeted locations:
  <https://support.google.com/google-ads/answer/9376662>
- AI Max for Search campaigns:
  <https://support.google.com/google-ads/answer/15913066>
- Final URL Expansion in Search:
  <https://support.google.com/google-ads/answer/16230205>

The official docs may recommend more automation than the reusable
offer-validation playbook uses by default. When this playbook chooses more
control, label it as playbook opinion and record any fork in the run record.

## Prerequisite Setup And CLI Boundary

Before planning from live account facts, identify which access path actually
exists:

1. Run `mb status --json --peek` and `mb connect plan` from the business repo.
2. If a site repo exists, run `mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json`.
3. Treat `mb connect` as the Main Branch readiness and repair surface, not as
   proof that Google Ads campaign creation is supported from the terminal.
4. Treat the current Google/Workspace connection as a docs/sheets/drive bridge
   unless this release's `mb connect list` or `mb connect doctor --json`
   explicitly reports a Google Ads provider adapter.
5. Use live Google Ads reads only when an approved runtime tool, MCP server,
   sidecar, or future `mb` adapter is already configured and the operator
   approves read-only account inspection for this business.
6. Use Google Ads UI/manual provider steps for account creation, billing,
   OAuth consent, customer selection, campaign creation, launch/unpause, and
   budget changes unless a shipped adapter with smoke evidence says otherwise.

For a first-time or new-offer setup, prerequisite facts are:

- Google account or manager account that owns the business relationship;
- Google Ads customer selected for this business/offer boundary;
- billing and spend owner confirmed in Google Ads;
- Google Ads conversion action or GA4-imported conversion chosen for the
  launch goal;
- GTM or gtag instrumentation plan verified through `/mb-site`;
- consent/privacy posture and policy pages reviewed;
- account history either unavailable, intentionally ignored, or read through
  a sanctioned source.

If `mb connect` reports Google Ads as missing, planned, unsupported, or absent
from the provider list, do not block copy/plan work. Continue in plan-only mode
using repo facts, `mb site check`, sanitized exports, and manual Google Ads UI
steps.

## Decision Sequence

### 1. Offer And Policy Fit

Confirm the offer can be advertised as stated. Apply the offer-sharpening
rubric first: audience, outcome, transformation, mechanism, proof, price/value
logic, risk reversal, objections, reason to act, and next step. For regulated
categories, read provider policy before writing copy. If the offer or lander
triggers a restricted classification, stop and present options:

- rewrite the offer/lander/copy into a policy-safe form;
- build a separate product or front door only if the operator accepts the
  business, legal, and brand boundary;
- pursue required certification or verification;
- pause paid traffic and route to organic, SEO, referrals, or another channel.

Do not frame policy work as "bypassing" a provider. Frame it as accurate
classification, clean claims, and operator-approved compliance.

### 2. Execution Contract For Launch Plans

`/mb-ads launch-plan` must generate the reviewable launch spec, not merely tell
the operator what to think about. After intake and research, produce concrete
draft values for:

- campaign settings: goal, bid strategy, network toggles, geography mode,
  language, devices, schedule, URL options, and fork rationale;
- ad group structure, exact/phrase keywords, and launch negative keywords;
- Responsive Search Ad headlines, descriptions, display paths, pins, and
  rationale;
- sitelinks with description lines, final URLs, jobs, and destination audits;
- callouts, structured snippets, optional assets, skipped assets, and skip
  rationale;
- manual provider steps, approval gates, budget cap, review window, and
  continue/change/stop criteria.

If there is not enough evidence to draft one of those fields, output an explicit
`needs operator input` line instead of leaving the field implicit.

Use existing Main Branch skills as execution primitives:

- `/mb-think` for parallel market, competitor, customer-language, proof, and
  conversion-path research;
- `/mb-site` for lander, headline, proof, conversion endpoint, and measurement
  readiness when the destination is weak or missing;
- `/mb-ads launch-plan` for final Google Ads settings and asset generation;
- `/mb-ads check` for post-review-window judgment.

For Google Search, do not reuse social/static-ad copy generation blindly. Use
the same specificity and variety discipline, but adapt every asset to RSA
character limits, standalone rendering, query intent, policy review, and
destination-page proof.

### 3. Research-To-Ad-Spec Pass

For a new offer, thin offer, new geography, or first run in a market, do not
write assets from vibes. Route through `/mb-think` or an equivalent research
pass before finalizing campaign settings and copy.

Research in parallel when the runtime supports it:

- **Market/search intent:** buyer-intent terms, problem-aware terms, category
  terms, geo modifiers, high-friction phrases, and obvious bad-fit searches.
- **Competitor and offer positioning:** direct competitors, alternative offers,
  pricing or deposit norms, service area promises, guarantees, proof, and gaps.
- **Customer language and objections:** reviews, sales-call notes, testimonials,
  support tickets, forums, community posts, or operator notes that reveal how
  buyers describe the pain and decision.
- **Conversion-path fit:** whether this offer should validate through a call,
  booking, Stripe/deposit payment, checkout, lead form, trial, or manual
  qualification.

Persist durable findings to `research/` when the pass produces new business
truth. The campaign plan should cite the research files or operator-provided
facts it used.

Paid-search research is allowed to change the core, not just the ad plan. When
the research discovers durable truth, route it deliberately:

- update `core/offer.md` or `core/offers/<offer>/offer.md` when the offer,
  pricing, promise, guarantee, mechanism, conversion path, or service boundary
  changes;
- update `core/audience.md` or `core/offers/<offer>/audience.md` when search
  language, pains, objections, buyer stage, bad-fit audiences, or decision
  criteria become clearer;
- update `core/proof/` or `core/offers/<offer>/proof/` when a claim, proof
  angle, testimonial, or typicality caveat becomes reusable;
- update `core/content-strategy.md` or a strategy file when the research changes
  channel cadence, content pillars, market thesis, or launch sequencing;
- write a `decisions/` record when the operator accepts a durable tradeoff,
  such as call-first versus deposit-first validation.

Do not silently rewrite core truth while drafting ads. Present proposed core
changes with evidence and apply them only when the operator approves, unless
the operator already asked for the skill to update core as part of the run.
If approval is pending, record the proposed updates in the push playbook.

Minimum output before asset writing:

- primary intent clusters;
- excluded intent clusters;
- geography assumption and service boundary;
- conversion path and business value;
- strongest proof claims that are safe to advertise;
- claims to avoid because they are unproven, policy-sensitive, or bad-fit;
- landing pages and sitelink destinations to use or avoid.

### 4. Existing Campaign Versus New Campaign

Prefer an existing campaign when all are true:

- same offer or service line;
- same conversion event;
- same goal and budget structure;
- useful historical search/query/negative-list data exists;
- the problem is copy, lander, policy, or stale settings rather than a broken
  campaign structure.

Start a new campaign only when goal, product/service line, conversion event,
budget model, geography, or structural settings materially change.

When rescuing a campaign, pause bad or disapproved ads instead of immediately
deleting them. Add new clean assets inside the existing campaign or a new ad
group, keep the campaign paused until at least one new asset is approved, and
record the old asset status as audit context. After a clean review window, the
operator can delete stale assets manually.

### 5. Geography And Conversion Path

Campaign settings depend on geography and conversion path.

For local or radius tests:

- use presence targeting by default, not presence-or-interest;
- include city/service-area language only when the business can serve it;
- keep keywords, negatives, and sitelinks local enough to protect the proof
  budget;
- expect lower absolute volume and define the extension/widening rule before
  launch.

For multi-city or statewide tests:

- split campaigns or ad groups when geography changes intent, CPC, proof,
  licensing, or service capacity;
- keep location names in copy only where true and useful;
- record whether the operator wants one shared proof budget or separate
  geography budgets.

For national tests:

- do not reuse local-radius assumptions;
- segment by intent, offer tier, audience, or conversion path before segmenting
  by geography;
- require a stronger negative strategy and a clearer budget ceiling because
  national reach can burn proof budgets quickly.

For multi-location businesses:

- decide whether each location needs its own campaign, location asset, landing
  page, phone number, booking path, or review bar;
- do not point all sitelinks at generic pages if the query implies a specific
  location.

For call/booking conversion paths, verify booking friction, calendar capacity,
phone/call handling, and whether calls are actually desired. For
Stripe/deposit paths, verify price, refund terms, checkout link, confirmation
event, and whether the deposit is the real proof signal. For lead forms, verify
privacy and regulated-category posture before using provider-hosted forms.

### 6. Campaign Settings Defaults

For the first proof window, default to:

- campaign type: Search;
- networks: Search Network only, Search Partners off, Display Network off;
- bid strategy: Maximize Conversions when the selected primary conversion is
  verified;
- targeting: presence only for local, regulated, licensed, or service-area
  campaigns; presence-or-interest only as a recorded fork for national,
  location-independent, or travel-like intent;
- AI Max: off;
- Final URL Expansion: off;
- keyword expansion: exact and phrase first, broad match off;
- final URL: explicit operator-approved destination URL;
- URL options: empty unless the measurement plan needs final URL suffix,
  custom parameters, or a tracking template.

These are playbook defaults for small-budget offer validation, not universal
Google Ads doctrine. If the operator chooses Search Partners, broad match, AI
Max, Final URL Expansion, provider-hosted lead forms, price assets, or automated
URL options, record the fork, reason, risk, and review condition in the run
record.

Do not default to Target CPA or Target ROAS on a cold proof run. Mention them
as later optimization moves only after the account has enough recent conversion
volume and clean value tracking to make the constraint meaningful.

### 7. Campaign Structure

Draft only the structure that fits the evidence. Common search structures:

- brand defense: brand, founder, product, and close variants;
- geo/local intent: service plus city/region terms;
- high-intent service: ready-to-buy terms and "near me" variants;
- competitor/alternative: only when policy-safe and not misleading;
- proof or education: only when the lander and measurement path support it.

Each ad group should have:

- exact/phrase keyword targets where intent matters;
- broad match only with a clear reason and tight negatives;
- one lander or sitelink set;
- policy-safe headlines/descriptions;
- explicit manual review notes.

For offer-validation runs, default to Search only, explicit final URL,
no AI Max, no Final URL Expansion, and no broad match for the first proof
window unless the operator records a fork. This is not a universal Google Ads
rule; it is a playbook choice for small-budget tests where query, copy, and URL
control matter more than reach.

### 8. Keywords And Negative Strategy

Use account history first when available. Keep:

- historical converters;
- search terms with acceptable economics;
- brand and geo-intent winners;
- exact/phrase terms aligned with the lander promise.

Exclude:

- DIY, free, job, school, research, entertainment, definition, unrelated
  locations, competitor terms that create policy risk, and impossible-fit
  searches;
- regulated terms that imply unsupported claims, prescription/order behavior,
  guarantees, discriminatory targeting, or sensitive personal attributes;
- any term the operator marks as a bad-fit lead.

If a shared negative list exists, tell the operator to attach it to the campaign
manually. Do not paste a large account-specific negative export into public
docs or committed examples.

### 9. Ad Assets

Assets should be a researched spec, not a loose copy batch.

For Responsive Search Ads:

- draft 12-15 headlines and 4 descriptions per ad group when enough evidence
  exists; if evidence is thin, draft fewer only with `needs operator input`
  lines for missing proof or offer facts;
- organize headline angles before writing them:
  - keyword/search intent;
  - value or problem relief;
  - proof, trust, or risk reversal;
  - geography or availability when relevant;
  - CTA or conversion path;
  - brand/identity when useful;
- prioritize unique intent/proof angles over repetitive variants;
- check current character limits against official docs before the operator
  pastes them;
- write every unpinned headline as a standalone coherent claim because assets
  can appear in different combinations;
- pin only mandatory claims, disclaimers, or identity lines, and record why
  because pinning reduces combination flexibility;
- include at least one keyword/intent phrase where it fits naturally;
- separate offer clarity, proof, objection handling, geography, and CTA angles;
- remove or rewrite any claim the lander cannot support.

For display paths:

- choose paths that reinforce the offer or intent, such as `evaluation`,
  `quote`, `deposit`, `booking`, or the service category;
- avoid paths that imply unsupported claims, policy-sensitive language, or a
  different conversion path than the final URL.

For sitelinks:

- use only pages that are safe, live, fast, and aligned with the ad promise;
- audit every sitelink destination, not just the final URL;
- prefer fewer clean sitelinks over more risky ones;
- record each sitelink's job: book, proof, pricing, process, location, FAQ,
  comparison, or objection handling;
- for local offers, include location/service-area pages only when they match
  real service capacity;
- for national offers, avoid local-looking sitelinks unless the campaign is
  intentionally segmented.

For callouts:

- use short verified claims: service speed, guarantee boundaries, licensing,
  pricing posture, audience fit, proof, support model, or risk reversal;
- do not use callouts for unverified superlatives or claims the operator would
  not defend in review.

For structured snippets:

- use a header and values that honestly describe categories, services,
  programs, brands, styles, destinations, or other platform-supported groupings;
- skip snippets when the values would be vague, repetitive, policy-sensitive,
  or unsupported by the lander.

For other assets and options:

- use logo/business-name/image assets only when brand assets are correct for
  this offer and not inherited from a mismatched prior account;
- use location assets only when physical/local presence is real and helpful;
- use call assets only when calls are desired, staffed, and measured;
- use price or promotion assets only when price/promo is central to the offer
  and policy-safe in the category;
- avoid provider-hosted lead forms for sensitive or regulated categories unless
  privacy, consent, and data handling have been explicitly approved;
- leave tracking templates, final URL suffixes, and custom parameters empty
  unless the measurement plan requires them; auto-tagging plus GA4/GTM may be
  enough for many proof runs.

Record skipped assets with reasons. "Skipped" is useful evidence, not a gap.

### 10. Generated Asset Quality Gates

Before the plan is ready for operator approval, self-review the generated spec:

- every RSA asset fits character limits or is marked for rewrite;
- no two headlines say the same thing with different adjectives;
- every proof or superlative claim has a source in the lander, research, or
  operator-provided facts;
- every unpinned headline can render alone without becoming fragmentary or
  misleading;
- every sitelink URL is live, relevant, mobile-safe enough to review, and has a
  plausible conversion or trust job;
- every callout is factual and short;
- every structured snippet uses a supported header and honest values;
- every skipped asset has a reason;
- Search Partners, Display Network, AI Max, Final URL Expansion, broad match,
  and URL automation are still off unless the run record shows an approved
  fork.

### 11. Lander And Conversion Prerequisites

Before recommending launch:

- run `mb site check` when a site repo exists;
- verify GTM/dataLayer event names match
  `docs/google-ads-gtm-conversion-rubric.md`;
- confirm the primary conversion action matches the launch goal;
- audit every sitelink destination, not only the final URL;
- confirm consent/privacy posture and policy pages are acceptable;
- if conversion tracking has been dark or stale, require a manual test before
  trusting performance data.

Use the `mb site check` readiness state. Never invent `ready_for_launch`, and
never treat `ready` as permission to spend.

### 12. Budget And Review Window

Capture:

- daily/monthly budget cap;
- bid strategy for the first review window;
- launch geography and schedule;
- review date or spend threshold;
- continue/change/stop criteria;
- who approves spend.

If the account has stale conversion history, recommend conservative bidding
until recent conversion data exists. Do not switch to automated bidding because
it sounds sophisticated; tie it to evidence and volume.

For this playbook, Maximize Conversions is the default automated bid strategy
only after the primary conversion is verified. That is different from enabling
AI Max, broad match, Search Partners, Display expansion, or URL automation.
Keep those separate in the plan so the operator can approve bidding without
accidentally approving broader automation.

### 13. Approval Gates

The plan must show separate approvals for:

- campaign structure and keywords;
- negative list;
- ad copy and assets;
- lander/sitelinks;
- conversion action and GTM/Tag Assistant evidence;
- consent/privacy posture;
- budget and billing;
- launch/unpause.

Main Branch may write the plan and checklist. The operator performs provider
actions unless a future adapter ships with approval gates and smoke evidence.

## Output Shape

For `pushes/<push>/ads.md` or the campaign-plan playbook body, include:

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

Keep real account IDs, screenshots, raw exports, customer data, and private
spend details out of public-safe committed examples.
