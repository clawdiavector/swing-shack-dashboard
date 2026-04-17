#!/usr/bin/env node
/**
 * generate_auto_messages.js
 * Drafts actual reminder copy for each nudge type.
 * Output: data/auto-messages.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'auto-messages.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const nudges = readJson('nudge-queue.json') || {};

function uid() { return 'msg_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

// ── Message templates ────────────────────────────────────────
const TEMPLATES = {
  asset_reminder: (n) =>
    `📦 Quick one — need a ${n.asset_needed || 'asset'} for the ${n.post_day || 'upcoming'} post.\n` +
    `Drop it in the shared drive or ping me when it's ready.`,

  approval_reminder: (n) =>
    `Hey — the ${n.post_title || 'post'} is waiting on ${n.missing || 'approval info'}.\n` +
    `Can you sort that before end of day so we can get it scheduled?`,

  overdue_task: (n) =>
    `⚠️ This was due today: "${n.post_title || n.task_title}"\n` +
    `It's still blocked. What's the fix — swap to a fallback or sort the blocker?`,

  cta_missing: (n) =>
    `📝 Post caption is missing a booking CTA: "${n.post_title || n.task_title}"\n` +
    `Add this to the caption before scheduling:\n` +
    `Book your session \u2192 swingshack.co.za/membership`,

  deadline_warning: (n) =>
    `🚨 ${n.owner || 'Team'} — "${n.what_will_slip || n.task_title}" is at risk of slipping.\n` +
    `Fix: ${n.fix || n.action}\n` +
    `This needs to happen ${n.urgency || 'today'}.`,

  owner_overload_warning: (n) =>
    `📊 Heads up — ${n.owner || 'Coach Cat'} has ${n.task_count || 'a lot'} tasks this week.\n` +
    `Can we move some to Swing Shack page to keep things on track?`,

  blocked_post: (n) =>
    `🔒 "${n.post_title || n.task_title}" is blocked.\n` +
    `Blocker: ${n.blocker || 'unknown'}\n` +
    `Fix: ${n.fallback_suggestion || 'Swap to a fallback post or resolve the blocker'}`,

  fallback_ready: (n) =>
    `✅ Fallback ready for "${n.original_title || n.task_title}":\n` +
    `"${n.fallback_caption || n.fallback_hook}"\n` +
    `Same CTA, same booking link — safe to post.`,

  tomorrow_reminder: (n) =>
    `📅 Tomorrow's post for ${n.owner}: "${n.post_title}"\n` +
    `Is everything ready to go? Reply done or flag if blocked.`,

  booking_cta_reminder: (n) =>
    `📲 Booking CTA is missing from this post's caption.\n` +
    `Quick add: Book your session \u2192 swingshack.co.za/bookings\n` +
    `Direct CTA = better tracking = better data next week.`,
};

// ── Generate messages ───────────────────────────────────────────
const nudgeList = nudges.nudges || [];
const messages = nudgeList
  .filter(n => n.status === 'ready')
  .map(n => {
    const template = TEMPLATES[n.type];
    if (!template) return null;
    return {
      message_id:   uid(),
      nudge_id:     n.nudge_id,
      type:         n.type,
      owner:        n.owner,
      channel:      n.channel || 'discord',
      subject:      n.subject || `Action needed: ${n.type.replace(/_/g, ' ')}`,
      body:         template(n),
      reason:       n.reason,
      severity:     n.severity,
      send_window:  n.send_window,
      status:       'draft',
    };
  })
  .filter(Boolean);

const byType = {};
messages.forEach(m => { byType[m.type] = (byType[m.type] || 0) + 1; });

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_auto_messages.js',
  summary: {
    total:     messages.length,
    by_type:  byType,
    high_sev: messages.filter(m => m.severity === 'high').length,
  },
  messages,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Auto messages: ${OUTPUT}`);
console.log(`   Total: ${messages.length} | High: ${output.summary.high_sev}`);
messages.slice(0, 5).forEach(m => {
  console.log(`   [${m.type}] \u2192 ${m.owner} (${m.channel})`);
  console.log(`   ${m.body.substring(0, 80)}`);
});
