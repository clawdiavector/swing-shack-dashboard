#!/usr/bin/env node
/**
 * generate_pulse_keeper.js
 * System health report — Pulse Keeper's primary output.
 * Output: data/system-health.json
 */
const fs = require('fs');
const path = require('path');

const BASE   = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA   = path.join(BASE, 'data');
const OUTPUT = path.join(DATA, 'system-health.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, name), 'utf8')); }
  catch { return null; }
}

function readLog(name) {
  try { return fs.readFileSync(path.join(BASE, 'logs', name), 'utf8').split('\n').filter(Boolean); }
  catch { return []; }
}

function ageHours(iso) {
  if (!iso) return 999;
  return (Date.now() - new Date(iso).getTime()) / 3600000;
}
function ageLabel(iso) {
  if (!iso) return 'never';
  const h = ageHours(iso);
  if (h < 1) return `${Math.round(h * 60)}m ago`;
  if (h < 24) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

// ── Sources ────────────────────────────────────────────────────
const buildMeta = readJson('build-meta.json') || {};
const sum      = readJson('dashboard-summary.json') || {};
const agentsReg = readJson('agents/registry.json') || {};
const scorecards = readJson('agent-scorecards.json') || {};
const delAudit  = readJson('delivery-audit.json') || {};
const blockers  = readJson('blockers.json') || {};
const deadlines = readJson('deadline-risk.json') || {};
const nudgeQ    = readJson('nudge-queue.json') || {};
const apprQueue = readJson('approval-queue.json') || {};

const logLines = readLog('daily-run.log');

// ── Pipeline run ───────────────────────────────────────────────
const lastRunTime = buildMeta.last_run || null;
const lastRunAge  = ageHours(lastRunTime);

// ── Script failures from log ───────────────────────────────────
const scriptFails = [];
logLines.forEach(line => {
  if ((line.includes('❌') || line.includes('FAIL')) && line.includes('Running:')) {
    const m = line.match(/→ Running: (.+)/);
    if (m && !scriptFails.includes(m[1].trim())) scriptFails.push(m[1].trim());
  }
});

// ── Data source freshness ──────────────────────────────────────
const SOURCE_FILES = [
  { file: 'ig-analytics.json',          label: 'IG Analytics',   maxAge: 26 },
  { file: 'ga4-report.json',             label: 'GA4',             maxAge: 52 },
  { file: 'seo-rankings.json',           label: 'SEO Rankings',    maxAge: 26 },
  { file: 'reddit-trends.json',          label: 'Reddit Trends',   maxAge: 26 },
  { file: 'youtube-trends.json',         label: 'YouTube Trends',  maxAge: 26 },
  { file: 'golf-news.json',              label: 'Golf News',       maxAge: 26 },
  { file: 'hook-bank.json',              label: 'Hook Bank',       maxAge: 52 },
  { file: 'post-plan.json',              label: 'Post Plan',       maxAge: 26 },
  { file: 'recommendation-scores.json',  label: 'Rec Scores',      maxAge: 26 },
  { file: 'recommendation-outcomes.json',label: 'Rec Outcomes',   maxAge: 26 },
  { file: 'nudge-queue.json',           label: 'Nudge Queue',      maxAge: 26 },
  { file: 'delivery-audit.json',         label: 'Delivery Audit',  maxAge: 26 },
  { file: 'daily-task-cards.json',       label: 'Task Cards',      maxAge: 26 },
  { file: 'blockers.json',               label: 'Blockers',         maxAge: 26 },
  { file: 'experiment-queue.json',        label: 'Experiment Q',   maxAge: 52 },
];

const sources = SOURCE_FILES.map(d => {
  const json   = readJson(d.file);
  const updated = json && (json.updated || json.generated);
  const age    = ageHours(updated);
  const stale  = age > d.maxAge;
  return {
    file:      d.file,
    label:     d.label,
    updated:   updated || null,
    age_label: ageLabel(updated),
    age_hours: Math.round(age * 10) / 10,
    status:    !updated ? 'MISSING' : stale ? 'STALE' : 'FRESH',
  };
});

// ── Schema compliance ───────────────────────────────────────────
const nonCompliant = sources.filter(d => {
  const json = readJson(d.file);
  return json && !json.schema;
});

// ── Agent health ──────────────────────────────────────────────
const agentList = agentsReg.agents || [];
const agentHealth = agentList.map(a => {
  const card = (scorecards.agents || []).find(s => s.agent_id === a.agent_id);
  return {
    agent_id:    a.agent_id,
    name:        a.name,
    layer:       a.layer,
    status:      a.status,
    criticality: a.criticality,
    score:       card ? card.overall_score : null,
    failed_scripts: scriptFails.filter(f => (a.scripts || []).includes(f)),
  };
});

// ── Operational ────────────────────────────────────────────────
const activeBlockers  = blockers.summary?.total_blockers || 0;
const highRisks       = (deadlines.risks || []).filter(r => r.severity === 'high').length;
const pendingApprovals = (apprQueue.pending_items || []).length;
const pendingNudges    = (nudgeQ.nudges || []).filter(n => n.status === 'ready').length;
const sentToday        = delAudit.summary?.sent || 0;
const suppressedToday  = delAudit.summary?.suppressed || 0;

// ── Counts ─────────────────────────────────────────────────────
const fresh    = sources.filter(s => s.status === 'FRESH').length;
const staleCnt = sources.filter(s => s.status === 'STALE').length;
const missing  = sources.filter(s => s.status === 'MISSING').length;

// ── Top risk ───────────────────────────────────────────────────
let topRisk = 'All clear';
let topRiskLevel = 'LOW';
if (scriptFails.length > 0)  { topRisk = `Script failures: ${scriptFails[0]}`; topRiskLevel = 'CRITICAL'; }
else if (activeBlockers > 0) { topRisk = `${activeBlockers} blocked tasks`;      topRiskLevel = 'HIGH'; }
else if (highRisks > 0)       { topRisk = `${highRisks} high-severity deadline risk(s)`; topRiskLevel = 'HIGH'; }
else if (staleCnt > 0)        { topRisk = `${staleCnt} data source(s) stale`;   topRiskLevel = 'MEDIUM'; }
else if (lastRunAge > 26)     { topRisk = `Pipeline not run in ${Math.round(lastRunAge)}h`; topRiskLevel = 'HIGH'; }

// ── Fix ─────────────────────────────────────────────────────────
let fix = 'Dashboard healthy — no action needed.';
if (scriptFails.length > 0)  fix = 'Check failed scripts: ' + scriptFails.join(', ');
else if (activeBlockers > 0)  fix = 'Unblock tasks in RUN THE WEEK section';
else if (staleCnt > 0)        fix = 'Run `node master_pipeline.js` to refresh stale sources';
else if (lastRunAge > 26)    fix = 'Run `node master_pipeline.js` to restore freshness';

// ── Build output ───────────────────────────────────────────────
const output = {
  schema:     'https://clawdia.io/agents/output-schema/v1',
  agent_id:   'pulse_keeper',
  generated:  new Date().toISOString(),
  status:     topRiskLevel === 'CRITICAL' ? 'FAIL' : topRiskLevel === 'HIGH' ? 'PARTIAL' : 'PASS',
  data_status: staleCnt > 0 || missing > 0 ? 'STALE' : 'FRESH',
  confidence: Math.max(3, 10 - staleCnt - missing),
  priority:   topRiskLevel,
  owner:      'pulse_keeper',
  next_action: fix,
  notes:      [],
  qa_warnings: staleCnt > 0 ? [`${staleCnt} source(s) older than 24h`] : [],
  runtime_ms: 0,

  pipeline: {
    last_run:      lastRunTime,
    last_run_age:  Math.round(lastRunAge * 10) / 10,
    last_run_label: ageLabel(lastRunTime),
    script_failures: scriptFails,
    failure_count:  scriptFails.length,
  },

  data_sources: {
    total:  sources.length,
    fresh,
    stale:  staleCnt,
    missing,
    sources,
  },

  schema_compliance: {
    compliant_count:    sources.length - nonCompliant.length,
    non_compliant_count: nonCompliant.length,
    non_compliant_files: nonCompliant.map(s => s.file),
  },

  agents: agentHealth,

  operational: {
    active_blockers:   activeBlockers,
    high_risks:        highRisks,
    pending_approvals: pendingApprovals,
    pending_nudges:    pendingNudges,
    sent_today:        sentToday,
    suppressed_today:  suppressedToday,
  },

  top_risk: { level: topRiskLevel, message: topRisk, fix },

  summary_line:
    `${lastRunTime ? 'Pipeline ' + ageLabel(lastRunTime) : 'Pipeline never run'}` +
    ` · ${fresh}/${sources.length} sources fresh` +
    `${scriptFails.length > 0 ? ' · ⚠️ ' + scriptFails.length + ' script failure(s)' : ''}` +
    `${activeBlockers > 0 ? ' · ' + activeBlockers + ' blocked tasks' : ''}`,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));

console.log(`✅ Pulse Keeper: ${OUTPUT}`);
console.log(`   Status: ${output.status} | Risk: ${topRiskLevel}`);
console.log(`   Sources: ${fresh} fresh / ${staleCnt} stale / ${missing} missing`);
console.log(`   Pipeline: ${ageLabel(lastRunTime)}`);
console.log(`   Top risk: ${topRisk}`);
console.log(`   Fix: ${fix}`);
if (scriptFails.length > 0) console.log(`   Failed scripts: ${scriptFails.join(', ')}`);
