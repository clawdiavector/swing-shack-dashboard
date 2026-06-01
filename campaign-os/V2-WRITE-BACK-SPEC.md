# Campaign OS v2 — Agent Write-Back Layer
**Version:** 1.0
**Date:** 2026-06-01
**Status:** DRAFT — awaiting GitHub transfer
**Owner:** Clawdia
**Reference:** V2-FOUNDATION-SPEC.md, V2-TEMPLATE-SPEC.md

---

## Purpose

The Agent Write-Back Layer is the operational foundation of Campaign OS. It closes the loop between agent actions and campaign state — ensuring every meaningful action updates the system so the cockpit always reflects what's real.

Without write-back, the cockpit is a static display. With write-back, it becomes a living operational environment where every asset, approval, publish, and analytics update flows back into campaign state automatically.

---

## Architecture

```
Agent Action
    → Validation (pre-write checks)
    → Write to campaign-data.json (or staged change)
    → Git commit
    → Clawfix verification
    → Git push
    → Webhook triggers cockpit refresh
    → Cockpit reflects updated state
```

**Blocking dependency:** GitHub transfer (Christelle personal GitHub account → repo collaborator for clawdiavector)

---

## 1. Which Agents Write Back

| Agent | Domain | Write Frequency | Write Targets |
|-------|--------|----------------|---------------|
| Copywriter | Copy | On generation of each hook/caption variant | `assets[].copy[]` |
| ImageGen | Visual | On generation + on quality gate result | `assets[].visual[]` |
| TruthCollector | Analytics | On daily analytics pull | `analytics.engagement{}`, `analytics.conversions{}` |
| Lab | Health | On health score calculation | `campaign.healthScore`, `campaign.diagnostic` |
| Publisher | Distribution | On post dispatch + Postiz confirmation | `assets[].publishState`, `assets[].publishedAt` |
| Clawfix | Verification | On every write from every agent | `assets[].verificationState` |

**Agents that don't write directly:**
- Scout: Writes research to shared/research/ directory (not campaign-data.json)
- Gremlin: Audit/stress-test only, no state writes
- Memories: Reads and tracks, no campaign state writes

---

## 2. What Each Agent Writes

### Copywriter → `campaign-data.json`

**Triggers:**
- New hook variant generated (on generation, not on approval)
- Caption generated for an asset
- Copy revision after rejection

**Write to:** `assets[].copy[]`

```json
{
  "assetId": "hook-a",
  "type": "hook",
  "copy": [
    {
      "copyId": "hook-a-copy-v1",
      "variantId": "hook-a-v1",
      "headline": "YOUR DRIVE: 217M",
      "subtext": "Pros avg 264m. TrackMan found the gap.",
      "caption": "How does your avg drive compare? TrackMan benchmarking tells you where you stack up. PGA Tour avg: 264m. From R250.",
      "cta": "Book Your Assessment",
      "owner": "copywriter",
      "status": "generated",
      "generatedAt": "2026-06-01T09:00:00Z",
      "qualityGateState": "pending",
      "rejected": false,
      "history": [
        {
          "action": "generated",
          "by": "copywriter",
          "at": "2026-06-01T09:00:00Z",
          "reason": "Round 3 stats hook — club speed angle"
        }
      ]
    }
  ]
}
```

**On rejection:**
```json
{
  "copyId": "hook-a-copy-v1",
  "status": "rejected",
  "rejectedAt": "2026-06-01T12:00:00Z",
  "rejectedBy": "christelle",
  "rejectionReason": "Subtext is too aggressive. Rewrite with softer close.",
  "history": [
    {
      "action": "rejected",
      "by": "christelle",
      "at": "2026-06-01T12:00:00Z",
      "reason": "Subtext is too aggressive. Rewrite with softer close."
    }
  ]
}
```

**On approval:**
```json
{
  "copyId": "hook-a-copy-v1",
  "status": "approved",
  "approvedAt": "2026-06-01T14:00:00Z",
  "approvedBy": "christelle",
  "qualityGateState": "gate2-passed",
  "history": [
    {
      "action": "approved",
      "by": "christelle",
      "at": "2026-06-01T14:00:00Z"
    }
  ]
}
```

---

### ImageGen → `campaign-data.json`

