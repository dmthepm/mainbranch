# Flexible Entry Points

The skill detects intent from natural language and routes to the right pipeline. Users describe what they need, and the skill assembles modular components accordingly.

---

## Why Flexible Entry Points

Real ad workflows don't fit neat categories. Someone might have images but need copy, want 5 variations instead of 50, need to check account performance before creating, or want to turn a video into multiple ad formats. Intent detection handles all of these by assembling the right pipeline from modular components.

---

## Entry Point Detection

### User-Says Table

| User Says | Intent | Components Assembled | Ad account? |
|-----------|--------|---------------------|------------|
| "I want ideas for an ad" | Ideation | Account check (if available) + research + concept generation | Read-only |
| "Make an ad from this video" | Video Repurpose | Use approved source material for paid hooks + ad copy variants | No |
| "Make short clips from this sales video" | Organic clips | Route to `/mb-organic` | No |
| "I already have images, just need copy" | Copy Only | Skip image gen, primaries + headlines | No |
| "Just need images for existing copy" | Image Only | Image prompts and optional provider generation | No |
| "Full from scratch" | Full Pipeline | Copy + compliance + images (classic static flow) | Optional |
| "Check my ad performance" | Account Check | Read-only account context -- insights, winners/losers | Required |
| "Launch ads", "paid traffic plan", "Google Ads launch" | Launch Plan | Readiness, policy, keyword, budget, approval plan | Plan-only |
| "Check launch", "continue or kill", "how are ads doing" | Launch Check | Status/outcomes/manual exports, continue/change/stop call | Read-only |
| "Weekly pack", "next Meta pack", "build this week's ads" | Launch Plan (pack) | Text slots + media specs + names + PAUSED build checklist ([meta-pack-loop.md](meta-pack-loop.md)) | Plan-only |
| "Daily read", "stop rules", "day-14 verdict", "Google Ads daily check" | Launch Check (scored) | Stop rules and verdicts ([meta-pack-loop.md](meta-pack-loop.md)) or the Google rubric ([google-ads-check.md](google-ads-check.md)) | Read-only |
| "Give me 50 creative variations" | Hook Library | Bulk generation (flexible quantity) | No |
| "Give me 5 variations of this winning ad" | Performance Iteration | Pull winner + generate variants | Read-only |
| "Make me video scripts" | Video Scripts | Full video script pipeline | No |
| "Review my ads" / "compliance check" | Review | 6-lens compliance review | No |
| "What's working before we create?" | Pre-Gen Account Check | Account overview + creative audit | Required |

### Intent Detection Logic

```
1. Parse user message for trigger phrases
2. Check for explicit mode keywords first:
   - "review" / "compliance" / "audit" → Review
   - "video scripts" / "spoken word" → Video Scripts
   - "static ads" / "full from scratch" → Full Pipeline
3. Check for component-specific language:
   - "just copy" / "only copy" / "have images" → Copy Only
   - "just images" / "only images" / "have copy" → Image Only
   - "make an ad from this video" / "repurpose for paid ads" → Video Repurpose
   - "short clips from a sales video" / "organic cuts from a VSL" → `/mb-organic`
   - "variations" / "hook library" / "one-liners" / "creative variations" → Hook Library
4. Check for account-related language:
   - "performance" / "what's working" / "check account" / "CPA" / "ROAS" → Account Check
5. Check for ideation language:
   - "ideas" / "brainstorm" / "concepts" / "what should I run" → Ideation
6. If unclear → ask: "What do you have and what do you need?"
```

### Alternate Triggers

These shorthand names also route correctly:

| Trigger | Routes To |
|---------|-----------|
| "static ads" | Full Pipeline |
| "static" | Full Pipeline |
| "video scripts" | Video Scripts |
| "video" | Video Scripts |
| "one-liners" | Hook Library (creative variations) |
| "review" | Review |

---

## Component Architecture

Each entry point assembles different components. Components are modular -- they can be combined in any order.

### Available Components

| Component | What It Does | Reference |
|-----------|-------------|-----------|
| **Pre-flight** | Score core files, check readiness | [preflight-algorithm.md](preflight-algorithm.md) |
| **Account Check** | Pull live account data when `mb connect` and runtime tools are verified | [meta-ads-integration.md](meta-ads-integration.md) |
| **Copy Engine** | Generate primaries, headlines, hooks | SKILL.md (Static Ads section) |
| **Hook Library** | Generate N creative variations (also called "one-liners") | [one-liner-methodology.md](one-liner-methodology.md) |
| **Video Scripts** | Generate spoken-word scripts | [video-templates-hooks.md](video-templates-hooks.md) |
| **Image Gen** | Image prompts + optional provider generation | [image-generation-workflow.md](image-generation-workflow.md) |
| **Compliance Review** | 6-lens review pipeline | [review-workflow.md](review-workflow.md) |
| **Launch Plan / Check** | Provider-safe paid-traffic plan and outcome check | [launch-plan-check.md](launch-plan-check.md) |
| **Post-Gen Pipeline** | Git commit + compliance + image gen | [post-generation-pipeline.md](post-generation-pipeline.md) |
| **Transcription** | Video/audio transcription (whisper or manual) | `/mb-think` references |

