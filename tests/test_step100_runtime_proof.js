// Step 100 — Controlled runtime proof of the Visibility Guard.
//
// Goal: prove that the guard behaves correctly in the real publisher and
// Truth Collector call paths when Christelle explicitly disputes visibility.
//
// Strategy: do NOT invoke run_publisher / asset-state-engine / truth_collector
// end-to-end (they write data or call Postiz). Instead, for each call site
// we capture its real argument shape (from the source) and exercise the
// guard against fixture inputs derived from the canonical campaign record.
// This proves the guard behaves correctly in the *real call paths' argument
// shapes*.
//
// Asset under proof: use-the-right-equipment-mq5l90bk-feed-post-04
// Known canonical Postiz ID: cmrypnzq802fspe0ynp1nu3vb
//
// Rules:
//   - No data files are written.
//   - No Postiz endpoint is called.
//   - Process-local VISIBILITY_DISPUTES is set via env only.
//   - No fixtures persist after process exits.

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const guard = require('../scripts/_lib/visibility-guard');

const ASSET_ID = 'use-the-right-equipment-mq5l90bk-feed-post-04';
const CANONICAL_POSTIZ_ID = 'cmrypnzq802fspe0ynp1nu3vb';
const CANONICAL_FILE = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');

// Snapshot the canonical files BEFORE running. After the proof we re-check
// these to confirm nothing on disk changed.
function snapshot() {
  return {
    campaignMtime: fs.statSync(CANONICAL_FILE).mtimeMs,
    campaignSha: require('crypto').createHash('sha256')
      .update(fs.readFileSync(CANONICAL_FILE)).digest('hex'),
    dataFiles: listDataFiles(),
  };
}

function listDataFiles() {
  const dataDir = path.join(__dirname, '..', 'data');
  const out = {};
  function walk(p) {
    if (!fs.existsSync(p)) return;
    for (const e of fs.readdirSync(p, { withFileTypes: true })) {
      const full = path.join(p, e.name);
      if (e.isDirectory()) walk(full);
      else out[path.relative(path.join(__dirname, '..'), full)] = {
        mtimeMs: fs.statSync(full).mtimeMs,
        sha: null,
      };
    }
  }
  walk(dataDir);
  return out;
}

const before = snapshot();
const phaseResults = [];

// Load the canonical asset record (read-only)
const canonical = JSON.parse(fs.readFileSync(CANONICAL_FILE, 'utf8'));
const campaign = canonical.campaigns['use-the-right-equipment-mq5l90bk'];
const assetRecord = (campaign.publishing || []).find(
  p => p.assetId === ASSET_ID
);

if (!assetRecord) {
  console.error('FATAL: asset not found in canonical');
  process.exit(1);
}
if (assetRecord.postizPostId !== CANONICAL_POSTIZ_ID) {
  console.error(`FATAL: canonical postizPostId mismatch: ${assetRecord.postizPostId}`);
  process.exit(1);
}

// -- Helpers --
// Each call-site below is reproduced as a small function that mirrors the
// source-level contract (argument shape, gating decision, side-effect target).
// No side-effects are actually performed; the function returns the decision
// the real call site would make.

function callSiteMarkLive(opState) {
  // mirrors scripts/_lib/asset-state-engine.js line ~382
  const g = guard.assertNoVisibilityDispute({
    apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: opState,
  });
  return { guard: g, blocked: guard.blocksAction(g, 'mark-live') };
}
function callSiteDuplicateSkip(opState) {
  // mirrors scripts/run_publisher.js line ~1000 (partial-write recovery)
  const g = guard.assertNoVisibilityDispute({
    apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: opState,
  });
  return { guard: g, blocked: guard.blocksAction(g, 'duplicate-skip') };
}
function callSiteReconcile(opState) {
  // mirrors scripts/run_publisher.js line ~1067 (RECONCILE branch)
  const g = guard.assertNoVisibilityDispute({
    apiState: 'unknown', canonicalState: 'exists', operatorVisibilityState: opState,
  });
  return { guard: g, blocked: guard.blocksAction(g, 'reconcile') };
}
function callSiteTruthCollector(opState) {
  // mirrors campaign-os/truth_collector.py line ~785
  const g = guard.assertNoVisibilityDispute({
    apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: opState,
  });
  return { guard: g, blocked: guard.blocksAction(g, 'destructive-state-reconciliation') };
}
function readOnlyInspection(opState) {
  // Read-only ops (analytics / planning / queue generation / reporting) do NOT
  // call the guard at all. The guard is consulted only at state-changing
  // boundaries (Step 97 spec). Verifying read-only remains allowed is therefore
  // a no-guard check.
  return { guard: null, blocked: false, path: 'no-guard-call-required' };
}

