# Asset State Engine

> **Step 87.** The canonical Asset State Engine owns the five
> publishing-state fields on every Campaign OS asset. Producers
> (Cockpit, Publisher, Image-Gen, Copywriter, Review Queue, Truth
> Collector) emit history events only — they never compute state.
>
> History is canonical. State is derived.

## Why this exists

Before Step 87, five fields were scattered across scripts with no owner:

- `qualityGateState`
- `captionStatus`
- `visualStatus`
- `approvalStatus`
- `publishStatus`

The only writer in the repo was `scripts/generate-production-plan.py`,
which only wrote initial seed values (`pending`, `draft`, `brief-written`,
`review`, `planned`). No script advanced them in response to events.
This was the orphan state machine Step 84 diagnosed.

Step 87 creates a single owner: the Asset State Engine. The engine is a
**pure projection layer** — given an asset + its history + external
signals, it returns the desired 5-field state. Nothing else writes
those fields.

## API surface

Module: `scripts/_lib/asset-state-engine.js`

```js
const engine = require('./scripts/_lib/asset-state-engine');

// Event Recorder — producers NEVER push to asset.history directly.
// They MUST go through this helper so action strings are validated.
engine.recordEvent(history, action, payload);
//   history       Array — the asset's history[] (mutated in-place)
//   action        String — one of KNOWN_HISTORY_ACTIONS
//   payload       Object — {by, at?, ...context}
//   returns       the appended event object

// Pure projection. No side effects.
engine.evaluateAsset(asset, history, externalSignals);
//   asset              Object — the asset record
//   history            Array — explicit history (caller passes, engine does
//                      NOT read asset.history itself)
//   externalSignals    {postizConfirmations?, bookingEvents?, approvalActions?}
//   returns            {qualityGateState, captionStatus, visualStatus,
//                       approvalStatus, publishStatus, observations[]}

// Field-only mutator. NEVER touches asset.history. NEVER touches
// caption / visualBrief / filePath / owner / assetType / keyFindings.
engine.applyStateTransition(asset, desiredState);
//   asset              Object — mutated in-place
//   desiredState       {qualityGateState?, captionStatus?, ...}
//   returns            {changed: boolean, fieldsChanged: string[]}

// Atomic reconcile one campaign (writes to canonical).
engine.reconcileCampaign(campaignId, canonicalPath?, opts?);
//   returns            {changed, summary, dryRun}

// Atomic reconcile all campaigns.
engine.reconcileAll(opts?);
//   returns            {changed, summary, dryRun}
```

## History action taxonomy

Producers emit events via `recordEvent()`. Allowed action strings:

| Category | Actions |
|---|---|
| Caption lifecycle | `caption-created`, `caption-revised`, `caption-approved`, `caption-rejected` |
| Visual lifecycle | `visual-generated`, `visual-revised`, `visual-approved`, `visual-rejected` |
| Approval lifecycle | `approval-requested`, `approval-approved`, `approval-rejected` |
| Publish lifecycle | `publish-requested`, `publish-confirmed`, `publish-failed` |
| Generic | `asset-edited`, `campaign-edited`, `engagement-recorded` |
| Regeneration | `regenerate-requested` (resets `gate2-failed` stickiness) |
| **Legacy (read-only)** | `caption-draft`, `visual-brief-written`, `delivered`, `generated`, `brief-created`, `created`, `shell-created`, `published`, `approved`, `rejected` |

Legacy actions already exist in canonical history from before Step 87.
The engine treats them as read-only aliases of canonical actions so old
assets converge naturally. New producers MUST emit canonical actions.

## State field allowed values

| Field | Values |
|---|---|
| `qualityGateState` | `pending`, `gate1-passed`, `gate2-passed`, `gate2-failed`, `approved`, `skipped` |
| `captionStatus` | `pending`, `draft`, `approved`, `rejected` |
| `visualStatus` | `pending`, `brief-written`, `generated`, `approved`, `rejected`, `skipped` |
| `approvalStatus` | `pending`, `review`, `approved`, `rejected` |
| `publishStatus` | `planned`, `scheduled`, `live`, `failed`, `skipped`, `archived` |

## Transition rules (paraphrased from Step 85 §STATE GRAPH)

The engine implements these rules as pure projections of `history[]`:

### qualityGateState

- `pending` → `gate1-passed` when `caption >= 50 chars` AND `visualBrief` non-empty AND `owner` set (non-research) OR `caption + keyFindings` present (research).
- `gate1-passed` → `gate2-passed` → `approved` when visual is approved/skipped.
- Any → `gate2-failed` is **sticky** unless a `regenerate-requested` event exists.

