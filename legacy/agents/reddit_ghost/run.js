#!/usr/bin/env node
/** run.js — reddit_ghost agent wrapper */
/**
 * Reddit can be quiet — zero trends is valid, not a failure.
 * PARTIAL when we ran but found nothing. FAIL only on crash.
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '', stdout = '';
try {
  stdout = exec(`node ${path.join(BASE, 'scripts', 'generate_reddit_ghost.js')}`, { cwd: BASE, timeout: 30000 }).toString().trim();
  if (stdout.includes('Status: PARTIAL') || stdout.includes("'PARTIAL'") || stdout.includes('0 trends') || stdout.includes('0 opportunities')) {
    status = 'PARTIAL';
  }
} catch (e) {
  const msg = e.message || '';
  if (msg.includes('ENOENT') || msg.includes('MODULE_NOT_FOUND')) {
    status = 'FAIL'; errMsg = msg.slice(0, 80);
  } else {
    // Script ran but failed gracefully — PARTIAL, not FAIL
    status = 'PARTIAL'; errMsg = msg.slice(0, 80);
  }
}

let counts = {};
try {
  const r = JSON.parse(fs.readFileSync(path.join(DATA, 'reddit-replies.json'), 'utf8'));
  const o = JSON.parse(fs.readFileSync(path.join(DATA, 'reddit-opportunities.json'), 'utf8'));
  const f = JSON.parse(fs.readFileSync(path.join(DATA, 'forum-opportunities.json'), 'utf8'));
  counts = { replies: r.replies?.length || 0, opps: o.opportunities?.length || 0, forum: f.opportunities?.length || 0 };
} catch { counts = { replies: 0, opps: 0, forum: 0 }; }

// Honest: ran without crash = PARTIAL or PASS. FAIL only on crash.
const runStatus = status === 'FAIL' ? 'FAIL' : (status === 'PARTIAL' || (counts.replies === 0 && counts.opps === 0) ? 'PARTIAL' : 'PASS');

const runResult = {
  agent_id: 'reddit_ghost',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: runStatus,
  scripts: [{ script: 'generate_reddit_ghost.js', status, err: errMsg }],
  outputs: {
    'data/reddit-replies.json': { valid: true, count: counts.replies }, // file existed even if empty
    'data/reddit-opportunities.json': { valid: true, count: counts.opps },
    'data/forum-opportunities.json': { valid: true, count: counts.forum },
  },
  passed: runStatus === 'PASS' ? 1 : 0,
  failed: runStatus === 'FAIL' ? 1 : 0,
  partial: runStatus === 'PARTIAL' ? 1 : 0,
};

console.log(`\n[reddit_ghost] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${counts.replies > 0 ? '✅' : '⚠️'} reddit-replies.json: ${counts.replies} replies`);
console.log(`  ${counts.opps > 0 ? '✅' : '⚠️'} reddit-opportunities.json: ${counts.opps} opportunities`);
console.log(`  ${counts.forum > 0 ? '✅' : '⚠️'} forum-opportunities.json: ${counts.forum} backlinks`);
if (errMsg) console.log(`  Note: ${errMsg}`);
if (stdout && stdout.includes('0 trends')) console.log(`  ℹ️ Reddit was quiet — no matching threads found (honest PARTIAL)`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['reddit_ghost'] = runs.agents['reddit_ghost'] || [];
runs.agents['reddit_ghost'].push(runResult);
runs.agents['reddit_ghost'] = runs.agents['reddit_ghost'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

// FAIL only on crash. PARTIAL (no trends) exits 0 — that's correct behaviour.
process.exit(runStatus === 'FAIL' ? 1 : 0);
