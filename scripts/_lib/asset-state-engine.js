/**
 * scripts/_lib/asset-state-engine.js
 *
 * Canonical Asset State Engine.
 *
 * Owns the five publishing-state fields exclusively:
 *   - qualityGateState
 *   - captionStatus
 *   - visualStatus
 *   - approvalStatus
 *   - publishStatus
 *
 * Architecture (Step 86 Revised):
 *   - Producers (Cockpit, Publisher, Image-Gen, Copywriter, Review Queue,
 *     Truth Collector) emit REAL history events only.
 *   - They do that via the Event Recorder (recordEvent, below). No producer
 *     ever touches asset.history[] directly.
 *   - evaluateAsset() is a PURE projection of (asset, history, externalSignals)
 *     into the desired 5-field state. No side effects.
 *   - applyStateTransition() mutates ONLY the 5 fields. No history writes.
 *   - History is canonical. State is derived.
 *
 * Hard rules:
 *   - evaluateAsset NEVER calls require('fs'). Verifiable via grep.
 *   - applyStateTransition NEVER appends to asset.history. Verifiable via grep.
 *   - applyStateTransition NEVER mutates caption, visualBrief, filePath,
 *     owner, assetType, keyFindings, or any non-state field.
 *
 * Run: this file is a module, not a CLI. Use scripts/reconcile-asset-state.js
 * for command-line reconciliation.
 *
 * Module exports:
 *   - ASSET_STATE_SCHEMA     (object of allowed values per field)
 *   - KNOWN_HISTORY_ACTIONS  (array of accepted history.action strings)
 *   - recordEvent            (Event Recorder — single entry point for producers)
 *   - evaluateAsset          (pure projection)
 *   - applyStateTransition   (field-only mutator)
 *   - reconcileCampaign      (atomic reconcile one campaign)
 *   - reconcileAll           (atomic reconcile all campaigns)
 *   - InvalidFieldValueError (exported for tests)
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const visibilityGuard = require('./visibility-guard');

// ── Schema ────────────────────────────────────────────────────────────────

const ASSET_STATE_SCHEMA = {
  qualityGateState: ['pending', 'gate1-passed', 'gate2-passed', 'gate2-failed', 'approved', 'skipped'],
  captionStatus:    ['pending', 'draft', 'approved', 'rejected'],
  visualStatus:     ['pending', 'brief-written', 'generated', 'approved', 'rejected', 'skipped'],
  approvalStatus:   ['pending', 'review', 'approved', 'rejected'],
  publishStatus:    ['planned', 'scheduled', 'live', 'failed', 'skipped', 'archived'],
};

// History actions the engine RECOGNISES for read-only consumption.
// The engine never writes these. Producers emit them via recordEvent().
const KNOWN_HISTORY_ACTIONS = [
  // canonical caption lifecycle
  'caption-created', 'caption-revised', 'caption-approved', 'caption-rejected',
  // canonical visual lifecycle
  'visual-generated', 'visual-revised', 'visual-approved', 'visual-rejected',
  // canonical approval lifecycle
  'approval-requested', 'approval-approved', 'approval-rejected',
  // canonical publish lifecycle (Step 94b: split the publish lifecycle so a
  // draft, scheduled, and live outcome each have a truthful event name).
  //   publish-draft-created: Postiz returned a draft (not live)
  //   publish-scheduled:     Postiz returned a scheduled post
  //   publish-confirmed:     Postiz returned a live/published post
  //   publish-failed:        Postiz returned a failure
  // Only publish-confirmed may move publishStatus to 'live'.
  'publish-requested', 'publish-draft-created', 'publish-scheduled',
  'publish-confirmed', 'publish-failed',
  // generic
  'asset-edited', 'campaign-edited', 'engagement-recorded',
  // regeneration request (resets gate2-failed stickiness)
  'regenerate-requested',
  // legacy events already in canonical history (pre-Step 87) — READ ONLY.
  // The engine treats them as aliases of canonical events for backward
  // convergence. New producers must emit the canonical actions above.
  'created', 'generated', 'brief-created', 'delivered', 'rejected',
  'approved', 'caption-draft', 'visual-brief-written', 'shell-created',
  'published',
];

// Alias map: legacy event.action -> canonical event.action (read-only).
// Used internally by evaluators so legacy history converges correctly.
const LEGACY_ACTION_ALIAS = {
  'caption-draft':          'caption-created',
  'visual-brief-written':   'visual-revised',
  'delivered':              'visual-generated',
  'brief-created':          'visual-revised',
  'generated':              'visual-generated',
  'created':                'asset-edited',
  'shell-created':          'asset-edited',
  'published':              'publish-confirmed',
  'approved':               'approval-approved',
  'rejected':               'approval-rejected',
};

// ── Errors ────────────────────────────────────────────────────────────────

class InvalidFieldValueError extends Error {
  constructor(field, value) {
    super(`Invalid value for ${field}: ${JSON.stringify(value)}`);
    this.name = 'InvalidFieldValueError';
    this.field = field;
    this.value = value;
  }
}

class InvalidHistoryActionError extends Error {
  constructor(action) {
    super(`Unknown history action: ${JSON.stringify(action)}`);
    this.name = 'InvalidHistoryActionError';
    this.action = action;
  }
}

// ── Event Recorder ────────────────────────────────────────────────────────
//
// SINGLE entry point for producers to append history events. Producers must
// NEVER push to asset.history[] directly. This guarantees:
//   1. Action strings are validated against the known taxonomy
//   2. Event shape is normalised ({action, by, at, ...rest})
//   3. The at timestamp is auto-stamped if not provided
//   4. Timestamps are ISO 8601

function recordEvent(history, action, payload = {}) {
  if (!Array.isArray(history)) {
    throw new TypeError('recordEvent: history must be an array');
  }
  if (typeof action !== 'string') {
    throw new TypeError('recordEvent: action must be a string');
  }
  if (!KNOWN_HISTORY_ACTIONS.includes(action)) {
    throw new InvalidHistoryActionError(action);
  }
  const event = {
    action,
    by: typeof payload.by === 'string' && payload.by.length > 0 ? payload.by : 'unknown',
    at: typeof payload.at === 'string' && payload.at.length > 0 ? payload.at : new Date().toISOString(),
  };
  // Carry through any extra context (reason, filePath, postizPostId, ...)
  for (const [k, v] of Object.entries(payload)) {
    if (k === 'by' || k === 'at') continue;
    if (event[k] === undefined) event[k] = v;
  }
  history.push(event);
  return event;
}

// ── Pure evaluator ────────────────────────────────────────────────────────
//
// evaluateAsset(asset, history, externalSignals) -> {
//   qualityGateState, captionStatus, visualStatus,
//   approvalStatus, publishStatus,
//   observations: [{axis, evidence}]
// }
//
// PURE. No file I/O. No asset mutation. Caller passes history explicitly.

function evaluateAsset(asset, history, externalSignals) {
  if (!asset || typeof asset !== 'object') {
    throw new TypeError('evaluateAsset: asset must be an object');
  }
  const rawHistory = Array.isArray(history) ? history : (asset.history || []);
  // Normalise legacy actions to canonical for projection only. Original
  // history is never modified by the engine.
  const historyArr = _normalizedHistory(rawHistory);
  const ext = externalSignals || {};
  const observations = [];

  const result = {
    qualityGateState: evaluateQualityGateState(asset, historyArr, ext, observations),
    captionStatus:    evaluateCaptionStatus(asset, historyArr, ext, observations),
    visualStatus:     evaluateVisualStatus(asset, historyArr, ext, observations),
    approvalStatus:   evaluateApprovalStatus(asset, historyArr, ext, observations),
    publishStatus:    evaluatePublishStatus(asset, historyArr, ext, observations),
    observations,
  };
  return result;
}

// Build a normalised view of history where legacy actions are mapped to
// canonical equivalents. Each normalised entry is {action, by, at, ...rest}.
// The original history array is NEVER mutated.
function _normalizedHistory(rawHistory) {
  const out = [];
  for (const h of rawHistory) {
    if (!h || typeof h !== 'object' || typeof h.action !== 'string') continue;
    const aliased = LEGACY_ACTION_ALIAS[h.action] || h.action;
    if (!KNOWN_HISTORY_ACTIONS.includes(h.action)) continue;
    const norm = { action: aliased, by: h.by || 'unknown', at: h.at || '' };
    for (const [k, v] of Object.entries(h)) {
      if (k === 'action' || k === 'by' || k === 'at') continue;
      norm[k] = v;
    }
    out.push(norm);
  }
  return out;
}

// ── Internal axis evaluators ──────────────────────────────────────────────

function evaluateQualityGateState(asset, history, ext, observations) {
  // R3 — sticky gate2-failed
  if (asset.qualityGateState === 'gate2-failed') {
    const regenReq = history.find(h => h && h.action === 'regenerate-requested');
    if (!regenReq) {
      observations.push({ axis: 'qualityGateState', evidence: { reason: 'sticky gate2-failed' } });
      return 'gate2-failed';
    }
  }
  // R4 — research skip of visual-only gates; research only needs gate1
  if (asset.assetType === 'research') {
    const hasCaption = typeof asset.caption === 'string' && asset.caption.length >= 50;
    const hasFindings = Array.isArray(asset.keyFindings) && asset.keyFindings.length > 0;
    if (hasCaption && hasFindings) {
      observations.push({ axis: 'qualityGateState', evidence: { reason: 'research gate1 satisfied', hasCaption, hasFindings } });
      return 'gate1-passed';
    }
    observations.push({ axis: 'qualityGateState', evidence: { reason: 'research gate1 incomplete', hasCaption, hasFindings } });
    return 'pending';
  }
  // Preserve past-gate1 states when visual is still approved/skipped
  if (asset.qualityGateState === 'gate2-passed' || asset.qualityGateState === 'approved') {
    const visualApproved = asset.visualStatus === 'approved' || asset.visualStatus === 'skipped';
    if (!visualApproved) {
      // visual regressed — fall back to gate1
      observations.push({ axis: 'qualityGateState', evidence: { reason: 'visual regressed; demote to gate1' } });
      return 'gate1-passed';
    }
    observations.push({ axis: 'qualityGateState', evidence: { reason: 'preserved past gate1' } });
    return asset.qualityGateState;
  }
  // Standard gate1: caption + visualBrief + owner present
  const hasCaption = typeof asset.caption === 'string' && asset.caption.length >= 50;
  const hasVisualBrief = checkVisualBrief(asset);
  const hasOwner = !!asset.owner;
  if (hasCaption && hasVisualBrief && hasOwner) {
    observations.push({ axis: 'qualityGateState', evidence: { reason: 'gate1: caption + visualBrief + owner', hasCaption, hasVisualBrief, hasOwner } });
    return 'gate1-passed';
  }
  observations.push({ axis: 'qualityGateState', evidence: { reason: 'gate1: missing inputs', hasCaption, hasVisualBrief, hasOwner } });
  return 'pending';
}

function evaluateCaptionStatus(asset, history, ext, observations) {
  // Backward transitions win: latest event determines state when applicable
  const captions = history.filter(h => h && CAPTION_EVENTS.includes(h.action));
  const lastRejection = findLast(captions, 'caption-rejected');
  if (lastRejection) {
    // Rejection can be reopened by a later caption-revised
    const lastRevisedAfter = captions.find(h => h.action === 'caption-revised' && h.at > lastRejection.at);
    if (!lastRevisedAfter) {
      observations.push({ axis: 'captionStatus', evidence: { reason: 'caption-rejected in history (no revision after)' } });
      return 'rejected';
    }
  }
  const lastApproval = findLast(captions, 'caption-approved');
  if (lastApproval) {
    // Approval can be reopened by a later caption-revised
    const lastRevisedAfter = captions.find(h => h.action === 'caption-revised' && h.at > lastApproval.at);
    if (!lastRevisedAfter) {
      observations.push({ axis: 'captionStatus', evidence: { reason: 'caption-approved in history (no revision after)' } });
      return 'approved';
    }
    observations.push({ axis: 'captionStatus', evidence: { reason: 'caption-revised after approval' } });
    return 'draft';
  }
  const lastDraft = findLast(captions, 'caption-created') || findLast(captions, 'caption-revised');
  const captionLen = typeof asset.caption === 'string' ? asset.caption.length : 0;
  if (lastDraft || captionLen >= 100) {
    if (captionLen >= 100) {
      observations.push({ axis: 'captionStatus', evidence: { reason: 'caption present, length OK, no rejection', captionLen } });
      return 'approved';
    }
    observations.push({ axis: 'captionStatus', evidence: { reason: 'caption draft present', captionLen, hasDraftEvent: !!lastDraft } });
    return 'draft';
  }
  observations.push({ axis: 'captionStatus', evidence: { reason: 'no caption evidence' } });
  return 'pending';
}

function evaluateVisualStatus(asset, history, ext, observations) {
  if (asset.assetType === 'research') {
    observations.push({ axis: 'visualStatus', evidence: { reason: 'research assetType skips visual gate' } });
    return 'skipped';
  }
  const visualEvents = history.filter(h => h && VISUAL_EVENTS.includes(h.action));
  const lastRejection = findLast(visualEvents, 'visual-rejected');
  if (lastRejection) {
    const lastRevisedAfter = visualEvents.find(h => h.action === 'visual-revised' && h.at > lastRejection.at);
    if (!lastRevisedAfter) {
      observations.push({ axis: 'visualStatus', evidence: { reason: 'visual-rejected in history (no revision after)' } });
      return 'rejected';
    }
  }
  const lastApproval = findLast(visualEvents, 'visual-approved');
  if (lastApproval) {
    const lastRevisedAfter = visualEvents.find(h => h.action === 'visual-revised' && h.at > lastApproval.at);
    if (!lastRevisedAfter) {
      observations.push({ axis: 'visualStatus', evidence: { reason: 'visual-approved in history (no revision after)' } });
      return 'approved';
    }
    observations.push({ axis: 'visualStatus', evidence: { reason: 'visual-revised after approval' } });
    return 'generated';
  }
  const hasFilePath = !!asset.filePath;
  const lastDelivered = findLast(visualEvents, 'visual-generated') || findLast(visualEvents, 'asset-edited');
  // A visual-generated event with filePath implies generated
  const visualGenerated = visualEvents.find(h => h.action === 'visual-generated' && (h.filePath || asset.filePath));
  if (visualGenerated || (hasFilePath && lastDelivered)) {
    observations.push({ axis: 'visualStatus', evidence: { reason: 'visual-generated + filePath set', filePath: asset.filePath } });
    return 'generated';
  }
  const lastBrief = findLast(visualEvents, 'visual-revised') || findLast(visualEvents, 'asset-edited');
  const hasBrief = checkVisualBrief(asset) || !!lastBrief;
  if (hasBrief) {
    observations.push({ axis: 'visualStatus', evidence: { reason: 'visual brief present' } });
    return 'brief-written';
  }
  observations.push({ axis: 'visualStatus', evidence: { reason: 'no visual evidence' } });
  return 'pending';
}

function evaluateApprovalStatus(asset, history, ext, observations) {
  // External approval/rejection from cockpit/review-queue wins
  const extApproval = (ext.approvalActions || []).find(a => a && a.assetId === asset.assetId);
  if (extApproval && extApproval.action === 'approved') {
    observations.push({ axis: 'approvalStatus', evidence: { reason: 'external approval action' } });
    return 'approved';
  }
  if (extApproval && extApproval.action === 'rejected') {
    observations.push({ axis: 'approvalStatus', evidence: { reason: 'external rejection action' } });
    return 'rejected';
  }
  // History-driven approval/rejection
  const approvalEvents = history.filter(h => h && APPROVAL_EVENTS.includes(h.action));
  const lastRejection = findLast(approvalEvents, 'approval-rejected') || findLast(approvalEvents, 'rejected'); // legacy
  const lastApproval = findLast(approvalEvents, 'approval-approved') || findLast(approvalEvents, 'approved'); // legacy
  // Backward wins: latest event determines state when in conflict
  const lastEv = history.filter(h => h && APPROVAL_EVENTS.includes(h.action)).slice(-1)[0];
  if (lastEv && (lastEv.action === 'approval-rejected' || lastEv.action === 'rejected')) {
    observations.push({ axis: 'approvalStatus', evidence: { reason: 'rejected in history' } });
    return 'rejected';
  }
  if (lastEv && (lastEv.action === 'approval-approved' || lastEv.action === 'approved') && lastEv.by === 'christelle') {
    observations.push({ axis: 'approvalStatus', evidence: { reason: 'christelle approved in history' } });
    return 'approved';
  }
  // If caption and visual are ready, auto-promote to review
  const captionDraft = history.some(h => h && (h.action === 'caption-created' || h.action === 'caption-revised'));
  const visualBriefWritten = history.some(h => h && h.action === 'visual-revised') || checkVisualBrief(asset);
  if (captionDraft && visualBriefWritten) {
    observations.push({ axis: 'approvalStatus', evidence: { reason: 'caption + visual brief present -> review' } });
    return 'review';
  }
  observations.push({ axis: 'approvalStatus', evidence: { reason: 'no review/approval evidence' } });
  return 'pending';
}

function evaluatePublishStatus(asset, history, ext, observations) {
  // Postiz confirmation from external signals (Step 94b).
  //
  // ONLY a confirmed-live status flips publishStatus to 'live'. A draft or
  // scheduled confirmation leaves publishStatus where eligibility puts it
  // (typically 'scheduled' when all 5 engine gates are satisfied).
  //
  // The history event `publish-confirmed` alone does NOT flip to live — that
  // event is only emitted when Postiz returned a live/published response. If
  // the external signal is missing or non-live, the engine trusts eligibility
  // (which keeps the asset at 'scheduled' until proven live by a poll).
  const extPostiz = (ext.postizConfirmations || []).find(p => p && p.assetId === asset.assetId);
  if (extPostiz && (extPostiz.status === 'live' || extPostiz.status === 'published')) {
    const operatorState = (ext.operatorVisibility && ext.operatorVisibility[asset.assetId]) || 'unknown';
    const guard = visibilityGuard.assertNoVisibilityDispute({ apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: operatorState });
    if (visibilityGuard.blocksAction(guard, 'mark-live')) {
      observations.push({ axis: 'publishStatus', evidence: { reason: `visibility guard blocks mark-live: ${guard.reason}` } });
    } else {
      observations.push({ axis: 'publishStatus', evidence: { reason: 'Postiz confirmation -> live' } });
      return 'live';
    }
  }
  if (extPostiz && extPostiz.status === 'failed') {
    observations.push({ axis: 'publishStatus', evidence: { reason: 'Postiz failure recorded' } });
    return 'failed';
  }
  // History-driven failure (Step 87 contract preserved).
  const failedEvent = history.find(h => h && h.action === 'publish-failed');
  if (failedEvent) {
    observations.push({ axis: 'publishStatus', evidence: { reason: 'publish-failed in history' } });
    return 'failed';
  }
  // Step 94b: draft / scheduled history events are informational. They
  // confirm that the publisher reached Postiz successfully, but do NOT
  // move publishStatus beyond the eligibility projection below.
  // (publish-draft-created, publish-scheduled, publish-confirmed history
  //  events are all recognised by the engine but none of them alone flips
  //  to 'live' — only ext.postizConfirmations[].status === 'live'/'published' does.)
  // Eligibility for scheduled. Step 88 fix:
  //
  // "scheduled" means genuinely ready to enter Publisher. Each axis must
  // satisfy the ENGINE-PROJECTED current state, not just the raw history.
  // A visual brief is planning; scheduling is execution readiness. They
  // are separate states.
  //
  // - captionStatus: must be the engine's projected state (not history alone)
  // - visualStatus:  must be approved or skipped (production artefact exists
  //                 or is not required for research). brief-written is NOT
  //                 sufficient.
  // - approvalStatus: must be approved by christelle (history-driven)
  // - qualityGateState: must be at or past gate1
  const captionState = asset.captionStatus;
  const visualState = asset.visualStatus;
  const approvalState = asset.approvalStatus;
  const gateState = asset.qualityGateState;

  // History-derived overrides (only for backward-compat with assets whose
  // engine fields haven't been applied yet — e.g. immediately after an
  // approval event in the same evaluateAsset call).
  const captionEventApproved = history.some(h => h && (h.action === 'caption-approved' || h.action === 'approved'));
  const visualEventApproved = history.some(h => h && h.action === 'visual-approved');
  const approvalEventApproved = history.some(h => h && (h.action === 'approval-approved' || h.action === 'approved') && h.by === 'christelle') ||
    (ext.approvalActions || []).some(a => a && a.assetId === asset.assetId && a.action === 'approved');

  const captionApproved =
    captionState === 'approved' ||
    (captionState === undefined && captionEventApproved) ||
    (typeof asset.caption === 'string' && asset.caption.length >= 100 && !history.some(h => h && h.action === 'caption-rejected'));

  var visualApproved =
        visualState==='approved' ||
        visualState==='skipped' ||
        (visualState===undefined && asset.assetType==='research') ||
        (visualState===undefined && visualEventApproved) ||
        // Field is stale (still at brief-written/generated) but the
        // canonical visual-approved event is in history. The engine
        // treats the event as authoritative when the field hasn't been
        // re-applied yet in this call.
        ((visualState==='brief-written' || visualState==='generated') && visualEventApproved);

  const approvalApproved =
    approvalState === 'approved' ||
    (approvalState === undefined && approvalEventApproved);

  // qualityGateState: eligible means at or past gate1. For research, a
  // caption + keyFindings is sufficient for gate1. For non-research, a
  // caption + visualBrief + owner is sufficient. If the field is unset but
  // the inputs prove gate1, fall back to that derivation.
  const gatePassed =
    gateState === 'gate1-passed' ||
    gateState === 'gate2-passed' ||
    gateState === 'approved' ||
    gateState === 'skipped' ||
    (gateState === undefined && asset.assetType === 'research' && typeof asset.caption === 'string' && asset.caption.length >= 50) ||
    (gateState === undefined && asset.assetType !== 'research' &&
     typeof asset.caption === 'string' && asset.caption.length >= 50 &&
     (asset.visualBrief && (
       (typeof asset.visualBrief === 'string' && asset.visualBrief.length > 20) ||
       (typeof asset.visualBrief === 'object' && asset.visualBrief.concept && asset.visualBrief.concept.length > 20)
     )) &&
     !!asset.owner);

  // All required production artefacts present:
  //   - caption field non-empty (the actual copy)
  //   - platform set (so Publisher knows where to dispatch)
  //   - visual brief OR filePath OR (research + keyFindings) (production
  //     artefact exists or planning document is complete)
  const isResearch = asset.assetType === 'research';
  const researchArtefacts = isResearch && Array.isArray(asset.keyFindings) && asset.keyFindings.length > 0;
  const artefactsPresent =
    typeof asset.caption === 'string' && asset.caption.length > 0 &&
    typeof asset.platform === 'string' && asset.platform.length > 0 &&
    (asset.visualBrief || asset.filePath || researchArtefacts);

  const eligible = approvalApproved && captionApproved && visualApproved && gatePassed && artefactsPresent;
  if (eligible) {
    observations.push({
      axis: 'publishStatus',
      evidence: {
        reason: 'all gates satisfied -> scheduled',
        captionApproved, visualApproved, approvalApproved, gatePassed, artefactsPresent,
        visualState, captionState, approvalState, gateState,
      },
    });
    return 'scheduled';
  }
  observations.push({
    axis: 'publishStatus',
    evidence: {
      reason: 'not eligible (gates not satisfied)',
      captionApproved, visualApproved, approvalApproved, gatePassed, artefactsPresent,
      visualState, captionState, approvalState, gateState,
      missingGates: [
        !captionApproved && 'captionApproved',
        !visualApproved && 'visualApproved',
        !approvalApproved && 'approvalApproved',
        !gatePassed && 'gatePassed',
        !artefactsPresent && 'artefactsPresent',
      ].filter(Boolean),
    },
  });
  return 'planned';
}

// ── Apply (mutator) ───────────────────────────────────────────────────────
//
// applyStateTransition(asset, desiredState)
//   -> {changed: boolean, fieldsChanged: string[]}
//
// MUTATES asset in-memory. Writes ONLY the 5 publishing state fields.
// NEVER appends to asset.history. NEVER touches caption/visualBrief/filePath.

function applyStateTransition(asset, desiredState) {
  if (!asset || typeof asset !== 'object') {
    throw new TypeError('applyStateTransition: asset must be an object');
  }
  if (!desiredState || typeof desiredState !== 'object') {
    throw new TypeError('applyStateTransition: desiredState must be an object');
  }
  const fieldsChanged = [];
  for (const field of Object.keys(ASSET_STATE_SCHEMA)) {
    const candidate = desiredState[field];
    if (candidate === undefined) continue;
    if (!ASSET_STATE_SCHEMA[field].includes(candidate)) {
      throw new InvalidFieldValueError(field, candidate);
    }
    if (asset[field] !== candidate) {
      asset[field] = candidate;
      fieldsChanged.push(field);
    }
  }
  if (fieldsChanged.length > 0) {
    asset.updatedAt = new Date().toISOString();
  }
  return { changed: fieldsChanged.length > 0, fieldsChanged };
}

// ── Event taxonomy helpers ────────────────────────────────────────────────

const CAPTION_EVENTS = ['caption-created', 'caption-revised', 'caption-approved', 'caption-rejected'];
const VISUAL_EVENTS = ['visual-generated', 'visual-revised', 'visual-approved', 'visual-rejected', 'asset-edited'];
const APPROVAL_EVENTS = ['approval-requested', 'approval-approved', 'approval-rejected'];

function findLast(arr, action) {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] && arr[i].action === action) return arr[i];
  }
  return null;
}

function checkVisualBrief(asset) {
  if (!asset.visualBrief) return false;
  if (typeof asset.visualBrief === 'string') return asset.visualBrief.length > 20;
  if (typeof asset.visualBrief === 'object') {
    if (typeof asset.visualBrief.concept === 'string' && asset.visualBrief.concept.length > 20) return true;
    if (typeof asset.visualBrief.description === 'string' && asset.visualBrief.description.length > 20) return true;
  }
  return false;
}

// ── Reconciler (atomic file ops) ──────────────────────────────────────────

const DEFAULT_CANONICAL = path.join(__dirname, '..', '..', 'campaign-os', 'campaign-data.json');

function _canonicalLockPath(p) { return p + '.lock'; }

function _acquireLock(p) {
  const lockPath = _canonicalLockPath(p);
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
  throw new Error('could not acquire canonical lock after 100 attempts');
}

function _releaseLock(fd, p) {
  const lockPath = _canonicalLockPath(p);
  try { fs.closeSync(fd); } catch (_) {}
  try { fs.unlinkSync(lockPath); } catch (_) {}
}

function _atomicWrite(p, content) {
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, content);
  fs.renameSync(tmp, p);
}

function reconcileCampaign(campaignId, canonicalPath, opts) {
  const cp = canonicalPath || DEFAULT_CANONICAL;
  const o = opts || {};
  if (!fs.existsSync(cp)) {
    throw new Error(`canonical file not found: ${cp}`);
  }
  const canonical = JSON.parse(fs.readFileSync(cp, 'utf8'));
  const campaign = canonical.campaigns && canonical.campaigns[campaignId];
  if (!campaign) {
    throw new Error(`campaign not found: ${campaignId}`);
  }
  const assets = campaign.assets || {};
  const summary = [];
  let changed = 0;
  for (const [assetId, asset] of Object.entries(assets)) {
    const history = Array.isArray(asset.history) ? asset.history : [];
    const desired = evaluateAsset(asset, history, {});
    const applyResult = applyStateTransition(asset, desired);
    if (applyResult.changed) {
      changed++;
      summary.push({ assetId, fieldsChanged: applyResult.fieldsChanged });
    }
  }
  if (changed > 0 && !o.dryRun) {
    const fd = _acquireLock(cp);
    try {
      canonical.updatedAt = new Date().toISOString();
      _atomicWrite(cp, JSON.stringify(canonical, null, 2));
    } finally {
      _releaseLock(fd, cp);
    }
  }
  return { changed, summary, dryRun: !!o.dryRun };
}

function reconcileAll(opts) {
  const o = opts || {};
  const cp = o.canonicalPath || DEFAULT_CANONICAL;
  if (!fs.existsSync(cp)) {
    throw new Error(`canonical file not found: ${cp}`);
  }
  const canonical = JSON.parse(fs.readFileSync(cp, 'utf8'));
  const summary = [];
  let totalChanged = 0;
  for (const [campaignId, campaign] of Object.entries(canonical.campaigns || {})) {
    const assets = campaign.assets || {};
    for (const [assetId, asset] of Object.entries(assets)) {
      const history = Array.isArray(asset.history) ? asset.history : [];
      const desired = evaluateAsset(asset, history, {});
      const applyResult = applyStateTransition(asset, desired);
      if (applyResult.changed) {
        totalChanged++;
        summary.push({ campaignId, assetId, fieldsChanged: applyResult.fieldsChanged });
      }
    }
  }
  if (totalChanged > 0 && !o.dryRun) {
    const fd = _acquireLock(cp);
    try {
      canonical.updatedAt = new Date().toISOString();
      _atomicWrite(cp, JSON.stringify(canonical, null, 2));
    } finally {
      _releaseLock(fd, cp);
    }
  }
  return { changed: totalChanged, summary, dryRun: !!o.dryRun };
}

// ── Exports ───────────────────────────────────────────────────────────────

module.exports = {
  ASSET_STATE_SCHEMA,
  KNOWN_HISTORY_ACTIONS,
  recordEvent,
  evaluateAsset,
  applyStateTransition,
  reconcileCampaign,
  reconcileAll,
  InvalidFieldValueError,
  InvalidHistoryActionError,
};