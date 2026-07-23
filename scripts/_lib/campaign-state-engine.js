/**
 * scripts/_lib/campaign-state-engine.js
 *
 * Canonical Campaign Lifecycle Engine.
 *
 * Owns the campaign-level identity.status field. Defines the contract for
 * campaign-status transitions, validates readiness evidence, records campaign-
 * level history events, and persists canonical atomically.
 *
 * This module is the ONLY legitimate writer of campaign.identity.status.
 * No other code path may set identity.status to a new value.
 *
 * Architecture (Step 91):
 *   - evaluateCampaignActivation() is a PURE projection of (campaign) into
 *     {ready, blockers, scheduledAssetIds}. No side effects, no I/O.
 *   - recordCampaignEvent() is the single entry point for writes to
 *     campaign.history[]. Validates action against CAMPAIGN_EVENT_TAXONOMY.
 *   - applyCampaignStatusTransition() mutates ONLY identity.status. Writes
 *     nothing else.
 *   - activateCampaign() orchestrates: evaluate -> record event ->
 *     apply transition -> atomic persist.
 *
 * Hard rules:
 *   - evaluateCampaignActivation NEVER calls require('fs'). Verifiable via grep.
 *   - applyCampaignStatusTransition NEVER appends to campaign.history.
 *     History writes are exclusively via recordCampaignEvent.
 *   - applyCampaignStatusTransition NEVER mutates identity.owner, identity.name,
 *     identity.audience, brief, strategy, assets, blueprint, dna, or any other
 *     campaign field.
 *   - No code outside this module may write identity.status. Enforced by
 *     convention + Step 91's documented contract; tooling does not police this.
 *
 * Module exports:
 *   - CAMPAIGN_STATUS_SCHEMA
 *   - CAMPAIGN_EVENT_TAXONOMY
 *   - ALLOWED_TRANSITIONS
 *   - evaluateCampaignActivation(campaign)
 *   - recordCampaignEvent(campaign, action, payload)
 *   - applyCampaignStatusTransition(campaign, desiredStatus)
 *   - activateCampaign(campaignId, canonicalPath, options)
 *   - isTerminalStatus(status)
 *   - InvalidCampaignActionError
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ── Schema ────────────────────────────────────────────────────────────────

const CAMPAIGN_STATUS_SCHEMA = Object.freeze({
  draft: 'draft',
  generatingBlueprint: 'generatingBlueprint',
  active: 'active',
  cancelled: 'cancelled',
  archived: 'archived'
});

const CAMPAIGN_EVENT_TAXONOMY = Object.freeze([
  'campaign-activated',
  'campaign-cancelled',
  'campaign-archived'
]);

// Allowed status transitions. Terminal states have no outgoing edges.
const ALLOWED_TRANSITIONS = Object.freeze({
  draft: ['generatingBlueprint'],
  generatingBlueprint: ['active'],
  active: ['cancelled', 'archived'],
  cancelled: [],
  archived: []
});

// ── Errors ────────────────────────────────────────────────────────────────

class InvalidCampaignActionError extends Error {
  constructor(action) {
    super(`Invalid campaign history action: ${action}. Allowed: ${CAMPAIGN_EVENT_TAXONOMY.join(', ')}`);
    this.name = 'InvalidCampaignActionError';
    this.action = action;
  }
}

class IllegalCampaignTransitionError extends Error {
  constructor(fromStatus, toStatus) {
    super(`Illegal campaign status transition: ${fromStatus} -> ${toStatus}`);
    this.name = 'IllegalCampaignTransitionError';
    this.fromStatus = fromStatus;
    this.toStatus = toStatus;
  }
}

// ── Pure helpers ──────────────────────────────────────────────────────────

function isTerminalStatus(status) {
  return status === 'cancelled' || status === 'archived';
}

function isAllowedTransition(fromStatus, toStatus) {
  const allowed = ALLOWED_TRANSITIONS[fromStatus];
  if (!allowed) return false;
  return allowed.indexOf(toStatus) !== -1;
}

/**
 * Evaluate whether a campaign has the evidence required to activate.
 * Pure — never reads from disk, never mutates the campaign argument.
 *
 * Returns:
 *   {
 *     ready: boolean,
 *     blockers: string[],
 *     scheduledAssetIds: string[],
 *     fromStatus: string|null
 *   }
 */
