# Campaign OS — Full Specifications & Requirements
**Version:** 1.0
**Date:** 2026-06-11
**Status:** Living document — reflects current committed state + target state
**Owner:** Fleet (Christelle authority)
**Reference:** V2-FOUNDATION-SPEC.md (operational philosophy), V2-TEMPLATE-SPEC.md (schema), V2-WRITE-BACK-SPEC.md (write-back layer)

---

## PURPOSE

This document is the single source of truth for what Campaign OS is, what exists today, what works, and what must be built to reach full function.

It is structured as:
- **Part 1:** Specifications — what is built and how it works
- **Part 2:** Requirements — what is missing and in what priority order
- **Part 3:** Architecture — how the pieces connect

Read this document to understand the current state of the system, what each component does, and what remains to be built.

---

# PART 1 — SPECIFICATIONS (WHAT EXISTS)

---

## 1. Core Concepts

### What Campaign OS Is

A campaign production machine that lives in GitHub Pages, backed by a JSON data file, maintained by a fleet of agents. Every campaign, asset, and decision is stateful, inspectable, and honest.

The system answers four questions at all times:
1. **What is the state of every campaign?** (campaign list, health rings)
2. **What is the state of every asset?** (caption, visual, approval, publishing)
3. **What is blocked and why?** (blockedBy[], quality gates, pending approvals)
4. **What is the highest-leverage next action?** (nextAction field, priority stack)

### What Campaign OS Is Not

- Not a scheduler (Postiz owns scheduling)
- Not a content library (assets exist in campaign-data.json, files on disk)
- Not a reporting layer (Truth Collector owns analytics)
- Not a design tool (ImageGen generates, assets are files)

### The Data Model

```
campaign-data.json
├── campaigns/{campaignId}
│   ├── identity{}          Campaign identity
│   ├── brief{}             Campaign brief
│   ├── strategy{}          Strategy notes
│   ├── assets{}            All production assets (key = assetId)
│   ├── blueprint{}         Strategy blueprint (pillars, DNA, visual direction)
│   ├── productionPlan{}    Production schedule + asset shells
│   ├── researchAngles[]    Scout's research angles
│   ├── researchFindings[]  Scout's atomic findings
│   ├── researchSummary{}   Competitive landscape summary
│   ├── memory{}            Campaign notes, history, insights
│   ├── pipeline{}          Pipeline state machine
│   └── healthScore{}       Lab's health diagnostic
```

Each `assets[assetId]` has:
```
assetId, campaignId, name, assetType, pillar, pillarName, objective
caption, captionStatus, captionDraft, captionLength, captionTone, copyRequirement
visualBrief, realPhotoBrief, aiAllowedFor, aiForbiddenFor, visualStatus, visualQualityTier
approvalStatus, approvalState, qualityGateState
publishStatus, platform, contentType, owner
realImageNeeded, aiImageAllowed
researchRefs[], findingIds[]
history[], status
```

---

## 2. What's Built and Working

### A. Campaign Data Layer ✅

**Location:** `campaign-os/campaign-data.json`
**Status:** Active, committed, GitHub Pages backed

4 campaigns exist:
- `trackman-intelligence` (evergreen, 0 assets, blueprint not built)
- `takomo-101t` (product-launch, 4 assets, Takomo 101T club fitting — has rejected visual)
- `winter-golf` (seasonal, 0 assets, not started)
- `use-the-right-equipment-mq5l90bk` (awareness, 36 assets, fully briefed through M6)

The "Use the Right Equipment" campaign is the most complete — it has:
- Full blueprint (version 289, active, 5 pillars, DNA, visual direction)
- Research angles (7 angles) and findings (7 findings) from Scout
- Production plan with 30-day calendar
- 36 asset shells with research grounding
- M6 complete — all 36 assets at `approvalStatus: review`

**Write-back path:** Agent writes → Git commit → GitHub Actions → `cockpit-operational.html` regenerated → deployed to GitHub Pages (~60s latency after push)

---

### B. Cockpit Dashboard ✅

**Location:** `https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html`
**Status:** Live, regenerating from campaign-data.json on every push

Views available:
1. **Campaign List** — all 4 campaigns, health rings, status
2. **Campaign Detail / Blueprint** — strategy, pillars, DNA, visual direction
3. **Production Plan** — 30-day calendar, asset counts, pillar distribution
4. **Asset Queue** — all assets with caption/visual/approval/publish status

