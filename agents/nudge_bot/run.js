#!/usr/bin/env node
/**
 * run.js — nudge_bot agent wrapper
 * Nudge generation, suppression, delivery, auto-messages
 * Owns: nudge-queue.json, auto-messages.json, suppression-rules.json, fallback-queue.json, discord-deliveries.json
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

function run(script) {
  const start = Date.now();
  try {
    exec(`node ${path.join(BASE, 'scripts', script)}`, { cwd: BASE, timeout: 30000 });
    return { status: 'PASS', duration_ms: Date.now() - start };
  } catch (e) {
    return { status: 'FAIL', duration_ms: Date.now() - start, err: e.message.slice(0, 80) };
  }
}

const SCRIPTS = [
  'generate_nudge_queue.js',
  'generate_suppression_rules.js',
  'generate_fallback_queue.js',
  'generate_auto_messages.js',
  'send_discord_nudges.js',
  'log_discord_deliveries.js',
];

const start = Date.now();
const results = SCRIPTS.map(s => ({ script: s, ...run(s) }));
const passed = results.filter(r => r.status === 'PASS').length;

const runResult = {
  agent_id: 'nudge_bot',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: passed === SCRIPTS.length ? 'PASS' : 'PARTIAL',
  scripts: results,
  passed,
  failed: SCRIPTS.length - passed,
};

console.log(`\n[nudge_bot] ${runResult.status} (${runResult.duration_ms}ms) — ${passed}/${SCRIPTS.length} scripts`);
results.forEach(r => console.log(`  ${r.status === 'PASS' ? '✅' : '❌'} ${r.script}${r.err ? ': ' + r.err : ''}`));

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['nudge_bot'] = runs.agents['nudge_bot'] || [];
runs.agents['nudge_bot'].push(runResult);
runs.agents['nudge_bot'] = runs.agents['nudge_bot'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(0); // nudge_bot is non-critical, always exit 0