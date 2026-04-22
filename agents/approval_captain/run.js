#!/usr/bin/env node
/** run.js — approval_captain agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'run_approval_captain.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const q = JSON.parse(fs.readFileSync(path.join(DATA, 'approval-queue.json'), 'utf8'));
  const s = JSON.parse(fs.readFileSync(path.join(DATA, 'approval-summary.json'), 'utf8'));
  counts = { total: q.total || 0, waiting_copy: q.categories?.waiting_copy || 0, waiting_creative: q.categories?.waiting_creative || 0, blocked: q.categories?.blocked || 0, high: q.high_priority_count || 0 };
} catch { counts = {}; }

const runResult = {
  agent_id: 'approval_captain',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: counts.total >= 0 && status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_approval_captain.js', status, err: errMsg }],
  outputs: {
    'data/approval-queue.json': { valid: true, ...counts },
    'data/approval-summary.json': { valid: true },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[approval_captain] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.total !== undefined) {
  console.log(`   Queue: ${counts.total} items | Waiting copy: ${counts.waiting_copy} | Waiting creative: ${counts.waiting_creative} | Blocked: ${counts.blocked}`);
}
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['approval_captain'] = runs.agents['approval_captain'] || [];
runs.agents['approval_captain'].push(runResult);
runs.agents['approval_captain'] = runs.agents['approval_captain'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);