function evaluateCampaignActivation(campaign) {
  const blockers = [];
  const scheduledAssetIds = [];

  if (!campaign || typeof campaign !== 'object') {
    return { ready: false, blockers: ['campaign object missing'], scheduledAssetIds: [], fromStatus: null };
  }

  const identity = campaign.identity || {};
  const fromStatus = identity.status || null;

  // Negative constraints — terminal states block activation
  if (isTerminalStatus(fromStatus)) {
    blockers.push(`campaign is in terminal status: ${fromStatus}`);
  }

  // Strategy layer (5 items)
  if (!identity.campaignId) blockers.push('identity.campaignId missing');
  if (!identity.owner || (typeof identity.owner === 'string' && identity.owner.trim().length === 0)) {
    blockers.push('identity.owner missing');
  }

  const audience = identity.audience || (campaign.brief && campaign.brief.audience);
  if (!audience) blockers.push('audience missing (identity.audience and brief.audience both empty)');

  const goal = identity.primaryGoal || (campaign.brief && campaign.brief.goalNotes);
  if (!goal) blockers.push('primary goal missing (identity.primaryGoal and brief.goalNotes both empty)');

  const primaryOffer = campaign.strategy && campaign.strategy.primaryOffer;
  if (!primaryOffer || (typeof primaryOffer === 'string' && primaryOffer.trim().length === 0)) {
    blockers.push('strategy.primaryOffer missing');
  }

  // Channel layer (1 item)
  const platforms = Array.isArray(identity.platforms) ? identity.platforms : [];
  if (platforms.length === 0) blockers.push('identity.platforms empty');

  // Brief layer (1 item)
  const brief = campaign.brief || {};
  const briefHasContent = ['audience', 'goalNotes', 'successTarget', 'context']
    .some(k => brief[k] && (typeof brief[k] !== 'string' || brief[k].trim().length > 0));
  if (!briefHasContent) blockers.push('campaign.brief has no populated fields');

  // Strategy pillars (1 item)
  const pillars = campaign.strategy && Array.isArray(campaign.strategy.pillars)
    ? campaign.strategy.pillars
    : [];
  if (pillars.length < 3) blockers.push(`strategy.pillars count ${pillars.length} < 3`);

  // Asset readiness (1 item) — at least one asset satisfies ALL five engine gates
  const assets = campaign.assets || {};
  for (const [assetId, asset] of Object.entries(assets)) {
    if (!asset || typeof asset !== 'object') continue;
    const history = Array.isArray(asset.history) ? asset.history : [];

    // Inline axis checks mirror asset-state-engine's evaluation rules. The
    // campaign engine does NOT require('fs') — we re-evaluate inline using
    // the same observable evidence. If asset-state-engine becomes stricter,
    // this check must be updated in lockstep.
    const gateState = asset.qualityGateState;
    const captionState = asset.captionStatus;
    const visualState = asset.visualStatus;
    const approvalState = asset.approvalStatus;
    const publishState = asset.publishStatus;

    // Engine-projected state — trust the field if it's set, else fall back
    // to history-driven logic. Mirrors asset-state-engine's primary-signal
    // preference.
    const captionApprovedByHistory = hasApprovedEvent(history, ['caption-approved']);
    const visualApprovedByHistory = hasApprovedEvent(history, ['visual-approved']);
    const approvalApprovedByHistory = hasApprovedEvent(history, ['approval-approved']);

    const gateEligible = ['gate1-passed', 'gate2-passed', 'gate3-passed', 'approved', 'skipped']
      .indexOf(gateState) !== -1;
    const captionApproved = captionState === 'approved'
      || captionState === 'skipped'
      || (!captionState && captionApprovedByHistory);
    const visualApproved = visualState === 'approved'
      || visualState === 'skipped'
      || (!visualState && visualApprovedByHistory);
    const approvalApproved = approvalState === 'approved'
      || (!approvalState && approvalApprovedByHistory);
    const publishScheduled = publishState === 'scheduled';

    if (gateEligible && captionApproved && visualApproved && approvalApproved && publishScheduled) {
      scheduledAssetIds.push(assetId);
    }
  }

  if (scheduledAssetIds.length === 0) {
    blockers.push('no asset satisfies all five engine gates (qualityGate/caption/visual/approval/publish)');
  }

  return {
    ready: blockers.length === 0,
    blockers,
    scheduledAssetIds,
    fromStatus
  };
}

