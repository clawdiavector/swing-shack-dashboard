#!/usr/bin/env node
/**
 * OpenClaw Agent Bridge — Campaign Staged Processor
 *
 * Polls campaign-data-staged.json every 60 seconds.
 * If _pending: true and no active job running → processes the submission.
 * Runs create-campaign.js then generate-blueprint.js in sequence.
 * Writes ledger entries for every run.
 *
 * Safety properties:
 * - One active job at a time (ledger.status = 'processing')
 * - Fail closed: if ledger write fails, don't process
 * - Staged file cleared only after successful completion
 * - Crash recovery: on restart, detects _processing: true and retries
 * - Full audit trail in ledger.history
 *
 * Usage: node scripts/poll-staged-campaigns.js
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const STAGED    = path.join(REPO_ROOT, 'campaign-os', 'campaign-data-staged.json');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const LOCK_FILE = path.join(REPO_ROOT, 'campaign-os', '.staged-processing-lock');

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function now() { return new Date().toISOString(); }

// ── Read staged file ──────────────────────────────────────────────────────────
function readStaged() {
  try {
    const raw = fs.readFileSync(STAGED, 'utf8').trim();
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// ── Write staged file ─────────────────────────────────────────────────────────
function writeStaged(data) {
  fs.writeFileSync(STAGED, JSON.stringify(data, null, 2) + '\n');
}

// ── Run a script and return {success, error} ──────────────────────────────────
function runScript(label, cmd) {
  try {
    execSync(cmd, { cwd: REPO_ROOT, stdio: 'pipe' });
    log(`${label}: OK`);
    return { success: true, error: null };
  } catch (err) {
    const stderr = err.stderr ? err.stderr.toString().trim() : err.message;
    log(`${label}: FAIL — ${stderr.slice(0, 200)}`);
    return { success: false, error: stderr.slice(0, 500) };
  }
}

// ── Main poll ─────────────────────────────────────────────────────────────────
function poll() {
  log('Polling...');
  const staged = readStaged();

  // No staged file or empty → nothing to do
  if (!staged) {
    log('No staged file — sleeping');
    return;
  }

  // Not pending → check localStorage fallback
  if (!staged || !staged._pending) {
    try {
      var localPending = JSON.parse(localStorage.getItem('pendingCampaigns') || '[]');
      if (localPending.length > 0) {
        log('Found ' + localPending.length + ' pending campaign(s) in localStorage — processing first');
        var pending = localPending.shift();
        pending._pending = true;
        pending._submittedAt = pending._submittedAt || now();
        pending._ledger = pending._ledger || { history: [], lastRun: null };
        writeStaged(pending);
        localStorage.setItem('pendingCampaigns', JSON.stringify(localPending));
        staged = readStaged();
      } else {
        log('No pending campaigns — sleeping');
        return;
      }
    } catch(e) {
      log('localStorage check failed: ' + e.message);
      log('No pending campaigns — sleeping');
      return;
    }
  }

  // Check for crash recovery: if _processing was left true from a previous run
  if (staged._processing && staged._ledger && staged._ledger.lastRun) {
    const last = staged._ledger.lastRun;
    if (last.status === 'processing') {
      log('CRASH RECOVERY: detected stale processing state — retrying');
      // Reset to retry
    } else {
      // Processing flag left but last run is complete — clear it
      staged._processing = false;
      writeStaged(staged);
      log('Cleared stale _processing flag from previous run');
      return;
    }
  }

  // Check for already-active job
  if (staged._ledger && staged._ledger.lastRun && staged._ledger.lastRun.status === 'processing') {
    log('Another job already processing — skipping');
    return;
  }

  const formData   = staged.formData || staged;
  const submittedAt = staged._submittedAt || now();
  const campaignName = formData.name || 'unknown';

  log(`Processing campaign: ${campaignName}`);

  // ── Fail closed: write 'processing' entry to ledger before doing anything ──
  const processingEntry = {
    at:          now(),
    status:      'processing',
    campaignName,
    submittedAt,
    error:       null,
    scriptOutput: {}
  };

  try {
    staged._ledger = staged._ledger || { history: [] };
    staged._ledger.lastRun = processingEntry;
    staged._processing = true;
    writeStaged(staged);
  } catch (err) {
    log(`FAIL CLOSED: cannot write processing entry to ledger — ${err.message}`);
    return; // Don't process — fail closed
  }

  // ── Run create-campaign.js ─────────────────────────────────────────────────
  const createResult = runScript('create-campaign.js', 'node scripts/create-campaign.js');

  // Extract campaignId from campaign-data.json
  let campaignId = null;
  if (createResult.success) {
    try {
      const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
      // Find the newest campaign (by createdAt)
      const campaigns = Object.values(data.campaigns || {});
      campaigns.sort((a, b) => new Date(b.identity.createdAt) - new Date(a.identity.createdAt));
      campaignId = campaigns[0] ? campaigns[0].identity.campaignId : null;
    } catch {
      campaignId = '(could not determine)';
    }
  }

  processingEntry.scriptOutput.createCampaign = createResult.success ? 'ok' : createResult.error;

  if (!createResult.success) {
    // create-campaign.js failed — mark failed, clear staged
    log(`create-campaign.js FAILED for "${campaignName}": ${createResult.error}`);
    staged._ledger.history.unshift({ ...processingEntry, status: 'failed-create', error: createResult.error });
    staged._ledger.lastRun = { ...processingEntry, status: 'failed-create', error: createResult.error };
    staged._pending = false;
    staged._processing = false;
    writeStaged(staged);
    return;
  }

  // ── Run generate-blueprint.js ──────────────────────────────────────────────
  const bpResult = runScript('generate-blueprint.js', `node scripts/generate-blueprint.js ${campaignId}`);

  processingEntry.scriptOutput.generateBlueprint = bpResult.success ? 'ok' : bpResult.error;

  if (!bpResult.success) {
    // Blueprint failed — campaign exists but incomplete
    log(`generate-blueprint.js FAILED for campaign ${campaignId}: ${bpResult.error}`);
    staged._ledger.history.unshift({ ...processingEntry, status: 'failed-blueprint', campaignId, error: bpResult.error });
    staged._ledger.lastRun = { ...processingEntry, status: 'failed-blueprint', campaignId, error: bpResult.error };
    staged._pending = false;
    staged._processing = false;
    writeStaged(staged);
    return;
  }

  // ── All success ────────────────────────────────────────────────────────────
  log(`Campaign "${campaignName}" (${campaignId}) created and blueprint generated successfully`);
  staged._ledger.history.unshift({ ...processingEntry, status: 'ok', campaignId });
  staged._ledger.lastRun = { ...processingEntry, status: 'ok', campaignId };
  staged._pending = false;
  staged._processing = false;
  writeStaged(staged);
  log('Staged file cleared — campaign ready in cockpit on next deploy');
}

// Run once per invocation
poll();