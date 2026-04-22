#!/usr/bin/env node
/**
 * run.js — hook_smith agent wrapper
 * Populates and maintains the hook bank from IG analytics and trend signals.
 * Owns: hook-bank.json, hook-variants.json, hook-recommendations.json
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
    const msg = e.message?.includes('ENOTFOUND') ? 'AUTH_ERROR' : 'FAIL';
    return { status: msg, duration_ms: Date.now() - start, err: e.message.slice(0, 80) };
  }
}

const start = Date.now();
const results = [];

// Run analyse_hooks — primary hook bank generator
const ah = run('analyse_hooks.js');
results.push({ script: 'analyse_hooks.js', ...ah });

// Validate hook-bank.json output (file must exist and be valid JSON — 0 hooks is ok if IG analytics are empty)
let valid = false, hookCount = 0, bucketCount = 0;
try {
  const hb = JSON.parse(fs.readFileSync(hbFile, 'utf8'));
  if (!hb.schema && !hb.total_hooks) throw new Error('not a hook bank file');
  hookCount = hb.total_hooks || 0;
  const buckets = hb.output_buckets || {};
  bucketCount = Object.values(buckets).reduce((s, a) => s + (Array.isArray(a) ? a.length : 0), 0);
  valid = true; // file exists and is valid JSON
} catch (e) {
  valid = false;
}

const runResult = {
  agent_id: 'hook_smith',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid && ah.status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: results,
  outputs: {
    'data/hook-bank.json': { valid, total_hooks: hookCount, bucket_entries: bucketCount }
  },
  passed: results.filter(r => r.status === 'PASS').length,
  failed: results.filter(r => r.status === 'FAIL').length,
};

console.log(`\n[hook_smith] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${valid ? '✅' : '❌'} hook-bank.json: ${hookCount} hooks, ${bucketCount} bucket entries`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['hook_smith'] = runs.agents['hook_smith'] || [];
runs.agents['hook_smith'].push(runResult);
runs.agents['hook_smith'] = runs.agents['hook_smith'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(ah.status === 'PASS' ? 0 : 1);