**Triggers:**
- Visual asset generated (on generation completion)
- Visual asset delivered to Discord
- Quality gate result received (passed/failed)
- Visual revision after rejection

**Write to:** `assets[].visual[]`

```json
{
  "assetId": "hook-a",
  "type": "hook",
  "visual": [
    {
      "visualId": "hook-a-visual-v1",
      "variantId": "hook-a-v1",
      "type": "hero-visual",
      "description": "TrackMan data overlay on dark background. Club speed stat.",
      "filePath": "assets/campaigns/trackman/hook-a/hook-a-visual-v1.png",
      "discordMessageId": "1234567890",
      "owner": "image-gen",
      "status": "generated",
      "generatedAt": "2026-06-01T09:30:00Z",
      "qualityGateState": "pending",
      "visualQualityTier": "hero",
      "rejected": false,
      "history": [
        {
          "action": "generated",
          "by": "image-gen",
          "at": "2026-06-01T09:30:00Z",
          "reason": "Hero visual for Hook A — stats angle, dark palette"
        },
        {
          "action": "delivered",
          "by": "image-gen",
          "at": "2026-06-01T09:31:00Z",
          "channel": "discord",
          "messageId": "1234567890"
        }
      ]
    }
  ]
}
```

**On quality gate passed (Clawfix verification):**
```json
{
  "visualId": "hook-a-visual-v1",
  "status": "verified",
  "qualityGateState": "gate1-passed",
  "verificationResult": "passed",
  "verifiedBy": "clawfix",
  "verifiedAt": "2026-06-01T10:00:00Z",
  "history": [
    {
      "action": "verified",
      "by": "clawfix",
      "at": "2026-06-01T10:00:00Z",
      "result": "passed",
      "reason": "Visual matches brief. Dark palette correct. Data overlay legible."
    }
  ]
}
```

**On rejection:**
```json
{
  "visualId": "hook-a-visual-v1",
  "status": "rejected",
  "rejectedAt": "2026-06-01T12:30:00Z",
  "rejectedBy": "christelle",
  "rejectionReason": "Club speed number is wrong. Should be 83 MPH, not 89.",
  "blockedBy": ["incorrect-data"],
  "history": [
    {
      "action": "rejected",
      "by": "christelle",
      "at": "2026-06-01T12:30:00Z",
      "reason": "Club speed number is wrong. Should be 83 MPH, not 89."
    }
  ]
}
```

---

### TruthCollector → `campaign-data.json`

**Triggers:**
- Daily analytics pull (06:00 SAST cron)
- On-demand analytics refresh

**Write to:** `analytics`, `campaign.reach`, `campaign.engagement`, `campaign.conversions`

```json
{
  "analytics": {
    "instagram": {
      "posts": {
        "hook-a": {
          "postId": "cmpnuw1yx0379ql0ywyup8ynm",
          "platformPostId": "IG-post-id",
          "postedAt": "2026-05-27T11:27:00Z",
          "reach": 90,
          "likes": 4,
          "comments": 0,
          "saves": 1,
          "shares": 0,
          "profileVisits": 3,
          "websiteClicks": 2,
          "engagementRate": 4.44,
          "impressions": 155,
          "updatedAt": "2026-06-01T06:00:00Z",
          "dataState": "current"
        }
      },
      "totalFollowers": 412,
      "followerDelta": 3,
      "profileEngagement": 1.7,
      "updatedAt": "2026-06-01T06:00:00Z",
      "dataState": "current"
    },
    "google": {
      "gmbPosts": {},
      "websiteSessions": 847,
      "organicSearchClicks": 234,
      "directBookings": 12,
      "updatedAt": "2026-06-01T06:00:00Z",
      "dataState": "current"
    }
  },
  "campaign": {
    "campaignId": "trackman-intelligence",
    "reach": 1247,
    "engagement": 38,
    "engagementRate": 3.05,
    "conversions": 4,
    "conversionRate": 0.32,
    "revenue": 4200,
    "updatedAt": "2026-06-01T06:00:00Z"
  }
}
```

**On stale data (data > 48h old):**
```json
{
  "postId": "hook-e",
  "dataState": "stale",
  "staleSince": "2026-05-30T06:00:00Z",
  "reason": "No new data in 72h. Post may be in shadowban or platform issue."
}
```