### captionStatus

- `pending` → `draft` when `caption-created`/`caption-revised` event exists OR caption field non-empty.
- `draft` → `approved` when caption ≥ 100 chars AND no `caption-rejected` after the latest `caption-revised`.
- Latest event wins for backward transitions (`caption-rejected` after `caption-approved` → `draft`).

### visualStatus

- `pending` → `brief-written` when `visualBrief.concept` non-empty or `visual-revised` event.
- `brief-written` → `generated` when `filePath` set AND `visual-generated` event.
- `generated` → `approved` when `visual-approved` event exists.
- `assetType === 'research'` forces `visualStatus: 'skipped'`.

### approvalStatus

- `pending` → `review` when `caption-created`/`caption-revised` event exists AND `visualBrief` non-empty.
- `review` → `approved` when `approval-approved` event by `christelle` exists.
- External `approvalActions[]` in `externalSignals` overrides history.

### publishStatus

- `planned` → `scheduled` when ALL of: `approvalStatus=approved` AND `captionStatus=approved` AND `visualStatus ∈ {approved, skipped}` AND `qualityGateState ∈ {gate1-passed, gate2-passed, approved, skipped}`.
- `scheduled` → `live` when external `postizConfirmations[]` with `status: 'live'` for this asset.
- Any → `failed` when `publish-failed` event exists or Postiz confirmation reports failure.

## Integration points

### Campaign Builder

When the user saves a new asset or edits fields, the builder should:

1. Emit `asset-edited` history event via `recordEvent`.
2. Emit `caption-revised` / `visual-revised` if those fields changed.
3. Call `evaluateAsset(asset, asset.history, {})`.
4. Call `applyStateTransition(asset, desired)` — fields only.
5. Persist the asset atomically.

### Review Queue (M7)

Approve / Reject / Request Revision buttons:

1. Emit `approval-approved` / `approval-rejected` (by `christelle`) or `caption-revised-requested` / `visual-revised-requested` history event.
2. Call `evaluateAsset(asset, asset.history, {})`.
3. Call `applyStateTransition(asset, desired)`.
4. Persist.

### Publisher

After a successful live Postiz call (`scripts/run_publisher.js`):

1. Append `publish-confirmed` history event via `recordEvent` (by `publisher`, with `postizPostId`, `releaseURL`, `releaseId`, `currentStatus`).
2. Call `evaluateAsset(asset, asset.history, {postizConfirmations: [{assetId, status: 'live', postizPostId, releaseURL}]})`.
3. Call `applyStateTransition(asset, desired)`.
4. Persist atomically.

After a failed Postiz call, the publisher does NOT enter the engine (no reference is created). The next successful publish will project the correct state.

### Cockpit (`cockpit-operational.html`)

`changeAssetStatus(id, newStatus)`:

1. Existing behavior preserved: writes `a.status`, pushes `status-changed` event.
2. Augmented: after the existing write, calls `AssetStateEngine.evaluateAsset(a, a.history, {})` then `AssetStateEngine.applyStateTransition(a, desired)`.
3. Engine errors are logged but do not block the cockpit save.

