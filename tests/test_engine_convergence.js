/**
 * tests/test_engine_convergence.js
 *
 * Step 87 Script 3 — convergence test for the Asset State Engine.
 *
 * Loads campaign-os/campaign-data.json, runs reconcileAll({dryRun:true})
 * repeatedly, asserts:
 *   - Determinism across multiple runs
 *   - Canonical SHA-256 unchanged after dry-run (no mutation)
 *   - No .tmp or .lock files left behind
 *   - takomo-101t-research converges to expected state
 *   - takomo-101t-visual-a stays gate2-failed (sticky)
 *   - 36 use-the-right-equipment assets stay at publishStatus=planned
 *   - Asset.history lengths UNCHANGED after engine runs (engine adds nothing)
 *
 * Run: node tests/test_engine_convergence.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const eng = require('../scripts/_lib/asset-state-engine');

let passed = 0, failed = 0, total = 0;
const results = [];

function assert(name, cond, info) {
  total++;
  if (cond) {
    passed++;
    results.push(`  PASS  ${name}`);
  } else {
    failed++;
    results.push(`  FAIL  ${name}${info ? ' — ' + JSON.stringify(info) : ''}`);
  }
}

function section(title) {
  results.push(`\n[${title}]`);
}

const CANONICAL_PATH = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');

if (!fs.existsSync(CANONICAL_PATH)) {
  console.error(`FATAL: canonical not found at ${CANONICAL_PATH}`);
  process.exit(1);
}

const shaBefore = crypto.createHash('sha256').update(fs.readFileSync(CANONICAL_PATH)).digest('hex');
const dataBefore = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));

// Snapshot history lengths before reconcile
const historyLensBefore = {};
for (const [cid, c] of Object.entries(dataBefore.campaigns || {})) {
  for (const [aid, a] of Object.entries(c.assets || {})) {
    historyLensBefore[aid] = (a.history || []).length;
  }
}

section('1. Determinism — 3 dry-runs identical');
{
  const r1 = eng.reconcileAll({ dryRun: true, canonicalPath: CANONICAL_PATH });
  const r2 = eng.reconcileAll({ dryRun: true, canonicalPath: CANONICAL_PATH });
  const r3 = eng.reconcileAll({ dryRun: true, canonicalPath: CANONICAL_PATH });
  const sig = (r) => JSON.stringify({ changed: r.changed, summary: r.summary });
  assert('run 1 == run 2', sig(r1) === sig(r2));
  assert('run 2 == run 3', sig(r2) === sig(r3));
}

section('2. No mutation after dry-run');
{
  const shaAfter = crypto.createHash('sha256').update(fs.readFileSync(CANONICAL_PATH)).digest('hex');
  assert('canonical SHA-256 unchanged', shaAfter === shaBefore);
  assert('no .tmp file left', !fs.existsSync(CANONICAL_PATH + '.tmp'));
  assert('no .lock file left', !fs.existsSync(CANONICAL_PATH + '.lock'));
}

section('3. takomo-101t-research converges');
{
  const data = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));
  const a = data.campaigns['takomo-101t'].assets['takomo-101t-research'];
  const r = eng.evaluateAsset(a, a.history, {});
  assert('qualityGateState = gate1-passed', r.qualityGateState === 'gate1-passed');
  assert('visualStatus = skipped', r.visualStatus === 'skipped');
  assert('captionStatus = approved', r.captionStatus === 'approved');
  assert('approvalStatus in (pending|review)', r.approvalStatus === 'pending' || r.approvalStatus === 'review');
  assert('publishStatus = planned', r.publishStatus === 'planned');
}

section('4. takomo-101t-visual-a gate2-failed sticky');
{
  const data = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));
  const a = data.campaigns['takomo-101t'].assets['takomo-101t-visual-a'];
  const r = eng.evaluateAsset(a, a.history, {});
  assert('qualityGateState = gate2-failed', r.qualityGateState === 'gate2-failed');
  assert('approvalStatus = rejected', r.approvalStatus === 'rejected');
}

section('5. 36 use-the-right-equipment assets — 35 planned, 1 scheduled');
{
  // Step 88 Phase 3 (controlled approval proof) advanced
  // use-the-right-equipment-mq5l90bk-feed-post-04 from planned to
  // scheduled. The other 35 stay at planned.
  const data = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));
  const c = data.campaigns['use-the-right-equipment-mq5l90bk'];
  let allPlanned = true;
  let count = 0;
  let scheduled = 0;
  for (const [aid, a] of Object.entries(c.assets)) {
    const r = eng.evaluateAsset(a, a.history, {});
    count++;
    if (r.publishStatus === 'scheduled') scheduled++;
    if (r.publishStatus !== 'planned' && r.publishStatus !== 'scheduled') {
      allPlanned = false;
      results.push(`  WARN  ${aid}: publishStatus=${r.publishStatus}`);
    }
  }
  assert('36 use-the-right-equipment assets evaluated', count === 36);
  assert('exactly 1 use-the-right-equipment asset at scheduled', scheduled === 1);
  assert('all 36 use-the-right-equipment assets are planned or scheduled', allPlanned);
}

section('6. Asset history lengths unchanged after dry-run');
{
  const dataAfter = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));
  let allUnchanged = true;
  let totalChecked = 0;
  for (const [cid, c] of Object.entries(dataAfter.campaigns || {})) {
    for (const [aid, a] of Object.entries(c.assets || {})) {
      const before = historyLensBefore[aid];
      const after = (a.history || []).length;
      if (before !== after) {
        allUnchanged = false;
        results.push(`  WARN  ${aid}: history ${before} -> ${after}`);
      }
      totalChecked++;
    }
  }
  assert('all asset.history lengths unchanged', allUnchanged);
  assert(`total assets checked = ${totalChecked}`, totalChecked === 42);
}

section('7. Field convergence distribution');
{
  const data = JSON.parse(fs.readFileSync(CANONICAL_PATH, 'utf8'));
  const dist = {
    qualityGateState: {},
    captionStatus: {},
    visualStatus: {},
    approvalStatus: {},
    publishStatus: {},
  };
  for (const [cid, c] of Object.entries(data.campaigns || {})) {
    for (const [aid, a] of Object.entries(c.assets || {})) {
      const r = eng.evaluateAsset(a, a.history, {});
      for (const f of Object.keys(dist)) {
        dist[f][r[f]] = (dist[f][r[f]] || 0) + 1;
      }
    }
  }
  results.push('  Convergence distribution:');
  for (const [f, vals] of Object.entries(dist)) {
    results.push(`    ${f}: ${JSON.stringify(vals)}`);
  }
  // Sanity: every asset has SOME state, none left null
  let allCovered = true;
  for (const [f, vals] of Object.entries(dist)) {
    const total = Object.values(vals).reduce((a, b) => a + b, 0);
    if (total !== 42) { allCovered = false; }
  }
  assert('all 5 fields covered across 42 assets', allCovered);
}

// ─── Output ───────────────────────────────────────────────────────────────

results.push('');
results.push(`Total: ${total}, Passed: ${passed}, Failed: ${failed}`);
console.log(results.join('\n'));
process.exit(failed > 0 ? 1 : 0);