**On no data available:**
```json
{
  "postId": "hook-g",
  "dataState": "NO DATA",
  "reason": "Post has not been published yet. Cannot fetch analytics."
}
```

---

### Lab → `campaign-data.json`

**Triggers:**
- Health score calculation (on demand, min once per hour)
- After significant campaign events (new asset published, approval given, etc.)

**Write to:** `campaign.healthScore`, `campaign.healthBreakdown`, `campaign.diagnostic`

```json
{
  "campaign": {
    "campaignId": "trackman-intelligence",
    "healthScore": 68,
    "healthState": "degraded",
    "healthBreakdown": {
      "assetPipeline": 40,
      "approvalVelocity": 55,
      "publishCadence": 30,
      "engagementTrend": 80,
      "conversionRate": 75
    },
    "diagnostic": "Conversion degraded: last published hook 14 days ago. Hook A best performer never re-published. GMB lapsed 7 days.",
    "healthHistory": [
      {
        "score": 68,
        "state": "degraded",
        "at": "2026-06-01T06:00:00Z",
        "trigger": "scheduled-calculation"
      },
      {
        "score": 82,
        "state": "healthy",
        "at": "2026-05-27T06:00:00Z",
        "trigger": "hook-a-published"
      }
    ],
    "updatedAt": "2026-06-01T06:00:00Z"
  }
}
```

---

### Publisher → `campaign-data.json`

**Triggers:**
- Post dispatched to Postiz (write: scheduled)
- Post confirmed live on platform (write: live)
- Post failed on platform (write: failed)

**Write to:** `assets[].publishState`, `assets[].postizDraftId`, `assets[].publishedAt`, `assets[].publishError`

```json
{
  "assetId": "hook-a",
  "variantId": "hook-a-v1",
  "publishState": "scheduled",
  "postizDraftId": "draft-abc123",
  "scheduledAt": "2026-06-02T09:00:00Z",
  "dispatchedBy": "publisher",
  "dispatchedAt": "2026-06-01T15:00:00Z",
  "platform": "instagram",
  "history": [
    {
      "action": "dispatched",
      "by": "publisher",
      "at": "2026-06-01T15:00:00Z",
      "result": "postiz-accepted",
      "draftId": "draft-abc123"
    }
  ]
}
```

**On Postiz confirmation — live:**
```json
{
  "assetId": "hook-a",
  "publishState": "live",
  "publishedAt": "2026-06-02T09:05:00Z",
  "postizPostId": "post-xyz789",
  "platformPostUrl": "https://instagram.com/p/xyz789",
  "publishedBy": "publisher",
  "confirmationSource": "postiz-webhook",
  "history": [
    {
      "action": "published",
      "by": "publisher",
      "at": "2026-06-02T09:05:00Z",
      "result": "live",
      "platform": "instagram",
      "postUrl": "https://instagram.com/p/xyz789"
    }
  ]
}
```

**On Postiz confirmation — failed:**
```json
{
  "assetId": "hook-a",
  "publishState": "failed",
  "publishError": "Instagram API error: invalid image dimensions. Expected 1080x1080, received 1080x1070.",
  "failedAt": "2026-06-02T09:01:00Z",
  "retryable": true,
  "retryCount": 0,
  "history": [
    {
      "action": "publish-failed",
      "by": "publisher",
      "at": "2026-06-02T09:01:00Z",
      "error": "Instagram API error: invalid image dimensions",
      "retryable": true
    }
  ]
}
```

---

## 3. Which Files Agents Write To

**Primary file:** `campaign-data.json` (root of repo)

```
swing-shack-dashboard/
├── campaign-data.json          ← PRIMARY WRITE TARGET
├── assets/
│   └── campaigns/
│       └── trackman-intelligence/
│           ├── hook-a/
│           │   ├── hook-a-visual-v1.png
│           │   └── hook-a-copy-v1.json
│           └── hook-e/
│               └── ...
└── campaign-os/
    └── V2-FOUNDATION-SPEC.md
    └── V2-TEMPLATE-SPEC.md
```

**Staged changes:** Before writing directly to `campaign-data.json`, agents write to a staging file to enable atomic updates:

```
campaign-data-staged.json  ← atomic write target
```

On successful validation and Clawfix verification, staged file is moved to `campaign-data.json` and committed.

---

## 4. What Triggers a Write