The cockpit inlines a minimal engine subset (since it's a self-contained HTML file). The canonical source is `scripts/_lib/asset-state-engine.js`. Parity is verified manually.

### Truth Collector (Stage 3, separate repo)

When GA4/Meta pullback arrives:

1. Append `engagement-recorded` history event via `recordEvent` (with metrics).
2. Call `evaluateAsset(asset, asset.history, {})`.
3. Call `applyStateTransition(asset, desired)`.
4. Persist.

### Manual reconcile

```bash
node scripts/reconcile-asset-state.js                    # all campaigns, live
node scripts/reconcile-asset-state.js --dry-run          # report only
node scripts/reconcile-asset-state.js --campaign takomo-101t
node scripts/reconcile-asset-state.js --json             # machine-readable
node scripts/reconcile-asset-state.js --canonical-path <p>
```

The CLI is a thin wrapper. It calls `evaluateAsset` + `applyStateTransition` on every asset and persists atomically. It NEVER writes to `asset.history`.

## Worked examples

### takomo-101t-research

```json
{
  "assetId": "takomo-101t-research",
  "assetType": "research",
  "caption": "...296 chars...",
  "keyFindings": ["...", "..."],
  "history": [
    { "action": "created",   "by": "scout",   "at": "2026-06-02T06:36:56Z" },
    { "action": "published", "by": "scout",   "at": "2026-06-02T06:36:56Z" }
  ]
}
```

After `evaluateAsset()`:

| Field | Value | Reason |
|---|---|---|
| `qualityGateState` | `gate1-passed` | research: caption ≥50 + keyFindings present |
| `captionStatus` | `approved` | caption ≥100 chars, no rejection in history |
| `visualStatus` | `skipped` | assetType === 'research' |
| `approvalStatus` | `pending` | no `approval-approved` by `christelle` in history |
| `publishStatus` | `planned` | not eligible (approvalStatus not yet approved) |

### use-the-right-equipment-mq5l90bk-feed-post-01

```json
{
  "assetId": "use-the-right-equipment-mq5l90bk-feed-post-01",
  "assetType": "feed-post",
  "owner": "copywriter",
  "caption": "...311 chars...",
  "visualBrief": { "concept": "..." },
  "history": [
    { "action": "caption-draft", "by": "copywriter", "at": "2026-06-09T09:46:00Z" }
  ]
}
```

After `evaluateAsset()`:

| Field | Value | Reason |
|---|---|---|
| `qualityGateState` | `gate1-passed` | caption ≥50 + visualBrief + owner |
| `captionStatus` | `approved` | caption ≥100, no rejection |
| `visualStatus` | `brief-written` | visualBrief present, no filePath |
| `approvalStatus` | `review` | caption-created alias + visualBrief present |
| `publishStatus` | `planned` | not eligible (no christelle approval yet) |

### takomo-101t-visual-a (gate2-failed sticky)

```json
{
  "assetId": "takomo-101t-visual-a",
  "assetType": "hero-visual",
  "owner": "image-gen",
  "filePath": "assets/campaigns/trackman/takomo-101t-hero-a.png",
  "visualBrief": { "concept": "..." },
  "qualityGateState": "gate2-failed",
  "history": [
    { "action": "brief-created", "by": "copywriter", "at": "..." },
    { "action": "generated",     "by": "image-gen",  "at": "..." },
    { "action": "delivered",     "by": "image-gen",  "at": "..." },
    { "action": "rejected",      "by": "christelle", "at": "2026-06-02T09:03:00Z", "reason": "Club does not look real enough..." }
  ]
}
```

After `evaluateAsset()`:

| Field | Value | Reason |
|---|---|---|
| `qualityGateState` | `gate2-failed` | sticky — no `regenerate-requested` event |
| `captionStatus` | `pending` | no caption field |
| `visualStatus` | `generated` | filePath + visual-generated (delivered alias) |
| `approvalStatus` | `rejected` | rejected by christelle in history |
| `publishStatus` | `planned` | not eligible (gate2-failed, approval rejected) |

## Testing

```bash
node tests/test_asset_state_engine.js     # 30 sections, 74 assertions
node tests/test_engine_convergence.js     # 17 assertions on real canonical
node tests/test_publisher_writeback.js    # 28 assertions (no regression)
```

The convergence test loads `campaign-os/campaign-data.json`, runs `reconcileAll({dryRun:true})`, and asserts:
- Determinism across 3 runs
- Canonical SHA-256 unchanged after dry-run
- No `.tmp` or `.lock` files left behind
- takomo-research converges to expected state
- takomo-visual-a stays at `gate2-failed`
- 36 use-the-right-equipment assets stay at `publishStatus: planned`
- All 42 asset.history lengths unchanged (engine adds nothing)

## Hard rules (verifiable via grep)

```bash
# evaluateAsset has no require('fs') call
grep -n "function evaluateAsset" scripts/_lib/asset-state-engine.js
# Inspect function body — must not contain fs.readFile, fs.writeFile, or require('fs')

# applyStateTransition never appends to asset.history
grep -A 20 "function applyStateTransition" scripts/_lib/asset-state-engine.js
# Must not contain .history.push or asset.history.push

# applyStateTransition only mutates the 5 fields
grep -A 20 "function applyStateTransition" scripts/_lib/asset-state-engine.js
# Mutates only: asset[field] where field ∈ ASSET_STATE_SCHEMA
```

## Architecture summary

```
Producers                       Canonical                          Engine
─────────                       ─────────                          ──────
Cockpit ───┐                    campaign-data.json
Publisher ─┤──recordEvent()───► asset.history[] ──evaluateAsset()──► desired state
Image-gen ─┤                                            │
Copywriter ┤                                            └─applyStateTransition()──►
Review Q ──┤                                                              │
Truth Coll ┘                                                              ▼
                                                              asset.{5 fields}
```

History is the source of truth. State is a derived view.