#!/usr/bin/env node
/**
 * run_agent.js
 * Universal agent runner — runs a specific agent by agent_id.
 * Usage:
 *   node run_agent.js pulse_keeper
 *   node run_agent.js --list
 *   node run_agent.js --all
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const AGENTS = path.join(BASE, 'agents');

function run(script, agentDir) {
  const scriptPath = path.join(agentDir, script);
  const start = Date.now();
  try {
    const out = exec(`node ${scriptPath}`, { cwd: BASE, timeout: 120000 });
    return { status: 'PASS', duration_ms: Date.now() - start, out: out.toString().trim() };
  } catch (e) {
    return { status: 'FAIL', duration_ms: Date.now() - start, err: e.message.slice(0, 120) };
  }
}

function getManifest(agentId) {
  try {
    return JSON.parse(fs.readFileSync(path.join(AGENTS, agentId, 'manifest.json'), 'utf8'));
  } catch {
    return null;
  }
}

function runAgent(agentId) {
  const agentDir = path.join(AGENTS, agentId);
  const manifest = getManifest(agentId);
  if (!manifest) { console.error(`Unknown agent: ${agentId}`); return null; }

  console.log(`\n${'='.repeat(50)}`);
  console.log(`AGENT: ${agentId} (layer ${manifest.layer})`);
  console.log(`ROLE:  ${manifest.role}`);
  console.log(`${'='.repeat(50)}`);

  const runJs = path.join(agentDir, 'run.js');
  if (!fs.existsSync(runJs)) {
    console.error(`  No run.js found for ${agentId}`);
    return null;
  }

  const result = run('run.js', agentDir);

  console.log(`\nRESULT: ${result.status} (${result.duration_ms}ms)`);
  if (result.err) console.log(`  ERROR: ${result.err}`);

  return { agent_id: agentId, manifest, ...result };
}

const args = process.argv.slice(2);
if (args.length === 0 || args[0] === '--help') {
  console.log('Usage:');
  console.log('  node run_agent.js <agent_id>   Run one agent');
  console.log('  node run_agent.js --list      List agents');
  console.log('  node run_agent.js --all [layer]  Run all agents (optionally: --all 2 for layer 2 only)');
  console.log('\nAgents:');
  for (const d of fs.readdirSync(AGENTS)) {
    const m = getManifest(d);
    if (!m) continue;
    console.log(`  ${d} (layer ${m.layer}) — ${m.role.substring(0, 50)}`);
  }
  process.exit(0);
}

if (args[0] === '--list') {
  for (const d of fs.readdirSync(AGENTS)) {
    const m = getManifest(d);
    if (!m) continue;
    console.log(`${d}: ${m.role} [${m.criticality}]`);
  }
  process.exit(0);
}

if (args[0] === '--all') {
  const layerFilter = args[1] ? parseInt(args[1]) : null;
  const results = [];
  for (const d of fs.readdirSync(AGENTS)) {
    const m = getManifest(d);
    if (!m) continue;
    if (layerFilter !== null && m.layer !== layerFilter) continue;
    const r = runAgent(d);
    if (r) results.push(r);
  }
  const passed = results.filter(r => r.status === 'PASS').length;
  console.log(`\n${'='.repeat(50)}`);
  const label = layerFilter !== null ? `layer-${layerFilter} agents` : 'all agents';
  console.log(`${label.toUpperCase()}: ${passed}/${results.length} passed`);
  process.exit(passed === results.length ? 0 : 1);
}

const agentId = args[0];
const result = runAgent(agentId);
process.exit(result?.status === 'PASS' ? 0 : 1);
