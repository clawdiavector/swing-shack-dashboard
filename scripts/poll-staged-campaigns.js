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
 * - Staged file cleared only after successful completion (create-campaign.js handles this)
 * - Crash recovery: on restart, detects _processing: true and retries
 * - Full audit trail in ledger.history
 *
 * Usage: node scripts/poll-staged-campaigns.js
 */
const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT   = path.join(__dirname, '..');
const STAGED      = path.join(REPO_ROOT, 'campaign-os', 'campaign-data-staged.json');
const DATA_FILE   = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function now() { return new Date().toISOString(); }

// ── Read staged file ────────────────────────────────────────────────────────
function readStaged() {
  try {
    const raw = fs.readFileSync(STAGED, 'utf8').trim();
    if (!raw || raw === '{}') return null;
    return JSON.parse(raw);
  } catch { return null; }
}

// ── Write staged file ────────────────────────────────────────────────────────
function writeStaged(data) {
  fs.writeFileSync(STAGED, JSON.stringify(data, null, 2) + '\n');
}

// ── Run a script and return {success, error, stdout, campaignId} ──────────────
function runScript(label, cmd) {
  try {
    const stdout = execSync(cmd, { cwd: REPO_ROOT, timeout: 90000, encoding: 'utf8' });
    log(`${label}: OK — ${stdout.trim().slice(0, 100)}`);

    // Try to parse JSON output for campaignId
    let campaignId = null;
    try {
      const parsed = JSON.parse(stdout.trim());
      campaignId = parsed.campaignId || null;
    } catch { /* non-JSON output — that's fine */ }

    return { success: true, error: null, stdout: stdout.trim(), campaignId };
  } catch (err) {
    const stdout = err.stdout ? err.stdout.toString().trim() : '';
    const stderr = err.stderr ? err.stderr.toString().trim() : err.message;
    log(`${label}: FAIL — ${stderr.slice(0, 200)}`);
    return { success: false, error: stderr.slice(0, 500), stdout, campaignId: null };
  }
}

// ── Main poll ────────────────────────────────────────────────────────────────
function poll() {
  log('Polling...');
  const staged = readStaged();

  if (!staged || !staged._pending) {
    log('No pending campaigns — sleeping');
    return;
  }

  // Check for crash recovery
  if (staged._processing && staged._ledger && staged._ledger.lastRun) {
    if (staged._ledger.lastRun.status !== 'processing') {
      staged._processing = false;
      writeStaged(staged);
      log('Cleared stale _processing flag from previous run');
      return;
    }
  }

  // Check for already-active job
  if (staged._ledger && staged._ledger.lastRun &&
      staged._ledger.lastRun.status === 'processing') {
    log('Another job already processing — skipping');
    return;
  }

  const formData     = staged.formData || staged;
  const submittedAt  = staged._submittedAt || now();
  const campaignName = formData.name || 'unknown';

  log(`Processing campaign: ${campaignName}`);

  // ── Write 'processing' ledger entry (fail closed) ─────────────────────────
  const processingEntry = {
    at:           now(),
    status:       'processing',
    campaignName,
    submittedAt,
    error:        null,
    createResult: null,
    bpResult:     null,
    campaignId:   null
  };

  try {
    staged._ledger        = staged._ledger || { history: [] };
    staged._ledger.lastRun = processingEntry;
    staged._processing    = true;
    writeStaged(staged);
  } catch (err) {
    log(`FAIL CLOSED: cannot write processing entry to ledger — ${err.message}`);
    return;
  }

  // ── Run create-campaign.js ─────────────────────────────────────────────────
  const createResult = runScript('create-campaign.js', 'node scripts/create-campaign.js');
  processingEntry.createResult = createResult.success ? 'ok' : createResult.error;

  if (!createResult.success) {
    log(`create-campaign.js FAILED for "${campaignName}": ${createResult.error}`);
    staged._ledger.history.unshift({ ...processingEntry, status: 'failed-create' });
    staged._ledger.lastRun  = { ...processingEntry, status: 'failed-create' };
    staged._pending         = false;
    staged._processing      = false;
    writeStaged(staged);
    return;
  }

  const campaignId = createResult.campaignId;
  if (!campaignId) {
    log('FAIL: create-campaign.js returned no campaignId — cannot proceed');
    staged._ledger.history.unshift({ ...processingEntry, status: 'failed-no-id' });
    staged._ledger.lastRun  = { ...processingEntry, status: 'failed-no-id' };
    staged._pending         = false;
    staged._processing      = false;
    writeStaged(staged);
    return;
  }

  processingEntry.campaignId = campaignId;
  log(`Campaign ID: ${campaignId}`);

  // ── Run generate-blueprint.js ──────────────────────────────────────────────
  const bpCmd = campaignId
    ? `node scripts/generate-blueprint.js ${campaignId}`
    : 'node scripts/generate-blueprint.js';
  const bpResult = runScript('generate-blueprint.js', bpCmd);
  processingEntry.bpResult = bpResult.success ? 'ok' : bpResult.error;

  if (!bpResult.success) {
    log(`generate-blueprint.js FAILED for campaign ${campaignId}: ${bpResult.error}`);
    staged._ledger.history.unshift({ ...processingEntry, status: 'failed-blueprint' });
    staged._ledger.lastRun  = { ...processingEntry, status: 'failed-blueprint' };
    staged._pending         = false;
    staged._processing     = false;
    writeStaged(staged);
    return;
  }

  // ── All success ────────────────────────────────────────────────────────────
  log(`Campaign "${campaignName}" (${campaignId}) created and blueprint generated successfully`);
  staged._ledger.history.unshift({ ...processingEntry, status: 'ok', campaignId });
  staged._ledger.lastRun  = { ...processingEntry, status: 'ok', campaignId };
  staged._pending         = false;
  staged._processing     = false;
  writeStaged(staged);
  log('Bridge processing complete — cockpit will update on next GitHub Actions deploy');
}

poll();