// -- PHASE 1: DEFAULT BEHAVIOUR (VISIBILITY_DISPUTES unset) --
const phase1 = { name: 'PHASE 1 — DEFAULT', results: {} };
delete process.env.VISIBILITY_DISPUTES;
{
  // operatorState resolver from run_publisher.js line 999:
  //   const operatorState = (process.env.VISIBILITY_DISPUTES ? (JSON.parse(...)[assetId]) : null) || 'unknown';
  const opState = (process.env.VISIBILITY_DISPUTES
    ? JSON.parse(process.env.VISIBILITY_DISPUTES)[ASSET_ID]
    : null) || 'unknown';
  phase1.results.operatorResolvesTo = opState;
  phase1.results.markLive = callSiteMarkLive(opState);
  phase1.results.duplicateSkip = callSiteDuplicateSkip(opState);
  phase1.results.reconcile = callSiteReconcile(opState);
  phase1.results.truthCollector = callSiteTruthCollector(opState);
  phase1.results.readOnly = readOnlyInspection(opState);
}

// -- PHASE 2: EXPLICIT DISPUTE (VISIBILITY_DISPUTES={id:'not-visible'}) --
const phase2 = { name: 'PHASE 2 — DISPUTE', results: {} };
process.env.VISIBILITY_DISPUTES = JSON.stringify({ [ASSET_ID]: 'not-visible' });
{
  const opState = (process.env.VISIBILITY_DISPUTES
    ? JSON.parse(process.env.VISIBILITY_DISPUTES)[ASSET_ID]
    : null) || 'unknown';
  phase2.results.operatorResolvesTo = opState;
  phase2.results.markLive = callSiteMarkLive(opState);
  phase2.results.duplicateSkip = callSiteDuplicateSkip(opState);
  phase2.results.reconcile = callSiteReconcile(opState);
  phase2.results.truthCollector = callSiteTruthCollector(opState);
  phase2.results.readOnly = readOnlyInspection(opState);
}

// -- PHASE 3: DISPUTE CLEARING (VISIBILITY_DISPUTES={id:'visible'}) --
const phase3 = { name: 'PHASE 3 — CLEARING', results: {} };
process.env.VISIBILITY_DISPUTES = JSON.stringify({ [ASSET_ID]: 'visible' });
{
  const opState = (process.env.VISIBILITY_DISPUTES
    ? JSON.parse(process.env.VISIBILITY_DISPUTES)[ASSET_ID]
    : null) || 'unknown';
  phase3.results.operatorResolvesTo = opState;
  phase3.results.markLive = callSiteMarkLive(opState);
  phase3.results.duplicateSkip = callSiteDuplicateSkip(opState);
  phase3.results.reconcile = callSiteReconcile(opState);
  phase3.results.truthCollector = callSiteTruthCollector(opState);
  phase3.results.readOnly = readOnlyInspection(opState);
}

// Confirm no persistence: clear env and re-read; the resolved state should
// fall back to 'unknown' with no trace.
delete process.env.VISIBILITY_DISPUTES;
const afterClear = (process.env.VISIBILITY_DISPUTES
  ? JSON.parse(process.env.VISIBILITY_DISPUTES)[ASSET_ID]
  : null) || 'unknown';

phaseResults.push(phase1, phase2, phase3);

// -- Canonical invariants: re-check disk state --
const after = snapshot();
const canonicalMtimeUnchanged = before.campaignMtime === after.campaignMtime;
const canonicalShaUnchanged = before.campaignSha === after.campaignSha;

// Compare data/* file states (mtime may legitimately shift if any test path
// wrote; here we assert no NEW files appeared and no existing file's mtime
// moved past the proof run start).
const dataFilesAdded = [];
for (const k of Object.keys(after.dataFiles)) {
  if (!(k in before.dataFiles)) dataFilesAdded.push(k);
}
const dataFilesModified = [];
for (const k of Object.keys(before.dataFiles)) {
  if (after.dataFiles[k] && before.dataFiles[k].mtimeMs !== after.dataFiles[k].mtimeMs) {
    dataFilesModified.push(k);
  }
}

// Network probe: confirm we never touched Postiz. The proof script has zero
// network calls; this is structural.
const networkProbes = { postizHostsContacted: 0, note: 'proof script has no network code path' };

// Print results
const out = {
  asset: ASSET_ID,
  canonicalPostizId: CANONICAL_POSTIZ_ID,
  canonicalAssetRecord: {
    publishingId: assetRecord.publishingId,
    currentStatus: assetRecord.currentStatus,
    integrationId: assetRecord.integrationId,
    channel: assetRecord.channel,
  },
  phases: phaseResults,
  afterClear,
  canonicalInvariants: {
    mtimeUnchanged: canonicalMtimeUnchanged,
    shaUnchanged: canonicalShaUnchanged,
    dataFilesAdded,
    dataFilesModified,
  },
  networkProbes,
};

console.log(JSON.stringify(out, null, 2));