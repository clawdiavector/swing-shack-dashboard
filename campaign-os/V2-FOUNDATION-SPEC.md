# Campaign OS v2 — Foundation Spec
**Version:** 2.0
**Date:** 2026-05-28
**Status:** LOCKED — Build phase active
**Owner:** Clawdia
**Source:** Fleet alignment (Christelle authority)

---

## Purpose

This document is the constitutional architecture reference for Campaign OS v2. It explains WHY the system exists, not just WHAT the fields are. Every future decision, implementation, and verification step references this document.

The fleet independently converged on these principles from multiple domains. That convergence is the signal that the architecture is coherent.

---

## 1. Operational Philosophy

### The North Star

> Campaign OS is: "A calm, inspectable, AI-native campaign operating environment that always tells the truth about the state of the work and helps surface the highest-leverage next action."

Campaign OS is not:
- A dashboard
- A scheduler
- A content tracker
- A reporting layer
- A storage bin for generated content

Campaign OS is:
- An operational intelligence layer
- A living campaign environment
- An auditable operational ledger
- A collaborative AI-native workspace

### Why Operational Philosophy Exists

The architecture exists to solve a specific problem: marketing automation at scale produces chaos without an explicit operational layer.

Agents generate content. Content goes to multiple platforms. Platforms return fragmented data. Data sits in isolation. No one knows what is real, what is blocked, what is working, or what needs attention.

Campaign OS solves this by being the single operational truth layer — where every campaign, asset, and decision is stateful, inspectable, and honest.

### Core Philosophical Principles

**A. Truthful State > Complete State**

The system must prefer honest gaps over fake completeness.

Examples:
- `NO DATA` is better than fake metrics
- `BLOCKED` is better than pretending work is progressing
- `UNVERIFIED` is better than assumed truth
- `FAILED` is better than silent collapse

Operational trust compounds. False confidence destroys systems.

**B. Operational Meaning Is Mandatory**

An object only exists in Campaign OS if it is operationally meaningful. Every object must help answer:
- What is happening?
- Why is it happening?
- Who owns it?
- What state is it in?
- What is blocking it?
- What happens next?

If an object cannot answer those questions, it is noise and should not exist in the system.

**C. Explainable Beats Merely Inspectable**

Inspectable answers: what changed?
Explainable answers: why did it change? what caused it? what was the tradeoff? what decision triggered it?

The system should increasingly explain itself like a competent operator would — not just report state, but explain reasoning.

**D. blockedBy[] Is a First-Class Intelligence Signal**

Multiple agents independently surfaced `blockedBy[]` as operationally critical. That convergence is a signal.

It is not metadata. It is a first-class operational intelligence signal.

Campaign OS should aggressively surface:
- Bottlenecks
- Stalled dependencies
- Hidden blockers
- Unresolved approvals

The system should naturally answer: "What is slowing the campaign down?" without requiring investigation.

**E. Calmness Is an Operational UX Principle**

This is not aesthetic preference. It is operational design.

A good Campaign OS should make Christelle feel:
- Oriented
- Informed
- Calm
- Decisive

NOT:
- Overwhelmed
- Behind
- Buried in updates
- Forced into Discord archaeology

Every feature should be evaluated against this. If it creates noise instead of calm, it is complexity debt.

**F. Leverage Over Activity**

The system should surface:
- Highest-leverage fixes
- Highest-impact blockers
- Most dangerous hidden failures
- Strongest opportunities

NOT:
- Longest activity feeds
- Biggest metric walls
- Most recent updates

Operational clarity beats operational noise.

**G. No Agent Output Dumping**

Campaign OS is not a storage bin for generated content. Every asset must remain:
- Stateful
- Owned
- Inspectable
- Actionable
- Operationally meaningful

If content does not improve operational clarity, it should not exist in the system.

**H. Anti-Hidden-State**

No hidden transitions. No silent state changes. No invisible ownership transfers. Every meaningful event leaves a traceable history entry.

### Why These Principles Matter

Future contributors will be tempted to optimise for features instead of operational truth. This section exists so that the WHY is documented, not just the WHAT.

If someone wants to add a field, they should first answer: does this improve operational clarity? Does it tell the truth better? Does it reduce cognitive load?

If the answer is no, the field should not exist.

---

## 2. Core Data Model

### Source of Truth

`campaign-data.json` is the single source of truth for all campaign state. It is:
- Written by agents on every meaningful action
- Committed to git on every state change
- Loaded by Campaign OS on page load
- The basis for all health scoring and diagnostics

Git history serves as the audit trail. Every commit is a timestamped, verifiable record of what changed and why.

### File Structure

```
campaign-os/
  campaign-data.json      # Source of truth — all campaigns, assets, state
  task-registry.json      # Task queue — agents claim and complete tasks
  approval-queue.json     # Pending approvals — awaiting gate clearance
  V2-FOUNDATION-SPEC.md   # This document
```

### Campaign Data Schema (High-Level)

