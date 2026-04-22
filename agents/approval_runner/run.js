#!/usr/bin/env node
/** run.js — approval_runner agent wrapper */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  execSync(`node ${path.join(BASE, 'scripts', 'run_approval_runner.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const aa = JSON.parse(fs.readFileSync(path.join(DATA, 'approval-actions.json'), 'utf8'));
  const ae = JSON.parse(fs.readFileSync(path.join(DATA, 'approval-expiry.json'), 'utf8'));
  counts = { actions: aa.total_actions || 0, expired: ae.total_expired || 0 };
} catch { counts = {}; }

const runResult = {
  agent_id: 'approval_runner',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_approval_runner.js', status, err: errMsg }],
  outputs: {
    'data/approval-actions.json': { valid: true, ...counts },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[approval_runner] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.actions !== undefined) console.log(`   Actions: ${counts.actions} | Expired approvals: ${counts.expired}`);
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['approval_runner'] = runs.agents['approval_runner'] || [];
runs.agents['approval_runner'].push(runResult);
runs.agents['approval_runner'] = runs.agents['approval_runner'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);