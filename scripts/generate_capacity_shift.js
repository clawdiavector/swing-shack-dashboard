#!/usr/bin/env node
/**
 * generate_capacity_shift.js
 * Rebalances workload this week — suggests realistic swaps and fallbacks.
 * Output: data/capacity-shift.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'capacity-shift.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const owner   = readJson('owner-workload.json')            || {};
const tasks   = readJson('daily-task-cards.json')         || {};
const assets = readJson('asset-needs.json')               || {};
const plan   = readJson('post-plan.json')                 || {};
const retarget= readJson('retargeting-recommendations.json') || {};

function uid() { return 'shift_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];

const allTasks = tasks.all_tasks || [];
const owners = owner.owners || [];

// ── 1. Overloaded owners: suggest reassignments ────────────────
const overloadedThreshold = 5;
const overloadedOwners = owners.filter(o => (o.total || 0) > overloadedThreshold);

const reassignSuggestions = [];
overloadedOwners.forEach(o => {
  const theirTasks = allTasks.filter(t => t.owner === o.owner);
  const blockedTasks = theirTasks.filter(t => t.status === 'blocked');
  const lowUrgTasks = theirTasks.filter(t =>
    (t.urgency_score || 5) < 5 && t.status !== 'blocked'
  );
  const flexibleOwner = o.owner === 'Coach Cat' ? 'Swing Shack page' : 'Swing Shack page';

  // Suggest moving 1-2 low-urgency tasks
  lowUrgTasks.slice(0, 2).forEach(task => {
    reassignSuggestions.push({
      shift_id:       uid(),
      action:        'reassign',
      from_owner:     o.owner,
      to_owner:      flexibleOwner,
      task_title:     task.title,
      task_id:       task.task_id,
      reason:        o.owner + ' has ' + o.total + ' tasks — move low-urgency item to balance',
      new_status:    'ready',
      urgency_before: task.urgency,
      urgency_after:  task.urgency,
      severity:      o.total > 7 ? 'high' : 'medium',
    });
  });
});

// ── 2. Delay low-priority assets ────────────────────────────────
const delaySuggestions = (assets.needs || []).filter(n =>
  n.urgency === 'flexible' || n.urgency === 'this_week'
).slice(0, 3).map(n => ({
  shift_id:   uid(),
  action:    'delay',
  owner:     n.owner,
  asset:     n.asset_label || n.asset_raw,
  posts_affected: n.count,
  reason:    'Asset needed for ' + n.count + ' post(s) but urgency is ' + n.urgency + ' — push to next week',
  new_urgency: 'next_week',
  severity:  'low',
}));

// ── 3. Swap Reel for static if asset unavailable ──────────────
const reelTasks = allTasks.filter(t =>
  (t.format === 'reel' || t.format === 'video') &&
  t.asset_needed && !['none', 'text graphic'].includes(t.asset_needed)
);
const reelSwaps = reelTasks.filter(t =>
  t.status === 'blocked' && t.blockers && t.blockers.some(b => b.includes('asset'))
).slice(0, 3).map(t => ({
  shift_id:    uid(),
  action:     'format_swap',
  from_format: t.format,
  to_format:  'static',
  task_title:  t.title,
  task_id:    t.task_id,
  owner:      t.owner,
  reason:     'Reel blocked by missing ' + t.asset_needed + ' — swap to static to keep timeline',
  asset_needed: t.asset_needed,
  swap_benefit: 'Keeps schedule on track — static image is faster to produce',
  severity:   t.urgency === 'today' ? 'high' : 'medium',
}));

// ── 4. Replace blocked post with ready fallback ─────────────────
const blockedPosts = allTasks.filter(t =>
  t.status === 'blocked' && t.source === 'post_plan'
);
const fallbackSuggestions = blockedPosts.slice(0, 3).map(t => {
  // Find a ready fallback from same objective
  const fallbacks = allTasks.filter(f =>
    f.status === 'ready' &&
    f.objective === t.objective &&
    f.task_id !== t.task_id
  ).slice(0, 1);
  return {
    shift_id:   uid(),
    action:    'fallback_replace',
    blocked_task: t.title,
    blocked_id: t.task_id,
    owner:      t.owner,
    replacement: fallbacks[0] ? fallbacks[0].title : null,
    replacement_id: fallbacks[0] ? fallbacks[0].task_id : null,
    reason:    'Blocked: ' + (t.blockers || []).join(', ') + ' — replace with ready fallback',
    swap_benefit: fallbacks[0]
      ? 'Fallback already ready — ' + fallbacks[0].title.substring(0, 50)
      : 'No fallback available — source asset immediately',
    severity:  t.urgency === 'today' ? 'high' : 'medium',
  };
});

// ── 5. Suggest deferral of low-priority retargeting ─────────────
const retargetFlexible = (retarget.recommendations || []).filter(r =>
  r.urgency === 'flexible' && !r.already_planned
).slice(0, 2).map(r => ({
  shift_id:   uid(),
  action:    'defer_retarget',
  task_title: r.action || r.type,
  owner:      r.owner,
  reason:    'Retarget urgency is flexible — move to next week to focus on high-urgency items',
  new_window: 'next_week',
  severity:  'low',
}));

// ── 6. Move low-value tasks off Coach Cat ──────────────────────
const coachTasks = allTasks.filter(t =>
  t.owner === 'Coach Cat' && (t.urgency_score || 5) < 4
).slice(0, 2).map(t => ({
  shift_id:   uid(),
  action:    'reassign_to_page',
  from_owner: 'Coach Cat',
  to_owner:  'Swing Shack page',
  task_title: t.title,
  task_id:   t.task_id,
  reason:    'Coach Cat is the highest-loaded specialist — move low-priority non-lesson tasks to page',
  new_status: 'ready',
  urgency_before: t.urgency,
  severity:  'medium',
}));

// ── Combine ───────────────────────────────────────────────────
const allShifts = [
  ...reassignSuggestions,
  ...delaySuggestions,
  ...reelSwaps,
  ...fallbackSuggestions,
  ...retargetFlexible,
  ...coachTasks,
].filter(Boolean).sort((a, b) => {
  const sevOrder = { high: 0, medium: 1, low: 2 };
  return sevOrder[a.severity] - b.severity;
});

const byAction = {};
allShifts.forEach(s => { byAction[s.action] = (byAction[s.action] || 0) + 1; });

const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_capacity_shift.js',
  summary: {
    total_shifts:    allShifts.length,
    high_urgency:    allShifts.filter(s => s.severity === 'high').length,
    by_action:       byAction,
    overloads_found:  overloadedOwners.length,
    fallbacks_found: fallbackSuggestions.filter(f => f.replacement).length,
  },
  shifts: allShifts,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Capacity shift: ${OUTPUT}`);
console.log(`   Total shifts: ${allShifts.length} | High: ${output.summary.high_urgency}`);
console.log(`   By action: ${Object.entries(byAction).map(([k,v]) => k + '×' + v).join(', ')}`);
allShifts.slice(0, 5).forEach(s => {
  const detail = s.from_owner ? ` from ${s.from_owner} to ${s.to_owner}` : s.replacement ? ` → ${s.replacement.substring(0,40)}` : '';
  console.log(`   [${s.severity.toUpperCase()}] ${s.action} | ${s.task_title || s.asset || s.reason.substring(0, 50)}${detail}`);
});
