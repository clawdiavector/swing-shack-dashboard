#!/usr/bin/env node
/** run.js — brand_guard agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'run_brand_guard.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const b = JSON.parse(fs.readFileSync(path.join(DATA, 'brand-guard-report.json'), 'utf8'));
  const t = JSON.parse(fs.readFileSync(path.join(DATA, 'tone-violations.json'), 'utf8'));
  counts = { total: b.total_items || 0, pass: b.pass || 0, warn: b.warn || 0, fail: b.fail || 0, score: b.brand_score || 0, violations: t.total_violations || 0 };
} catch { counts = {}; }

const runResult = {
  agent_id: 'brand_guard',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: counts.total >= 0 && status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_brand_guard.js', status, err: errMsg }],
  outputs: {
    'data/brand-guard-report.json': { valid: counts.total >= 0, score: counts.score, pass: counts.pass, warn: counts.warn, fail: counts.fail },
    'data/tone-violations.json': { valid: true, violations: counts.violations },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[brand_guard] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.total !== undefined) {
  console.log(`   Items: ${counts.total} | PASS: ${counts.pass} | WARN: ${counts.warn} | FAIL: ${counts.fail} | Score: ${counts.score}/100`);
  console.log(`   Voice: direct, SA, data-driven, no fluff`);
}
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['brand_guard'] = runs.agents['brand_guard'] || [];
runs.agents['brand_guard'].push(runResult);
runs.agents['brand_guard'] = runs.agents['brand_guard'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);