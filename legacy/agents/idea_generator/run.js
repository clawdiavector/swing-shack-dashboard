#!/usr/bin/env node
/**
 * run.js — idea_generator agent wrapper
 * Owns: content ideas, follow-up queue, retargeting angles
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

const start = Date.now();
const results = [];

const ci = run('generate_content_ideas.js');
results.push({ script: 'generate_content_ideas.js', ...ci });

const fu = run('generate_follow_up_queue.js');
results.push({ script: 'generate_follow_up_queue.js', ...fu });

const rt = run('generate_retargeting_recommendations.js');
results.push({ script: 'generate_retargeting_recommendations.js', ...rt });

const passed = results.filter(r => r.status === 'PASS').length;

const runResult = {
  agent_id: 'idea_generator',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: passed === 3 ? 'PASS' : 'PARTIAL',
  scripts: results,
  passed,
  failed: 3 - passed,
};

console.log(`\n[idea_generator] ${runResult.status} (${runResult.duration_ms}ms) — ${passed}/3 scripts passed`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['idea_generator'] = runs.agents['idea_generator'] || [];
runs.agents['idea_generator'].push(runResult);
runs.agents['idea_generator'] = runs.agents['idea_generator'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);