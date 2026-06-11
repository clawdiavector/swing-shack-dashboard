# Campaign OS — Full Specification Document
**Version:** 1.0
**Date:** 2026-06-11
**Status:** LIVE — M1–M7 operational, M8 in progress
**Owner:** Clawdia (build) + Christelle (authority)
**Source:** Fleet consensus + Christelle mandate

---

## 1. What Is Campaign OS?

Campaign OS is a content operations system for Swing Shack that replaces scattered Google Docs, Discord threads, and gut-feel scheduling with a single verifiable pipeline.

It manages the full lifecycle of a social media campaign — from research → planning → content creation → review → publishing → analytics — with full visibility and explicit human approval gates at every stage.

**The north star:** A calm, inspectable, AI-native campaign operating environment that always tells the truth about the state of the work and helps surface the highest-leverage next action.

**The core principle:** Truthful state > complete state. Nothing publishes without approval. Nothing is marked done until verified.

---

## 2. The Problem It Solves

**Before Campaign OS:**

| Symptom | Consequence |
|---|---|
| Content decisions buried in Discord | Decisions disappear, nobody knows what's approved |
| No visibility on campaign state | Christelle is always chasing status |
| No quality gates | Wrong captions ship, fake images go live |
| Scattered Google Docs | Version history lost, nobody knows the latest |
| Manual Postiz posting | Publishing happens without tracking |
| No research grounding | Content generated from assumptions, not intelligence |

**After Campaign OS:**

| Symptom | Resolution |
|---|---|
| Decisions tracked in one place | campaign-data.json as single source of truth |
| State always visible | Cockpit dashboard shows everything |
| Quality gates before publishing | Clawfix verifies before any asset moves forward |
| Git-backed audit trail | Every change timestamped and verifiable |
| Agent write-backs | Each agent owns their lane, writes to JSON |
| Research-informed generation | Scout intelligence feeds every asset |

---

## 3. The Complete Feature Set

### 3.1 Campaign Management

**What it does:**
- Create campaigns from a brief (campaign name, goal, target audience, offer, start date)
- Store full campaign state: status, owner, health score, assets, blockers, history
- Track campaign lifecycle: planning → active → paused → completed → archived

**What's built:**
- Campaign object schema in `campaign-data.json`
- Blueprint generation (M2) — strategy, pillars, tone, visual direction
- Git-backed state with timestamped commits
- Campaign health scoring (Lab) with diagnostic explanations

**Still to build:**
- Campaign archive/restore functionality
- Campaign comparison view (side-by-side health of multiple campaigns)
- Campaign duplication (clone a campaign as template for new season)

---

### 3.2 Research Intelligence Layer (Scout's Lane)

**What it does:**
Before any content is created, Scout researches the competitive landscape, search intent, audience language, and market gaps. This intelligence is written to `campaign-data.json` and inherited by every asset generated.

**What's built:**
- Competitive landscape scan (JHB golf market — competitors, pricing, positioning)
- Search intent mapping (what golfers search, why, when)
- Audience language capture (real golfer phrases, not marketing language)
- Objection mapping (why golfers avoid fittings, blame swing not equipment)
- Content opportunity mapping (findings mapped to campaign pillars)
- `campaign.researchAngles[]` — top-level intelligence angles (7 angles)
- `campaign.researchFindings[]` — granular findings (7 findings)
- `campaign.memory.insights[]` — platform/content performance patterns (5 entries)
- `campaign.researchSummary` — full landscape brief
- `researchRefs[]` + `findingIds[]` on every asset shell (36 assets)
- G-R1–G-R5 research gates (verified by Clawfix)

**Research inheritance rules:**
- Every asset carries `researchRefs[]` (which angle drives it) + `findingIds[]` (which findings back it)
- No asset can be generated without at least one research angle reference
- Primary angle must match the asset's pillar
- Supporting angles can cross-pillar (the campaign theme bleeds through)

**Still to build:**
- Automated competitor monitoring (weekly scan vs manual)
- GA4 / Meta ad data ingestion into `campaign.memory.insights[]`
- Research freshness indicator (when was the last scan done?)

---

### 3.3 Blueprint Builder (M2/M4)