```json
{
  "campaigns": {
    "[campaignId]": {
      "id": "string",
      "name": "string",
      "status": "active|paused|completed|archived",
      "owner": "string",
      "createdAt": "ISO8601",
      "updatedAt": "ISO8601",
      "verificationState": "NO_DATA|STALE_DATA|UNVERIFIED_DATA|VERIFIED|FAILED|DISPUTED",
      "healthScore": {
        "value": "number (0-100)",
        "status": "NO_DATA|STALE_DATA|UNVERIFIED_DATA|healthy|degraded|critical",
        "breakdown": {
          "conversion": { "value": "number", "weight": 0.35 },
          "compounding": { "value": "number", "weight": 0.25 },
          "engagement": { "value": "number", "weight": 0.25 },
          "momentum": { "value": "number", "weight": 0.15 }
        },
        "diagnostic": "string — causal explanation",
        "verifiedAt": "ISO8601",
        "source": "string"
      },
      "assets": {},
      "blockedBy": [],
      "dependencies": [],
      "history": [],
      "tags": []
    }
  }
}
```

### Asset Core Contract

Every asset in Campaign OS inherits the shared operational asset contract. Domain-specific extensions are allowed. The core contract is mandatory.

```json
{
  "id": "string — unique asset identifier",
  "type": "string — copy|visual|analytics|hook|prompt|research",
  "owner": "string — agent or human responsible",
  "status": "string — domain-specific valid states",
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601",
  "verificationState": "NO_DATA|STALE_DATA|UNVERIFIED_DATA|VERIFIED|FAILED|DISPUTED",
  "qualityGateState": "pending|passed|failed|skipped",
  "approvalState": "pending|approved|rejected|disputed",
  "history": [],
  "dependencies": [],
  "blockedBy": [],
  "tags": []
}
```

Domain extensions add fields to this base. The base fields are always present.

### Task Registry Schema

```json
{
  "tasks": {
    "[taskId]": {
      "id": "string",
      "campaignId": "string",
      "assetId": "string|null",
      "type": "string — research|write|design|verify|review|publish",
      "description": "string",
      "owner": "string|null — agent assigned",
      "status": "backlog|claimed|in_progress|pending_review|done|blocked|failed",
      "priority": "high|medium|low",
      "blockedBy": [],
      "createdAt": "ISO8601",
      "updatedAt": "ISO8601",
      "history": []
    }
  }
}
```

### Approval Queue Schema

```json
{
  "approvals": {
    "[approvalId]": {
      "id": "string",
      "assetId": "string",
      "campaignId": "string",
      "gate": "1|2|3",
      "status": "pending|approved|rejected|disputed",
      "requestedBy": "string",
      "requestedAt": "ISO8601",
      "reviewedBy": "string|null",
      "reviewedAt": "ISO8601|null",
      "notes": "string|null",
      "history": []
    }
  }
}
```

---

## 3. Campaign Object Structure

### What Is a Campaign?

A campaign is not a page. It is not a content calendar. It is not a reporting unit.

A campaign is a **living operational entity** that:
- Exists over time
- Contains assets that evolve
- Has owners that change
- Moves through states
- Surfaces blockers
- Generates diagnostics
- Tells the truth about its own health

### Campaign Lifecycle States

```
backlog → planning → active → paused → completed → archived
                ↓
 disputed
```

| State | Meaning |
|-------|---------|
| `backlog` | Campaign exists as an idea. No active work. |
| `planning` | Campaign is being scoped. Assets being defined. |
| `active` | Campaign is live. Assets being produced and published. |
| `paused` | Campaign temporarily halted. State preserved. |
| `completed` | Campaign objectives met. Final assets published. |
| `archived` | Campaign retired. State frozen for audit. |
| `disputed` | Campaign has a contested state. Requires resolution. |

### Campaign Fields

```json
{
  "id": "trackman",
  "name": "TrackMan Intelligence",
  "status": "active",
  "owner": "Clawdia",
  "createdAt": "2026-03-01T00:00:00Z",
  "updatedAt": "2026-05-28T12:00:00Z",
  "verificationState": "VERIFIED",
  "healthScore": {
    "value": 72,
    "status": "degraded",
    "breakdown": {
      "conversion": { "value": 68, "weight": 0.35 },
      "compounding": { "value": 75, "weight": 0.25 },
      "engagement": { "value": 70, "weight": 0.25 },
      "momentum": { "value": 80, "weight": 0.15 }
    },
    "diagnostic": "Conversion degraded: last published hook was 14 days ago. Best-performing hook variant (Hook E — swing speed) never re-published. GMB support posts lapsed 7 days ago.",
    "verifiedAt": "2026-05-28T06:00:00Z",
    "source": "ga4-analytics-tracker"
  },
  "assets": { /* asset map */ },
  "blockedBy": [],
  "dependencies": [],
  "history": [
    {
      "timestamp": "2026-05-28T12:00:00Z",
      "action": "health_recalculated",
      "owner": "lab",
      "source": "scheduled_daily_job",
      "what": "Health score recalculated from fresh GA4 data",
      "why": "Daily health refresh"
    }
  ],
  "tags": ["indoor-golf", "trackman", "performance", "sa"]
}
```

### Why Campaigns Are Living Entities

A static campaign page shows what was true at a point in time. A living campaign entity shows what is true now, what changed recently, what is blocked, and what needs attention.

Campaign OS campaign objects should increasingly behave like a competent marketing manager would: always knowing the state, always able to explain it, always surfacing what needs attention.

---

## 4. Asset Object Structure

### Asset Types