### Component Composition by Entry Point

| Entry Point | Pre-flight | Account | Copy | Hooks | Video | Images | Review | Post-Gen |
|-------------|-----------|---------|------|-------|-------|--------|--------|----------|
| Full Pipeline | Yes | Optional | Yes | -- | -- | Yes | Auto | Yes |
| Copy Only | Yes | -- | Yes | -- | -- | -- | Auto | Yes |
| Image Only | Lite | -- | -- | -- | -- | Yes | -- | Yes |
| Hook Library | Yes | -- | -- | Yes | -- | Optional | Auto | Yes |
| Video Scripts | Yes | -- | -- | -- | Yes | -- | Auto | Yes |
| Video Repurpose | Yes | -- | Yes | -- | -- | Optional | Auto | Yes |
| Ideation | Lite | Optional | Concepts | -- | -- | -- | -- | -- |
| Account Check | -- | Yes | -- | -- | -- | -- | -- | -- |
| Review | -- | -- | -- | -- | -- | -- | Yes | -- |
**Legend:** Yes = always included, Optional = if available/requested, Auto = runs automatically, Lite = abbreviated check, -- = not included

---

## Quantity Flexibility

Quantity is flexible -- the user says how many, the skill delivers:

| User Says | Quantity |
|-----------|---------|
| "Give me 5 variations" | 5 |
| "50 creative variations" | 50 |
| "A few hooks to test" | 5-10 (suggest range, confirm) |
| "Full batch" | Default (30 for hooks, 5-6 concepts for static) |
| No quantity specified | Ask: "How many do you want? A few to test (5-10) or a full batch (30+)?" |

---

## Routing Flow

```
User message arrives
│
├─ Pre-flight runs (Step 0 — always, unless pure Account Check)
│
├─ Detect intent (see detection logic above)
│
├─ If Meta ad account context is verified AND relevant intent:
│   └─ "Want me to check what's working before we create?"
│       ├─ Yes → Account Check component runs first
│       └─ No → Skip, proceed to generation
│
├─ Assemble component pipeline for detected intent
│
├─ Execute pipeline:
│   ├─ Copy/Hooks/Video generation
│   ├─ Save output to pushes/
│   └─ Post-Gen Pipeline (auto: commit + compliance + images)
│
└─ Done (write operations like Duplicate + Swap are on the roadmap)
```

---

## Campaign Naming

Campaign name is still required before saving output. The entry point doesn't change this -- all output paths include the campaign name:

```
pushes/YYYY-MM-DD-{type}-[offer]-{campaign}/
```

Where `{type}` maps from the entry point:
- Full Pipeline / Copy Only → `static-ads`
- Hook Library → `creative-variations`
- Video Scripts → `video-ads`
- Video Repurpose → `video-repurpose`

Meta packs live inside the push they serve, one record per pack:
`pushes/<push>/packs/p<NN>-<slug>.md`, with Meta object names from
[naming-and-utm.md](naming-and-utm.md).

---

## Error Handling

| Situation | What Happens |
|-----------|-------------|
| Intent unclear | Ask: "What do you have and what do you need?" |
| Ad account required but missing | "This needs live Meta ad account context, which is optional and not ready here. Check Ads Manager manually and paste metrics, or skip and work from reference files only." |
| Pre-flight fails (thin reference) | Route to /mb-think (same as current behavior) |
| User changes mind mid-pipeline | "No problem. What would you like instead?" Re-detect intent. |

---

## Roadmap Entry Points

These entry points require official Meta write operations and are not yet
active. They are documented here for future implementation.

| User Says | Intent | Components | Account access |
|-----------|--------|-----------|-----------|
| "Duplicate this ad set with new creative" | Duplicate + Swap | Clone ad set + swap creative | Write (required) |

**Duplicate + Swap** would duplicate a winning ad set in a paused/reviewable
state, upload new creative, and swap it in only after explicit operator
approval. This remains roadmap until the official Meta write surface has setup
proof, verified tool names, and approval gates. See
[meta-ads-integration.md](meta-ads-integration.md) for the boundary.

---

## See Also

- [meta-ads-integration.md](meta-ads-integration.md) -- Account access details
- [launch-plan-check.md](launch-plan-check.md) -- Paid-traffic launch-plan and check boundary
- [one-liner-methodology.md](one-liner-methodology.md) -- Hook library methodology (Joel's cold-traffic work preserved)
- [preflight-algorithm.md](preflight-algorithm.md) -- Pre-flight scoring
