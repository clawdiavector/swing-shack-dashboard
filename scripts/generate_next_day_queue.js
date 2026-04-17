#!/usr/bin/env node
/**
 * generate_next_day_queue.js
 * Prepares tomorrow's posting queue before tomorrow arrives.
 * Output: data/next-day-queue.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'next-day-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const tasks   = readJson('daily-task-cards.json')       || {};
const appr   = readJson('approval-queue.json')         || {};
const assets = readJson('asset-needs.json')            || {};
const fallb  = readJson('fallback-queue.json')        || {};
const plan  = readJson('post-plan.json')             || {};

function uid() { return 'ndq_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const tomorrow = new Date(now + 86400000).toISOString().split('T')[0];

// Day name from date
const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const tomorrowName = dayNames[new Date(now + 86400000).getDay()];

const allTasks   = tasks.all_tasks || [];
const allAppr   = appr.pending_items || [];
const allAssets = assets.needs || [];
const allFallb  = fallb.fallbacks || [];

// Posts for tomorrow in the plan
const tomorrowPlan = (plan.plan || []).filter(p => p.date === tomorrow);
const tomorrowTasks = allTasks.filter(t =>
  (t.due_date === tomorrow || t.date === tomorrow) && t.status !== 'done'
);

// Ready posts for tomorrow
const readyForTomorrow = tomorrowTasks.filter(t => t.status === 'ready');
const blockedTomorrow  = tomorrowTasks.filter(t => t.status === 'blocked');

// Items needing approval before tomorrow
const needsApproval = allAppr.filter(a =>
  a.urgency === 'today' || a.urgency === 'tomorrow'
);

// Assets needed by tomorrow
const assetsByTomorrow = allAssets.filter(n =>
  n.urgency === 'today' || n.urgency === 'this_week'
).map(n => ({
  asset:       n.asset_label || n.asset_raw,
  owner:      n.owner,
  posts_count: n.count,
  urgency:    n.urgency,
  posts:      (n.posts || []).map(p => p.hook || p.day || 'unnamed post'),
}));

// Fallback options for blocked items
const fallbackOptions = allFallb.filter(f =>
  blockedTomorrow.some(b => b.task_id === f.original_task_id)
);

// Approval status for tomorrow's posts
const tomorrowApprStatus = tomorrowTasks.map(t => {
  const apprItem = allAppr.find(a =>
    a.title && t.title && a.title.includes(t.title.substring(0, 30))
  );
  return {
    task_id:    t.task_id,
    title:      t.title,
    owner:      t.owner,
    status:     t.status,
    missing:    apprItem ? apprItem.what_missing : null,
    approver:   t.owner,
    approval_status: !apprItem || apprItem.missing.length === 0 ? 'approved' : 'needs_info',
  };
});

// Build the queue
const postQueue = readyForTomorrow.slice(0, 3).map((t, i) => ({
  position:     i + 1,
  task_id:      t.task_id,
  title:       t.title,
  hook:       t.suggested_hook || t.title,
  cta:        t.suggested_cta || 'Book your session \u00b7 swingshack.co.za/membership',
  owner:       t.owner,
  format:     t.format || 'static',
  platform:   t.platform || 'instagram',
  objective:  t.objective || 'REACH',
  asset_status: t.asset_needed ? 'needed:' + t.asset_needed : 'none',
  approval_status: tomorrowApprStatus.find(a => a.task_id === t.task_id)?.approval_status || 'unknown',
  missing:     tomorrowApprStatus.find(a => a.task_id === t.task_id)?.missing || null,
  fallback_id: fallbackOptions.find(f => f.original_task_id === t.task_id)?.fallback_id || null,
}));

// What will slip if not resolved tonight
const willSlip = blockedTomorrow.filter(t =>
  !fallbackOptions.some(f => f.original_task_id === t.task_id)
).map(t => ({
  task_id:   t.task_id,
  title:    t.title,
  owner:    t.owner,
  blockers: t.blockers,
  urgency:  t.urgency,
}));

const output = {
  updated:      new Date().toISOString(),
  generated:   'generate_next_day_queue.js',
  summary: {
    date:               tomorrow,
    day_name:           tomorrowName,
    posts_ready:        readyForTomorrow.length,
    posts_blocked:      blockedTomorrow.length,
    needs_approval:     needsApproval.length,
    will_slip:          willSlip.length,
    assets_needed:      assetsByTomorrow.length,
    confidence:         readyForTomorrow.length >= 3 ? 'high' : readyForTomorrow.length >= 1 ? 'medium' : 'low',
  },
  post_queue:      postQueue,
  blocked_items:   willSlip,
  assets_needed:   assetsByTomorrow,
  fallback_options: fallbackOptions,
  approval_items: tomorrowApprStatus,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Next day queue: ${OUTPUT}`);
console.log(`   ${tomorrowName} ${tomorrow}: ${readyForTomorrow.length} posts ready | ${willSlip.length} will slip`);
postQueue.forEach((p, i) => {
  console.log(`   ${i+1}. [${p.status.toUpperCase()}] ${p.owner}: ${p.title.substring(0, 50)}`);
  if (p.missing) console.log(`      Missing: ${p.missing}`);
  if (p.asset_status !== 'none') console.log(`      Asset: ${p.asset_status}`);
});
if (willSlip.length > 0) {
  console.log(`   ⚠️ Will slip:`);
  willSlip.forEach(s => console.log(`      ${s.owner}: ${s.title.substring(0, 50)} — ${s.blockers.join(', ')}`));
}
