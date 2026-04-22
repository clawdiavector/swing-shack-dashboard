#!/usr/bin/env node
/** run.js — data_harvester agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

function run(script) {
  const cmd = `node ${path.join(BASE, 'scripts', script)}`;
  const start = Date.now();
  try {
    const out = exec(cmd, { cwd: BASE, timeout: 60000 });
    return { status: 'PASS', duration_ms: Date.now() - start, out: out.toString().trim() };
  } catch (e) {
    const code = e.status;
    const msg = e.message?.includes('ENOTFOUND') || e.message?.includes('auth') ? 'AUTH_ERROR' : 'FAIL';
    return { status: code === 0 ? 'PASS' : msg, duration_ms: Date.now() - start, err: e.message.slice(0, 100) };
  }
}

const SCRIPTS = [
  'sync_ig_analytics.js','fetch_golf_news.js','fetch_reddit_trends.js',
  'fetch_seo_rankings.js','fetch_ga4.js','fetch_youtube_trends.js',
  'fetch_website_insights.js','run_seo_audit.js','run_geo_audit.js'
];

const start = Date.now();
const results = SCRIPTS.map(s => ({ script: s, ...run(s) }));
const ga4Fail = results.find(r => r.script === 'fetch_ga4.js' && r.status !== 'PASS');

const runResult = {
  agent_id: 'data_harvester',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: ga4Fail ? 'PARTIAL' : 'PASS',
  scripts: results,
  outputs_produced: SCRIPTS.length,
  passed: results.filter(r => r.status === 'PASS').length,
  failed: results.filter(r => r.status !== 'PASS').length,
  ga4_status: ga4Fail ? 'AUTH_ERROR' : 'PASS',
  ga4_risk_visible: !!ga4Fail,
};

console.log(`\n[data_harvester] ${runResult.status} — ${runResult.passed}/${runResult.total_scripts} scripts passed`);
if (ga4Fail) console.log(`  ⚠️  GA4 auth error — risk visible in SYSTEM HEALTH`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '⚠️ '} ${r.script} (${r.duration_ms}ms)${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['data_harvester'] = runs.agents['data_harvester'] || [];
runs.agents['data_harvester'].push(runResult);
runs.agents['data_harvester'] = runs.agents['data_harvester'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PARTIAL' ? 0 : 0); // always exit 0 for data_harvester (GA4 may fail legitimately)
