#!/usr/bin/env node
/**
 * generate_approval_queue.js
 * Tracks posts and items waiting for sign-off, captions, visuals, pricing.
 * Output: data/approval-queue.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'approval-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const plan     = readJson('post-plan.json')                   || {};
const tasks    = readJson('daily-task-cards.json')            || {};
const retarget = readJson('retargeting-recommendations.json')  || {};

function uid() { return 'ap_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];
const tomorrow = new Date(now + 86400000).toISOString().split('T')[0];

// Items from post plan that need caption or visual
const postPlanItems = (plan.plan || []).map(p => {
  const missing = [];
  const captionOk = p.hook && p.hook.length > 10;
  const visualOk = p.asset_needed && !['none', 'text graphic', 'generic'].includes(p.asset_needed);
  const ctaOk = p.cta && p.cta.length > 3;
  if (!captionOk) missing.push('caption_needed');
  if (visualOk)    missing.push('visual_needed:' + p.asset_needed);
  if (!ctaOk)      missing.push('cta_needed');
  if (p.objective === 'BOOKINGS' && !ctaOk) missing.push('booking_link_needed');
  const urgency = p.date === today ? 'today' : p.date === tomorrow ? 'tomorrow' : 'this_week';
  return {
    item_id:      uid(),
    title:        (p.hook || 'Post ' + p.day).substring(0, 60),
    owner:        p.owner,
    day:          p.day,
    date:         p.date,
    source:       'post_plan',
    missing,
    what_missing:  missing.map(m => m.replace(/_needed/, '').replace(/_/g, ' ')).join(', '),
    urgency,
    approver:     p.owner === 'Coach Cat' ? 'Coach Cat' : p.owner === 'Divan' ? 'Divan' : 'Swing Shack page',
    deadline:     p.date || today,
    suggested_hook: p.hook,
    suggested_cta:  p.cta,
    status:        missing.length === 0 ? 'approved' : 'awaiting_info',
  };
});

// Retargeting items needing approval
const retargetItems = (retarget.recommendations || []).map(r => {
  const missing = [];
  if (!r.suggested_cta || r.suggested_cta.length < 5) missing.push('caption_needed');
  if (!r.suggested_hook || r.suggested_hook.length < 10) missing.push('hook_needed');
  const urgency = r.expiration_window === 'today' ? 'today' : r.expiration_window === '48h' ? 'tomorrow' : 'this_week';
  return {
    item_id:     uid(),
    title:       (r.action || r.type).substring(0, 60),
    owner:       r.owner,
    source:      'retarget',
    missing,
    what_missing: missing.join(', '),
    urgency,
    approver:    'Swing Shack page',
    deadline:     r.expiration_window === 'today' ? today : tomorrow,
    suggested_hook: r.suggested_hook,
    suggested_cta: r.suggested_cta,
    status:       missing.length === 0 ? 'approved' : 'awaiting_info',
  };
});

// All pending items
const pendingItems = [
  ...postPlanItems.filter(p => p.missing.length > 0),
  ...retargetItems.filter(r => r.missing.length > 0),
].sort((a, b) => {
  const urgOrder = { today: 0, tomorrow: 1, this_week: 2 };
  return (urgOrder[a.urgency] || 2) - (urgOrder[b.urgency] || 2);
});

// Approved but not scheduled
const approvedNotScheduled = [
  ...postPlanItems.filter(p => p.missing.length === 0),
  ...retargetItems.filter(r => r.missing.length === 0),
];

// Summary
const missingCaption = pendingItems.filter(i => i.missing.some(m => m.includes('caption'))).length;
const missingVisual  = pendingItems.filter(i => i.missing.some(m => m.includes('visual'))).length;
const missingCTA    = pendingItems.filter(i => i.missing.some(m => m.includes('cta'))).length;
const byOwner = {};
pendingItems.forEach(i => {
  const o = i.owner || 'Unassigned';
  if (!byOwner[o]) byOwner[o] = [];
  byOwner[o].push(i);
});

const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_approval_queue.js',
  summary: {
    pending:       pendingItems.length,
    approved_not_scheduled: approvedNotScheduled.length,
    missing_caption: missingCaption,
    missing_visual:  missingVisual,
    missing_cta:     missingCTA,
    today_urgency:   pendingItems.filter(i => i.urgency === 'today').length,
  },
  pending_items:     pendingItems,
  approved_not_scheduled: approvedNotScheduled,
  by_owner:    Object.fromEntries(
    Object.entries(byOwner).sort(([a], [b]) => a.localeCompare(b))
  ),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Approval queue: ${OUTPUT}`);
console.log(`   Pending: ${pendingItems.length} | Approved not scheduled: ${approvedNotScheduled.length}`);
console.log(`   Missing caption: ${missingCaption} | visual: ${missingVisual} | CTA: ${missingCTA}`);
pendingItems.slice(0, 5).forEach(i => {
  console.log(`   [${i.urgency.toUpperCase()}] ${i.owner}: ${i.title.substring(0, 45)} — missing: ${i.what_missing}`);
});
