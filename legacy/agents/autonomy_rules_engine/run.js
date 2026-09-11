#!/usr/bin/env node
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');
const AGENT = 'autonomy_rules_engine';
const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  execSync('node ' + path.join(BASE, 'scripts', 'run_' + AGENT + '.js'), { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }
const runResult = { agent_id: AGENT, run_at: new Date().toISOString(), duration_ms: Date.now() - start, status: status === 'PASS' ? 'PASS' : 'PARTIAL', scripts: [{ script: 'run_' + AGENT + '.js', status, err: errMsg }], passed: status === 'PASS' ? 1 : 0, failed: status === 'FAIL' ? 1 : 0 };
console.log('
[' + AGENT + '] ' + runResult.status + ' (' + runResult.duration_ms + 'ms)');
if (errMsg) console.log('   ERROR: ' + errMsg);
const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents[AGENT] = runs.agents[AGENT] || [];
runs.agents[AGENT].push(runResult);
runs.agents[AGENT] = runs.agents[AGENT].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));
process.exit(runResult.status === 'PASS' ? 0 : 1);
