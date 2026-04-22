#!/usr/bin/env node
/** run.js — postback_logger agent wrapper */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  execSync(`node ${path.join(BASE, 'scripts', 'run_postback_logger.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const pbl = JSON.parse(fs.readFileSync(path.join(DATA, 'postback-log.json'), 'utf8'));
  counts = { entries: pbl.total_entries || 0, used_marked: pbl.used_items_marked_count || 0 };
} catch { counts = {}; }

const runResult = {
  agent_id: 'postback_logger',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: status === 'PASS' ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'run_postback_logger.js', status, err: errMsg }],
  outputs: {
    'data/postback-log.json': { valid: true, ...counts },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[postback_logger] ${runResult.status} (${runResult.duration_ms}ms)`);
if (counts.entries !== undefined) console.log(`   Log entries: ${counts.entries} | Used items marked: ${counts.used_marked}`);
if (errMsg) console.log(`   ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['postback_logger'] = runs.agents['postback_logger'] || [];
runs.agents['postback_logger'].push(runResult);
runs.agents['postback_logger'] = runs.agents['postback_logger'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);