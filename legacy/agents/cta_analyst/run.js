#!/usr/bin/env node
/**
 * run.js — cta_analyst agent wrapper
 * Owns: CTA ranking, testing logic, replacement strategy, booking vs awareness selection
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

function run(script) {
  const start = Date.now();
  try {
    exec(`node ${path.join(BASE, 'scripts', script)}`, { cwd: BASE, timeout: 60000 });
    return { status: 'PASS', duration_ms: Date.now() - start };
  } catch (e) {
    return { status: 'FAIL', duration_ms: Date.now() - start, err: e.message.slice(0, 80) };
  }
}

function validateOutput(file, key) {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(DATA, file), 'utf8'));
    if (!j.schema && !j[key] && !j.recommendations) return { valid: false, reason: 'missing data' };
    return { valid: true, keys: Object.keys(j).length };
  } catch (e) {
    return { valid: false, reason: e.code };
  }
}

const start = Date.now();
const results = [];

// Run CTA performance analysis
const cta = run('generate_cta_performance.js');
results.push({ script: 'generate_cta_performance.js', ...cta });

const runResult = {
  agent_id: 'cta_analyst',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: cta.status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: results,
  passed: results.filter(r => r.status === 'PASS').length,
  failed: results.filter(r => r.status === 'FAIL').length,
};

console.log(`\n[cta_analyst] ${runResult.status} (${runResult.duration_ms}ms)`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['cta_analyst'] = runs.agents['cta_analyst'] || [];
runs.agents['cta_analyst'].push(runResult);
runs.agents['cta_analyst'] = runs.agents['cta_analyst'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);