function hasApprovedEvent(history, actionSet) {
  for (let i = history.length - 1; i >= 0; i--) {
    const e = history[i];
    if (!e || typeof e !== 'object') continue;
    if (actionSet.indexOf(e.action) !== -1) return true;
  }
  return false;
}

// ── Event Recorder (campaign) ─────────────────────────────────────────────

/**
 * Append one campaign-level history event. The single entry point for writes
 * to campaign.history[]. Validates action against CAMPAIGN_EVENT_TAXONOMY.
 * Does NOT mutate any field except campaign.history[].
 */
function recordCampaignEvent(campaign, action, payload) {
  if (CAMPAIGN_EVENT_TAXONOMY.indexOf(action) === -1) {
    throw new InvalidCampaignActionError(action);
  }
  if (!campaign || typeof campaign !== 'object') {
    throw new Error('campaign object required');
  }
  if (!Array.isArray(campaign.history)) campaign.history = [];

  const event = {
    action,
    at: new Date().toISOString(),
    by: (payload && payload.by) || 'unknown',
    reason: (payload && payload.reason) || '',
    evidence: (payload && payload.evidence) || {}
  };

  // Reject duplicate activations (same action already at the top of history).
  // Idempotency: if the latest event is the same action by the same actor,
  // refuse to append another.
  if (campaign.history.length > 0) {
    const last = campaign.history[campaign.history.length - 1];
    if (last && last.action === action && last.by === event.by) {
      return { changed: false, event: last, reason: 'duplicate-event' };
    }
  }

  campaign.history.push(event);
  return { changed: true, event };
}

// ── Status Transition (field-only mutator) ────────────────────────────────

/**
 * Mutate ONLY identity.status. Refuses illegal transitions. Never appends
 * history, never mutates any other field.
 *
 * Returns { changed: boolean, fieldsChanged: string[], fromStatus, toStatus }.
 */
function applyCampaignStatusTransition(campaign, desiredStatus) {
  if (!CAMPAIGN_STATUS_SCHEMA[desiredStatus]) {
    throw new IllegalCampaignTransitionError(
      (campaign && campaign.identity && campaign.identity.status) || null,
      desiredStatus
    );
  }
  if (!campaign || !campaign.identity) {
    throw new Error('campaign.identity required');
  }

  const fromStatus = campaign.identity.status || null;
  if (fromStatus === desiredStatus) {
    return { changed: false, fieldsChanged: [], fromStatus, toStatus: desiredStatus };
  }
  if (!isAllowedTransition(fromStatus, desiredStatus)) {
    throw new IllegalCampaignTransitionError(fromStatus, desiredStatus);
  }

  campaign.identity.status = desiredStatus;
  return {
    changed: true,
    fieldsChanged: ['identity.status'],
    fromStatus,
    toStatus: desiredStatus
  };
}

// ── Atomic write helpers ──────────────────────────────────────────────────

