#!/usr/bin/env node
/** run.js — publisher agent wrapper */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  execSync(`node ${path.join(BASE, 'scripts', 'run_publisher.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const pq = JSON.parse(fs.readFileSync(path.join(DATA, 'publish-queue.json'), 'utf8'));
  const pf = JSON.parse(fs.readFileSync(path.join(DATA, 'publish-failures.json'), 'utf8'));
  counts = { queued: pq.total || 0, failures: pf.total || 0, mode: pq.mode || 'DRY_RUN' };
} catch { counts = {}; }

const runResult = {
  agent_id: 'publisher',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_publisher.js', status, err: errMsg }],
  outputs: {
    'data/publish-queue.json': { valid: true, ...counts },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[publisher] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.queued !== undefined) console.log(`   Mode: ${counts.mode} | Queued: ${counts.queued} | Failures: ${counts.failures}`);
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['publisher'] = runs.agents['publisher'] || [];
runs.agents['publisher'].push(runResult);
runs.agents['publisher'] = runs.agents['publisher'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);