**Current limitation:** Cockpit reads from embedded campaign-data at build time. Real-time updates require Git push. No live WebSocket connection.

---

### C. Blueprint Generation (M2) ✅

**Location:** `scripts/generate-blueprint.py`
**Status:** Built, tested, committed

Blueprint includes:
- `dna` — tone, contentMix, CTA philosophy
- `pillars[]` — 5 pillars with id, name, hook, visualBrief, copyDirection, postingSchedule, contentType
- `visualDirection` — mood, colorPalette, typography, layout principles

Trigger condition: `blueprint.active === true` + `blueprintVersion >= 1` + `pillars.length >= 3`

---

### D. Production Plan Generation (M5) ✅

**Location:** `scripts/generate-production-plan.py`
**Status:** Built, G1-G8 validation passing, committed

Generates:
- `productionPlan.assetRequirements` — asset counts by type
- `productionPlan.calendar[]` — 30-day rolling publish schedule
- `productionPlan.realImageRule` — equipment campaign real-image enforcement
- Asset shells in `assets[]` with pillar, contentType, platform, researchRefs, visual/copy requirement fields

G1-G8 gates validate: non-zero counts, calendar length, unique assetIds, pillar coverage, real image rule, platform coverage, no duplication, status consistency.

---

### E. M6 Content Generation Pipeline ✅

**Status:** Complete for "Use the Right Equipment" campaign (36/36 assets)

Process:
- Locked batch manifests (no scope drift allowed)
- Copywriter writes captions → `captionStatus: draft`, `caption` field populated
- ImageGen writes visual briefs → `visualStatus: brief-written`, `visualBrief`, `aiAllowedFor`, `aiForbiddenFor`, `realPhotoBrief` populated
- Clawfix gates verify all fields before batch closes
- Christelle approves batches

Rules enforced:
- Equipment campaign: `realImageNeeded: true`, `aiImageAllowed: false` for all non-story assets
- Stories: `aiImageAllowed: true` (AI for background/layout/typography only)
- No fake club heads, no AI golfer likeness, no AI swing motion
- `visualQualityTier`: hero/supporting/seasonal per asset role

---

### F. Template Schema ✅

**Location:** `V2-TEMPLATE-SPEC.md`
**Status:** v1.1, locked

5 campaign types defined:
- `club-fitting` — TrackMan fitting focus, real photography required
- `coaching` — instructor-led, requires real instructor photography
- `event` — leaderboard graphics, format only
- `product` — Takomo clubs, real product photography required, `requiresRealProductImage: true`
- `membership` — retention/upgrade, softer sell

Each type specifies: contentMix, cadence, asset types, visual requirements, heroVisual specs, story specs, GMB specs.

---

### G. Write-Back Specification ✅

**Location:** `V2-WRITE-BACK-SPEC.md`
**Status:** v1.0, committed

Defines:
- Which agents write (Copywriter, ImageGen, Truth Collector, Lab, Publisher, Clawfix)
- What they write and where
- Write triggers and validation
- Git commit → Clawfix verification → webhook → cockpit refresh chain
- Staged writes (campaign-data-staged.json) → Clawfix → campaign-data.json

**Current limitation:** Write-back scripts for Copywriter, ImageGen, Truth Collector, Lab not yet built. Clawfix verification service exists but not yet wired to all agent write paths.

---

### H. Foundation Philosophy ✅

**Location:** `V2-FOUNDATION-SPEC.md`
**Status:** LOCKED

8 Pillars of Campaign OS v2:
1. Delivery verification via file:line (if Clawfix has not verified it, it is NOT done)
2. 3-gate pipeline (Verification → Quality → Distribution)
3. Core asset contract (every asset has id, type, owner, status, timestamps, qualityGateState, history, blockedBy[])
4. No fake data (NO DATA > false metrics)
5. blockedBy[] as first-class intelligence signal
6. Calm over noisy UX
7. Leverage over activity
8. Explainable over inspectable

---

## 3. Agent Lanes — What Each Does