const DEFAULT_CANONICAL = path.join(__dirname, '..', '..', 'campaign-os', 'campaign-data.json');

function _lockPath(p) { return p + '.campaign-lock'; }

function _acquireLock(p) {
  const lockPath = _lockPath(p);
  let attempts = 0;
  while (attempts < 100) {
    try {
      const fd = fs.openSync(lockPath, 'wx');
      fs.writeSync(fd, `${process.pid}\n`);
      return fd;
    } catch (e) {
      if (e.code === 'EEXIST') {
        const waitMs = 50 + Math.floor(Math.random() * 100);
        const start = Date.now();
        while (Date.now() - start < waitMs) { /* busy wait */ }
        attempts++;
        continue;
      }
      throw e;
    }
  }
  throw new Error('could not acquire campaign-engine lock after 100 attempts');
}

function _releaseLock(fd, p) {
  const lockPath = _lockPath(p);
  try { fs.closeSync(fd); } catch (_) {}
  try { fs.unlinkSync(lockPath); } catch (_) {}
}

function _atomicWriteJson(targetPath, obj) {
  const tmpPath = targetPath + '.campaign-tmp-' + crypto.randomBytes(6).toString('hex');
  fs.writeFileSync(tmpPath, JSON.stringify(obj, null, 2));
  fs.renameSync(tmpPath, targetPath);
}

// ── Orchestrator ──────────────────────────────────────────────────────────

/**
 * Activate a campaign end-to-end:
 *   1. Load canonical.
 *   2. evaluateCampaignActivation(campaign) — pure check.
 *   3. If already active: idempotent no-op, return.
 *   4. If blockers: return {ok:false, blockers} — no writes.
 *   5. Otherwise:
 *      a. Capture timestamp.
 *      b. recordCampaignEvent('campaign-activated') — appends to campaign.history[].
 *      c. applyCampaignStatusTransition('active') — flips identity.status.
 *      d. _atomicWriteJson — persists canonical.
 *   6. On any error: lock released, no write.
 *
 * Options:
 *   - by: string (default 'christelle')
 *   - reason: string
 *   - canonicalPath: string (override default)
 *   - dryRun: boolean (default false)
 *
 * Returns:
 *   {
 *     ok: boolean,
 *     changed: boolean,
 *     reason: string,
 *     blockers: string[],
 *     scheduledAssetIds: string[],
 *     fromStatus: string,
 *     toStatus: string,
 *     event: object|null
 *   }
 */
