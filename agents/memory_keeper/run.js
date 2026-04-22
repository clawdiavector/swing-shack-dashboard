#!/usr/bin/env node
/** run.js — memory_keeper agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');
const MEM  = path.join(BASE, 'memory');

const start = Date.now();
const today = new Date().toISOString().split('T')[0];

// Run store_daily_learnings
let status = 'PASS';
let errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'store_daily_learnings.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) {
  status = 'FAIL';
  errMsg = e.message.slice(0, 100);
}

// Validate daily log was written
const dailyFile = path.join(MEM, 'daily', `${today}.json`);
const dailyWritten = fs.existsSync(dailyFile);
const indexFile = path.join(MEM, 'index.json');
const indexValid = (() => {
  try { return JSON.parse(fs.readFileSync(indexFile, 'utf8')).updated !== undefined; }
  catch { return false; }
})();

const runResult = {
  agent_id: 'memory_keeper',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: dailyWritten && indexValid ? 'PASS' : 'FAIL',
  scripts: [{ script: 'store_daily_learnings.js', status, err: errMsg }],
  outputs: {
    daily_log_written: dailyWritten,
    index_updated: indexValid,
  },
};

console.log(`\n[memory_keeper] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${dailyWritten ? '✅' : '❌'} Daily log: ${today}.json ${dailyWritten ? 'written' : 'MISSING'}`);
console.log(`  ${indexValid ? '✅' : '❌'} Index ${indexValid ? 'updated' : 'NOT UPDATED'}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['memory_keeper'] = runs.agents['memory_keeper'] || [];
runs.agents['memory_keeper'].push(runResult);
runs.agents['memory_keeper'] = runs.agents['memory_keeper'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));
process.exit(runResult.status === 'PASS' ? 0 : 1);
