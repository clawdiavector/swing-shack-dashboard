#!/usr/bin/env node
/**
 * generate_delivery_audit.js
 * Audit log: sent / skipped / suppressed / failed / duplicates_prevented
 * Output: data/delivery-audit.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'delivery-audit.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const deliveries = readJson('discord-deliveries.json') || {};
const supprRul  = readJson('suppression-rules.json')    || {};
const fallbQ    = readJson('fallback-queue.json')        || {};

const now   = new Date().toISOString();
const today = now.split('T')[0];

const log     = deliveries.deliveries || [];
const todayLog = log.filter(d => d.sent_at && d.sent_at.split('T')[0] === today);

// SENT
const sent = todayLog.filter(d =>
  d.delivery_status === 'sent' || d.decision === 'send' || d.decision === 'fallback_swap'
).map(d => ({
  delivery_id:    d.delivery_id,
  nudge_id:       d.nudge_id,
  type:           d.type,
  owner:          d.owner,
  channel:        d.channel,
  severity:       d.severity,
  sent_at:        d.sent_at,
  fallback_used:  !!d.fallback_used,
  message_preview: d.message_preview,
}));

// SKIPPED (not high severity / not in send window)
const skipped = todayLog.filter(d => d.decision === 'skip').map(d => ({
  nudge_id: d.nudge_id, type: d.type, owner: d.owner, reason: d.suppressed_reason || 'not_high_severity'
}));

// SUPPRESSED (rule blocked)
const suppressed = todayLog.filter(d =>
  d.decision === 'suppress' || d.decision === 'suppress_low_priority' || d.delivery_status === 'suppressed'
).map(d => ({
  nudge_id: d.nudge_id, type: d.type, owner: d.owner, severity: d.severity,
  suppression_reason: d.suppressed_reason || 'unknown', fallback_used: !!d.fallback_used
}));

// FAILED
const failed = todayLog.filter(d => d.decision === 'failed' || d.delivery_status === 'failed').map(d => ({
  delivery_id: d.delivery_id, nudge_id: d.nudge_id, type: d.type, owner: d.owner, error: d.error || 'unknown'
}));

// DUPLICATES PREVENTED — nudge_ids that appear more than once today
const dupMap = {};
todayLog.forEach(d => { if (d.nudge_id) dupMap[d.nudge_id] = (dupMap[d.nudge_id] || 0) + 1; });
const dp = Object.entries(dupMap).filter(([,c]) => c > 1).map(([nudge_id, occ]) => ({ nudge_id, occurrences: occ }));

// DRY RUN count
const dryRunCount = todayLog.filter(d => d.DRY_MODE === true || d.delivery_status === 'dry_run').length;

// By-owner
const byOwner = {};
todayLog.forEach(d => {
  if (!byOwner[d.owner]) byOwner[d.owner] = { sent: 0, suppressed: 0, skipped: 0, failed: 0 };
  if (d.decision === 'send' || d.decision === 'fallback_swap' || d.delivery_status === 'sent') byOwner[d.owner].sent++;
  else if (d.decision === 'suppress' || d.decision === 'suppress_low_priority') byOwner[d.owner].suppressed++;
  else if (d.decision === 'skip') byOwner[d.owner].skipped++;
  else if (d.decision === 'failed') byOwner[d.owner].failed++;
});

// Rule effectiveness
const ruleHits = {};
(supprRul.rules || []).forEach(r => {
  const hits = todayLog.filter(d => d.suppressed_reason && d.suppressed_reason.includes(r.type)).length;
  if (hits > 0) ruleHits[r.type] = hits;
});

// Fallback swaps
const fswaps = todayLog.filter(d => d.fallback_used || d.decision === 'fallback_swap' || d.decision === 'dry_run_fallback');
const fallbacksAvailable = (fallbQ.fallbacks || []).length;

const output = {
  updated:   now,
  generated: 'generate_delivery_audit.js',
  period:    { date: today, type: 'today' },
  summary: {
    total_evaluated: todayLog.length,
    sent:           sent.length,
    skipped:        skipped.length,
    suppressed:     suppressed.length,
    failed:         failed.length,
    dry_run:        dryRunCount,
    duplicates_prevented: dp.length,
    fallback_swaps: fswaps.length,
    fallbacks_available: fallbacksAvailable,
    by_owner: byOwner,
  },
  suppression_rule_effectiveness: ruleHits,
  sent,
  skipped,
  suppressed,
  failed,
  duplicates_prevented: dp,
  fallback_swaps: fswaps,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));

console.log(`✅ Delivery audit: ${OUTPUT}`);
console.log(`   Evaluated: ${todayLog.length} | Sent: ${sent.length} | Suppressed: ${suppressed.length} | Skipped: ${skipped.length} | Failed: ${failed.length}`);
if (fswaps.length > 0) console.log(`   Fallback swaps: ${fswaps.length} (${fallbacksAvailable} available)`);
if (dp.length > 0) console.log(`   Duplicates prevented: ${dp.length}`);
if (Object.keys(ruleHits).length > 0) Object.entries(ruleHits).forEach(([r,h]) => console.log(`   Rule [${r}]: ${h} hit(s)`));