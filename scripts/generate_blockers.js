#!/usr/bin/env node
/**
 * generate_blockers.js
 * Identifies what's blocking execution — explicit and fixable.
 * Output: data/blockers.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'blockers.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const tasks    = readJson('daily-task-cards.json')        || {};
const plan     = readJson('post-plan.json')              || {};
const assets   = readJson('asset-needs.json')            || {};
const retarget = readJson('retargeting-recommendations.json') || {};

function uid() { return 'blk_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];

const allTasks = tasks.all_tasks || [];

// ── 1. Missing asset ────────────────────────────────────────────
const assetBlocked = allTasks.filter(t =>
  t.blockers && t.blockers.some(b => b.includes('asset')) && t.asset_needed
).map(t => ({
  blocker_id: uid(),
  type:       'missing_asset',
  blocker:    'Missing: ' + t.asset_needed,
  affected:   t.title,
  affected_id: t.source_id,
  owner:      t.owner,
  fix:        'Source or create ' + t.asset_needed + ' — needed for ' + t.source + ' post',
  urgency:    t.urgency === 'today' ? 'today' : 'this_week',
  severity:   t.urgency === 'today' ? 'high' : 'medium',
}));

// ── 2. No owner assigned ───────────────────────────────────────
const noOwner = allTasks.filter(t =>
  !t.owner || t.owner === 'Swing Shack page' || t.owner === 'undefined'
).map(t => ({
  blocker_id: uid(),
  type:       'no_owner',
  blocker:    'No owner assigned',
  affected:   t.title,
  affected_id: t.source_id,
  owner:      'Unassigned',
  fix:        'Assign owner — who is responsible for this ' + (t.source || 'task') + '?',
  urgency:    'this_week',
  severity:   'medium',
}));

// ── 3. No CTA on post ──────────────────────────────────────────
const noCTA = allTasks.filter(t =>
  t.blockers && t.blockers.some(b => b === 'no_cta' || b.includes('cta'))
).map(t => ({
  blocker_id: uid(),
  type:       'no_cta',
  blocker:    'No CTA added',
  affected:   t.title,
  affected_id: t.source_id,
  owner:      t.owner,
  fix:        'Add direct booking CTA to caption: Book your session · swingshack.co.za/membership',
  urgency:    t.urgency || 'this_week',
  severity:   'high',
}));

// ── 4. No approval given ────────────────────────────────────────
const approvalNeeded = (retarget.recommendations || []).filter(r =>
  r.reason_blocked === 'needs_approval'
).map(r => ({
  blocker_id: uid(),
  type:       'no_approval',
  blocker:    'Needs approval before posting',
  affected:   r.action || r.type,
  affected_id: r.recommendation_id,
  owner:      r.owner,
  fix:        'Get sign-off from ' + (r.owner || 'Swing Shack page') + ' before scheduling',
  urgency:    r.urgency || 'this_week',
  severity:   'medium',
}));

// ── 5. Asset needed today not yet sourced ───────────────────────
const todayAssetsNeeded = (assets.needs || []).filter(n =>
  n.urgency === 'today'
).map(n => ({
  blocker_id: uid(),
  type:       'asset_needed_today',
  blocker:    'Asset needed today',
  affected:   n.asset_label || n.asset_raw,
  affected_id: null,
  owner:      n.owner,
  fix:        'Source ' + n.asset_raw + ' — ' + n.count + ' post(s) need this today',
  urgency:    'today',
  severity:   'high',
}));

// ── 6. Booking link missing ─────────────────────────────────────
const noBookingLink = allTasks.filter(t =>
  t.blockers && t.blockers.some(b => b.includes('booking'))
).map(t => ({
  blocker_id: uid(),
  type:       'no_booking_link',
  blocker:    'Booking link missing',
  affected:   t.title,
  affected_id: t.source_id,
  owner:      t.owner,
  fix:        'Add swingshack.co.za/bookings or swingshack.co.za/membership to caption',
  urgency:    t.urgency || 'this_week',
  severity:   'high',
}));

// ── 7. Post ready but not scheduled ────────────────────────────
const readyNotScheduled = allTasks.filter(t =>
  t.status === 'ready' && !t.date && t.source === 'retarget'
).map(t => ({
  blocker_id: uid(),
  type:       'not_scheduled',
  blocker:    'Ready but not in schedule',
  affected:   t.title,
  affected_id: t.source_id,
  owner:      t.owner,
  fix:        'Add to this week\'s post schedule before expiration window closes',
  urgency:    t.expiration_window === 'today' ? 'today' : 'this_week',
  severity:   t.expiration_window === 'today' ? 'high' : 'medium',
}));

// ── Combine ───────────────────────────────────────────────────
const allBlockers = [
  ...todayAssetsNeeded,
  ...noBookingLink,
  ...assetBlocked,
  ...noCTA,
  ...readyNotScheduled,
  ...noOwner,
  ...approvalNeeded,
].sort((a, b) => {
  const sevOrder = { high: 0, medium: 1, low: 2 };
  if (sevOrder[a.severity] !== sevOrder[b.severity]) return sevOrder[a.severity] - sevOrder[b.severity];
  const urgOrder = { today: 0, this_week: 1 };
  return (urgOrder[a.urgency] || 1) - (urgOrder[b.urgency] || 1);
});

const byType = {};
allBlockers.forEach(b => { byType[b.type] = (byType[b.type] || 0) + 1; });

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_blockers.js',
  summary: {
    total_blockers:  allBlockers.length,
    by_type:        byType,
    high_severity:  allBlockers.filter(b => b.severity === 'high').length,
    today_urgency:  allBlockers.filter(b => b.urgency === 'today').length,
    actionable:      allBlockers.length,
  },
  blockers: allBlockers,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Blockers: ${OUTPUT}`);
console.log(`   Total: ${allBlockers.length} | High: ${output.summary.high_severity} | Today: ${output.summary.today_urgency}`);
console.log(`   By type: ${Object.entries(byType).map(([k,v]) => k + '×' + v).join(', ')}`);
allBlockers.slice(0, 6).forEach(b => {
  console.log(`   [${b.severity.toUpperCase()}] ${b.blocker} — ${b.affected.substring(0, 45)}`);
  console.log(`      Fix: ${b.fix}`);
});