| Type | Description | Domain Owner |
|------|-------------|--------------|
| `copy` | Hooks, captions, ad copy | Copywriter |
| `visual` | Images, overlays, graphics | ImageGen |
| `analytics` | Performance data, metrics | TruthCollector |
| `hook` | A/B test hook variants | Copywriter |
| `prompt` | Generation prompts, briefs | Various |
| `research` | Market research, competitor data | Scout |

### Copy Asset Extension

```json
{
  "id": "hook-trackman-speed-001",
  "type": "copy",
  "subtype": "hook",
  "owner": "copywriter",
  "status": "approved",
  "createdAt": "2026-04-01T09:00:00Z",
  "updatedAt": "2026-04-01T12:00:00Z",
  "verificationState": "VERIFIED",
  "qualityGateState": "passed",
  "approvalState": "approved",
  "headline": "SWING SPEED: 83 MPH",
  "subtext": "Pros average 112 mph. TrackMan found you could gain 29 meters.",
  "caption": "How does your club head speed compare? A few sessions with certified instructors could add serious yards.",
  "testGroup": "round-2-variant-E",
  "parentAssetId": null,
  "platform": "instagram",
  "imagePath": null,
  "postizDraftId": null,
  "history": [
    {
      "timestamp": "2026-04-01T09:00:00Z",
      "action": "created",
      "owner": "copywriter",
      "what": "Hook created — round 2 variant E",
      "why": "A/B test round 2 — swing speed angle"
    },
    {
      "timestamp": "2026-04-01T12:00:00Z",
      "action": "approved",
      "owner": "Clawdia",
      "what": "Approved for publishing",
      "why": "Passed QC — clear stat angle, specific numbers"
    }
  ],
  "dependencies": [],
  "blockedBy": [],
  "tags": ["trackman", "stats", "swing-speed"]
}
```

### Visual Asset Extension

```json
{
  "id": "visual-trackman-hero-001",
  "type": "visual",
  "subtype": "hero",
  "owner": "imagegen",
  "status": "approved",
  "createdAt": "2026-04-01T10:00:00Z",
  "updatedAt": "2026-04-01T14:00:00Z",
  "verificationState": "VERIFIED",
  "qualityGateState": "passed",
  "approvalState": "approved",
  "visualStatus": "approved",
  "visualOwner": "imagegen",
  "visualSpecs": {
    "aspectRatio": "1:1",
    "platform": "instagram",
    "format": "png",
    "colorPalette": ["#0a0a0a", "#00ff88", "#ffffff"],
    "background": "bg-a-data"
  },
  "imagePath": "media/overlaid/hook-e-visual.png",
  "prompt": "Dark premium background with TrackMan data overlay. Bold white text. Green accent.1:1 ratio.",
  "qcNotes": "Passed. Stat text legible. Dark background premium-feeling. Good contrast.",
  "history": [
    {
      "timestamp": "2026-04-01T10:00:00Z",
      "action": "generated",
      "owner": "imagegen",
      "what": "Visual generated — bg-a-data + hook E overlay",
      "why": "Hook E companion visual for A/B test round 2",
      "model": "openai/gpt-image-1"
    },
    {
      "timestamp": "2026-04-01T14:00:00Z",
      "action": "qc_passed",
      "owner": "imagegen",
      "what": "QC passed — approved for use",
      "why": "Visual meets platform specs and brand guidelines"
    }
  ],
  "dependencies": ["hook-trackman-speed-001"],
  "blockedBy": [],
  "tags": ["trackman", "hero", "dark-theme"]
}
```

### Analytics Asset Extension

```json
{
  "id": "analytics-trackman-ig-001",
  "type": "analytics",
  "subtype": "instagram-post",
  "owner": "truth-collector",
  "status": "active",
  "createdAt": "2026-05-28T06:00:00Z",
  "updatedAt": "2026-05-28T06:00:00Z",
  "verificationState": "VERIFIED",
  "qualityGateState": "passed",
  "approvalState": "approved",
  "postId": "cmpnuw1yx0379ql0ywyup8ynm",
  "platform": "instagram",
  "performance": {
    "reach": { "value": 116, "status": "fresh", "source": "meta-api", "verified": true, "verifiedAt": "2026-05-28T06:00:00Z" },
    "likes": { "value": 2, "status": "fresh", "source": "meta-api", "verified": true, "verifiedAt": "2026-05-28T06:00:00Z" },
    "engagement": { "value": 1.72, "status": "fresh", "source": "calculated", "verified": true, "verifiedAt": "2026-05-28T06:00:00Z" },
    "conversions": { "value": 2, "status": "fresh", "source": "ga4", "verified": true, "verifiedAt": "2026-05-28T06:00:00Z" }
  },
  "history": [
    {
      "timestamp": "2026-05-28T06:00:00Z",
      "action": "data_pulled",
      "owner": "truth-collector",
      "what": "Instagram analytics refreshed from Meta API",
      "why": "Daily analytics cron"
    }
  ],
  "dependencies": [],
  "blockedBy": [],
  "tags": ["instagram", "trackman", "round-2"]
}
```

### Hook Asset Extension (A/B Variants)

