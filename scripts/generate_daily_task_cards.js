#!/usr/bin/env node
/**
 * generate_daily_task_cards.js
 * Turns all recommendations into actionable task cards.
 * Output: data/daily-task-cards.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'daily-task-cards.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const plan     = readJson('post-plan.json')                    || {};
const retarget = readJson('retargeting-recommendations.json')  || {};
const expQ     = readJson('experiment-queue.json')            || {};
const scale    = readJson('scaling-recommendations.json')        || {};
const asset    = readJson('asset-needs.json')                 || {};
const owner    = readJson('owner-workload.json')              || {};
const missed   = readJson('missed-opportunities.json')         || {};
const recOut   = readJson('recommendation-outcomes.json')     || {};

function uid() {
  return 'task_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4);
}
function scoreSort(a, b) {
  return (b.urgency_score || 0) - (a.urgency_score || 0);
}

const now = Date.now();
const today = new Date().toISOString().split('T')[0];
const tomorrow = new Date(now + 86400000).toISOString().split('T')[0];
const dayAfter = new Date(now + 2 * 86400000).toISOString().split('T')[0];

// ── 1. Post plan tasks ─────────────────────────────────────────
const postPlanTasks = (plan.plan || []).map(p => {
  const blocked = [];
  if (!p.asset_needed || p.asset_needed === 'text graphic' || p.asset_needed === 'generic') {}
  else blocked.push('asset_needed:' + p.asset_needed);
  if (!p.owner || p.owner === 'Swing Shack page') {}
  const status = blocked.length === 0 ? 'ready' : 'blocked';
  return {
    task_id:      uid(),
    title:        (p.hook || 'Post').substring(0, 60),
    description:  p.hook + '\nCTA: ' + p.cta,
    owner:        p.owner,
    source:       'post_plan',
    source_id:    p.hook ? uid() : null,
    format:       p.format,
    platform:     p.platform || 'instagram',
    objective:   p.objective,
    day:          p.day,
    date:         p.date,
    due_date:     p.date || today,
    asset_needed: p.asset_needed,
    dependency:   p.asset_needed && !['none', 'text graphic'].includes(p.asset_needed) ? 'asset_required' : null,
    expected_outcome: p.objective === 'REACH' ? 'reach > 200, eng > 3%' : 'saves > 3, booking_ctr > 1%',
    urgency_score: (p.urgency === 'today' ? 10 : p.urgency === 'this_week' ? 6 : 3) * (p.freshness_score || 5) / 5,
    urgency:      p.urgency,
    status,
    blockers:     blocked,
    suggested_hook: p.hook,
    suggested_cta:  p.cta,
  };
});

// ── 2. Retargeting tasks ───────────────────────────────────────
const retargetTasks = (retarget.recommendations || []).map(r => {
  const blocked = [];
  if (!r.suggested_cta || r.suggested_cta.length < 5) blocked.push('no_cta');
  if (r.already_planned) blocked.push('already_scheduled');
  return {
    task_id:      uid(),
    title:        (r.action || r.type || 'Retarget').substring(0, 60),
    description:  'Hook: ' + (r.suggested_hook || r.hook || '—') + '\nCTA: ' + (r.suggested_cta || '—'),
    owner:        r.owner,
    source:       'retarget',
    source_id:    r.recommendation_id,
    channel:      r.channel,
    format:       r.format,
    asset_needed: r.suggested_cta ? null : 'booking_cta',
    expected_outcome: r.expected_outcome?.label || 'retarget engagement',
    urgency_score: (r.expiration_window === 'today' ? 10 : r.expiration_window === '48h' ? 7 : 4) * (r.score || 5) / 10,
    urgency:      r.urgency,
    status:        blocked.length === 0 ? 'ready' : 'blocked',
    blockers:      blocked,
    suggested_hook: r.suggested_hook || r.hook,
    suggested_cta:  r.suggested_cta,
    expiration_window: r.expiration_window,
  };
});

// ── 3. Experiment tasks ──────────────────────────────────────
const expTasks = (expQ.experiments || []).slice(0, 5).map(e => ({
  task_id:       uid(),
  title:         ('A/B Test: ' + (e.variable || e.type)).substring(0, 60),
  description:   'Test: ' + e.description + '\nSuccess: ' + e.success_metric,
  owner:         e.owner,
  source:        'experiment',
  source_id:     e.test_id,
  channel:       e.channel,
  asset_needed:  'variant_a_and_b_creative',
  expected_outcome: 'winner emerges in 3-5 days',
  urgency_score: (e.urgency === 'today' ? 10 : 6) * (e.confidence || 3) / 5,
  urgency:       e.urgency,
  status:        'ready',
  blockers:      [],
  test_variant_a: e.variant_a,
  test_variant_b: e.variant_b,
  success_metric: e.success_metric,
}));

// ── 4. Scaling tasks ────────────────────────────────────────────
const scaleTasks = (scale.recommendations || []).slice(0, 4).map(s => ({
  task_id:      uid(),
  title:       ('Scale: ' + (s.action || s.type || 'Scale')).substring(0, 60),
  description: (s.recommendation || s.action) + '\nExpected: ' + (s.expected_impact || 'growth'),
  owner:       s.owner,
  source:      'scale',
  asset_needed: s.type === 'landing_page' ? 'landing_page_copy' : null,
  expected_outcome: s.expected_impact,
  urgency_score: (s.urgency === 'today' ? 8 : 5) * (s.confidence || 3) / 5,
  urgency:     s.urgency,
  status:      s.type === 'landing_page' ? 'blocked' : 'ready',
  blockers:    s.type === 'landing_page' ? ['needs_landing_page'] : [],
  suggested_hook: s.hook,
  suggested_cta:  s.cta_type || s.cta || s.recommendation,
}));

// ── 5. Follow-up queue tasks ───────────────────────────────────
const fuTasks = (retarget.followUpQ || []).map(q => ({
  task_id:      uid(),
  title:       ('Follow-up: ' + (q.topic || q.suggested_hook || '')).substring(0, 60),
  description:  'Hook: ' + (q.suggested_hook || q.original_hook || '—') + '\nCTA: ' + (q.suggested_cta || '—'),
  owner:       q.owner,
  source:      'follow_up',
  reason_blocked: q.reason_blocked,
  urgency:     q.urgency,
  urgency_score: q.urgency === 'high' ? 8 : q.urgency === 'medium' ? 5 : 3,
  status:       q.reason_blocked === 'in_plan' ? 'scheduled' : q.reason_blocked === 'needs_asset' ? 'blocked' : 'ready',
  blockers:     q.reason_blocked === 'needs_asset' ? ['asset_missing'] : q.reason_blocked === 'needs_owner' ? ['no_owner'] : [],
  suggested_hook: q.suggested_hook,
  suggested_cta:  q.suggested_cta,
}));

// ── Combine ───────────────────────────────────────────────────
const allTasks = [
  ...postPlanTasks,
  ...retargetTasks,
  ...expTasks,
  ...scaleTasks,
  ...fuTasks,
];

// Status counts
const byStatus = { ready: 0, blocked: 0, scheduled: 0, done: 0, waiting_approval: 0 };
allTasks.forEach(t => {
  if (byStatus[t.status] !== undefined) byStatus[t.status]++;
});

// Top 10 by urgency score
const topTasks = [...allTasks].sort(scoreSort).slice(0, 10);

// Group by owner
const byOwner = {};
allTasks.forEach(t => {
  const o = t.owner || 'Unassigned';
  if (!byOwner[o]) byOwner[o] = [];
  byOwner[o].push(t);
});
const ownerSummary = Object.entries(byOwner).map(([owner, tasks]) => ({
  owner,
  count:       tasks.length,
  ready:       tasks.filter(t => t.status === 'ready').length,
  blocked:     tasks.filter(t => t.status === 'blocked').length,
  scheduled:   tasks.filter(t => t.status === 'scheduled').length,
  top_task:    tasks.sort(scoreSort)[0]?.title || '—',
})).sort((a, b) => b.count - a.count);

// ── Write ─────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_daily_task_cards.js',
  summary: {
    total:       allTasks.length,
    by_status:   byStatus,
    by_owner:    ownerSummary.length,
    today_count: allTasks.filter(t => t.due_date === today).length,
    blocked_count: byStatus.blocked,
  },
  top_tasks:    topTasks,
  by_owner:     ownerSummary,
  all_tasks:     allTasks.sort(scoreSort),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Daily task cards: ${OUTPUT}`);
console.log(`   Total: ${allTasks.length} | Ready: ${byStatus.ready} | Blocked: ${byStatus.blocked} | Scheduled: ${byStatus.scheduled}`);
console.log(`   Top 5 tasks by urgency:`);
topTasks.slice(0, 5).forEach((t, i) => {
  console.log(`   ${i+1}. [${t.status.toUpperCase()}] ${t.owner} | ${t.title.substring(0, 50)}`);
  console.log(`      Urgency: ${t.urgency_score.toFixed(1)} | ${t.due_date || 'no due date'}`);
});