| Agent | Core Function | Where They Operate |
|-------|--------------|-------------------|
| **Scout** | Market research, competitive intel, audience insights | Writes to `campaign.researchAngles[]`, `campaign.researchFindings[]`, `campaign.memory.insights[]` |
| **Clawdia** | Campaign orchestration, blueprint, production planning | Writes to `campaign.blueprint{}`, `campaign.productionPlan{}`, `campaign.assets[]` |
| **Copywriter** | Caption drafts, copy direction, hashtag strategy | Writes to `assets[].caption`, `assets[].captionStatus`, `assets[].copyRequirement` |
| **ImageGen** | Visual briefs, image rules, real photography requirements, brand QC | Writes to `assets[].visualBrief`, `assets[].aiAllowedFor`, `assets[].aiForbiddenFor`, `assets[].realPhotoBrief` |
| **Publisher** | Platform format compliance, GMB rules, publishing readiness, Postiz dispatch | Writes to `assets[].publishStatus`, `assets[].postizDraftId`, `assets[].publishedAt` |
| **Clawfix** | Verification — every asset checked against gates before it moves forward | Writes to `assets[].qualityGateState`, `assets[].verificationState` |
| **Truth Collector** | Real analytics from GA4 and Meta — not fake metrics | Writes to `campaign.analytics{}`, `assets[].engagement{}` |
| **Lab** | Health scoring — conversion signals, not vanity metrics | Writes to `campaign.healthScore{}`, `campaign.diagnostic` |
| **Memories** | Decision logging, build board tracking | Reads and logs, no campaign state writes |

---

## 4. Campaign OS Workflow (M1–M8)

```
M1 — Campaign Created
    └── Scout researches market + audience
        → writes researchAngles[], researchFindings[], researchSummary
        → memory.insights[] populated

M2 — Blueprint Built
    └── Clawdia creates strategy, pillars, DNA, visual direction
        → blueprint{} with pillars[], dna{}, visualDirection{}
        → blueprint.active = true, blueprintVersion incremented

M3 — Write-Back Infrastructure
    └── Agent → campaign-data.json → Clawfix → Git push → webhook → cockpit refresh
        → NOT YET BUILT (blocking all automatic write paths)

M4 — Content Briefed
    └── Copywriter writes copyRequirement, captionAngles, copyDirection
    └── ImageGen writes visualBrief, realPhotoBrief, aiAllowedFor, aiForbiddenFor

M5 — Production Plan Generated
    └── Clawdia runs generate-production-plan.py
        → productionPlan{} with calendar, assetRequirements, realImageRule
        → Asset shells created in assets[]

M6 — Content Generated (batched)
    └── Copywriter writes captions → captionStatus: draft
    └── ImageGen writes visual briefs → visualStatus: brief-written
    └── Clawfix gates verify before batch closes
    └── Christelle reviews batch → approvalStatus: review

M7 — Review + Approval Workflow ⏳ IN PROGRESS
    └── Review Queue UI in cockpit
    └── Christelle approves/rejects/revises through UI
    └── Rejection reason + lane assignment required
    └── Batch tools: select all, bulk approve/reject
    └── Approved assets do NOT auto-publish

M8 — Publishing Workflow 🔴 BLOCKED (M7 incomplete)
    └── Publisher dispatches approved assets to Postiz
    └── Postiz confirmation → publishStatus: published
    └── Real photography sourced for equipment campaign assets
    └── Platform compliance verified before dispatch
```

---

## 5. Cockpit Views — What Each Shows

### Campaign List View
- All campaigns with name, type, status
- Health rings (color-coded conversion signals)
- Priority stack (ordered by leverage)
- Quick links to detail views

### Blueprint View
- Campaign identity and brief
- 5 pillars with hooks, visual briefs, copy directions
- DNA (tone, contentMix, CTA philosophy)
- Visual direction (mood, palette, typography)
- Blueprint version and generation timestamp

### Production Plan View
- Asset requirements summary (feed-post: X, carousel: Y, reel: Z, story: W, gmb-post: V)
- 30-day calendar grid (platform × content type × pillar)
- Real image rule status (enforced vs not)
- Pillar distribution chart

### Asset Queue View
- All 36 assets in table format
- Columns: assetId, name, pillar, contentType, platform, captionStatus, visualStatus, approvalStatus, publishStatus, owner, nextAction
- Filter by: pillar, contentType, platform, status
- Sort by: pillar, planned date, status

### Review Queue View ⏳ (M7 — in progress)
- All assets at approvalStatus=review
- Caption draft visible
- Visual brief visible
- Real photo brief visible
- Image rules visible (aiAllowedFor, aiForbiddenFor, realImageNeeded)
- Quick actions: Approve, Reject, Request Revision
- Batch tools: select all, bulk approve, bulk reject

