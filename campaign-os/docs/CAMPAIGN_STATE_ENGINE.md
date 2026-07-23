# Campaign State Engine

**Module**: `scripts/_lib/campaign-state-engine.js`
**CLI**: `scripts/activate-campaign.js`
**Spec**: Step 91

The canonical writer of `campaign.identity.status`. The single legitimate entry point for the transition `generatingBlueprint → active`.

## Allowed campaign statuses

| Status | Terminal? | Notes |
|---|---|---|
| `draft` | no | Initial creation state |
| `generatingBlueprint` | no | Blueprint generation in progress (M5) |
| `active` | no | Campaign ready for production/publishing |
| `cancelled` | yes | Permanently terminated |
| `archived` | yes | Completed / closed |

## Allowed transitions

```
draft ───────────────► generatingBlueprint
                          │
                          ▼
                        active ────────────► cancelled
                          │
                          └────────────────► archived
```

Terminal states (`cancelled`, `archived`) have no outgoing edges. Any transition not in this graph is rejected with `IllegalCampaignTransitionError`.

## Required evidence for `generatingBlueprint → active`

All items must be true:

### Strategy layer
- `identity.campaignId` exists
- `identity.owner` exists
- `identity.audience` OR `brief.audience` exists
- `identity.primaryGoal` OR `brief.goalNotes` exists
- `strategy.primaryOffer` exists

### Channel layer
- `identity.platforms` is non-empty array

### Brief layer
- `campaign.brief` has at least one populated field (`audience`, `goalNotes`, `successTarget`, or `context`)

### Strategy pillars
- `strategy.pillars` length ≥ 3

### Asset readiness
- At least one asset satisfies ALL five engine-projected state gates:
  - `qualityGateState ∈ {gate1-passed, gate2-passed, gate3-passed, approved, skipped}`
  - `captionStatus ∈ {approved, skipped}`
  - `visualStatus ∈ {approved, skipped}`
  - `approvalStatus === "approved"`
  - `publishStatus === "scheduled"`

### Negative constraints
- `identity.status !== "cancelled"` (enforced by terminal-state check)
- `identity.status !== "archived"` (enforced by terminal-state check)

## Legitimate writer

Only `activateCampaign(campaignId, canonicalPath, options)` exported from `scripts/_lib/campaign-state-engine.js`. No other code path writes `identity.status`.

## Canonical event

Appended to `campaign.history[]` (new additive field — distinct from `asset.history[]`):

```json
{
  "action": "campaign-activated",
  "by": "<operator id>",
  "at": "<ISO timestamp>",
  "reason": "<operator-supplied string>",
  "evidence": {
    "scheduledAssetIds": ["<assetId>", ...],
    "fromStatus": "generatingBlueprint",
    "toStatus": "active",
    "by": "<operator id>",
    "at": "<ISO timestamp>"
  }
}
```

### Campaign event taxonomy

- `campaign-activated`
- `campaign-cancelled` (future)
- `campaign-archived` (future)

Anything else is rejected by `recordCampaignEvent` with `InvalidCampaignActionError`.

## Idempotency

- `activateCampaign` on an already-`active` campaign: `{changed: false, reason: "already-active"}`. Zero writes.
- `recordCampaignEvent` rejects duplicate events (same action + same `by` at the top of history): `{changed: false, reason: "duplicate-event"}`. Zero appends.
- Atomic write under lock with TOCTOU re-read.

## Rejection

- `evaluateCampaignActivation` returns `{ready: false, blockers: [...]}`. Never throws.
- `activateCampaign` returns `{ok: false, blockers}`. Never writes.

## Rollback

Not defined in this contract. `active → generatingBlueprint` is not a valid transition. Rollback requires a separate future contract.

## Failure modes

- Atomic write failure: canonical unchanged, error surfaced.
- Lock contention: throws after 100 attempts.
- Unknown event action: `InvalidCampaignActionError`.
- Illegal transition: `IllegalCampaignTransitionError`.

## Module exports

```js
const {
  CAMPAIGN_STATUS_SCHEMA,
  CAMPAIGN_EVENT_TAXONOMY,
  ALLOWED_TRANSITIONS,
  evaluateCampaignActivation,
  recordCampaignEvent,
  applyCampaignStatusTransition,
  activateCampaign,
  isTerminalStatus,
  InvalidCampaignActionError,
  IllegalCampaignTransitionError
} = require('./scripts/_lib/campaign-state-engine');
```

## CLI

```bash
node scripts/activate-campaign.js \
  --campaign use-the-right-equipment-mq5l90bk \
  --dry-run

node scripts/activate-campaign.js \
  --campaign use-the-right-equipment-mq5l90bk \
  --by christelle \
  --reason "Campaign activation approved after readiness proof"

node scripts/activate-campaign.js \
  --campaign <id> --json
```

Exit codes: `0` for success / idempotent no-op / dry-run; `1` for failure.

## Integration points

- **Asset State Engine** (`scripts/_lib/asset-state-engine.js`): provides the 5-field projection that the activation contract's asset-readiness gate consumes. The campaign engine re-evaluates inline (no `require('fs')`) so the lifecycle module stays pure for evaluation; if the asset engine adds new eligible state values, both engines must be updated in lockstep.
- **Canonical Publish Queue Generator** (`scripts/generate_publish_queue.js`): unchanged. The generator's `identity.status === 'active'` filter is satisfied by activation. No generator changes required.
- **Publisher** (`scripts/run_publisher.js`): unchanged. Publisher consumes `ready-for-approval.json` after the generator runs.

## Hard rules

- `evaluateCampaignActivation` has zero `require('fs')` calls.
- `applyCampaignStatusTransition` never appends to `campaign.history`.
- `applyCampaignStatusTransition` never mutates any field except `identity.status`.
- `recordCampaignEvent` is the single entry point for `campaign.history[]` writes.
- Atomic write via temp-file rename under PID-based lock.