**What it does:**
Generates the creative DNA of a campaign from the brief — tone, pillars, content mix, platform strategy, visual direction.

**What's built:**
- Blueprint generator script (Python + MiniMax)
- Blueprint schema with DNA, pillars, visualDirection, platformStrategy
- Blueprint versioning (multiple versions, active flag)
- Campaign Mothership cockpit with Blueprint tab
- Blueprint comparison view (diff between versions)

**Blueprint schema:**
```json
{
  "blueprintVersion": 1,
  "generatedAt": "ISO8601",
  "modelUsed": "MiniMax-M2.7",
  "active": true,
  "dna": {
    "tone": "string",
    "contentMix": "string",
    "requiredContentTypes": [],
    "preferredVisualStyles": [],
    "forbiddenVisualStyles": [],
    "ctaPhilosophy": "string",
    "platformStrategy": {}
  },
  "pillars": [
    {
      "id": "p1",
      "name": "string",
      "description": "string"
    }
  ],
  "visualDirection": {
    "palette": {},
    "mood": "string",
    "creativeDirection": "string",
    "imageReferences": [],
    "colorUsage": "string",
    "typography": "string",
    "layoutStyle": "string"
  }
}
```

**Still to build:**
- Blueprint acceptance workflow (Christelle "Accept Blueprint" button)
- Blueprint regeneration from revised brief
- Blueprint A/B testing (two strategies for same brief)

---

### 3.4 Production Plan Generator (M5)

**What it does:**
Takes the blueprint and generates a 30-day content calendar — how many posts, what type, which pillar, which platform, which day. Creates named asset shells with all production fields pre-populated.

**What's built:**
- `generate-production-plan.py` with G1–G8 validation gates
- `productionPlan` schema with `assetRequirements`, `calendar[]`, `realImageRule`
- 36 asset shells created with full schema (captionStatus, visualStatus, approvalStatus, publishStatus, researchRefs, findingIds, realImageNeeded, aiImageAllowed, copyRequirement, etc.)
- Pillar distribution logic (round-robin weighted by contentMix)
- Platform distribution (IG 60% feed / 20% carousel / 10% reel / 10% story; GMB Mon/Tue; TikTok 70% reel / 30% carousel)
- Real image rule enforced for equipment campaigns
- Campaign Mothership Production Plan tab (read-only)
- Batch manifests locked before work starts (prevents scope drift)

**Production plan schema:**
```json
{
  "planVersion": 1,
  "generatedAt": "ISO8601",
  "planStatus": "draft",
  "assetRequirements": {
    "feedPosts": { "count": 13, "platforms": ["instagram"], "realImageNeeded": false, "aiImageAllowed": true },
    "carousels": { "count": 4, "slides": 4, "platforms": ["instagram"], "realImageNeeded": false, "aiImageAllowed": true },
    "reels": { "count": 2, "durationSec": 30, "platforms": ["instagram", "tiktok"], "realImageNeeded": false, "aiImageAllowed": true },
    "stories": { "count": 8, "platforms": ["instagram"], "realImageNeeded": false, "aiImageAllowed": true },
    "gmbPosts": { "count": 9, "platforms": ["gmb"], "realImageNeeded": true, "aiImageAllowed": false },
    "total": 36
  },
  "calendar": [
    {
      "date": "2026-06-09",
      "platform": "gmb",
      "contentType": "gmb-post",
      "pillar": "p1",
      "assetId": "use-the-right-equipment-mq5l90bk-gmb-post-01",
      "assetRequirement": "string",
      "captionStatus": "pending",
      "visualStatus": "pending",
      "approvalStatus": "pending",
      "publishStatus": "planned"
    }
  ],
  "realImageRule": {
    "enforced": true,
    "reason": "Equipment campaign — product photography required",
    "aiAllowedFor": ["background", "layout", "concept-mood", "typography"],
    "aiForbiddenFor": ["club heads", "equipment on-face", "golfer likeness", "swing motion"]
  }
}
```

**Still to build:**
- Production plan regeneration with `--approve` flag (locks plan, prevents re-generation)
- Production plan editing (add/remove/reorder assets manually)
- Seasonal campaign support (auto-adjust calendar for known seasons)

---

### 3.5 Content Generation (M6)