```json
{
  "id": "hook-trackman-speed-001",
  "type": "hook",
  "subtype": "stats",
  "owner": "copywriter",
  "status": "approved",
  "testGroup": "round-2-variant-E",
  "parentAssetId": null,
  "abTestRound": 2,
  "winner": false,
  "headline": "SWING SPEED: 83 MPH",
  "subtext": "Pros average 112 mph. TrackMan found you could gain 29 meters.",
  "caption": "How does your club head speed compare? A few sessions with certified instructors could add serious yards.",
  "platform": "instagram",
  "imagePath": null,
  "postizDraftId": null,
  "published": true,
  "publishedAt": "2026-04-01T12:05:00Z",
  "postId": null,
  "performance": {
    "reach": { "value": 116, "status": "fresh" },
    "engagement": { "value": 1.72, "status": "fresh" }
  },
  "history": [],
  "dependencies": [],
  "blockedBy": [],
  "tags": []
}
```

---

## 5. Task Model

### Task States

```
backlog → claimed → in_progress → pending_review → done
                              ↓
 blocked
 ↓
                          failed
```

| State | Meaning |
|-------|---------|
| `backlog` | Task exists. Not yet claimed by any agent. |
| `claimed` | An agent has claimed the task. Work not started. |
| `in_progress` | Agent is actively working on the task. |
| `pending_review` | Work complete. Awaiting verification gate. |
| `done` | Task complete and verified. |
| `blocked` | Task blocked by a dependency or external factor. |
| `failed` | Task failed. Requires intervention. |

### Task Ownership

- Tasks start in `backlog`
- An agent claims a task by setting `owner` and `status: claimed`
- Agent moves to `in_progress` when work starts
- Agent moves to `pending_review` when done and requests gate clearance
- Task moves to `done` when gate 1 (verification) passes
- Task moves to `blocked` if a dependency is unmet
- Task moves to `failed` if work cannot be completed

### Task Priority Rules

| Priority | When to Use |
|----------|-------------|
| `high` | Campaign blocked. Asset overdue. Critical path item. |
| `medium` | Normal workflow. Standard production. |
| `low` | Optimisation. Nice-to-have. Research. |

### Task Registry Operations

Agents claim tasks from the registry. Only one agent claims a task at a time. Claiming requires:
1. Read `task-registry.json`
2. Find task with matching `type` and `status: backlog`
3. Set `owner` to agent id and `status: claimed`
4. Write updated `task-registry.json`
5. Commit to git

---

## 6. Gate System

### Three-Gate Pipeline

Every asset passes through three gates before reaching distribution. Gates are sequential. An asset cannot skip a gate.

```
[Asset Created]
 ↓
Gate 1: Verification Gate
Owner: Clawfix
      ↓ passed
Gate 2: Specialist Quality Gate
Owner: Domain Specialist (imagegen/copywriter/lab/etc.)
      ↓ passed
Gate 3: Distribution Gate
Owner: Publisher
      ↓ passed
[Asset Published]
```

### Gate 1 — Verification Gate (Clawfix)

**Owner:** Clawfix
**Purpose:** Prevent phantom success. Verify that what was claimed to be built actually exists in the files.

**Checks:**
- File exists at the claimed path
- Schema is valid (required fields present)
- Timestamps are present and plausible
- Owner is assigned
- Commit exists in git history
- Write actually happened (not just claimed)

**Valid outcomes:**
- `passed` — verification successful
- `failed` — asset does not exist, is malformed, or is unverifiable
- `skipped` — verification not applicable (e.g., external asset)

**Anti-phantom-success rule:** If Clawfix cannot verify it, it is NOT done. No exceptions.

### Gate 2 — Specialist Quality Gate

**Owner:** Domain specialist (imagegen for visuals, copywriter for copy, lab for analytics, etc.)
**Purpose:** Prevent low-quality or strategically wrong outputs from entering the system.

**Checks (by domain):**

| Domain | Quality Gate Focus |
|--------|-------------------|
| `visual` | ImageGen checks: brand guidelines, platform specs, visual clarity, stat legibility, messaging alignment |
| `copy` | Copywriter checks: hook clarity, CTA presence, pricing accuracy, brand voice, platform compliance |
| `analytics` | TruthCollector checks: data source valid, freshness confirmed, calculation logic correct |
| `research` | Scout checks: source cited, data fresh, methodology sound |
| `strategy` | Lab checks: test design valid, metrics appropriate, kill criteria defined |

**Valid outcomes:**
- `passed` — quality standards met
- `failed` — quality issues found. Asset returned to owner with notes.
- `skipped` — quality gate not applicable

**Explainability requirement:** Every quality decision must include a `qcNotes` entry explaining WHY the asset passed or failed. "Passed QC" is not enough. The reasoning must be recorded.

### Gate 3 — Distribution Gate (Publisher)

**Owner:** Publisher
**Purpose:** Prevent silent publishing failures and disconnected deployment state.

**Checks:**
- Approval cleared (gate 2 passed)
- Platform-ready (image optimised, caption correct, hashtags appropriate)
- Postiz state valid (draft created, media uploaded)
- Publish proof recorded (post ID captured, timestamp recorded)
- Reconciliation completed (asset linked to post record)

**Valid outcomes:**
- `passed` — asset successfully published
- `failed` — publish action failed. Asset returned to pending_review with error notes.
- `skipped` — distribution not applicable (e.g., internal asset)

### Gate State Persistence

Every gate attempt is recorded in the asset's `history[]` array:

