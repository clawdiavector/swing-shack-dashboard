#!/usr/bin/env node
/** run.js — reddit_ghost agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'generate_reddit_ghost.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const r = JSON.parse(fs.readFileSync(path.join(DATA, 'reddit-replies.json'), 'utf8'));
  const o = JSON.parse(fs.readFileSync(path.join(DATA, 'reddit-opportunities.json'), 'utf8'));
  const f = JSON.parse(fs.readFileSync(path.join(DATA, 'forum-opportunities.json'), 'utf8'));
  counts = { replies: r.replies?.length || 0, opps: o.opportunities?.length || 0, forum: f.opportunities?.length || 0 };
} catch { counts = { replies: 0, opps: 0, forum: 0 }; }

const valid = counts.replies > 0;
const runResult = {
  agent_id: 'reddit_ghost',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'generate_reddit_ghost.js', status, err: errMsg }],
  outputs: {
    'data/reddit-replies.json': { valid: counts.replies > 0, count: counts.replies },
    'data/reddit-opportunities.json': { valid: counts.opps > 0, count: counts.opps },
    'data/forum-opportunities.json': { valid: counts.forum > 0, count: counts.forum },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[reddit_ghost] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${counts.replies > 0 ? '✅' : '❌'} reddit-replies.json: ${counts.replies} replies`);
console.log(`  ${counts.opps > 0 ? '✅' : '❌'} reddit-opportunities.json: ${counts.opps} opportunities`);
console.log(`  ${counts.forum > 0 ? '✅' : '❌'} forum-opportunities.json: ${counts.forum} backlinks`);
if (errMsg) console.log(`  ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['reddit_ghost'] = runs.agents['reddit_ghost'] || [];
runs.agents['reddit_ghost'].push(runResult);
runs.agents['reddit_ghost'] = runs.agents['reddit_ghost'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(valid ? 0 : 0); // non-critical: exit 0 even if no content (no reddit trends is ok)