**What it does:**
Each agent writes captions and visual briefs for every asset in the production plan. All content is research-grounded and tone-matched.

**What's built:**
- 36 assets generated across 4 batches (pilot + 3 batches)
- All assets at: `captionStatus: draft`, `visualStatus: brief-written`, `approvalStatus: review`, `publishStatus: planned`
- Copywriter captions written with tone, length, platform compliance
- ImageGen visual briefs written with real photo requirements, AI rules, specific concept descriptions
- GMB compliance verified (no emojis, no hashtags, local relevance, 300-500 chars)
- ResearchRefs + findingIds on every asset
- Story assets: AI allowed for backgrounds only (no AI golfer likeness, no AI club heads)
- Reel + carousel + feed-post: real photography required, AI forbidden for equipment
- Equipment campaign rule: `realImageNeeded: true` on all non-story assets

**Content generation schema (per asset):**
```json
{
  "assetId": "string",
  "campaignId": "string",
  "pillar": "p1",
  "assetType": "feed-post|carousel|reel|story|gmb-post",
  "caption": "string",
  "captionStatus": "pending|draft|approved|rejected",
  "captionLength": "string",
  "captionTone": "string",
  "copyRequirement": "string",
  "visualStatus": "pending|brief-written|generated|approved|rejected",
  "visualBrief": "string",
  "realPhotoBrief": "string",
  "realImageNeeded": true,
  "aiImageAllowed": false,
  "aiForbiddenFor": ["club heads", "equipment on-face", "golfer likeness"],
  "researchRefs": [
    { "angleId": "sa-1", "relevance": "primary|supporting" }
  ],
  "findingIds": ["sf-1", "sf-2"],
  "approvalStatus": "pending|review|approved|rejected",
  "publishStatus": "planned|submitted|scheduled|live|failed|skipped",
  "status": "planned|in-progress|review|approved|published|rejected"
}
```

**Still to build:**
- Caption regeneration (request revision → Copywriter rewrites)
- Visual brief regeneration (request revision → ImageGen rewrites)
- A/B caption variants stored per asset (currently one caption per asset)
- Video/script generation for reels (briefs are written, no actual video content)

---

### 3.6 Review + Approval Queue (M7)

**What it does:**
Gives Christelle one place to review all 36 assets, approve what works, reject what doesn't (with mandatory reason), or request changes. Each asset routes to the correct agent lane for revision.

**What's built:**
- Campaign Mothership Review Queue tab (M7 build in progress by Clawdia)
- All 36 assets at `approvalStatus: review`
- Batch manifests locked before work (no scope drift)
- Research grounding verified on all assets
- Real image rules enforced
- Clawfix gates verified all batches

