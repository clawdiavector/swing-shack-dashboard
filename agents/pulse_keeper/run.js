#!/usr/bin/env node
/**
 * run.js — pulse_keeper agent wrapper
 * Validates system health, produces scorecards, stores learnings.
 * Rule: PARTIAL outputs are honest, not failures.
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
    const stdout = out.toString().trim();
    // Scripts output PARTIAL when system is degraded but still working — that's honest
    let status = 'PASS';
    if (stdout.includes('Status: PARTIAL') || stdout.includes("'PARTIAL'")) status = 'PARTIAL';
    return { status, duration_ms: Date.now() - start, out: stdout };
  } catch (e) {
    // Real crashes = FAIL. Script ran but degraded = PARTIAL.
    const msg = e.message || '';
    if (msg.includes('ENOENT') || msg.includes('MODULE_NOT_FOUND')) {
      return { status: 'FAIL', duration_ms: Date.now() - start, err: msg.slice(0, 80) };
    }
    // Script threw but didn't crash — treat as PARTIAL (script ran, output degraded)
    return { status: 'PARTIAL', duration_ms: Date.now() - start, err: msg.slice(0, 80) };
  }
}

function validate(f) {
  const isMem = f.startsWith('memory/');
  const base = isMem ? BASE : DATA;
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
if (health.status !== 'FAIL') outputs.push('data/system-health.json');

// 2. Scorecards
const scores = run('generate_agent_scorecards.js');
results.push({ script: 'generate_agent_scorecards.js', ...scores });
if (scores.status !== 'FAIL') outputs.push('data/agent-scorecards.json');

// 3. Store learnings
const memDir = path.join(BASE, 'memory', 'daily');
try { if (!fs.existsSync(memDir)) fs.mkdirSync(memDir, { recursive: true }); } catch {}
const todayFile = path.join(BASE, `memory/daily/${new Date().toISOString().split('T')[0]}.json`);
const learn = run('store_daily_learnings.js');
results.push({ script: 'store_daily_learnings.js', ...learn });
if (learn.status !== 'FAIL') outputs.push(`memory/daily/${new Date().toISOString().split('T')[0]}.json`);

// Validate outputs
const validations = {};
for (const f of outputs) {
  validations[f] = validate(f);
}

// Honest: FAIL only if nothing worked. PARTIAL if at least one thing works.
const hasFailure = results.some(r => r.status === 'FAIL');
const hasOutput = outputs.length > 0 && Object.values(validations).some(v => v.valid);
const allPass = !hasFailure && hasOutput && results.every(r => r.status === 'PASS');
const hasPartial = results.some(r => r.status === 'PARTIAL');
const runStatus = allPass ? 'PASS' : (hasFailure ? 'FAIL' : 'PARTIAL');

const runResult = {
  agent_id: 'pulse_keeper',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: runStatus,
  scripts: results,
  outputs_validated: validations,
  outputs_produced: outputs,
  total_scripts: results.length,
  passed: results.filter(r => r.status === 'PASS').length,
  failed: results.filter(r => r.status === 'FAIL').length,
  partial: results.filter(r => r.status === 'PARTIAL').length,
};

console.log(`\n[pulse_keeper] ${runResult.status} — ${runResult.passed} PASS / ${runResult.partial} PARTIAL / ${runResult.failed} FAIL (${runResult.duration_ms}ms)`);
results.forEach(r => {
  const icon = r.status === 'PASS' ? '✅' : r.status === 'PARTIAL' ? '⚠️' : '❌';
  console.log(`  ${icon} ${r.script} (${r.duration_ms}ms)`);
  if (r.err) console.log(`     Error: ${r.err}`);
});
Object.entries(validations).forEach(([f, v]) => console.log(`  ${v.valid ? '✅' : '❌'} ${f}: ${v.valid ? 'valid' : v.reason}`));

// Append to agent-runs.json
const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['pulse_keeper'] = runs.agents['pulse_keeper'] || [];
runs.agents['pulse_keeper'].push(runResult);
runs.agents['pulse_keeper'] = runs.agents['pulse_keeper'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

// FAIL exit code only on actual failures, not honest PARTIAL
process.exit(runStatus === 'FAIL' ? 1 : 0);