```json
{
  "timestamp": "2026-05-28T12:00:00Z",
  "action": "gate_2_passed",
  "owner": "imagegen",
  "gate": 2,
  "what": "Visual quality gate passed",
  "why": "Brand guidelines met. Platform specs correct. Stat text legible.",
  "qcNotes": "Passed. Dark background premium-feeling. Green accent consistent with TrackMan brand. 1:1 ratio correct for IG feed."
}
```

---

## 7. Truthful State Model

### Valid Operational States

These are valid operational states. They are not errors. They are not blanks. They are the system telling the truth.

| State | Meaning | Action Required |
|-------|---------|-----------------|
| `NO DATA` | No data exists for this field. Data has never been collected. | Surface honestly. Do not fake. |
| `STALE_DATA` | Data existed but has not been refreshed within the expected interval. | Flag as stale. Do not use for decisions. |
| `UNVERIFIED_DATA` | Data exists but has not passed verification. | Do not trust until verified. |
| `VERIFIED` | Data exists, is fresh, and has passed verification. | Safe to use for decisions. |
| `FAILED` | A process failed. The operation did not complete. | Surface the failure. Investigate. |
| `DISPUTED` | A state is contested. Human resolution required. | Escalate. Do not auto-resolve. |

### State Display Rules

**Always show the actual state.** Never:
- Replace `NO DATA` with a zero or "—"
- Replace `STALE_DATA` with a stale number and pretend it is current
- Replace `UNVERIFIED_DATA` with a calculated value
- Hide `FAILED` behind a spinner or loading state
- Auto-resolve `DISPUTED` without human input

**Show the state prominently.** The state label should be visible without clicking or expanding.

### Why This Matters

Campaign OS trust depends on the system always telling the truth. If the system starts hiding failures and blanks behind fake data, operators stop trusting it.

Christelle needs to be able to open Campaign OS and immediately know: is this data I can trust?

The truthful state model ensures the answer is always clear.

---

## 8. blockedBy[] Intelligence Model

### What blockedBy[] Represents

`blockedBy[]` is the dependency intelligence layer. It answers: what is preventing this asset/campaign/task from progressing?

It is not just a list of blockers. It is a first-class operational signal that surfaces what is slowing the work down.

### blockedBy[] Entry Format

```json
{
  "blockerId": "string — id of the blocking asset/task/dependency",
  "blockerType": "asset|task|dependency|approval|external",
  "blockerDescription": "string — human-readable explanation",
  "blockedSince": "ISO8601 — when the blocker was first detected",
  "severity": "critical|high|medium|low",
  "resolution": "string|null — how to unblock"
}
```

### Blocker Surfacing Rules

Campaign OS should surface blockers AGGRESSIVELY. Specifically:

1. **At the campaign level:** Show all active blockers across all assets. Sort by severity.
2. **At the asset level:** Show the asset's specific blockers.
3. **In the health diagnostic:** Include blockers as causal factors in degradation explanations.
4. **In the task queue:** Blocked tasks should be visually distinct and prominent.

### Examples of Blockers

| Blocker | Type | Resolution |
|---------|------|------------|
| "Copy hook blocked by missing visual brief" | `dependency` | ImageGen provides visual direction |
| "Visual blocked by missing campaign direction" | `dependency` | Clawdia provides creative direction |
| "Publish blocked by missing approval" | `approval` | Specialist approves asset |
| "Health score blocked by stale analytics" | `dependency` | TruthCollector refreshes data |
| "Research blocked by missing source validation" | `external` | Scout validates source |
| "Hook variant blocked by parent not published" | `asset` | Parent asset published first |

### Blocker Severity Rules

| Severity | When |
|----------|------|
| `critical` | Campaign health is failing. Core asset missing. Publish deadline missed. |
| `high` | Asset production halted. A/B test blocked. Campaign momentum stalled. |
| `medium` | Minor delay. Non-critical path. Optional feature blocked. |
| `low` | Cosmetic. Aesthetic. Nice-to-have blocked. |

---

## 9. History[] Operational Memory Model

### What history[] Is

`history[]` is the operational memory of every campaign object. It records what happened, why it happened, who did it, and what triggered it.

It is NOT version control. It is NOT an infinite log. It is an auditable record of operational reasoning.

### history[] Entry Format

```json
{
  "timestamp": "ISO8601",
  "action": "string — past tense verb",
  "owner": "string — agent or human",
  "source": "string — what triggered this (scheduled_job|manual|webhook|agent)",
  "what": "string — what happened",
  "why": "string — why it happened (may be null for automated events)",
  "fromState": "string — previous state (if state transition)",
  "toState": "string — new state (if state transition)",
  "evidence": "string|null — commit hash, post ID, API response, etc."
}
```

### What to Record in history[]

Record an entry when:
- State transitions occur (draft → review → approved → published)
- Verification is performed
- Quality gate decision is made
- Health score is recalculated
- A blocker is detected or resolved
- An owner is assigned or changed
- A strategic decision is made
- An asset is linked to a campaign
- A dependency is added or removed

### What NOT to Record

Do NOT record:
- Routine file saves with no meaningful state change
- Automated refreshes with no anomaly
- Typing/editing events
- View events
- Minor field edits with no operational impact

### The Test for Operational Memory

If understanding why a decision was made requires Discord archaeology, the history[] entry was not written.

