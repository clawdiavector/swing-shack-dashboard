#!/usr/bin/env node
/** run.js — caption_closer agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'generate_captions.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let capCount = 0, varCount = 0, capValid = false;
try {
  const c = JSON.parse(fs.readFileSync(path.join(DATA, 'captions.json'), 'utf8'));
  const v = JSON.parse(fs.readFileSync(path.join(DATA, 'caption-variants.json'), 'utf8'));
  capCount = c.captions?.length || 0;
  varCount = v.variants?.length || 0;
  capValid = capCount > 0;
} catch {}

const runResult = {
  agent_id: 'caption_closer',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: capValid ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'generate_captions.js', status, err: errMsg }],
  outputs: {
    'data/captions.json': { valid: capValid, count: capCount },
    'data/caption-variants.json': { valid: varCount > 0, count: varCount },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[caption_closer] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${capValid ? '✅' : '❌'} captions.json: ${capCount} captions`);
console.log(`  ${varCount > 0 ? '✅' : '❌'} caption-variants.json: ${varCount} variants`);
if (errMsg) console.log(`  ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['caption_closer'] = runs.agents['caption_closer'] || [];
runs.agents['caption_closer'].push(runResult);
runs.agents['caption_closer'] = runs.agents['caption_closer'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);