**M7 requirements (from Christelle's spec):**

| Feature | Status |
|---|---|
| Review Queue — all 36 assets visible | In progress |
| Asset title, platform, content type, pillar, planned date | In progress |
| Caption draft + visual brief + real photo brief per asset | In progress |
| Image rules visible per asset | In progress |
| Approve action | In progress |
| Reject action (reason required) | In progress |
| Request Copy Revision | In progress |
| Request Visual Revision | In progress |
| Edit Caption inline | In progress |
| Edit Visual Brief inline | In progress |
| Rejection reason: reason + what must change + assigned lane | In progress |
| Status flow: review → approved / review → revisionRequested / revisionRequested → review / review → rejected | In progress |
| Filter by platform | In progress |
| Filter by content type | In progress |
| Filter by pillar | In progress |
| Filter by status | In progress |
| Batch approve selected | In progress |
| Batch reject selected | In progress |

**Safety rules:**
- No asset can move to `publishStatus: submitted` unless: `approvalStatus=approved` AND `captionStatus=approved` AND `visualStatus=approved` AND real image rule passed AND Publisher gate passed
- Approved assets do NOT auto-publish
- No Postiz drafts created during review phase

**Still to build:**
- Full M7 UI (Clawdia building)
- Rejection reason persistence
- Inline caption editing + persistence
- Inline visual brief editing + persistence
- Batch operations (approve/reject selected)
- Export review decisions as JSON

---

### 3.7 Publishing Workflow (M8)

**What it does:**
Once content is approved, Publisher dispatches to Instagram (via Postiz), TikTok (via Postiz), and Google Business Profile (via Postiz). UTM tracking baked in. Analytics pulled back after publish.

**What's built:**
- Postiz API integration (partially — auth token, draft creation, scheduling)
- `publishState` enum: `planned → submitted → scheduled → live → failed`
- Postiz draft IDs written to `campaign-data.json`
- Publishing status tracked per asset
- GMB compliance rules verified before publish

**What's NOT built:**
- Postiz token refresh automation (manual intervention required when token expires)
- Instagram/Meta token stability (token goes stale)
- Live analytics reconciliation (Postiz → GA4/Meta pullback)
- UTM parameter injection (not automated)
- Publishing queue with retry logic for failed posts

**Postiz state machine:**
```
planned → submitted (Postiz draft created)
submitted → scheduled (Postiz accepts, returns scheduled time)
scheduled → live (Postiz confirms published)
planned → failed (Postiz returns error — publishError field required)
```

**Still to build (M8):**
- Postiz token refresh automation
- Instagram/Meta token stability fix
- Analytics write-back (GA4 + Meta → campaign-data.json → TruthCollector)
- UTM automation per platform per campaign
- Failed post retry workflow
- Publishing calendar view (what's scheduled when)
- Live post confirmation (Postiz → confirmed live → update publishState)

---

### 3.8 Analytics + Health Scoring

**What it does:**
Pulls real performance data from GA4 and Meta API. Calculates campaign health scores. Generates diagnostic explanations that name the specific cause of any degradation.

**What's built:**
- Health score schema (conversion 35%, compounding 25%, engagement 25%, momentum 15%)
- Health score states: `NO_DATA | STALE_DATA | healthy | degraded | critical`
- Diagnostic explanations per campaign (Lab writes these)
- Health rings in Campaign Mothership cockpit

**What's NOT built:**
- GA4 property ID wiring (TruthCollector — `analyticsConfig` fields missing)
- Meta ad account ID wiring
- Real analytics data flowing into campaign (seed data only)
- Health score auto-recalculation (cron not wired)
- Momentum signal for new campaigns (14-day history required)
- Platform-specific breakdown per asset

**Health score rules:**
- Score only computable from `VERIFIED` status data
- If stale or unverified data feeds conversion/engagement → output `STALE_DATA`
- Never produce a numeric score from unverified inputs
- New campaigns: momentum returns `NO_DATA` (honest, not a failure)

**Still to build:**
- `analyticsConfig` fields per campaign in `campaign-data.json`
- GA4 + Meta API credential wiring
- Daily health cron (scheduled refresh)
- Platform-specific asset-level analytics (not just campaign level)
- A/B test comparison view (which variant is winning)

---

### 3.9 Agent Write-Back Infrastructure

**What it does:**
Each agent writes their output directly to `campaign-data.json`. Changes commit to git. The cockpit reads from git. Full audit trail of who did what and when.

**What's built:**
- Scout → researchAngles, researchFindings, researchSummary, memory.insights
- Copywriter → captions, copyRequirement, captionLength, captionTone
- ImageGen → visualBrief, realPhotoBrief, visualQualityTier, image rules
- Lab → health scores, diagnostics
- TruthCollector → performance data (structure exists, live data pending)
- Clawfix → verificationState on all assets
- Publisher → publishState, postizDraftId, publishedAt
- All writes committed to git
- GitHub Actions regenerate cockpit on push

**Still to build:**
- Agent write-back scripts (automated write path from Discord agent to JSON)
- Webhook triggering (agent write → git commit → cockpit refresh)
- Discord notification routing (approved asset → notify Christelle)
- Write-back staging (write to temp first, only commit on clean exit — prevents partial writes on timeout)
- M3 action loop (agent write → auto-regenerate cockpit without manual push)

---

### 3.10 Campaign Mothership Dashboard

**What it is:**
The user-facing dashboard at `https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html`

**What's built:**
- Overview tab (campaign list, health rings, priority stack)
- Blueprint tab (strategy, pillars, DNA, visual direction per campaign)
- Production Plan tab (30-day calendar, asset counts, pillar distribution, read-only)
- Asset Queue tab (all assets with status, owner, blockedBy)
- Review Queue tab (M7 — approval interface, in progress)
- Build Board (fleet progress on open items)

**What's NOT built:**
- Full M7 Review Queue (interactive approve/reject/edit)
- Campaign creation form (brief entry → campaign created)
- Blueprint acceptance button (Christelle Accepts Blueprint)
- Campaign comparison view
- Calendar view with drag-to-reschedule
- Real-time updates (cockpit refreshes on git push, not live)

---

## 4. The Milestone Map

| Milestone | Description | Status |
|---|---|---|
| M1 | Campaign created — brief, owner, state | ✅ Complete |
| M2 | Blueprint built — strategy, pillars, DNA, visual direction | ✅ Complete |
| M3 | Production plan generated — asset shells, calendar, rules | ✅ Complete |
| M4 | Blueprint builder UI — Blueprint tab in cockpit | ✅ Complete |
| M5 | Production plan generator script + G1-G8 gates | ✅ Complete |
| M6 | Content generation — 36 assets with captions + visual briefs | ✅ Complete |
| M7 | Review + Approval Queue — Christelle's approval interface | 🔴 In progress |
| M8 | Publishing workflow — Postiz integration, live analytics | 🔴 Pending |
| M9 | Analytics wiring — GA4 + Meta → campaign-data.json | 🔴 Pending |
| M10 | Agent write-back automation — scripts + webhook triggering | 🔴 Pending |
| M11 | Campaign templates — Club Fitting, Coaching, Event, Product, Membership | 🟡 Draft spec |
| M12 | Self-diagnosing campaigns — campaign explains own degradation | 🟡 Future |

---

## 5. Current Campaign State

**Active campaign:** "Use the Right Equipment" (ID: `use-the-right-equipment-mq5l90bk`)
- Goal: Drive club fitting bookings, Johannesburg golfers
- Blueprint: Active, version 28
- Assets: 36 total
- Status: 36/36 at `approvalStatus: review` ✅

**Pipeline status:**
```
M1 ✅ Campaign created
M2 ✅ Blueprint generated (28 versions, active: version 28)
M3 ✅ Production plan generated (36 assets, 30-day calendar)
M4 ✅ Blueprint tab in cockpit
M5 ✅ generate-production-plan.py with G1-G8 gates
M6 ✅ 36 assets generated (captions + visual briefs)
M7 🔴 Review queue — in progress (Clawdia building)
M8 🔴 Publishing — blocked on M7
M9 🔴 Analytics — blocked on credentials
M10 🔴 Agent write-back automation — M3 not fully wired
```

---

## 6. What Campaign OS Is NOT

Campaign OS is not:
- A scheduler (it plans content, doesn't auto-publish without approval)
- A storage bin (every asset must be operationally meaningful)
- A reporting dashboard (it shows state with diagnostic explanation, not raw metric walls)
- A content generator without intelligence (every asset is research-grounded)
- A publishing tool (it prepares content for Postiz, Postiz does the actual publishing)
- A vanity metric tracker (health score measures conversion and compounding, not total likes)

---

## 7. Open Blockers

| Blocker | What's Needed | Owner |
|---|---|---|
| M7 Review Queue UI | Full approval interface build | Clawdia |
| Postiz token refresh | Token expires, no auto-refresh | Clawdia |
| GA4 credentials | `ga4PropertyId` per campaign in `campaign-data.json` | Christelle |
| Meta ad account ID | `metaAdAccountId` per campaign | Christelle |
| Agent write-back scripts | Automated write path from agents to JSON | Clawdia |
| M3 action loop | Agent write → cockpit auto-refresh without manual git push | Clawdia |
| GitHub ownership transfer | Personal GitHub account → repo transfer → collaborator-based access | Christelle |

---

## 8. How to Use This Document

**For Christelle:** This is your reference for what the system does, what it doesn't do, and what's still being built. Use it to understand what's been delivered and what to expect next.

**For the fleet:** This is the canonical spec. Before building anything new, reference this document. If something isn't listed here, propose it in #group-chat before building.

**To propose a change:** Present in #group-chat with: what, why, how it improves operational clarity, and how it affects existing schema. Christelle approves or rejects.

---

*Last updated: 2026-06-11 | Version 1.0 | Fleet consensus + Christelle authority*