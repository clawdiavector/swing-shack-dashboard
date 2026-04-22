#!/usr/bin/env node
/** run.js — schedule_captain agent wrapper */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  execSync(`node ${path.join(BASE, 'scripts', 'run_schedule_captain.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const sb = JSON.parse(fs.readFileSync(path.join(DATA, 'schedule-board.json'), 'utf8'));
  counts = { slots: sb.total_slots || 0, filled: sb.filled_slots || 0, balance_issues: (sb.balance_issues || []).length };
} catch { counts = {}; }

const runResult = {
  agent_id: 'schedule_captain',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_schedule_captain.js', status, err: errMsg }],
  outputs: {
    'data/schedule-board.json': { valid: true, ...counts },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[schedule_captain] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.slots !== undefined) console.log(`   Today: ${counts.slots} slots | Filled: ${counts.filled} | Balance gaps: ${counts.balance_issues}`);
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['schedule_captain'] = runs.agents['schedule_captain'] || [];
runs.agents['schedule_captain'].push(runResult);
runs.agents['schedule_captain'] = runs.agents['schedule_captain'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);