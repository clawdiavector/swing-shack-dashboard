#!/usr/bin/env node
/**
 * generate_suppression_rules.js
 * Rules to prevent spammy, noisy, or redundant automations.
 * Output: data/suppression-rules.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'suppression-rules.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const nudgeQueue = readJson('nudge-queue.json') || {};
const tasks     = readJson('daily-task-cards.json') || {};

function uid() { return 'spr_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const now = Date.now();
const today = new Date(now).toISOString().split('T')[0];
const tomorrow = new Date(now + 86400000).toISOString().split('T')[0];

// ── Built-in suppression rules ─────────────────────────────────
// These are the rules that govern when NOT to send

const rules = [
  {
    rule_id:      uid(),
    type:        'already_done',
    name:        'Task already done',
    description: 'Suppress nudge if the related task is marked done or scheduled',
    condition:   'task.status === "done" || task.status === "scheduled"',
    action:     'suppress',
    severity:   'high',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'duplicate_nudge',
    name:        'Duplicate nudge within 24h',
    description: 'Do not send the same nudge type to the same owner within 24 hours',
    condition:   'same_owner && same_type && last_sent_within_24h',
    action:     'suppress',
    window_hours: 24,
    severity:   'high',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'spam_owner',
    name:        'Max 3 nudges per owner per day',
    description: 'Never send more than 3 nudges to the same owner in a single day',
    condition:   'nudge_count_for_owner_today >= 3',
    action:     'suppress_low_priority',
    max_per_day: 3,
    severity:   'medium',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'low_priority_spam',
    name:        'Suppress low-priority during overload',
    description: 'When an owner is overloaded (5+ tasks), suppress low-severity nudges',
    condition:   'owner_task_count >= 5 && nudge.severity === "low"',
    action:     'suppress',
    threshold:  5,
    severity:   'medium',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'weekend_grace',
    name:        'No nudges on weekends',
    description: 'Suppress all nudges on Saturday and Sunday',
    condition:   'day === "Saturday" || day === "Sunday"',
    action:     'defer_to_monday',
    severity:   'low',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'approval_already_requested',
    name:        'Approval already requested',
    description: 'Suppress approval reminder if it was already sent today',
    condition:   'same_item && type === "approval_reminder" && sent_today',
    action:     'suppress',
    severity:   'high',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'task_not_due',
    name:        'Only nudge on the due day',
    description: 'Suppress reminder if the task is not due today or tomorrow',
    condition:   'task.due_date !== today && task.due_date !== tomorrow',
    action:     'defer',
    severity:   'low',
    active:     true,
  },
  {
    rule_id:      uid(),
    type:        'fallback_exists',
    name:        'Fallback available — no asset nudge needed',
    description: 'If a fallback exists for a blocked post, suppress asset nudge and send fallback instead',
    condition:   'fallback_available && nudge.type === "asset_reminder"',
    action:     'swap_to_fallback',
    severity:   'high',
    active:     true,
  },
];

// ── Apply suppression to current nudge queue ───────────────────
const nudges = nudgeQueue.nudges || [];
const tasksList = tasks.all_tasks || [];

// Count nudges per owner today
const nudgeCountByOwner = {};
nudges.filter(n => n.status === 'sent').forEach(n => {
  nudgeCountByOwner[n.owner] = (nudgeCountByOwner[n.owner] || 0) + 1;
});

// Task count per owner
const taskCountByOwner = {};
tasksList.forEach(t => { taskCountByOwner[t.owner] = (taskCountByOwner[t.owner] || 0) + 1; });

const suppressedNudges = [];
const appliedRules   = [];

nudges.filter(n => n.status === 'ready').forEach(n => {
  const task = tasksList.find(t => t.task_id === n.related_task_id);
  const day = new Date(now).getDay();
  const dayName = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][day];

  let suppressed = false;
  let appliedRule = null;

  for (const rule of rules) {
    if (!rule.active) continue;

    let triggered = false;
    if (rule.type === 'already_done' && task && (task.status === 'done' || task.status === 'scheduled')) triggered = true;
    if (rule.type === 'spam_owner' && (nudgeCountByOwner[n.owner] || 0) >= (rule.max_per_day || 3)) triggered = true;
    if (rule.type === 'low_priority_spam' && (taskCountByOwner[n.owner] || 0) >= (rule.threshold || 5) && n.severity === 'low') triggered = true;
    if (rule.type === 'weekend_grace' && (dayName === 'Saturday' || dayName === 'Sunday')) triggered = true;
    if (rule.type === 'task_not_due' && task && task.due_date !== today && task.due_date !== tomorrow) triggered = true;

    if (triggered) {
      suppressed = rule.action === 'suppress';
      appliedRule = rule;
      break;
    }
  }

  if (suppressed) {
    suppressedNudges.push({ ...n, suppressed: true, suppressed_by: appliedRule?.rule_id, suppression_reason: appliedRule?.name });
  }
});

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_suppression_rules.js',
  summary: {
    total_rules:   rules.length,
    active_rules:  rules.filter(r => r.active).length,
    suppressed:    suppressedNudges.length,
    reasons:      Object.fromEntries(
      [...new Set(suppressedNudges.map(n => n.suppression_reason))].filter(Boolean).map(r => [r, suppressedNudges.filter(n => n.suppression_reason === r).length])
    ),
  },
  rules,
  suppressed_nudges: suppressedNudges,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Suppression rules: ${OUTPUT}`);
console.log(`   Rules: ${rules.length} active | Suppressed: ${suppressedNudges.length}`);
if (suppressedNudges.length > 0) {
  console.log(`   Suppressed:`);
  suppressedNudges.forEach(n => console.log(`   \u2192 ${n.owner}: ${n.type} — ${n.suppression_reason}`));
}
