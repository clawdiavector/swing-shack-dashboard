#!/usr/bin/env node
/** run.js — insight_analyst agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

function run(script) {
  const start = Date.now();
  try {
    const out = exec(`node ${path.join(BASE, 'scripts', script)}`, { cwd: BASE, timeout: 60000 });
    return { status: 'PASS', duration_ms: Date.now() - start };
  } catch (e) {
    return { status: 'FAIL', duration_ms: Date.now() - start, err: e.message.slice(0, 80) };
  }
}

const SCRIPTS = [
  'analyse_hooks.js','extract_youtube_signals.js','generate_anomaly_alerts.js',
  'detect_missed_opportunities.js','generate_funnel_leaks.js',
  'generate_conversion_attribution.js','generate_retargeting_recommendations.js',
  'generate_recommendation_scores.js','generate_recommendation_outcomes.js'
];

const start = Date.now();
const results = SCRIPTS.map(s => ({ script: s, ...run(s) }));
const passed = results.filter(r => r.status === 'PASS').length;

const runResult = {
  agent_id: 'insight_analyst',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: passed === SCRIPTS.length ? 'PASS' : 'PARTIAL',
  scripts: results,
  passed,
  failed: results.length - passed,
};

console.log(`\n[insight_analyst] ${runResult.status} — ${passed}/${results.length} passed (${runResult.duration_ms}ms)`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['insight_analyst'] = runs.agents['insight_analyst'] || [];
runs.agents['insight_analyst'].push(runResult);
runs.agents['insight_analyst'] = runs.agents['insight_analyst'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));
process.exit(0);