Every meaningful history[] entry should allow a future operator to understand:
- What happened
- Why it happened
- Who changed it
- What state it was in before
- What state it is in after

---

## 10. Agent Interaction Model

### Agent Roles and Write Targets

| Agent | Role | Writes To | Gate |
|-------|------|-----------|------|
| Scout | Research | `campaign-data.json` (research assets) | Gate 1 → Gate 2 |
| Copywriter | Copy | `campaign-data.json` (copy assets) | Gate 1 → Gate 2 |
| ImageGen | Visuals | `campaign-data.json` (visual assets) | Gate 1 → Gate 2 |
| TruthCollector | Analytics | `campaign-data.json` (analytics assets) | Gate 1 → Gate 2 |
| Lab | Strategy/Health | `campaign-data.json` (health scores, diagnostics) | Gate 1 |
| Publisher | Distribution | `campaign-data.json` (publish state, post IDs) | Gate 3 |
| Memories | Tracking | Memory files, decision logs | N/A |
| Clawfix | Verification | `campaign-data.json` (verificationState fields) | Gate 1 |

### Agent Handoff Protocol

When one agent passes work to another:

1. **Write the asset state** to `campaign-data.json`
2. **Record the history[] entry** explaining what was done and why
3. **Set the blockedBy[]** if the next step requires another agent
4. **Commit to git** so the state change is timestamped and verifiable
5. **Notify the receiving agent** via Discord @mention

The receiving agent then:
1. Reads the asset from `campaign-data.json`
2. Checks the history[] to understand context
3. Proceeds with their work

### Agent Naming Convention

Agents are referenced by their canonical agent ID (Discord snowflake). This ensures:
- No ambiguity when multiple agents of the same type exist
- Audit trail is precise
- Ownership is unambiguous

### Anti-Loop Rules

- Do not @mention an agent more than once per task handoff
- If an agent does not respond within 30 minutes, escalate to the owner
- Do not create circular dependencies (A blocked by B blocked by A)
- Blocked tasks should be surfaced, not hidden

---

## 11. Health Diagnostic Architecture

### What Health Score Is NOT

Health score is NOT:
- A vanity metric (total likes, total posts)
- A static grade
- A popularity contest
- A ranking against other campaigns

### What Health Score IS

Health score is an operational diagnostic that answers:
- Is this campaign achieving its strategic objectives?
- What is causing any degradation?
- What is the highest-leverage fix?

### Health Score Calculation

Health score is a weighted composite of four signals:

```json
{
  "conversion": {
    "weight": 0.35,
    "signal": "Sessions from social → booking page → conversion",
    "why": "Conversion is the only metric that directly measures revenue impact"
  },
  "compounding": {
    "weight": 0.25,
    "signal": "Engagement velocity, save rate, share rate",
    "why": "Compounding engagement means content is being saved and shared — highest signal of value"
  },
  "engagement": {
    "weight": 0.25,
    "signal": "Reach-adjusted engagement rate (likes + comments + shares / reach)",
    "why": "Raw engagement is misleading. Reach-adjusted shows true content quality"
  },
  "momentum": {
    "weight": 0.15,
    "signal": "Trend direction (improving/stable/declining over14 days)",
    "why": "Direction matters as much as absolute value. Improving is a positive signal"
  }
}
```

### Health Score States

| State | Meaning | Visual Treatment |
|-------|---------|-----------------|
| `NO_DATA` | No analytics data available | Amber badge, no score |
| `STALE_DATA` | Data older than 48 hours | Amber badge, stale indicator |
| `healthy` | Score 70-100 | Green badge |
| `degraded` | Score 40-69 | Amber badge |
| `critical` | Score 0-39 | Red badge |

### Diagnostic Explanation

Every health score must include a `diagnostic` field. This is the causal explanation — not just the score.

Example:
```
"diagnostic": "Conversion degraded: last published hook was 14 days ago. 
Best-performing hook variant (Hook E — swing speed) never re-published. 
GMB support posts lapsed 7 days ago. 
Recommendation: Re-publish Hook E with fresh visual. Resume GMB rotation."
```

The diagnostic should:
- Name the specific cause of degradation
- Reference specific assets or gaps
- Provide a actionable recommendation
- Be written for a human operator, not a machine

### Self-Diagnosing Campaigns (Future State)

The target state is campaigns that can explain themselves:

> "TrackMan Intelligence is underperforming because:
> - No fresh hero visual in 12 days
> - 3 assets stuck pending approval
> - GA4 attribution stale
> - Strongest hook variant never published
> - No recent GMB support posts"

This is the diagnostic architecture working correctly. The campaign is telling the operator what needs attention, ranked by impact.

---

## 12. Verification Architecture

### Why Verification Exists

Verification exists to prevent phantom success — the pattern where agents claim work is done but
the work does not actually exist. This is the single most dangerous pattern in AI-driven automation.

### Clawfix Verification Protocol

Clawfix runs verification checks on every meaningful write to `campaign-data.json`. Verification is the first gate in the three-gate pipeline.

**Verification checks:**
1. File write exists at the claimed path
2. Schema is valid (required fields present and correctly typed)
3. Timestamps are present and logically consistent
4. Owner is assigned
5. Git commit exists for the write
6. Evidence field links to the verifiable proof (commit hash, post ID, API response)

