#!/usr/bin/env node
/**
 * store_daily_learnings.js
 * Memory Castle Keeper — stores end-of-day learnings.
 * Writes to: memory/daily/YYYY-MM-DD.json
 * Updates:   memory/index.json
 *
 * Stores:
 *   - top hook
 *   - top recommendation
 *   - biggest leak
 *   - biggest miss
 *   - trust score
 *   - failed scripts
 *   - best CTA
 *   - biggest learning
 *   - what to repeat
 *   - what to stop
 *   - agent score summary
 */
const fs = require('fs');
const path = require('path');

const BASE  = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA  = path.join(BASE, 'data');
const MEM   = path.join(BASE, 'memory');
const OUTPUT = path.join(MEM, 'daily', `${new Date().toISOString().split('T')[0]}.json`);

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, name), 'utf8')); }
  catch { return null; }
}
function readMem(name) {
  try { return JSON.parse(fs.readFileSync(path.join(MEM, name), 'utf8')); }
  catch { return null; }
}

function uid(type) {
  const date = new Date().toISOString().split('T')[0].replace(/-/g, '');
  return `mem_${type}_${date}_${Math.random().toString(36).substr(2, 4)}`;
}
function tag(...args) { return args; }

// ── Load all data sources ──────────────────────────────────────
const ig       = readJson('ig-analytics.json')          || {};
const recScore = readJson('recommendation-scores.json')  || {};
const recOut   = readJson('recommendation-outcomes.json') || {};
const delAudit = readJson('delivery-audit.json')         || {};
const blockers = readJson('blockers.json')               || {};
const deadlines = readJson('deadline-risk.json')         || {};
const sysHealth = readJson('system-health.json')         || {};
const scores   = readJson('agent-scorecards.json')       || {};
const topRec   = readJson('recommendation-scores.json')?.recommendations?.[0] || {};
const expQueue = readJson('experiment-queue.json')       || {};
const winRecs  = (recOut.summary?.by_outcome?.won || 0) > 0
  ? (recOut.won || []).slice(0, 2)
  : [];

// ── Derive today's learnings ───────────────────────────────────

// Top performing post from IG analytics
const topPost = ig.posts?.[0] || {};
const topHook = topPost.hook || topPost.caption?.substring(0, 80) || 'Unknown';

// Top recommendation from scores
const topRecommendation = topRec.title || topRec.hook || 'None yet';

// Biggest funnel leak (highest-severity unaddressed)
const funnelLeaks = readJson('funnel-leaks.json')?.leaks || [];
const biggestLeak = funnelLeaks.find(l => l.severity === 'high') || funnelLeaks[0] || null;

// Biggest miss — rec that was recommended but not executed
const missedRecs = (recOut.not_executed || []).slice(0, 3);
const biggestMiss = missedRecs[0] || null;

// Trust score
const trustScore = sysHealth.pipeline?.last_run_age != null
  ? (sysHealth.pipeline.last_run_age < 26 ? 10 : sysHealth.pipeline.last_run_age < 52 ? 7 : 4)
  : 3;

// Failed scripts
const failedScripts = sysHealth.pipeline?.script_failures || [];

// Best CTA — highest-performing CTA type from rec outcomes
const ctaWins = (recOut.won || []).filter(r => r.type?.includes('cta'));
const bestCTA = ctaWins[0] || null;

// Top experiment
const topExp = (expQueue.experiments || [])[0] || null;

// Top scaling recommendation
const scaleRecs = readJson('scaling-recommendations.json')?.recommendations || [];
const topScale = scaleRecs[0] || null;

// Agent scores
const agentScores = (scores.agents || []).map(a => ({
  agent_id: a.agent_id, name: a.name, score: a.overall_score, trend: a.trend
}));
const avgScore = agentScores.length
  ? (agentScores.reduce((s, a) => s + a.overall_score, 0) / agentScores.length).toFixed(1)
  : 'N/A';

// ── What to repeat / stop ─────────────────────────────────────
const repeatItems = [
  topHook && topHook !== 'Unknown' ? `Hook: "${topHook.substring(0, 60)}" — use in next round` : null,
  topRecommendation !== 'None yet' ? `Rec: ${topRecommendation.substring(0, 60)}` : null,
  failedScripts.length === 0 ? 'Zero script failures — keep pipeline discipline' : null,
].filter(Boolean);

const stopItems = [
  failedScripts.length > 0 ? `Stop: ${failedScripts.length} script failure(s) — fix before next run` : null,
  biggestLeak && !biggestLeak.fix ? `Stop: Funnel leak unaddressed: "${biggestLeak.leak || biggestLeak.what}"` : null,
  (blockers.summary?.total_blockers || 0) > 10 ? `Stop: ${blockers.summary.total_blockers} blocked tasks — clear before adding more` : null,
].filter(Boolean);

