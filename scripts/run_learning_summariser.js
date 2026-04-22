#!/usr/bin/env node
/**
 * run_learning_summariser.js
 * Reads: recommendation-outcomes, anomaly-alerts, missed-opportunities, postback-log, agent-runs
 * Produces: weekly-learnings.json, what-to-repeat.json, what-to-stop.json
 *
 * Schema: https://clawdia.io/agents/learning-summariser/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now     = new Date();
  const weekAgo = new Date(now - 7 * 86400000);

  const recOut  = readJson('recommendation-outcomes.json') || {};
  const anom    = readJson('anomaly-alerts.json') || {};
  const missed  = readJson('missed-opportunities.json') || {};
  const pbl     = readJson('postback-log.json') || {};
  const agentRu = readJson('agent-runs.json') || {};

  // Outcomes
  const outcomes = recOut.outcomes || [];
  const thisWk   = outcomes.filter(o => o.outcome_timestamp && new Date(o.outcome_timestamp) >= weekAgo);

  const hookMap = {};
  thisWk.forEach(o => {
    if (!o.hook_id) return;
    hookMap[o.hook_id] = hookMap[o.hook_id] || { published: 0, platform: o.platform };
    hookMap[o.hook_id].published++;
  });
  const goodHooks = Object.entries(hookMap).filter(([,v]) => v.published >= 1).map(([k,v]) => ({ hook_id: k, published: v.published, platform: v.platform }));
  const allHookIds = outcomes.map(o => o.hook_id).filter(Boolean);
  const coldHooks = allHookIds.filter(h => !hookMap[h]).map(h => ({ hook_id: h, reason: 'no_publish_in_2_weeks' }));

  // Anomalies
  const alerts = anom.alerts || [];
  const thisAlerts = alerts.filter(a => a.detected && new Date(a.detected) >= weekAgo);
  const criticalAlerts = thisAlerts.filter(a => a.severity === 'critical' || a.severity === 'high').map(a => ({ message: a.message || a.alert_type, severity: a.severity, detected: a.detected }));

  // Missed opportunities
  const missedOpp = missed.by_category || {};
  const criticalMissed = (missedOpp.critical || []).slice(0,3).map(m => ({ reason: (m.reason || m.description || JSON.stringify(m)).substring(0,100) }));

  // Postback
  const pblEntries = pbl.entries || [];
  const thisPbl    = pblEntries.filter(e => e.generated && new Date(e.generated) >= weekAgo);
  const usedMarkedCount = thisPbl.filter(e => e.used_items_marked).length;
  const publishEventsCount = thisPbl.filter(e => e.event === 'published').length;

  // Agent runs
  const agentsData = agentRu.agents || {};
  const slowAgents = [];
  Object.entries(agentsData).forEach(([agentId, runs]) => {
    const recent = (runs || []).filter(r => new Date(r.run_at) >= weekAgo);
    const slow   = recent.filter(r => r.duration_ms > 30000);
    if (slow.length > 2) slowAgents.push({ agent_id: agentId, slow_runs: slow.length, avg_ms: Math.round(slow.reduce((s,r) => s+r.duration_ms, 0)/slow.length) });
  });

  // Learnings
  const learnings = {
    schema: 'https://clawdia.io/agents/learning-summariser/v1',
    generated: now.toISOString(),
    period_from: weekAgo.toISOString().split('T')[0],
    period_to: now.toISOString().split('T')[0],
    summary: {
      total_published: thisWk.length,
      used_items_marked: usedMarkedCount,
      critical_alerts: criticalAlerts.length,
      slow_agent_runs: slowAgents.length,
    },
    what_worked: {
      hooks: goodHooks,
      signals: thisWk.length > 0 ? [`${thisWk.length} recommendations published this week`] : [],
    },
    what_didnt_work: {
      cold_hooks: coldHooks.slice(0, 5),
      critical_failures: criticalAlerts,
    },
    anomalies: criticalAlerts,
    missed_opportunities: criticalMissed,
    performance_notes: slowAgents.map(sa => `${sa.agent_id}: ${sa.slow_runs} slow runs avg ${sa.avg_ms}ms`),
  };

  const toRepeat = {
    schema: 'https://clawdia.io/agents/learning-summariser/v1',
    generated: now.toISOString(),
    type: 'what_to_repeat',
    items: [
      ...goodHooks.slice(0, 3).map(h => ({ action: 'use_hook', hook_id: h.hook_id, reason: `${h.published} publishes this week`, confidence: 'high' })),
      ...(usedMarkedCount > 0 ? [{ action: 'continue_postback_logging', reason: `${usedMarkedCount} used items marked in real time`, confidence: 'high' }] : []),
    ],
  };

  const toStop = {
    schema: 'https://clawdia.io/agents/learning-summariser/v1',
    generated: now.toISOString(),
    type: 'what_to_stop',
    items: [
      ...coldHooks.slice(0, 3).map(h => ({ action: 'suppress_hook', hook_id: h.hook_id, reason: h.reason, confidence: 'medium' })),
      ...criticalAlerts.slice(0, 3).map(a => ({ action: 'investigate_alert', message: a.message, severity: a.severity })),
      ...slowAgents.slice(0, 2).map(sa => ({ action: 'optimise_agent', agent_id: sa.agent_id, reason: `${sa.slow_runs} slow runs avg ${sa.avg_ms}ms` })),
    ],
  };

  fs.writeFileSync(path.join(DATA, 'weekly-learnings.json'), JSON.stringify(learnings, null, 2));
  fs.writeFileSync(path.join(DATA, 'what-to-repeat.json'), JSON.stringify(toRepeat, null, 2));
  fs.writeFileSync(path.join(DATA, 'what-to-stop.json'), JSON.stringify(toStop, null, 2));

  console.log(`✅ Learning summariser: ${thisWk.length} published | ${goodHooks.length} good hooks | ${coldHooks.length} cold hooks`);
  console.log(`   Critical alerts: ${criticalAlerts.length} | Missed opps: ${criticalMissed.length} | Slow agent runs: ${slowAgents.length}`);
  console.log(`   Repeat: ${toRepeat.items.length} | Stop: ${toStop.items.length}`);
}

module.exports = { run };
if (require.main === module) run();