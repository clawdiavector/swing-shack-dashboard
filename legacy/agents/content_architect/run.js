#!/usr/bin/env node
/**
 * run.js — content_architect agent wrapper
 * Bridge from idea to build brief — turns hook + CTA + goal + channel into content blueprints
 * Owns: content-blueprints.json
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS';
let errMsg = '';

try {
  exec(`node ${path.join(BASE, 'scripts', 'generate_content_blueprints.js')}`, { cwd: BASE, timeout: 60000 });
} catch (e) {
  status = 'FAIL';
  errMsg = e.message.slice(0, 80);
}

let valid = false, bpCount = 0;
try {
  const bp = JSON.parse(fs.readFileSync(path.join(DATA, 'content-blueprints.json'), 'utf8'));
  valid = bp.blueprints?.length > 0;
  bpCount = bp.blueprints?.length || 0;
} catch {}

const runResult = {
  agent_id: 'content_architect',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid && status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'generate_content_blueprints.js', status, err: errMsg }],
  outputs: { 'data/content-blueprints.json': { valid, blueprint_count: bpCount } },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[content_architect] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${valid ? '✅' : '❌'} content-blueprints.json: ${bpCount} blueprints`);
console.log(`  ${status === 'PASS' ? '✅' : '❌'} generate_content_blueprints.js${errMsg ? ': ' + errMsg : ''}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['content_architect'] = runs.agents['content_architect'] || [];
runs.agents['content_architect'].push(runResult);
runs.agents['content_architect'] = runs.agents['content_architect'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);