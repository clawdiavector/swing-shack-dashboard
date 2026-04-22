#!/usr/bin/env node
/** run.js — qa_inspector agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'run_qa_inspector.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const r = JSON.parse(fs.readFileSync(path.join(DATA, 'qa-report.json'), 'utf8'));
  const f = JSON.parse(fs.readFileSync(path.join(DATA, 'qa-failures.json'), 'utf8'));
  const a = JSON.parse(fs.readFileSync(path.join(DATA, 'ready-for-approval.json'), 'utf8'));
  counts = { total: r.total_items || 0, pass: r.pass || 0, fix: r.fix || 0, reject: r.reject || 0, pass_rate: r.pass_rate || 0, ready: a.count || 0, blocked: f.reject_count || 0 };
} catch { counts = {}; }

const valid = counts.total > 0;
const runResult = {
  agent_id: 'qa_inspector',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid && status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_qa_inspector.js', status, err: errMsg }],
  outputs: {
    'data/qa-report.json': { valid: counts.total > 0, total: counts.total, pass: counts.pass, fix: counts.fix, reject: counts.reject },
    'data/qa-failures.json': { valid: true, failures: counts.fix + counts.blocked },
    'data/ready-for-approval.json': { valid: true, ready: counts.ready },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[qa_inspector] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.total) {
  console.log(`   Items: ${counts.total} | PASS: ${counts.pass} | FIX: ${counts.fix} | REJECT: ${counts.reject} | Pass rate: ${counts.pass_rate}%`);
  console.log(`   Ready for approval: ${counts.ready} | Blocked: ${counts.blocked}`);
}
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['qa_inspector'] = runs.agents['qa_inspector'] || [];
runs.agents['qa_inspector'].push(runResult);
runs.agents['qa_inspector'] = runs.agents['qa_inspector'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);