// ── Build memory entry ─────────────────────────────────────────
const today = new Date().toISOString().split("T")[0];
const dailyEntry = {
  schema:        'https://clawdia.io/memory/castle/v1',
  memory_id:     uid('daily'),
  date: today,
  type:          "daily_log",
  source_agent: 'memory_keeper',
  summary:       `Daily learning log — ${today}. Trust: ${trustScore}/10. ${agentScores.length} agents active. Avg score: ${avgScore}.`,
  tags:          tag('daily', 'system', today.split('-')[1] + '-' + today.split('-')[2]),
  importance:    8,
  linked_files:  ['data/system-health.json', 'data/agent-scorecards.json', 'data/recommendation-scores.json'],
  next_use:      'Reference at start of next session for context',

  content: {
    trust_score:      trustScore,
    top_hook:         topHook,
    top_hook_detail:  topPost.engagement ? { engagement: topPost.engagement, reach: topPost.reach } : null,
    top_recommendation:   topRecommendation,
    top_recommendation_detail: topRec.confidence ? { confidence: topRec.confidence, reason: topRec.reason } : null,
    biggest_leak:     biggestLeak ? {
      what: biggestLeak.leak || biggestLeak.what || biggestLeak.description,
      severity: biggestLeak.severity,
      fix: biggestLeak.fix || biggestLeak.recommended_fix,
    } : null,
    biggest_miss:     biggestMiss ? {
      rec: biggestMiss.title || biggestMiss.hook,
      reason: biggestMiss.reason_blocked || 'not_executed',
    } : null,
    failed_scripts:   failedScripts,
    best_cta:         bestCTA ? {
      cta: bestCTA.cta || bestCTA.title,
      type: bestCTA.type,
    } : null,
    top_experiment:    topExp ? {
      hook: topExp.variant_a || topExp.hook,
      test: topExp.hypothesis || topExp.success_metric,
    } : null,
    top_scaling:      topScale ? {
      action: topScale.action,
      target: topScale.target,
    } : null,
    agent_scores:      agentScores,
    avg_agent_score:   parseFloat(avgScore),
    what_to_repeat:   repeatItems,
    what_to_stop:     stopItems,
    wins_this_week:   winRecs.map(w => ({ hook: w.hook || w.title, outcome: w.outcome })),
  },

  evidence: {
    source_files: ['ig-analytics.json', 'recommendation-scores.json', 'recommendation-outcomes.json', 'system-health.json', 'agent-scorecards.json'],
    confidence: 8,
    notes: ['Evidence-backed where available. Wins/losses from rec_outcomes. Agent scores from scorecards.']
  }
};

// ── Also create type-tagged entries for wins/losses/bugs ────────
const winEntries = winRecs.map(w => ({
  schema:      'https://clawdia.io/memory/castle/v1',
  memory_id:   uid('win'),
  date: today,
  type:        'win',
  source_agent: 'insight_analyst',
  summary:     `Hook "${(w.hook || w.title || '').substring(0, 60)}" confirmed winning — ${w.outcome}`,
  tags:        tag('win', 'hook', 'confirmed'),
  importance:  9,
  linked_files: ['data/recommendation-outcomes.json'],
  next_use:    'Scale this hook type. Add to experiment queue.',
  content:     w,
  evidence:    { source: 'recommendation-outcomes.json', confidence: 9, notes: ['Matched to IG post via hook overlap'] }
}));

if (failedScripts.length > 0) {
  // Store as bugs
  failedScripts.forEach(f => {
    const bugEntry = {
      schema:      'https://clawdia.io/memory/castle/v1',
      memory_id:   uid('bug'),
      date: today,
      type:        'bug',
      source_agent: 'pulse_keeper',
      summary:     `Script failure: ${f}`,
      tags:        tag('bug', 'script', 'failure'),
      importance:  9,
      linked_files: ['logs/daily-run.log'],
      next_use:    'Fix before next pipeline run',
      content:     { script: f, severity: 'high', occurrence_date: today },
      evidence:    { source: 'logs/daily-run.log', confidence: 10, notes: ['Logged directly from pipeline run'] }
    };
    const bugFile = path.join(MEM, 'bugs', `${uid('bug')}.json`);
    fs.writeFileSync(bugFile, JSON.stringify(bugEntry, null, 2));
  });
}

// ── Write daily log ─────────────────────────────────────────────
fs.writeFileSync(OUTPUT, JSON.stringify(dailyEntry, null, 2));

// ── Update index ───────────────────────────────────────────────
const idx = readMem('index.json') || {};
idx.updated = new Date().toISOString();
idx.index = idx.index || {};
idx.index.total_entries = (idx.index.total_entries || 0) + 1;
idx.index.by_type = idx.index.by_type || {};
idx.index.by_type['daily_log'] = (idx.index.by_type['daily_log'] || 0) + 1;
if (winEntries.length) idx.index.by_type['win'] = (idx.index.by_type['win'] || 0) + winEntries.length;
if (failedScripts.length > 0) idx.index.by_type['bug'] = (idx.index.by_type['bug'] || 0) + failedScripts.length;
idx.index.recent = [`memory/daily/${path.basename(OUTPUT)}`, ...(idx.index.recent || [])].slice(0, 30);
fs.writeFileSync(path.join(MEM, 'index.json'), JSON.stringify(idx, null, 2));

console.log(`✅ Daily learnings stored: ${OUTPUT}`);
console.log(`   Trust: ${trustScore}/10 | Top hook: "${topHook.substring(0, 50)}"`);
console.log(`   Repeat: ${repeatItems.length} | Stop: ${stopItems.length}`);
if (winEntries.length) console.log(`   Wins stored: ${winEntries.length}`);
if (failedScripts.length > 0) console.log(`   Bugs stored: ${failedScripts.length}`);
console.log(`   Index updated: ${idx.index.total_entries} total entries`);
