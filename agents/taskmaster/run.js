#!/usr/bin/env node
/** run.js — taskmaster agent wrapper */
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

const SCRIPTS = [
  'generate_post_plan.js','generate_sales_priority.js','generate_daily_task_cards.js',
  'generate_approval_queue.js','generate_deadline_risk.js','generate_blockers.js',
  'generate_capacity_shift.js','generate_follow_up_queue.js',
  'generate_experiment_queue.js','generate_scaling_recommendations.js',
  'generate_kill_list.js','generate_asset_needs.js','generate_owner_workload.js'
];

const start = Date.now();
const results = SCRIPTS.map(s => ({ script: s, ...run(s) }));
const passed = results.filter(r => r.status === 'PASS').length;

// Validate task cards were produced
let taskCount = 0;
try {
  const tc = JSON.parse(fs.readFileSync(path.join(DATA, 'daily-task-cards.json'), 'utf8'));
  taskCount = (tc.all_tasks || []).length;
} catch {}

const runResult = {
  agent_id: 'taskmaster',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: passed === SCRIPTS.length ? 'PASS' : 'PARTIAL',
  scripts: results,
  passed,
  failed: results.length - passed,
  outputs: { task_cards_produced: taskCount },
};

console.log(`\n[taskmaster] ${runResult.status} — ${passed}/${results.length} scripts (${runResult.duration_ms}ms)`);
console.log(`  📋 ${taskCount} task cards produced`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['taskmaster'] = runs.agents['taskmaster'] || [];
runs.agents['taskmaster'].push(runResult);
runs.agents['taskmaster'] = runs.agents['taskmaster'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));
process.exit(0);