| Trigger | Agent | Write Type |
|---------|-------|------------|
| Hook/caption variant generated | Copywriter | New entry in `assets[].copy[]` |
| Copy approved by Christelle | Clawfix | `status: approved` + `qualityGateState` |
| Copy rejected by Christelle | Clawfix | `status: rejected` + `rejectionReason` |
| Visual asset generated | ImageGen | New entry in `assets[].visual[]` |
| Visual delivered to Discord | ImageGen | `discordMessageId` + `status: delivered` |
| Visual quality gate passed | Clawfix | `qualityGateState: gate1-passed` |
| Visual rejected by Christelle | Clawfix | `status: rejected` + `blockedBy` |
| Daily analytics pull | TruthCollector | Full `analytics` section update |
| Health score calculated | Lab | `campaign.healthScore` + `diagnostic` |
| Post dispatched to Postiz | Publisher | `publishState: scheduled` |
| Post confirmed live | Publisher | `publishState: live` + `publishedAt` |
| Post failed | Publisher | `publishState: failed` + `publishError` |

**Write-back rules:**
1. Every meaningful action triggers a write. "Meaningful" = state changes or new data arrives.
2. Writes are idempotent. Re-writing the same state is safe.
3. Writes are append-only for `history[]`. Only field-level updates for state fields.
4. No deletes from `campaign-data.json`. Only status changes (rejected, failed, etc.).

---

## 5. What Validation Happens Before Writing

Before any agent writes to the staged file, pre-write validation runs:

### Copywriter Pre-Write Validation
```
1. Schema validation — copy object matches expected structure
2. Required fields present — copyId, headline, caption, owner
3. No duplicate copyId — reject if copyId already exists
4. Caption length check — max 2200 chars (Instagram limit)
5. No phone numbers in caption — GMB policy compliance
6. No prohibited content — check against content policy
```

### ImageGen Pre-Write Validation
```
1. Schema validation — visual object matches expected structure
2. Required fields present — visualId, type, filePath, owner
3. File exists at specified path — verify asset file is present
4. File size check — max 8MB for Instagram, 20MB for TikTok
5. Image dimensions — verify match platform spec (1080x1080 etc.)
6. No duplicate visualId — reject if visualId already exists
```

### TruthCollector Pre-Write Validation
```
1. Data freshness check — analytics data must be < 48h old
2. Required metrics present — reach, likes, engagementRate
3. No negative values — metrics must be >= 0
4. Rate sanity check — engagement rate must be <= 100%
5. Source attribution — each metric must have a source field
```

### Lab Pre-Write Validation
```
1. Health score range — must be 0-100
2. Breakdown sums to valid total — individual scores weighted correctly
3. Diagnostic is non-empty when healthState is degraded
4. No duplicate timestamps in healthHistory
```

### Publisher Pre-Write Validation
```
1. Postiz response is valid — draft ID present, no API errors
2. Platform target is valid — instagram/tiktok/gmb
3. Asset exists before dispatching — assetId must exist in campaign
4. Not already published — check publishState !== 'live'
5. Postiz credentials valid — auth check before dispatch
```

---

## 6. How Clawfix Verifies Every Write

Clawfix is the verification layer. It runs on every write before the staged file is committed to `campaign-data.json`.

### Clawfix Verification Sequence

```
Agent writes to campaign-data-staged.json
    → Clawfix receives write notification
    → Clawfix reads staged file
    → Clawfix runs verification checks:
        1. Schema integrity — does the file still parse? Any corruption?
        2. Field-level validation — do all fields pass type/range checks?
        3. Consistency check — does this write contradict previous state?
        4. blockedBy resolution — are all blockers still valid?
        5. History integrity — is history[] append-only? Any gaps?
        6. Ownership — is the writing agent authorized for this domain?
    → If passed:
        → Move staged → campaign-data.json
        → Git commit with write summary
        → Git push
        → Webhook fires to cockpit
    → If failed:
        → Reject write
        → Notify agent
        → Log verification failure with reason
        → Agent must fix and retry
```

### Clawfix Verification Rules