---

## 6. Safety Rules

### Publishing Safety
```
canMoveToPublish(asset) =
  approvalStatus === 'approved'
  AND captionStatus === 'approved'
  AND visualStatus === 'approved'
  AND realImageRulePassed === true
  AND publisherGatePassed === true
```

No `publishStatus: submitted` unless all conditions met.

### Equipment Campaign Rules
- `realImageNeeded: true` for all non-story assets
- `aiImageAllowed: false` for all equipment/product visuals
- AI forbidden for: club heads, equipment on-face, golfer likeness, swing motion
- AI allowed for: background, lighting, layout, typography treatment, text overlays
- `productImageryRule` enforced: real photography > official imagery > AI with product cutout > AI fallback

### Rejection Rules
- Rejection requires: reason (required), what must change (required), assigned lane (required)
- `reviewHistory[]` entry written on every approval/rejection/revision
- Silent failures prohibited — no asset moves state without a logged reason

### No Fake Data Rules
- `NO DATA` > false metrics
- `BLOCKED` > pretending work progresses
- `UNVERIFIED` > assumed truth
- `FAILED` > silent collapse

---

# PART 2 — REQUIREMENTS (WHAT'S MISSING)

---

## Priority 1 — M7 Review Queue (ACTIVE BUILD)

**Owner:** Clawdia (implementation), Clawfix (verification)

### What's needed:
1. **Review Queue tab** in cockpit — all 36 assets visible, filters work
2. **Quick actions per asset** — Approve, Reject, Request Revision
3. **Rejection modal** — reason required, lane assignment required
4. **Caption + Visual Brief editing** — inline or modal edit, persists to localStorage
5. **Batch tools** — select all, bulk approve, bulk reject
6. **Safety gates** — nothing moves to publishStatus=submitted unless all conditions pass
7. **localStorage persistence** — mid-review state survives cockpit regeneration
8. **Final write-back** — Clawfix writes review decisions to campaign-data.json on round close

### Current status:
- Clawdia has the implementation plan (Gates 1-7)
- Gate 1 (Review Queue tab) is in progress
- All 36 assets are at `approvalStatus: review` and ready

### Verification gates:
- G1: All 36 assets visible in review queue
- G2: Approve/reject changes persist
- G3: Rejection reason required
- G4: Caption edit persists
- G5: Visual brief edit persists
- G6: Approved assets do NOT auto-publish
- G7: No Postiz drafts created during review phase

---

## Priority 2 — M8 Publishing Workflow 🔴 BLOCKED

**Owner:** Publisher (primary), Clawdia (infrastructure)

### What's needed:
1. **Postiz API integration** — Publisher dispatches approved assets to Postiz
2. **Publish flow:** `approved → submitted → scheduled → live` (or `failed` / `skipped`)
3. **Postiz draft creation** — approved assets create drafts in Postiz (not published yet)
4. **Postiz confirmation loop** — webhook from Postiz confirms draft created → `postizDraftId` written
5. **Real photography sourcing** — equipment campaign assets with `realImageNeeded: true` need real photos before publishing
6. **Publish readiness check** — Publisher verifies platform format, GMB compliance, image rules before dispatch
7. **Real image gate** — Clawfix verifies real photography exists before `publishStatus: submitted`

### Current status:
- `publishStatus` field exists on all assets
- No Postiz integration built
- No publish flow implemented
- Real photography not sourced for any equipment campaign asset

### Publish status machine:
```
planned → submitted (Publisher dispatches approved asset)
submitted → scheduled (Postiz accepts draft)
scheduled → live (Postiz confirms publication)
submitted → failed (Postiz returns error)
planned → skipped (Christelle skips)
```

---

## Priority 3 — M3 Agent Write-Back Infrastructure 🔴 BLOCKED

**Owner:** Clawdia (infrastructure), each agent (write scripts)

### What's needed:
1. **Write-back scripts per agent:**
   - Copywriter: write captions to campaign-data.json on generation
   - ImageGen: write visual briefs on generation
   - Truth Collector: write analytics data on daily pull
   - Lab: write health scores on calculation
   - Publisher: write publish state on dispatch/confirmation

