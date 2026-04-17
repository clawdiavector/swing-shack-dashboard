#!/usr/bin/env node
/**
 * generate_deadline_risk.js
 * Detects what's about to slip this week.
 * Output: data/deadline-risk.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'deadline-risk.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const tasks  = readJson('daily-task-cards.json')          || {};
const owner  = readJson('owner-workload.json')            || {};
const sales = readJson('sales-priority.json')            || {};
const plan  = readJson('post-plan.json')                 || {};
const missed= readJson('missed-opportunities.json')       || {};
const retarget = readJson('retargeting-recommendations.json') || {};

function uid() { return 'risk_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];
const tomorrow = new Date(now + 86400000).toISOString().split('T')[0];
const weekEnd = new Date(now + 5 * 86400000).toISOString().split('T')[0];

const allTasks = tasks.all_tasks || [];

// ── 1. Tasks due today that are still blocked ──────────────────
const dueTodayBlocked = allTasks.filter(t =>
  (t.due_date === today || t.date === today) && t.status === 'blocked'
).map(t => ({
  risk_id:    uid(),
  type:       'due_today_blocked',
  title:      t.title,
  owner:      t.owner,
  severity:    'high',
  what_will_slip: 'Today\'s post — ' + (t.day || today),
  blockers:   t.blockers,
  fix:        t.blockers.map(b => {
    if (b.includes('asset')) return 'Get ' + t.asset_needed + ' from ' + t.owner;
    if (b === 'no_cta') return 'Add booking CTA to caption';
    return 'Resolve: ' + b;
  }).join(' | '),
  urgency:    'today',
  source:     t.source,
}));

// ── 2. Tomorrow's posts missing assets ───────────────────────────
const tomorrowPosts = allTasks.filter(t =>
  (t.due_date === tomorrow || t.date === tomorrow)
);
const tomorrowMissingAssets = tomorrowPosts.filter(t =>
  t.asset_needed && !['none', 'text graphic', 'generic'].includes(t.asset_needed) && t.status === 'blocked'
).map(t => ({
  risk_id:    uid(),
  type:       'tomorrow_asset_missing',
  title:      t.title,
  owner:      t.owner,
  severity:   'high',
  what_will_slip: 'Tomorrow\'s scheduled post — ' + (t.day || tomorrow),
  blockers:   t.blockers,
  fix:        'Source or create ' + t.asset_needed + ' before end of day',
  urgency:    'today',
  source:     t.source,
}));

// ── 3. One person overloaded this week ─────────────────────────
const ownerLoads = (owner.owners || []).map(o => ({
  owner:    o.owner,
  today:    o.by_urgency?.today || 0,
  this_week: o.by_urgency?.this_week || 0,
  total:   o.total || 0,
})).filter(Boolean);

const overloadedOwners = ownerLoads.filter(o =>
  o.total > 5 || o.this_week > 3
).map(o => ({
  risk_id:    uid(),
  type:       'owner_overload',
  title:      o.owner + ' has ' + o.total + ' tasks this week',
  owner:      o.owner,
  severity:    o.this_week > 4 ? 'high' : 'medium',
  what_will_slip: o.owner + ' may drop tasks — high workload (' + o.total + ' total)',
  fix:        'Move ' + (o.total - 3) + ' tasks to Swing Shack page or delay low-urgency items',
  blockers:   [],
  urgency:    'this_week',
  source:     'owner_workload',
}));

// ── 4. High-priority service with no content scheduled ─────────
const topSvc = (sales.priorities || [])[0];
const topSvcScheduled = topSvc && (plan.plan || []).filter(p =>
  topSvc.label && p.topics && p.topics.some(t => topSvc.label.toLowerCase().includes(t.toLowerCase()))
).length;
const svcAtRisk = topSvc && topSvc.score >= 7 && topSvcScheduled === 0 ? [{
  risk_id:    uid(),
  type:       'service_no_content',
  title:      topSvc.label + ' is priority #' + 1 + ' but has no scheduled content',
  owner:      topSvc.label.includes('Lesson') ? 'Coach Cat' : 'Divan',
  severity:   topSvc.score >= 8 ? 'high' : 'medium',
  what_will_slip: 'High-priority service push will be missed this week',
  fix:        'Schedule at least 1 post for ' + topSvc.label + ' this week — score ' + topSvc.score + '/10',
  blockers:   ['no_content_scheduled'],
  urgency:    'this_week',
  source:     'sales_priority',
}] : [];

// ── 5. Follow-up queue items not assigned ─────────────────────
const unassignedFollowUps = (retarget.recommendations || []).filter(r =>
  r.reason_blocked === 'needs_owner'
).map(r => ({
  risk_id:    uid(),
  type:       'unassigned_follow_up',
  title:      'Follow-up for ' + (r.topic || r.type) + ' has no owner',
  owner:      'Unassigned',
  severity:   'medium',
  what_will_slip: 'High-performing hook with no follow-up this week',
  fix:        'Assign to ' + (r.topic?.includes('lesson') ? 'Coach Cat' : 'Swing Shack page'),
  blockers:   ['no_owner'],
  urgency:    'this_week',
  source:     'retarget',
}));

// ── 6. High-severity missed opportunity not actioned ───────────
const missedHighSev = (missed.opportunities || [])
  .filter(o => o.severity === 'high' && o.category === 'follow_up_gap')
  .slice(0, 2)
  .map(o => ({
    risk_id:    uid(),
    type:       'missed_opportunity_ignored',
    title:      o.suggested_fix?.substring(0, 60) || 'High-severity opportunity',
    owner:      o.owner || 'Swing Shack page',
    severity:   'medium',
    what_will_slip: 'Hook winner with no follow-up — IG signal ' + o.ig_score + ' going stale',
    fix:        o.suggested_fix || 'Create follow-up post for ' + o.topic,
    blockers:   [],
    urgency:    'this_week',
    source:     'missed_opportunities',
  }));

// ── Combine ───────────────────────────────────────────────────
const allRisks = [
  ...dueTodayBlocked,
  ...tomorrowMissingAssets,
  ...overloadedOwners,
  ...svcAtRisk,
  ...unassignedFollowUps,
  ...missedHighSev,
].sort((a, b) => {
  const urgOrder = { today: 0, this_week: 1 };
  if (urgOrder[a.urgency] !== urgOrder[b.urgency]) return urgOrder[a.urgency] - urgOrder[b.urgency];
  const sevOrder = { high: 0, medium: 1, low: 2 };
  return sevOrder[a.severity] - sevOrder[b.severity];
});

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_deadline_risk.js',
  summary: {
    total_risks:   allRisks.length,
    high_urgency:  allRisks.filter(r => r.severity === 'high').length,
    medium_urgency: allRisks.filter(r => r.severity === 'medium').length,
    today_slip:    dueTodayBlocked.length + tomorrowMissingAssets.length,
    this_week_slips: allRisks.filter(r => r.urgency === 'this_week').length,
  },
  risks: allRisks,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Deadline risk: ${OUTPUT}`);
console.log(`   Total: ${allRisks.length} | High: ${output.summary.high_urgency} | Today slip: ${output.summary.today_slip}`);
allRisks.slice(0, 5).forEach(r => {
  console.log(`   [${r.severity.toUpperCase()}] ${r.title.substring(0, 55)}`);
  console.log(`      Fix: ${r.fix.substring(0, 70)}`);
});
