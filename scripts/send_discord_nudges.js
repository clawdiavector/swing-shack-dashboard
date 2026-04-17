#!/usr/bin/env node
/**
 * send_discord_nudges.js
 * Sends nudges to Discord — dry-run by default, live when DRY_RUN=false
 * Rules:
 *   - high-severity only
 *   - status = ready
 *   - not suppressed
 *   - within send window
 *   - fallback preferred over nagging where available
 *   - max 3 nudges per owner per day
 *   - no weekend nudges unless severity = critical
 *   - route by nudge type to appropriate channel
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR   = path.join(__dirname, '..', 'data');
const DELIVERY_F = path.join(DATA_DIR, 'discord-deliveries.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

function uid() { return 'snd_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = new Date();
const today = now.toISOString().split('T')[0];
const dayName = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][now.getDay()];
const isWeekend = dayName === 'Saturday' || dayName === 'Sunday';

// ── Load data ─────────────────────────────────────────────────
const nudgeQ    = readJson('nudge-queue.json')           || {};
const supprRul  = readJson('suppression-rules.json')     || {};
const fallbQ    = readJson('fallback-queue.json')        || { fallbacks: [] };
const taskCards = readJson('daily-task-cards.json')      || { all_tasks: [] };
const autoMsgs  = readJson('auto-messages.json')         || { messages: [] };

const DRY_MODE = process.env.DRY_RUN !== "false"; // true = dry run, false = live // default true

// ── Load existing deliveries for per-owner-per-day count ─────
let deliveries = [];
try {
  const log = JSON.parse(fs.readFileSync(DELIVERY_F, 'utf8'));
  const todayLogs = (log.deliveries || []).filter(d => d.sent_at && d.sent_at.split('T')[0] === today);
  deliveries = todayLogs;
} catch {}

// ── Channel routing ────────────────────────────────────────────
const CHANNEL_MAP = {
  asset_reminder:        '#content-assets',
  approval_reminder:     '#approvals',
  overdue_task:          '#ops-planning',
  cta_missing:           '#ops-planning',
  deadline_warning:      '#ops-planning',
  owner_overload_warning: '#ops-planning',
  blocked_post:          '#content-assets',
  fallback_ready:        '#content-assets',
  tomorrow_reminder:      '#ops-planning',
  booking_cta_reminder:  '#ops-planning',
};

// ── Build fallback lookup ──────────────────────────────────────
const fallbackByTask = {};
(fallbQ.fallbacks || []).forEach(f => {
  if (f.original_task_id) fallbackByTask[f.original_task_id] = f;
});

// ── Per-owner nudge count today ────────────────────────────────
const sentCountByOwner = {};
deliveries.filter(d => d.delivery_status === 'sent').forEach(d => {
  sentCountByOwner[d.owner] = (sentCountByOwner[d.owner] || 0) + 1;
});

// ── Evaluate each nudge ────────────────────────────────────────
const nudges = (nudgeQ.nudges || []).filter(n => n.status === 'ready');
const suppressionRules = (supprRul.rules || []).filter(r => r.active !== false);

const results = [];

for (const nudge of nudges) {
  const task = taskCards.all_tasks.find(t => t.task_id === nudge.related_task_id);
  const fallback = fallbackByTask[nudge.related_task_id];

  let decision = 'skip';
  let reason   = '';
  let sendChannel = CHANNEL_MAP[nudge.type] || '#ops-planning';

  // ── Severity filter ──────────────────────────────────────
  if (nudge.severity !== 'high') {
    reason = 'not_high_severity';
    decision = 'skip';
  }
  // ── Weekend filter ───────────────────────────────────────
  else if (isWeekend && nudge.severity !== 'critical') {
    reason = 'weekend_suppression';
    decision = 'suppress';
  }
  // ── Max 3 per owner per day ──────────────────────────────
  else if ((sentCountByOwner[nudge.owner] || 0) >= 3) {
    reason = 'max_3_per_owner_per_day';
    decision = 'suppress';
  }
  // ── Suppression rule evaluation ──────────────────────────
  else {
    for (const rule of suppressionRules) {
      if (rule.type === 'fallback_exists' && fallback) {
        // Don't nag if a fallback is ready — send fallback instead
        decision = 'fallback_swap';
        reason   = 'fallback_available';
        break;
      }
      if (rule.type === 'already_done' && task && (task.status === 'done' || task.status === 'scheduled')) {
        decision = 'suppress';
        reason   = 'task_already_done';
        break;
      }
      if (rule.type === 'spam_owner' && (sentCountByOwner[nudge.owner] || 0) >= (rule.max_per_day || 3)) {
        decision = 'suppress';
        reason   = 'spam_owner_rule';
        break;
      }
      if (rule.type === 'low_priority_spam' && (taskCards.all_tasks.filter(t => t.owner === nudge.owner).length >= (rule.threshold || 5)) && nudge.severity === 'low') {
        decision = 'suppress';
        reason   = 'low_priority_during_overload';
        break;
      }
    }
  }

  // ── Send window check ─────────────────────────────────────
  if (decision === 'skip' && nudge.severity === 'high') {
    if (nudge.send_window === 'now' || nudge.send_window === 'today') {
      decision = 'ready_to_send';
    } else if (nudge.send_window === 'today_evening') {
      // defer — will be picked up by evening run
      decision = 'defer';
      reason = 'send_window_today_evening';
    }
  }

  // ── Build message payload ────────────────────────────────
  let message = '';
  if (decision === 'fallback_swap' && fallback) {
    message =
      `⚠️ **BLOCKED POST — SWAP TO FALLBACK**\n\n` +
      `**Owner:** ${nudge.owner}\n` +
      `**Why:** ${nudge.reason}\n\n` +
      `**Fallback ready:**\n` +
      `${(fallback.fallback_hook || fallback.fallback_caption || '').substring(0, 120)}\n\n` +
      `**Format:** ${fallback.fallback_format || fallback.swap_to_format || 'static'}\n` +
      `**CTA:** ${fallback.fallback_cta || 'Book your session → swingshack.co.za/membership'}\n\n` +
      `No asset needed — safe to post now.`;
    decision = DRY_MODE ? 'dry_run_fallback' : 'fallback_swap';
  } else if (decision === 'ready_to_send' || decision === 'dry_run') {
    const fixLine = task && task.blockers ? `Fix: ${task.blockers.join(', ')}` : `Fix: ${nudge.reason}`;
    message =
      `📌 **NUDGE — ACTION NEEDED**\n\n` +
      `**Owner:** ${nudge.owner}\n` +
      `**Priority:** ${(nudge.severity || 'medium').toUpperCase()}\n` +
      `**Why:** ${nudge.reason}\n\n` +
      `${fixLine}\n\n` +
      `**Channel:** ${sendChannel}`;
    if (fallback) message += `\n**Fallback:** available — swap instead of nagging`;
    decision = DRY_MODE ? "dry_run" : 'send';
  }

  results.push({
    delivery_id:   uid(),
    nudge_id:       nudge.nudge_id,
    type:           nudge.type,
    owner:          nudge.owner,
    channel:        sendChannel,
    reason:         nudge.reason,
    severity:       nudge.severity,
    send_window:    nudge.send_window,
    decision,
    suppressed_reason: reason,
    fallback_used:  !!fallback && (decision === 'fallback_swap' || decision === 'dry_run_fallback'),
    fallback_id:    fallback?.fallback_id || null,
    task_id:        nudge.related_task_id,
    message_preview: message.substring(0, 80),
    DRY_MODE,
    sent_at:        null,
    delivery_status: decision.startsWith('dry_run') ? 'dry_run' : decision === 'skip' ? 'skipped' : decision === 'suppress' ? 'suppressed' : decision === 'defer' ? 'deferred' : 'sent',
  });
}

// ── Summary ────────────────────────────────────────────────────
const summary = {
  updated:         new Date().toISOString(),
  generated:      'send_discord_nudges.js',
  dry_run: DRY_MODE,
  total_nudges:   results.length,
  by_decision: {
    dry_run:       results.filter(r => r.decision === 'dry_run').length,
    dry_run_fallback: results.filter(r => r.decision === 'dry_run_fallback').length,
    send:           results.filter(r => r.decision === 'send').length,
    fallback_swap:  results.filter(r => r.decision === 'fallback_swap').length,
    suppress:       results.filter(r => r.decision === 'suppress' || r.decision === 'suppress_low_priority').length,
    skip:           results.filter(r => r.decision === 'skip').length,
    defer:          results.filter(r => r.decision === 'defer').length,
  },
  by_owner:       {},
  would_send_to:   results.filter(r => r.decision === 'send' || r.decision === 'fallback_swap').map(r => r.owner),
};

results.forEach(r => {
  summary.by_owner[r.owner] = summary.by_owner[r.owner] || [];
  summary.by_owner[r.owner].push({ type: r.type, decision: r.decision });
});

// ── Write delivery log ─────────────────────────────────────────
const existingDeliveries = (() => {
  try { return JSON.parse(fs.readFileSync(DELIVERY_F, 'utf8')).deliveries || []; }
  catch { return []; }
})();

// Append new results to existing (keeping historical)
const allDeliveries = [
  ...existingDeliveries.filter(d => d.sent_at !== null), // keep historical
  ...results.map(r => ({ ...r, sent_at: r.decision.startsWith('send') || r.decision === 'fallback_swap' ? new Date().toISOString() : null })),
];

const logOutput = {
  updated:    new Date().toISOString(),
  generated:  'send_discord_nudges.js',
  summary,
  deliveries: allDeliveries,
};

fs.writeFileSync(DELIVERY_F, JSON.stringify(logOutput, null, 2));

// ── Console output ─────────────────────────────────────────────
console.log(`\n${DRY_MODE ? '🔵 DRY RUN' : '🟢 LIVE'} — Discord nudge sender`);
console.log(`   Total nudges evaluated: ${results.length}`);
Object.entries(summary.by_decision).forEach(([k, v]) => {
  if (v > 0) console.log(`   ${k}: ${v}`);
});

const toSend = results.filter(r => r.decision === 'send' || r.decision === 'fallback_swap');
if (toSend.length > 0) {
  console.log(`\n📤 Would send ${toSend.length} nudge(s):`);
  toSend.forEach(r => {
    console.log(`   → ${r.owner} [${r.type}] (${r.channel})`);
    console.log(`     ${r.message_preview}`);
  });
} else {
  console.log(`\n📭 Nothing to send right now.`);
}

const suppressedHigh = results.filter(r => r.severity === 'high' && (r.decision === 'suppress' || r.decision === 'skip'));
if (suppressedHigh.length > 0) {
  console.log(`\n🔇 Suppressed ${suppressedHigh.length} high-severity nudge(s):`);
  suppressedHigh.forEach(r => console.log(`   ⏭ ${r.owner}: ${r.type} — ${r.suppressed_reason}`));
}