function activateCampaign(campaignId, options) {
  const opts = options || {};
  const canonicalPath = opts.canonicalPath || DEFAULT_CANONICAL;
  const by = opts.by || 'christelle';
  const reason = opts.reason || 'Campaign activation approved';
  const dryRun = opts.dryRun === true;

  if (!campaignId || typeof campaignId !== 'string') {
    return { ok: false, changed: false, reason: 'campaignId required', blockers: ['campaignId required'], scheduledAssetIds: [], fromStatus: null, toStatus: null, event: null };
  }

  let lockFd = null;
  try {
    // Phase A: read & evaluate (no lock needed for pure read)
    if (!fs.existsSync(canonicalPath)) {
      return { ok: false, changed: false, reason: `canonical not found: ${canonicalPath}`, blockers: ['canonical not found'], scheduledAssetIds: [], fromStatus: null, toStatus: null, event: null };
    }
    const canonical = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'));
    const campaign = canonical.campaigns && canonical.campaigns[campaignId];
    if (!campaign) {
      return { ok: false, changed: false, reason: `campaign not found: ${campaignId}`, blockers: ['campaign not found'], scheduledAssetIds: [], fromStatus: null, toStatus: null, event: null };
    }

    const evaluation = evaluateCampaignActivation(campaign);

    // Idempotency: already active
    const fromStatus = evaluation.fromStatus;
    if (fromStatus === 'active') {
      return {
        ok: true,
        changed: false,
        reason: 'already-active',
        blockers: [],
        scheduledAssetIds: evaluation.scheduledAssetIds,
        fromStatus,
        toStatus: 'active',
        event: null
      };
    }

    // Readiness gate
    if (!evaluation.ready) {
      return {
        ok: false,
        changed: false,
        reason: 'not-ready',
        blockers: evaluation.blockers,
        scheduledAssetIds: evaluation.scheduledAssetIds,
        fromStatus,
        toStatus: null,
        event: null
      };
    }

    // Wrong source state (e.g. draft, or terminal)
    if (!isAllowedTransition(fromStatus, 'active')) {
      return {
        ok: false,
        changed: false,
        reason: `illegal-transition: ${fromStatus} -> active`,
        blockers: [`illegal transition ${fromStatus} -> active`],
        scheduledAssetIds: evaluation.scheduledAssetIds,
        fromStatus,
        toStatus: null,
        event: null
      };
    }

    if (dryRun) {
      return {
        ok: true,
        changed: false,
        reason: 'dry-run',
        blockers: [],
        scheduledAssetIds: evaluation.scheduledAssetIds,
        fromStatus,
        toStatus: 'active',
        event: null
      };
    }

    // Phase B: acquire lock for write
    lockFd = _acquireLock(canonicalPath);

    // Re-read under lock to defeat TOCTOU
    const lockedCanonical = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'));
    const lockedCampaign = lockedCanonical.campaigns[campaignId];
    if (!lockedCampaign) {
      throw new Error(`campaign disappeared during lock: ${campaignId}`);
    }
    const lockedEval = evaluateCampaignActivation(lockedCampaign);
    if (!lockedEval.ready || lockedEval.fromStatus === 'active') {
      // state changed between read and lock — surface as not-ready
      return {
        ok: lockedEval.fromStatus === 'active',
        changed: false,
        reason: lockedEval.fromStatus === 'active' ? 'already-active' : 'state-changed-under-lock',
        blockers: lockedEval.blockers,
        scheduledAssetIds: lockedEval.scheduledAssetIds,
        fromStatus: lockedEval.fromStatus,
        toStatus: null,
        event: null
      };
    }

    // Phase C: write event + transition
    const at = new Date().toISOString();
    const evidence = {
      scheduledAssetIds: lockedEval.scheduledAssetIds,
      fromStatus: lockedEval.fromStatus,
      toStatus: 'active',
      by,
      at
    };

    const recordResult = recordCampaignEvent(lockedCampaign, 'campaign-activated', { by, reason, evidence });
    if (!recordResult.changed) {
      // Duplicate event guard — refuse to double-write
      return {
        ok: true,
        changed: false,
        reason: recordResult.reason || 'duplicate-event',
        blockers: [],
        scheduledAssetIds: lockedEval.scheduledAssetIds,
        fromStatus: lockedEval.fromStatus,
        toStatus: null,
        event: recordResult.event
      };
    }

    const transition = applyCampaignStatusTransition(lockedCampaign, 'active');
    if (!transition.changed) {
      throw new Error('status transition unexpectedly no-op after event write');
    }

    lockedCanonical.updatedAt = at;

    // Phase D: atomic persist
    _atomicWriteJson(canonicalPath, lockedCanonical);

    return {
      ok: true,
      changed: true,
      reason: 'activated',
      blockers: [],
      scheduledAssetIds: lockedEval.scheduledAssetIds,
      fromStatus: transition.fromStatus,
      toStatus: transition.toStatus,
      event: recordResult.event
    };
  } catch (err) {
    return {
      ok: false,
      changed: false,
      reason: `error: ${err.message}`,
      blockers: [err.message],
      scheduledAssetIds: [],
      fromStatus: null,
      toStatus: null,
      event: null
    };
  } finally {
    if (lockFd !== null) _releaseLock(lockFd, canonicalPath);
  }
}

module.exports = {
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
};