2. **Staged write path:**
   - Agent writes to `campaign-data-staged.json`
   - Clawfix verifies staged changes
   - Clawfix commits to `campaign-data.json`
   - Git push fires → webhook → cockpit refresh

3. **Webhook infrastructure:**
   - GitHub webhook fires on push to main
   - Webhook calls regeneration script
   - `regenerate-cockpit.py` reads campaign-data.json → rewrites cockpit HTML
   - Latency target: <60s from push to live

4. **Clawfix verification service:**
   - Clawfix reads staged changes
   - Runs gate checks (file exists, schema valid, quality gate passed, etc.)
   - Writes verification result
   - Commits or rejects staged changes

### Current status:
- V2-WRITE-BACK-SPEC.md exists and is detailed
- No write-back scripts built for any agent
- Staged write path not implemented
- Webhook fires but regeneration script had a dict/list bug (fixed by Clawfix)
- Clawfix verification service concept exists but not wired to agent write paths

### Why this is blocking:
Without M3, agents cannot write to campaign-data.json automatically. Every state change requires manual intervention or a human-committed push. The operational loop is broken.

---

## Priority 4 — Truth Collector Analytics Wiring 🔴 BLOCKED

**Owner:** Truth Collector

### What's needed:
1. **GA4 credentials** — `ga4PropertyId` per campaign in campaign-data.json
2. **Meta Ads API access** — `metaAdAccountId` per campaign
3. **Analytics write script** — pulls engagement/conversion data, writes to `campaign.analytics{}`
4. **Asset-level analytics** — `assets[].engagement{}` with reach, saves, shares, link clicks, conversions
5. **Campaign-level analytics** — `campaign.analytics{}` with overall performance
6. **No fake metrics rule** — if analytics source is disconnected, show `NO DATA` not fallback values

### Current status:
- Truth Collector is built and has a script structure
- `analyticsConfig` fields don't exist in campaign-data.json
- No GA4 or Meta credentials configured
- Analytics dashboard in cockpit shows `NO DATA` (correct behavior)

---

## Priority 5 — Health Scoring (Lab) 🔴 BLOCKED

**Owner:** Lab

### What's needed:
1. **Health score calculation** — conversion-weighted, not vanity metrics
2. **Health ring display** — in Campaign List view, color-coded
3. **Diagnostic string** — explains why score is what it is
4. **blockedBy[] integration** — stalled approvals, rejected assets, pending reviews shown in health
5. **Trend data** — is health improving or degrading?

### Current status:
- `campaign.healthScore` field exists but is `null` on all campaigns
- Health ring display is `null` (no score)
- Lab has the concept but no live calculation
- Blocked on M3 (write-back) to close the feedback loop

### Health scoring principles (from Foundation Spec):
- Must prioritize conversion, compounding value, quality engagement, strategic momentum
- Low likes + high bookings + high saves + strong retention may be healthier than "viral"
- Health diagnostic should surface leverage blockers, not just report numbers

---

## Priority 6 — New Campaign Instantiation 🔴 NOT BUILT

**Owner:** Clawdia

### What's needed:
1. **Campaign Factory** — instantiates a campaign from a V2-TEMPLATE-SPEC.md template
2. **Brief intake** — Christelle enters: campaign name, type, goal, duration, target audience, platforms
3. **Auto-runs M1-M2-M5** — Scout research → Blueprint generation → Production plan
4. **No manual setup** — new campaign is operational in one step

### Current status:
- Templates exist (V2-TEMPLATE-SPEC.md)
- No factory script
- New campaigns require manual setup by Clawdia
- Takomo 101T and Winter Golf campaigns are incomplete shells

---

## Priority 7 — Scout Research Phase Automation 🔴 PARTIAL

**Owner:** Scout

### What's needed:
1. **Research pipeline script** — automates the research pass for new campaigns
2. **Competitive intel gathering** — competitor analysis, audience query clusters
3. **researchAngles[] generation** — structured angles per pillar
4. **researchFindings[] generation** — atomic findings with source attribution
5. **researchSummary generation** — competitive landscape brief
6. **memory.insights[]** — platform performance patterns from historical data

### Current status:
- Scout wrote research for "Use the Right Equipment" manually
- Research arrays exist (7 angles, 7 findings)
- No automation script
- New campaign requires Scout to manually research and write

---

## Priority 8 — Discord Routing + Notification 🔴 NOT BUILT

