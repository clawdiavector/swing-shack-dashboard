#!/usr/bin/env node
/** run.js — visual_forge agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'generate_visual_briefs.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let valid = false, counts = {};
try {
  const v = JSON.parse(fs.readFileSync(path.join(DATA, 'visual-briefs.json'), 'utf8'));
  const p = JSON.parse(fs.readFileSync(path.join(DATA, 'image-prompts.json'), 'utf8'));
  const t = JSON.parse(fs.readFileSync(path.join(DATA, 'thumbnail-briefs.json'), 'utf8'));
  counts = { briefs: v.briefs?.length || 0, prompts: p.prompts?.length || 0, thumbs: t.thumbnails?.length || 0 };
  valid = counts.briefs > 0 && counts.prompts > 0;
} catch {}

const runResult = {
  agent_id: 'visual_forge',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'generate_visual_briefs.js', status, err: errMsg }],
  outputs: {
    'data/visual-briefs.json': { valid: counts.briefs > 0, count: counts.briefs },
    'data/image-prompts.json': { valid: counts.prompts > 0, count: counts.prompts },
    'data/thumbnail-briefs.json': { valid: counts.thumbs > 0, count: counts.thumbs },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[visual_forge] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${counts.briefs > 0 ? '✅' : '❌'} visual-briefs.json: ${counts.briefs} briefs`);
console.log(`  ${counts.prompts > 0 ? '✅' : '❌'} image-prompts.json: ${counts.prompts} prompts`);
console.log(`  ${counts.thumbs > 0 ? '✅' : '❌'} thumbnail-briefs.json: ${counts.thumbs} thumbnails`);
if (errMsg) console.log(`  ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['visual_forge'] = runs.agents['visual_forge'] || [];
runs.agents['visual_forge'].push(runResult);
runs.agents['visual_forge'] = runs.agents['visual_forge'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);