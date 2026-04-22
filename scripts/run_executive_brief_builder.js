#!/usr/bin/env node
/**
 * run_executive_brief_builder.js
 * Reads: weekly-report.json, anomaly-alerts.json, recommendation-outcomes.json, owner-performance.json
 * Produces: executive-brief.json
 *
 * Schema: https://clawdia.io/agents/executive-brief-builder/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();

  const weekly  = readJson('weekly-report.json') || {};
  const anom    = readJson('anomaly-alerts.json') || {};
  const recOut  = readJson('recommendation-outcomes.json') || {};
  const ownerPf = readJson('owner-performance.json') || {};
  const recSc   = readJson('recommendation-scores.json') || {};
  const missed  = readJson('missed-opportunities.json') || {};

  const sum     = weekly.summary || {};
  const wins    = weekly.wins   || {};
  const leaks   = weekly.leaks  || {};
  const weekOW  = weekly.week_over_week || {};

  // ── 5 bullets ───────────────────────────────────────────────────
  const bullets = [];

  // 1. Biggest win
  if (wins.top_hook) {
    bullets.push({ priority: 1, type: 'win', text: `Hook ${wins.top_hook.hook_id} led ${wins.top_hook.publish_count || 1} publishes (${sum.publish_success_rate} win rate)` });
  } else {
    bullets.push({ priority: 1, type: 'win', text: `${sum.published_count || 0} items published this week` });
  }

  // 2. Biggest problem
  if (leaks.biggest_funnel_leak) {
    bullets.push({ priority: 2, type: 'problem', text: `Funnel leak: ${leaks.biggest_funnel_leak.substring(0, 100)}` });
  } else if (sum.publish_failures > 0) {
    bullets.push({ priority: 2, type: 'problem', text: `${sum.publish_failures} publish failures this week` });
  } else if (sum.critical_alerts > 0) {
    bullets.push({ priority: 2, type: 'problem', text: `${sum.critical_alerts} critical alert(s) active` });
  } else {
    bullets.push({ priority: 2, type: 'problem', text: 'No critical problems this week' });
  }

  // 3. This week's priority
  const nextAction = (recSc.do_first && recSc.do_first[0]) ? recSc.do_first[0].reason || recSc.do_first[0].recommendation_id : null;
  bullets.push({ priority: 3, type: 'priority', text: nextAction ? `Execute: ${nextAction.substring(0, 100)}` : 'Execute top recommendation from scoring' });

  // 4. Risk to watch
  if (sum.overload_owners && sum.overload_owners.length > 0) {
    bullets.push({ priority: 4, type: 'risk', text: `Owner overload: ${sum.overload_owners.join(', ')}` });
  } else if (sum.missed_opportunities > 0) {
    bullets.push({ priority: 4, type: 'risk', text: `${sum.missed_opportunities} missed opportunities unaddressed` });
  } else {
    const recentAlerts = ((anom.alerts || []).filter(a => a.severity === 'high')).slice(0,1);
    if (recentAlerts.length > 0) {
      bullets.push({ priority: 4, type: 'risk', text: `Alert: ${(recentAlerts[0].message || recentAlerts[0].alert_type || '').substring(0, 80)}` });
    } else {
      bullets.push({ priority: 4, type: 'risk', text: 'No high-severity risks detected' });
    }
  }

  // 5. Action to take
  const overdue = (missed.by_category && missed.by_category.critical && missed.by_category.critical[0]) ? missed.by_category.critical[0] : null;
  if (overdue) {
    bullets.push({ priority: 5, type: 'action', text: `Address missed opportunity: ${(overdue.reason || overdue.description || '').substring(0, 100)}` });
  } else if (sum.critical_alerts > 0) {
    bullets.push({ priority: 5, type: 'action', text: 'Review critical alerts before next publish cycle' });
  } else {
    bullets.push({ priority: 5, type: 'action', text: 'Continue normal execution — all gates green' });
  }

  const brief = {
    schema: 'https://clawdia.io/agents/executive-brief-builder/v1',
    generated: now.toISOString(),
    period: weekly.period || { from: 'unknown', to: now.toISOString().split('T')[0] },
    headline: {
      published: sum.published_count || 0,
      win_rate: sum.publish_success_rate || '0%',
      alerts: sum.critical_alerts || 0,
      owners_overload: (sum.overload_owners || []).length,
    },
    bullets,
    evidence: {
      top_hook: wins.top_hook || null,
      top_cta: wins.top_cta || null,
      top_service: wins.top_service || null,
      biggest_leak: leaks.biggest_funnel_leak || null,
    },
  };

  fs.writeFileSync(path.join(DATA, 'executive-brief.json'), JSON.stringify(brief, null, 2));
  console.log(`✅ Executive brief builder: ${bullets.length} bullets`);
  bullets.forEach(b => console.log(`   [${b.priority}] ${b.type}: ${b.text.substring(0, 70)}...`));
}

module.exports = { run };
if (require.main === module) run();