**Verification outcomes written to `campaign-data.json`:**
- `verificationState: "VERIFIED"` — all checks passed
- `verificationState: "FAILED"` — checks did not pass
- `verificationState: "UNVERIFIED_DATA"` — verification not yet run
- `verificationState: "NO_DATA"` — nothing to verify

### Delivery Verification Rules

1. **If Clawfix has not verified it, it is NOT done.** (Christelle authority — hard rule)
2. **No exceptions.** Applies to code, assets, analytics, deployment, scheduling, campaign changes.
3. **Verification must precede quality gate.** Gate 2 does not run until Gate 1 passes.
4. **Verification must precede distribution.** Gate 3 does not run until Gate 1 passes.
5. **Phantom success = verification failure.** If work was claimed but not written, it is a failed state.

### What Clawfix Verifies

| Asset Type | Verification Focus |
|------------|-------------------|
| Copy | File exists, schema valid, headline/subtext present, owner assigned |
| Visual | File exists, image path valid, visual specs complete, prompt reference in history |
| Analytics | File exists, performance data structure valid, source and freshness confirmed |
| Task | File exists, status transitions valid, owner assigned, history entries present |
| Campaign | File exists, health score structure valid, diagnostic present, verifiedAt timestamp set |

### Clawfix Verification Flow

```
Agent writes to campaign-data.json
         ↓
Agent commits to git
         ↓
Clawfix triggered (cron or webhook)
         ↓
Clawfix reads campaign-data.json
         ↓
Clawfix runs verification checks
         ↓
Clawfix writes verificationState to campaign-data.json
         ↓
Clawfix commits to git
         ↓
If FAILED → agent notified → asset returned to owner
If VERIFIED → asset moves to Gate 2
```

---

## 13. Anti-Patterns

### What Anti-Patterns Are

Anti-patterns are recurring patterns that look like progress but are actually operational debt. They create the illusion of work while actually degrading the system's reliability, honesty, and usefulness.

Campaign OS must actively resist these patterns.

### Anti-Pattern 1: Dashboard Soup

**What it looks like:** Pages of metrics, charts, graphs, tables, counters. Everything visible at once. No clear priority.

**Why it is dangerous:** It creates the illusion of insight while burying the actual signal. Operators stop looking because everything is equally loud.

**How to resist:** Only show what requires action. If a metric is fine, show it briefly or not at all. If it needs attention, make it prominent. Calmness means only the important things are loud.

### Anti-Pattern 2: Hidden State

**What it looks like:** State that lives only in Discord messages, agent memory, or local files. Changes that happen without being recorded.

**Why it is dangerous:** No one knows what is real. Decisions are made on incomplete information. Audit trail is impossible.

**How to resist:** Every meaningful state change must be written to `campaign-data.json` and committed to git. If it is not in the file, it did not happen.

### Anti-Pattern 3: Fake Completeness

**What it looks like:** Filling `NO DATA` fields with zeros, dashes, or "N/A" to make the UI look complete. Pretending stale data is current.

**Why it is dangerous:** Operators trust the system. If the system lies, they make bad decisions without knowing it.

**How to resist:** Show `NO DATA` and `STALE DATA` prominently. Treat them as valid states. Never replace them with fake values.

### Anti-Pattern 4: Output Dumping

**What it looks like:** Agents generate content and dump it into Campaign OS without ownership, state, or context. Content exists but has no operational meaning.

**Why it is dangerous:** Campaign OS becomes a storage bin. Noise overwhelms signal. No one knows what is real and what is draft garbage.

**How to resist:** Every asset must have an owner, a status, a history entry, and a clear purpose. If content does not answer the operational meaning questions, it should not exist in Campaign OS.

### Anti-Pattern 5: Silent Automation

**What it looks like:** Automated actions that happen without being recorded. Cron jobs that run and produce no output. Integrations that fail silently.

**Why it is dangerous:** No one knows what ran, what succeeded, or what failed. Failures go undetected until they become crises.

**How to resist:** Every automated action must write to `campaign-data.json` and record a history entry. Failures must be surfaced explicitly with `FAILED` state and error notes.

### Anti-Pattern 6: Vanity Metrics

**What it looks like:** Tracking total likes, total posts, total followers, total impressions. Numbers that go up but do not correlate with business outcomes.

**Why it is dangerous:** Operators optimise for what is easy to measure, not what matters. Campaign looks healthy while conversion collapses.

**How to resist:** Health score explicitly excludes vanity metrics. Conversion, compounding engagement, and momentum are the signals. Everything else is secondary.

### Anti-Pattern 7: Unowned Work

**What it looks like:** Assets, tasks, or campaigns with no owner. Work that exists but no one is responsible for it.

**Why it is dangerous:** Blocked work accumulates. No one knows what needs attention. Problems go unaddressed because responsibility is diffuse.

**How to resist:** Every asset, task, and campaign must have an explicit owner. If ownership is unclaimed, it goes to `backlog` with no owner. `blockedBy[]` surfaces unowned blocked work prominently.

### Anti-Pattern 8: Phantom Success

**What it looks like:** Agents claim work is done but the work does not exist in the files. Code "written" but not committed. Assets "created" but not saved. Deployments "completed" but not verified.

**Why it is dangerous:** Trust collapses. Christelle cannot rely on what she is told. The system becomes theater.