```javascript
const verificationRules = {
  schemaIntegrity: {
    check: "campaign-data.json parses without error",
    failAction: "Reject write. File may be corrupted."
  },
  fieldValidation: {
    check: "All fields pass type/range validation against V2-FOUNDATION-SPEC schema",
    failAction: "Reject write. Return validation errors to agent."
  },
  consistencyCheck: {
    check: "New state does not contradict known previous state",
    failAction: "Reject write. Flag potential race condition or data conflict."
  },
  blockedByResolution: {
    check: "If blockedBy[] is populated, the blocking condition is still true",
    failAction: "Flag — blockedBy should be cleared if condition is resolved."
  },
  historyIntegrity: {
    check: "history[] is append-only. No edits to existing entries.",
    failAction: "Reject write. history[] violations are treated as critical."
  },
  ownershipCheck: {
    check: "Writing agent is authorized for the domain they're writing to",
    failAction: "Reject write. Log unauthorized write attempt."
  }
}
```

### Clawfix Write Summary Format

Every Clawfix-verified commit includes a write summary in the git commit message:

```
[write] Copywriter → assets.hook-a.copy[copyId: hook-a-copy-v1] — new copy generated
[write] ImageGen → assets.hook-a.visual[visualId: hook-a-visual-v1] — visual generated
[write] Publisher → assets.hook-a.publishState: scheduled — post dispatched to Postiz
[verify] Clawfix → campaign-data.json — schema OK, committed
```

---

## 7. How the Cockpit Updates After the Write

### Update Flow

```
Git push (campaign-data.json updated)
    → Git webhook fires
    → Webhook payload: { campaignId, changedFields[], commitHash }
    → OpenClaw cron or webhook receiver processes payload
    → campaign-data.json is re-read
    → Cockpit HTML is regenerated from template + data
    → New cockpit is deployed to GitHub Pages
    → Operators see updated state on next refresh (or auto-refresh)
```

### What Triggers a Cockpit Regeneration

| Event | Trigger | Update Scope |
|-------|---------|--------------|
| New asset generated | Agent write-back | Asset board, Missing Assets, Highest Leverage |
| Asset approved | Christelle approval | Approval queue, Production view, Completion |
| Asset rejected | Christelle rejection | Production view, blockedBy[] flags |
| Asset published | Publisher confirmation | Production view, Calendar, Campaign health |
| Analytics updated | TruthCollector pull | Campaign overview, engagement metrics, A/B results |
| Health score change | Lab calculation | Health ring, diagnostic, Campaign overview |
| New campaign created | Campaign Factory | All views reset for new campaign |

### Cockpit Update Latency

- **Ideal:** < 60 seconds from Git push to live cockpit update
- **Acceptable:** < 5 minutes
- **Measured:** tracked in HEARTBEAT.md per cron job

### Manual Refresh Option

Operators can force a cockpit refresh via:
- OpenClaw command: `openclaw cron run refresh-cockpit`
- Or wait for the automatic refresh cycle

---

## Implementation Sequence

### Phase 1: GitHub Transfer (BLOCKS ALL)
```
Christelle creates personal GitHub account
→ Initiates repo transfer to collaborator model
→ clawdiavector becomes collaborator (not owner)
→ Agents gain authenticated write access
```

### Phase 2: Write-Back Infrastructure
```
1. Create campaign-data.json schema with all domains
2. Set up write staging mechanism (campaign-data-staged.json)
3. Configure Clawfix verification on every write
4. Set up GitHub webhook for cockpit trigger
5. Test write-back loop with single agent (Copywriter first)
```

### Phase 3: Agent Write Scripts
```
Copywriter → write-back script (test first)
ImageGen → write-back script
TruthCollector → write-back script
Lab → write-back script
Publisher → write-back script
```

### Phase 4: Cockpit Live Updates
```
1. Webhook receiver configured
2. Cockpit regeneration triggered on each push
3. Latency measured and optimized
4. Auto-refresh implemented
```

---

## Summary — What This Achieves

| Before Write-Back | After Write-Back |
|-------------------|------------------|
| Cockpit shows last known state | Cockpit shows current state |
| Assets exist in Discord, not in system | Assets written to campaign-data.json |
| Approvals don't update state | Approval updates asset status + history |
| Publishing state unknown | publishState reflects: scheduled → live/failed |
| Analytics are stale snapshots | Analytics update daily, flagged when stale |
| No one knows what's real | Truthful state always visible |
| Christelle discovers work | Christelle is notified when action is required |

---

**Next:** Implement Phase 1 (GitHub transfer) to unblock all agent write-back.