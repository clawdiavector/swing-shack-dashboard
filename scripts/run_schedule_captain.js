#!/usr/bin/env node
/**
 * run_schedule_captain.js — schedule_captain agent core script
 * Reads: post-plan.json, ready-for-approval.json, daily-task-cards.json, fallback-queue.json, capacity-shift.json
 * Produces: schedule-board.json, tomorrow-slots.json, reschedule-log.json
 *
 * Rules:
 * - Only schedule executable items
 * - If blocked, swap in fallback
 * - Balance across: hook types, service pushes, content formats
 *
 * Schema: https://clawdia.io/agents/schedule-captain/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const plan    = readJson('post-plan.json') || {};
  const ready   = readJson('ready-for-approval.json') || {};
  const tasks   = readJson('daily-task-cards.json') || {};
  const fallbQ  = readJson('fallback-queue.json') || {};
  const capShift = readJson('capacity-shift.json') || {};

  const today = new Date().toISOString().split('T')[0];
  const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];

  // ── Build slot model ──────────────────────────────────────────────
  const DAY_SLOTS = [
    { time: '09:00', label: 'Morning — high reach', capacity: 1 },
    { time: '12:00', label: 'Lunch — engagement', capacity: 1 },
    { time: '18:00', label: 'Evening — conversions', capacity: 1 },
  ];

  const SERVICE_BUCKETS = ['Club Fitting', 'Coaching', 'Practice', 'Social Play'];
  const FORMAT_BUCKETS  = ['static', 'carousel', 'reel', 'blog', 'short_script'];

  // ── Get today's planned items ─────────────────────────────────────
  const todayPlan = (plan.plan || []).filter(p => p.dateISO === today);
  const tomorrowPlan = (plan.plan || []).filter(p => p.dateISO === tomorrow);

  // ── Get approved ready items ─────────────────────────────────────
  const approvedItems = (ready.items || []).filter(i => i.ready_for_qa && i.item_type === 'caption');

  // ── Build today's schedule board ─────────────────────────────────
  const boardEntries = [];
  let slotIdx = 0;

  todayPlan.forEach(entry => {
    const slot = DAY_SLOTS[slotIdx % DAY_SLOTS.length];
    boardEntries.push({
      slot_id: `slot-${uid()}`,
      schema: 'https://clawdia.io/agents/schedule-captain/v1',
      generated: new Date().toISOString(),
      scheduled_date: today,
      time: slot.time,
      slot_label: slot.label,
      item_id: entry.hook_id || null,
      hook_text: entry.hook || null,
      platform: 'instagram',
      format: entry.format || 'static',
      service: entry.service || 'Practice',
      status: 'planned',
      cta: entry.cta || 'Link in bio · Book your session',
      objective: entry.objective || 'awareness',
    });
    slotIdx++;
  });

  // ── Fill remaining slots with approved items ──────────────────────
  const remainingSlots = DAY_SLOTS.length - (slotIdx % DAY_SLOTS.length);
  approvedItems.slice(0, remainingSlots).forEach(item => {
    const slot = DAY_SLOTS[slotIdx % DAY_SLOTS.length];
    boardEntries.push({
      slot_id: `slot-${uid()}`,
      schema: 'https://clawdia.io/agents/schedule-captain/v1',
      generated: new Date().toISOString(),
      scheduled_date: today,
      time: slot.time,
      slot_label: slot.label,
      item_id: item.item_id,
      hook_text: item.hook_text || null,
      platform: 'instagram',
      format: 'static',
      service: item.service || 'Practice',
      status: 'approved_fill',
      objective: item.objective || 'awareness',
    });
    slotIdx++;
  });

  // ── Balance check ────────────────────────────────────────────────
  const serviceCounts = {};
  const formatCounts  = {};
  boardEntries.forEach(e => {
    serviceCounts[e.service] = (serviceCounts[e.service] || 0) + 1;
    formatCounts[e.format]  = (formatCounts[e.format]  || 0) + 1;
  });

  const balanceIssues = [];
  SERVICE_BUCKETS.forEach(svc => {
    if (!serviceCounts[svc]) balanceIssues.push(`${svc}: no items scheduled today`);
  });

  // ── Tomorrow's slots ──────────────────────────────────────────────
  const tomorrowSlots = DAY_SLOTS.map((slot, i) => ({
    slot_id: `slot-tomorrow-${uid()}`,
    schema: 'https://clawdia.io/agents/schedule-captain/v1',
    generated: new Date().toISOString(),
    scheduled_date: tomorrow,
    time: slot.time,
    slot_label: slot.label,
    status: 'open',
    fallback_pool: (approvedItems.slice(i * 2, i * 2 + 2).map(item => ({
      item_id: item.item_id,
      hook_text: item.hook_text || null,
      format: 'static',
      service: item.service || 'Practice',
    }))),
  }));

  // ── Fallback substitution log ────────────────────────────────────
  const fallbacks = (fallbQ.queue || fallbQ.items || fallbQ.nudges || fallbQ.fallbacks || []);
  const usedFallbacks = fallbacks.slice(0, 2).map(f => ({
    original_item_id: null,
    fallback_item_id: f.item_id || f.id || null,
    reason: f.reason || f.type || 'no_approved_item',
    timestamp: new Date().toISOString(),
  }));

  // ── Write outputs ─────────────────────────────────────────────────
  const board = {
    schema: 'https://clawdia.io/agents/schedule-captain/v1',
    generated: new Date().toISOString(),
    date: today,
    total_slots: boardEntries.length,
    filled_slots: boardEntries.filter(e => e.status !== 'open').length,
    open_slots: boardEntries.filter(e => e.status === 'open').length,
    balance: { service: serviceCounts, format: formatCounts },
    balance_issues: balanceIssues,
    schedule: boardEntries,
  };

  const tomorrowOut = {
    schema: 'https://clawdia.io/agents/schedule-captain/v1',
    generated: new Date().toISOString(),
    date: tomorrow,
    total_slots: tomorrowSlots.length,
    slots: tomorrowSlots,
  };

  const rescheduleLog = {
    schema: 'https://clawdia.io/agents/schedule-captain/v1',
    generated: new Date().toISOString(),
    total_reschedules: usedFallbacks.length,
    reschedules: usedFallbacks,
  };

  fs.writeFileSync(path.join(DATA, 'schedule-board.json'), JSON.stringify(board, null, 2));
  fs.writeFileSync(path.join(DATA, 'tomorrow-slots.json'), JSON.stringify(tomorrowOut, null, 2));
  fs.writeFileSync(path.join(DATA, 'reschedule-log.json'), JSON.stringify(rescheduleLog, null, 2));

  console.log(`✅ Schedule Captain: today ${boardEntries.length} slots filled`);
  console.log(`   Balance — Services: ${JSON.stringify(serviceCounts)} | Formats: ${JSON.stringify(formatCounts)}`);
  console.log(`   Tomorrow: ${tomorrowSlots.length} open slots`);
  console.log(`   Reschedules: ${usedFallbacks.length}`);
  if (balanceIssues.length > 0) console.log(`   ⚠️  Balance gaps: ${balanceIssues.join(', ')}`);
}

module.exports = { run };
if (require.main === module) run();
