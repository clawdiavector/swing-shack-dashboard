#!/usr/bin/env node
/**
 * run_weekly_reporter.js
 * Reads: recommendation-outcomes, published-posts, postback-log, agent-runs, recommendation-scores, anomaly-alerts, missed-opportunities
 * Produces: weekly-report.json, weekly-report.md
 *
 * Schema: https://clawdia.io/agents/weekly-reporter/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
const MEM  = path.join(__dirname, '..', '..', 'memory');

function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function readMem(n)  { try { return JSON.parse(fs.readFileSync(path.join(MEM, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function escMd(s) { return (s||'').replace(/[_*#`]/g, ''); }
function escHtml(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function run() {
  const now   = new Date();
  const weekAgo = new Date(now - 7 * 86400000);
  const weekStr = weekAgo.toISOString().split('T')[0];

  const recOut  = readJson('recommendation-outcomes.json') || {};
  const pubPost = readJson('published-posts.json') || {};
  const postLog = readJson('postback-log.json') || {};
  const agentRu = readJson('agent-runs.json') || {};
  const recSc   = readJson('recommendation-scores.json') || {};
  const anom    = readJson('anomaly-alerts.json') || {};
  const missed  = readJson('missed-opportunities.json') || {};

  // ── Recommendation outcomes ─────────────────────────────────────
  const outcomes = recOut.outcomes || [];
  const thisWeek = outcomes.filter(o => o.outcome_timestamp && new Date(o.outcome_timestamp) >= weekAgo);
  const prevWeek  = outcomes.filter(o => o.outcome_timestamp && new Date(o.outcome_timestamp) < weekAgo);

  // Win rate
  const publishedThisWk = thisWeek.filter(o => o.outcome === 'published').length;
  const totalRecs = thisWeek.length || 1;
  const winRate = Math.round((publishedThisWk / totalRecs) * 100);

  // Top performing hook (most published)
  const hookCounts = {};
  thisWeek.forEach(o => { if (o.hook_id) hookCounts[o.hook_id] = (hookCounts[o.hook_id] || 0) + 1; });
  const topHook = Object.entries(hookCounts).sort((a, b) => b[1] - a[1])[0];

  // Top CTA (from recommendation-scores do_first)
  const topCTA = (recSc.summary && recSc.summary.top_cta) ? recSc.summary.top_cta : null;

  // Top service push (from recommendation-scores do_first filtered by service)
  const topService = (recSc.summary && recSc.summary.top_service) ? recSc.summary.top_service : null;

  // ── Published posts ──────────────────────────────────────────────
  const published = pubPost.published || [];
  const thisWkPub  = published.filter(p => p.published_at && new Date(p.published_at) >= weekAgo);
  const prevWkPub  = published.filter(p => p.published_at && new Date(p.published_at) < weekAgo);

  const pubSuccess  = thisWkPub.filter(p => p.status !== 'failed').length;
  const pubFailures = thisWkPub.filter(p => p.status === 'failed').length;

  // ── Postback log ────────────────────────────────────────────────
  const pblEvents = postLog.entries || [];
  const thisPbl    = pblEvents.filter(e => e.generated && new Date(e.generated) >= weekAgo);
  const usedMarked = thisPbl.filter(e => e.used_items_marked).length;

  // ── Anomaly alerts ──────────────────────────────────────────────
  const alerts    = anom.alerts || [];
  const thisAlerts = alerts.filter(a => a.detected && new Date(a.detected) >= weekAgo);
  const critical  = thisAlerts.filter(a => a.severity === 'critical' || a.severity === 'high').length;

  // ── Missed opportunities ────────────────────────────────────────
  const missedOpp = (missed.by_category && missed.by_category.critical) ? missed.by_category.critical.length : 0;

  // ── Agent runs ─────────────────────────────────────────────────
  const agents = agentRu.agents || {};
  const agentCount = Object.keys(agents).length;
  let totalRuns = 0, passRuns = 0;
  Object.values(agents).forEach(ar => {
    (ar || []).forEach(r => { totalRuns++; if (r.status === 'PASS') passRuns++; });
  });

  // ── Owner workload ─────────────────────────────────────────────
  const ownerMap = {};
  thisWkPub.forEach(p => {
    if (!p.owner) return;
    ownerMap[p.owner] = ownerMap[p.owner] || { published: 0, failed: 0 };
    ownerMap[p.owner].published++;
  });
  const overloadOwners = Object.entries(ownerMap).filter(([,o]) => o.published > 5).map(([k]) => k);

  // ── Build weekly report JSON ───────────────────────────────────
  const reportJson = {
    schema: 'https://clawdia.io/agents/weekly-reporter/v1',
    generated: now.toISOString(),
    period: { from: weekStr, to: now.toISOString().split('T')[0] },
    summary: {
      total_recommendations: thisWeek.length,
      published_count: publishedThisWk,
      publish_success_rate: winRate + '%',
      publish_failures: pubFailures,
      used_items_marked: usedMarked,
      agent_runs: totalRuns,
      agent_pass_rate: totalRuns > 0 ? Math.round((passRuns / totalRuns) * 100) + '%' : '0%',
      critical_alerts: critical,
      missed_opportunities: missedOpp,
      overload_owners: overloadOwners,
    },
    wins: {
      top_hook: topHook ? { hook_id: topHook[0], publish_count: topHook[1] } : null,
      top_cta: topCTA,
      top_service: topService,
    },
    leaks: {
      biggest_funnel_leak: (missed.by_category && missed.by_category.critical && missed.by_category.critical[0])
        ? missed.by_category.critical[0].reason || missed.by_category.critical[0].description
        : null,
      publish_failures: pubFailures,
      critical_alerts: critical,
    },
    week_over_week: {
      published_change: prevWkPub.length > 0
        ? Math.round(((thisWkPub.length - prevWkPub.length) / prevWkPub.length) * 100) + '%'
        : '+100%' ,
      recommendation_change: prevWeek.length > 0
        ? Math.round(((thisWeek.length - prevWeek.length) / prevWeek.length) * 100) + '%'
        : '+100%',
    },
    owners: ownerMap,
    alerts: thisAlerts.slice(0, 5).map(a => ({ severity: a.severity, message: a.message || a.alert_type, detected: a.detected })),
  };

  // ── Build weekly report MD ───────────────────────────────────────
  const md = `# Weekly Report — ${weekStr} to ${now.toISOString().split('T')[0]}

## Headline Numbers
- **Published:** ${publishedThisWk} (${winRate}% win rate)
- **Failed:** ${pubFailures} | **Alerts:** ${critical} critical
- **Agent runs:** ${totalRuns} (${passRuns} passed, ${totalRuns - passRuns} failed)
- **Used items marked:** ${usedMarked}

## Top Performers
- **Hook:** ${topHook ? topHook[0] : 'n/a'} (${topHook ? topHook[1] : 0} publishes)
- **CTA:** ${topCTA || 'n/a'}
- **Service:** ${topService || 'n/a'}

## Biggest Leak
${reportJson.leaks.biggest_funnel_leak || 'None detected'}

## Owner Workload
${Object.keys(ownerMap).length === 0 ? 'No owner data this week.' : Object.entries(ownerMap).map(([owner, o]) =>
  `- **${owner}:** ${o.published} published ${o.failed > 0 ? `| ${o.failed} failed` : ''} ${overloadOwners.includes(owner) ? '⚠️ OVERLOAD' : ''}`).join('\n')}

## Alerts
${thisAlerts.length === 0 ? 'No critical alerts this week.' : thisAlerts.map(a => `- **[${a.severity}]** ${a.message}`).join('\n')}

## Week-on-Week
- Published: ${reportJson.week_over_week.published_change} vs last week
- Recommendations: ${reportJson.week_over_week.recommendation_change} vs last week
`;

  fs.writeFileSync(path.join(DATA, 'weekly-report.json'), JSON.stringify(reportJson, null, 2));
  fs.writeFileSync(path.join(DATA, 'weekly-report.md'), md);

  console.log(`✅ Weekly reporter: ${thisWeek.length} recs, ${publishedThisWk} published, ${winRate}% win rate`);
  console.log(`   Top hook: ${topHook ? topHook[0] : 'n/a'} | Top CTA: ${topCTA || 'n/a'} | Top service: ${topService || 'n/a'}`);
  console.log(`   Owner workload: ${Object.keys(ownerMap).length} owners | Overload: ${overloadOwners.length}`);
  console.log(`   Alerts: ${critical} critical | Missed opps: ${missedOpp}`);
}

module.exports = { run };
if (require.main === module) run();