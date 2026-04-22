#!/usr/bin/env node
/**
 * run.js — pulse_keeper agent wrapper
 * Validates system health, produces scorecards, stores learnings.
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

function run(script, args = '') {
  const cmd = `node ${path.join(BASE, 'scripts', script)} ${args}`;
  const start = Date.now();
  try {
    const out = exec(cmd, { cwd: BASE, timeout: 60000 });
    return { status: 'PASS', duration_ms: Date.now() - start, out: out.toString().trim() };
  } catch (e) {
    return { status: 'FAIL', duration_ms: Date.now() - start, err: e.message };
  }
}

function validate(f) {
  const isMem = f.startsWith('memory/');
  const base = isMem ? BASE : DATA;
  // memory/daily/foo.json → BASE/memory/daily/foo.json
  // data/system-health.json → DATA/system-health.json
  const fullPath = path.join(base, isMem ? f : f.replace(/^data\//, ''));
  try {
    const j = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
    if (!j.schema) return { valid: false, reason: 'missing schema' };
    if (!j.generated && !j.date) return { valid: false, reason: 'missing timestamp' };
    return { valid: true, keys: Object.keys(j).length };
  } catch (e) {
    return { valid: false, reason: e.code || e.message.slice(0, 60) };
  }
}

const start = Date.now();
const results = [];
const outputs = [];

// 1. Pulse keeper health
const health = run('generate_pulse_keeper.js');
results.push({ script: 'generate_pulse_keeper.js', ...health });
if (health.status === 'PASS') outputs.push('data/system-health.json');

// 2. Scorecards
const scores = run('generate_agent_scorecards.js');
results.push({ script: 'generate_agent_scorecards.js', ...scores });
if (scores.status === 'PASS') outputs.push('data/agent-scorecards.json');

// 3. Store learnings
const learn = run('store_daily_learnings.js');
results.push({ script: 'store_daily_learnings.js', ...learn });
if (learn.status === 'PASS') outputs.push(`memory/daily/${new Date().toISOString().split('T')[0]}.json`);

// Validate outputs
const validations = {};
for (const f of outputs) {
  validations[f] = validate(f);
}

const allPass = results.every(r => r.status === 'PASS') && Object.values(validations).every(v => v.valid);

const runResult = {
  agent_id: 'pulse_keeper',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: allPass ? 'PASS' : 'PARTIAL',
  scripts: results,
  outputs_validated: validations,
  outputs_produced: outputs,
  total_scripts: results.length,
  passed: results.filter(r => r.status === 'PASS').length,
  failed: results.filter(r => r.status === 'FAIL').length,
};

console.log(`\n[pulse_keeper] ${runResult.status} — ${runResult.passed}/${runResult.total_scripts} scripts passed (${runResult.duration_ms}ms)`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script} (${r.duration_ms}ms)`));
Object.entries(validations).forEach(([f, v]) => console.log(`  ${v.valid ? '✅' : '❌'} ${f}: ${v.valid ? 'valid' : v.reason}`));

// Append to agent-runs.json
const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['pulse_keeper'] = runs.agents['pulse_keeper'] || [];
runs.agents['pulse_keeper'].push(runResult);
runs.agents['pulse_keeper'] = runs.agents['pulse_keeper'].slice(-50); // keep last 50
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(allPass ? 0 : 1);