**Owner:** Clawdia

### What's needed:
1. **Campaign status notifications** — Christelle gets pinged when approval is needed
2. **Asset completion notifications** — relevant agents get pinged when their lane is needed
3. **Blocker alerts** — when an asset is blockedBy something, the blocking agent gets pinged
4. **Publishing confirmation** — Christelle gets notified when assets go live

### Current status:
- Agents communicate in Discord group chat
- No structured notification routing
- Christelle has to monitor the group chat manually
- No automated alerts for state changes

---

# PART 3 — ARCHITECTURE

---

## How the Pieces Connect

```
Christelle (decision authority)
    │
    ▼
campaign-data.json (source of truth)
    │
    ├──▶ cockpit-operational.html (GitHub Pages, regenerates on push)
    │
    ├──▶ Agents (read state, write actions)
    │       │
    │       ├──▶ Copywriter ──writes──▶ campaign-data.json
    │       ├──▶ ImageGen ──writes──▶ campaign-data.json
    │       ├──▶ Scout ──writes──▶ research arrays
    │       ├──▶ Publisher ──writes──▶ publishStatus
    │       ├──▶ TruthCollector ──writes──▶ analytics{}
    │       └──▶ Lab ──writes──▶ healthScore{}
    │
    └──▶ Clawfix ──verifies──▶ staged writes ──commits──▶ campaign-data.json
                                                    │
                                                    ▼
                                           GitHub Actions ──push──▶ Webhook
                                                                      │
                                                                      ▼
                                                             cockpit refresh (<60s)
```

---

## Key Files and Their Roles

| File | Role |
|------|------|
| `campaign-os/campaign-data.json` | Single source of truth — all campaign state |
| `campaign-os/cockpit-operational.html` | Live dashboard — reads embedded campaign data |
| `scripts/generate-blueprint.py` | M2 — builds campaign blueprint |
| `scripts/generate-production-plan.py` | M5 — builds production plan + asset shells |
| `scripts/regenerate-cockpit.py` | Reads campaign-data.json → rewrites cockpit HTML |
| `V2-FOUNDATION-SPEC.md` | Operational philosophy — why the system exists |
| `V2-TEMPLATE-SPEC.md` | Template schema — campaign type definitions |
| `V2-WRITE-BACK-SPEC.md` | Write-back layer — agent → data → cockpit flow |
| `V2-CAMPAIGN-OS-FULL-SPEC.md` | This document — full spec + requirements |

---

## What's Live Today

✅ **Campaign data layer** — 4 campaigns, 40 assets, all state tracked  
✅ **Cockpit dashboard** — live at GitHub Pages, regenerates on push  
✅ **Blueprint generation** — M2 works for "Use the Right Equipment"  
✅ **Production plan generation** — M5 works with G1-G8 validation  
✅ **M6 content pipeline** — 36 assets fully briefed through batched process  
✅ **Template schemas** — 5 campaign types defined  
✅ **Write-back specification** — detailed spec committed  
✅ **Foundation philosophy** — locked, guides all decisions  
✅ **Safety rules** — publish gates, equipment rules, real image rules enforced  
✅ **Fleet communication protocol** — @mention, one addressee, no loops

---

## What's Missing for Full Function

| Priority | Item | Blocks |
|----------|------|--------|
| 1 | M7 Review Queue UI | M8 Publishing |
| 2 | M8 Publishing Workflow | Live publishing |
| 3 | M3 Write-Back Infrastructure | All automatic agent writes |
| 4 | Truth Collector Analytics | Campaign health scoring |
| 5 | Health Scoring (Lab) | Campaign diagnostics |
| 6 | Campaign Factory | New campaign instantiation |
| 7 | Scout Research Automation | Research phase for new campaigns |
| 8 | Discord Notification Routing | Operational alerting |

---

## Cockpit URL

**Live:** `https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html`

**Repository:** `https://github.com/clawdiavector/swing-shack-dashboard`

---

## Decision Authority

Christelle is the decision authority. The fleet operates by:
1. Doing the work
2. Verifying the work (Clawfix gates)
3. Showing Christelle the results
4. Waiting for approval or correction

No agent publishes, ships, or marks complete without Christelle's review. No agent bypasses the gate system. No fake data enters the system.

---

*Document version: 1.0 | Last updated: 2026-06-11 | Status: Living*