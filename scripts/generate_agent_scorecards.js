#!/usr/bin/env node
/**
 * generate_agent_scorecards.js
 * Produces data/agent-scorecards.json — honest, evidence-based scores.
 */
const fs = require('fs');
const path = require('path');

const BASE   = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA   = path.join(BASE, 'data');
const OUTPUT = path.join(DATA, 'agent-scorecards.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, name), 'utf8')); }
  catch { return null; }
}
function readReg(name) {
  try { return JSON.parse(fs.readFileSync(path.join(BASE, 'agents', name), 'utf8')); }
  catch { return null; }
}

const now   = new Date().toISOString();
const today = now.split('T')[0];

// ── Load existing scores ──────────────────────────────────────
let existing = { agents: [] };
try { existing = JSON.parse(fs.readFileSync(OUTPUT, 'utf8')); } catch {}

// ── Load system data ───────────────────────────────────────────
const sysHealth = readJson('system-health.json')  || {};
const delAudit  = readJson('delivery-audit.json') || {};
const reg       = readReg('registry.json')         || {};
const recOut    = readJson('recommendation-outcomes.json') || {};

// Script failures this run
const failedScripts = sysHealth.pipeline?.script_failures || [];

// Output freshness helper
function outputAgeHours(file) {
  // Strip 'data/' prefix if present since DATA already points to data/
  const cleanFile = file.replace(/^data\//, '');
  const fullPath = path.join(DATA, cleanFile);
  const j = readJson(cleanFile);
  if (!j) return 999;
  const ts = j.updated || j.generated;
  if (ts) return (Date.now() - new Date(ts).getTime()) / 3600000;
  try {
    const stat = fs.statSync(fullPath);
    return (Date.now() - stat.mtime.getTime()) / 3600000;
  } catch { return 999; }
}
function isFresh(file, maxAge = 26) {
  return outputAgeHours(file) < maxAge;
}

// ── Score one agent ───────────────────────────────────────────
function scoreAgent(agent) {
  const prev = existing.agents?.find(a => a.agent_id === agent.agent_id);
  const runs = (prev?.runs || 0) + 1;
  const firstSeen = prev?.first_seen || today;
  const daysHist  = Math.max(1, Math.round((Date.now() - new Date(firstSeen)) / 86400000));

  // Script failures attributed to this agent
  const myFailures = failedScripts.filter(f =>
    (agent.scripts || []).some(s => s.includes(f.replace('.js', '')))
  );
  const failed = myFailures.length > 0;

  // Reliability: % of runs with no failures
  const prevFailures = (prev?.reliability_score ?? 10) >= 9 ? 0 : 1;
  const totalFailures = prevFailures + (failed ? 1 : 0);
  const reliability = Math.max(1, Math.round(((runs - totalFailures) / runs) * 10 * 10) / 10);

  // Freshness: % of outputs fresh
  const freshCount = (agent.outputs || []).filter(f => isFresh(f)).length;
  const freshness = agent.outputs?.length
    ? Math.round((freshCount / agent.outputs.length) * 10 * 10) / 10
    : (prev?.freshness_score ?? 8);

  // Usefulness: recommendations from this agent that got executed/won
  const usedByMe = (recOut.executed || recOut.won || []).filter(r => r.source_agent === agent.agent_id).length;
  const usefulness = Math.min(10, Math.round((5 + usedByMe * 0.5) * 10) / 10);

  // Bug rate: penalise if failures this run
  const bugRate = failed
    ? Math.max(4, (prev?.bug_rate_score ?? 8) - 1.5)
    : Math.min(10, Math.round(((prev?.bug_rate_score ?? 8) + 0.1) * 10) / 10);

  // Contribution: outputs fresh this run
  const contribFresh = (agent.outputs || []).filter(f => isFresh(f, 3)).length;
  const contribRaw = (agent.outputs?.length || 0) > 0
    ? ((contribFresh + 1) / (agent.outputs.length + 1)) * 10
    : (prev?.contribution_score ?? 7);
  const contribution = Math.round(Math.min(10, contribRaw) * 10) / 10;

  // Overall
  let overall = Math.round((
    reliability * 0.30 +
    freshness * 0.20 +
    usefulness * 0.20 +
    bugRate * 0.15 +
    contribution * 0.15
  ) * 10) / 10;

  // Cap at 9.5 until 14+ days history
  if (overall > 9.5 && daysHist < 14) overall = 9.5;
  if (overall > 10) overall = 10;
  // Hard cap: no 10s without history
  if (overall === 10) overall = 9.5;

  // Trend
  const trend = prev?.overall_score
    ? overall > prev.overall_score + 0.2 ? 'improving'
    : overall < prev.overall_score - 0.2 ? 'declining' : 'stable'
    : 'new';

  // Notes
  const notes = [];
  if (failed) notes.push(`Script fail(s): ${myFailures.join(', ')}`);
  if (daysHist < 14) notes.push(`${daysHist}/14 days`);
  if (agent.agent_id === 'data_harvester') notes.push('GA4 risk — SYSTEM HEALTH');
  if (trend === 'improving') notes.push('Trending up');
  if (trend === 'declining') notes.push('Trending down');

  return {
    agent_id:           agent.agent_id,
    name:                agent.name,
    first_seen:          firstSeen,
    runs,
    days_history:        daysHist,
    reliability_score:   reliability,
    freshness_score:     freshness,
    usefulness_score:    usefulness,
    bug_rate_score:      bugRate,
    contribution_score:   contribution,
    overall_score:       overall,
    trend,
    notes,
    last_updated:        today,
  };
}

// ── Score all agents ─────────────────────────────────────────
const agents = (reg.agents || []).filter(a => a.layer === 1 || a.layer === 2);
const scored = agents.map(scoreAgent);

// Summary
const avg = scored.length
  ? Math.round(scored.reduce((s, a) => s + a.overall_score, 0) / scored.length * 10) / 10
  : 0;
const top = [...scored].sort((a, b) => b.overall_score - a.overall_score)[0];
const attention = scored.filter(a =>
  a.overall_score < 6.0 || (a.trend === 'declining' && a.days_history >= 3)
);
const newAgs = scored.filter(a => a.days_history <= 2 || a.trend === 'new');

// ── Build output ──────────────────────────────────────────────
const output = {
  schema:     'https://clawdia.io/agents/output-schema/v1',
  agent_id:   'pulse_keeper',
  generated:  now,
  status:     attention.length > 0 ? 'PARTIAL' : 'PASS',
  data_status: 'FRESH',
  confidence: 8,
  priority:   attention.length > 0 ? 'HIGH' : 'MEDIUM',
  owner:      'pulse_keeper',
  next_action: attention.length > 0
    ? `Investigate: ${attention.map(a => `${a.name}(${a.overall_score})`).join(', ')}`
    : 'All agents within acceptable range.',
  notes:     [],
  qa_warnings: [],
  scoring_rule: 'No agent scores 10 until 14+ days history + no critical failures. Max 9.5 for agents with <14 days.',
  agents: scored,
  summary: {
    total_agents:  scored.length,
    avg_score:      avg,
    top_performer:  top?.agent_id || null,
    needs_attention: attention.map(a => a.agent_id),
    new_agents:     newAgs.map(a => a.agent_id),
  },
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));

console.log(`✅ Scorecards: ${OUTPUT}`);
console.log(`   Agents: ${scored.length} | Avg: ${avg}/10 | Top: ${top?.name}(${top?.overall_score})`);
if (attention.length) console.log(`   ⚠️  ${attention.length} need attention`);
scored.forEach(a => console.log(`   ${a.name.padEnd(22)} ${a.overall_score.toFixed(1)} | rel:${a.reliability_score.toFixed(1)} fre:${a.freshness_score.toFixed(1)} use:${a.usefulness_score.toFixed(1)} | ${a.trend}${a.notes.length ? ' | '+a.notes[0] : ''}`));
