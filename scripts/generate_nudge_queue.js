#!/usr/bin/env node
/**
 * generate_nudge_queue.js
 * Queue of nudges the system wants to send to owners.
 * Output: data/nudge-queue.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'nudge-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const tasks     = readJson('daily-task-cards.json')        || {};
const blockers  = readJson('blockers.json')               || {};
const appr     = readJson('approval-queue.json')         || {};
const deadline = readJson('deadline-risk.json')          || {};
const capShift = readJson('capacity-shift.json')         || {};
const suppr   = readJson('suppression-rules.json')       || {};

function uid() { return 'ndg_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];

const allTasks  = tasks.all_tasks  || [];
const allBlk   = blockers.blockers || [];
const allAppr  = appr.pending_items || [];
const allRisks = deadline.risks   || [];
const supRules = suppr.rules       || [];

// ── Suppression check ──────────────────────────────────────────
function isSuppressed(nudge) {
  const rules = supRules.filter(r => r.active !== false);
  for (const rule of rules) {
    if (rule.type === 'duplicate_nudge') {
      // suppress if same owner + same nudge type within window
      // (checked at send time — here we just mark potential)
    }
    if (rule.type === 'spam_owner') {
      // suppress if owner already nudged in last N hours
    }
  }
  return false;
}

// ── 1. Asset reminder nudge ───────────────────────────────────
const assetNudges = allTasks.filter(t =>
  t.status === 'blocked' && t.blockers && t.blockers.some(b => b.includes('asset'))
).map(t => ({
  nudge_id:        uid(),
  type:           'asset_reminder',
  owner:          t.owner,
  channel:        'discord',
  reason:         'Missing ' + t.asset_needed + ' for ' + t.source + ' post',
  related_task_id: t.task_id,
  severity:       t.urgency === 'today' ? 'high' : 'medium',
  send_window:    t.urgency === 'today' ? 'now' : 'this_week',
  status:         'ready',
}));

// ── 2. Approval reminder nudge ─────────────────────────────────
const approvalNudges = allAppr.filter(a =>
  a.missing && a.missing.length > 0 && a.urgency !== 'this_week'
).map(a => ({
  nudge_id:        uid(),
  type:           'approval_reminder',
  owner:          a.approver,
  channel:        'discord',
  reason:         a.what_missing + ' needed for: ' + a.title,
  related_item_id: a.item_id,
  severity:       a.urgency === 'today' ? 'high' : 'medium',
  send_window:    a.urgency === 'today' ? 'now' : 'today_evening',
  status:         'ready',
}));

// ── 3. Overdue / due-today nudge ────────────────────────────────
const overdueNudges = allTasks.filter(t =>
  (t.due_date === today || t.date === today) && t.status === 'blocked'
).map(t => ({
  nudge_id:        uid(),
  type:           'overdue_task',
  owner:          t.owner,
  channel:        'discord',
  reason:         'This post was due today and is still blocked: ' + t.title,
  related_task_id: t.task_id,
  severity:       'high',
  send_window:    'now',
  status:         'ready',
}));

// ── 4. Booking CTA missing nudge ────────────────────────────────
const ctaNudges = allTasks.filter(t =>
  t.blockers && t.blockers.some(b => b.includes('cta') || b.includes('booking'))
).map(t => ({
  nudge_id:        uid(),
  type:           'cta_missing',
  owner:          t.owner,
  channel:        'discord',
  reason:         'Post is missing a booking CTA — add to caption to enable conversion tracking',
  related_task_id: t.task_id,
  severity:       'medium',
  send_window:    'today',
  status:         'ready',
}));

// ── 5. High-risk deadline warning ─────────────────────────────
const riskNudges = allRisks.filter(r =>
  r.severity === 'high'
).map(r => ({
  nudge_id:        uid(),
  type:           'deadline_warning',
  owner:          r.owner !== 'Unassigned' ? r.owner : null,
  channel:        'discord',
  reason:         r.what_will_slip || r.fix,
  related_task_id: r.risk_id,
  severity:       'high',
  send_window:    'now',
  status:         'ready',
}));

// ── 6. Owner overload warning ────────────────────────────────
const overloadNudges = allRisks.filter(r =>
  r.type === 'owner_overload'
).map(r => ({
  nudge_id:        uid(),
  type:           'owner_overload_warning',
  owner:          r.owner,
  channel:        'discord',
  reason:         r.what_will_slip,
  related_task_id: r.risk_id,
  severity:       r.severity,
  send_window:    'today',
  status:         'ready',
}));

// ── Combine ───────────────────────────────────────────────────
const allNudges = [
  ...overdueNudges,
  ...riskNudges,
  ...assetNudges,
  ...approvalNudges,
  ...ctaNudges,
  ...overloadNudges,
].filter(Boolean);

// Remove duplicates (same owner + same type + same task)
const seen = new Set();
const deduped = allNudges.filter(n => {
  const key = n.owner + ':' + n.type + ':' + (n.related_task_id || '');
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
}).map(n => ({ ...n, suppressed: false }));

const byStatus = { ready: 0, suppressed: 0, sent: 0 };
deduped.forEach(n => { if (byStatus[n.status] !== undefined) byStatus[n.status]++; });

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_nudge_queue.js',
  summary: {
    total:      deduped.length,
    by_status: byStatus,
    by_type:   Object.fromEntries(
      [...new Set(deduped.map(n => n.type))].map(t => [t, deduped.filter(n => n.type === t).length])
    ),
    high_severity: deduped.filter(n => n.severity === 'high').length,
  },
  nudges: deduped,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Nudge queue: ${OUTPUT}`);
console.log(`   Total: ${deduped.length} | Ready: ${byStatus.ready} | High: ${output.summary.high_severity}`);
deduped.slice(0, 8).forEach(n => {
  console.log(`   [${n.severity.toUpperCase()}] ${n.type} → ${n.owner} (${n.send_window})`);
  console.log(`      ${n.reason.substring(0, 70)}`);
});