**How to resist:** Clawfix verification gate. Git commit as evidence. Delivery verification protocol. No "done" until verification passes.

### Anti-Pattern 9: Complexity Drift

**What it looks like:** Adding fields, states, and abstractions faster than the system can maintain coherence. Each individual addition seems reasonable. The aggregate is overwhelming.

**Why it is dangerous:** The system becomes too complex to understand. New operators cannot reason about it. The architecture collapses under its own weight.

**How to resist:** The complexity debt rule. A feature is only progress if it improves operational clarity, reduces friction, surfaces leverage, reduces hidden state, improves truthful state visibility, or lowers cognitive load. Otherwise it is debt.

### Anti-Pattern 10: Enterprise Chaos

**What it looks like:** Too many alerts, too many dashboards, too many statuses, too many notifications. The system creates anxiety instead of reducing it.

**Why it is dangerous:** Operators stop trusting alerts. Important signals are missed because everything is equally loud.

**How to resist:** Calmness as a design constraint. If an alert fires and the operator does not need to take action, the alert should not fire. Alerts should be rare, clear, and actionable.

---

## 14. Scalability Principles

### What Scalability Means Here

Scalability does not mean handling more campaigns or more agents. It means the system remaining coherent, calm, and honest as complexity increases.

A system that works at 5 campaigns and collapses at 20 is not scalable. A system that works at 20 campaigns but requires a flowchart to understand is not scalable.

### Scalability Principle 1: Operational Compression

As the system scales, it should become simpler to understand, not more complex.

This means:
- Fewer, more powerful abstractions
- Stronger leverage surfacing
- Clearer ownership
- Less noise, more truth

The architecture should handle complexity internally while presenting a calm, legible surface.

### Scalability Principle 2: Agent Specialisation

As the fleet grows, agents should specialise rather than generalise.

Each agent should:
- Own one domain deeply
- Write to one set of fields
- Operate within one gate
- Speak one clear handoff language

This prevents overlapping authority, diffuse ownership, and circular dependencies.

### Scalability Principle 3: Schema Extension Rules

New asset types, new fields, and new states must follow the extension rules:

1. **Core contract is mandatory.** Every asset inherits the 13 required fields.
2. **Extensions must justify themselves.** Why does this field need to exist? What operational question does it answer?
3. **Complexity cost is explicit.** Every added field has a cognitive cost. That cost must be worth it.
4. **Domain isolation.** Extensions belong to their domain. They do not leak into the core contract unless truly universal.

### Scalability Principle 4: Verification Must Scale

As more agents write to `campaign-data.json`, verification must remain rigorous.

Clawfix must:
- Run verification on every write, not just critical ones
- Flag schema drift before it compounds
- Maintain the anti-phantom-success rule at scale

If verification cannot keep pace with agent output, the bottleneck must be surfaced and resolved.

### Scalability Principle 5: Health Score Must Remain Honest

As campaigns accumulate data, health score must remain a truthful signal — not a加权 average that smooths over important variance.

Rules:
- Always show the diagnostic explanation alongside the score
- Always surface the specific cause of degradation
- Never average across campaigns to hide individual failures
- Never smooth historical data to hide volatility

### Scalability Principle 6: Git as Scalable Audit Trail

Git is the audit trail. As the number of agents and writes increases, git history must remain the single source of truth for what changed and when.

Rules:
- Every meaningful write is a git commit
- Commits are atomic (one logical change per commit)
- Commit messages describe what and why, not just what
- Branches are used for experimental work; main is always deployable

### Scalability Principle 7: New Agents Onboard Against This Document

When a new agent joins the fleet, this document is their onboarding reference.

They should be able to read this document and understand:
- What Campaign OS is (and what it is not)
- Why the architecture exists
- What their role is
- How they interact with other agents
- What states are valid
- What anti-patterns to avoid

This document is the constitution. New agents agree to it before they operate.

---

## Appendix: Canonical State Reference

### Asset Status Values (by domain)

| Domain | Valid Statuses |
|--------|---------------|
| Copy | `draft`, `review`, `approved`, `rejected`, `published`, `archived` |
| Visual | `draft`, `concept`, `approved`, `rejected`, `published`, `archived` |
| Analytics | `pending`, `active`, `stale`, `archived` |
| Task | `backlog`, `claimed`, `in_progress`, `pending_review`, `done`, `blocked`, `failed` |
| Campaign | `backlog`, `planning`, `active`, `paused`, `completed`, `archived`, `disputed` |

### Verification State Values

`NO_DATA` | `STALE_DATA` | `UNVERIFIED_DATA` | `VERIFIED` | `FAILED` | `DISPUTED`

### Quality Gate State Values

`pending` | `passed` | `failed` | `skipped`

### Approval State Values

`pending` | `approved` | `rejected` | `disputed`

---

## Document Governance

**Who can modify this document:** Christelle (authority) or fleet consensus with Christelle approval.

**How to propose a change:** Present the change in #group-chat with rationale. If no objection within 24 hours and Christelle approves, change is incorporated.

**Version history:**
- v2.0 (2026-05-28) — Initial locked version. Fleet alignment complete. Build phase active.

---

*This document is the constitutional architecture reference for Campaign OS v2. It was written after the fleet independently converged on the same principles from multiple domains. That convergence is the signal that the architecture is coherent.*
