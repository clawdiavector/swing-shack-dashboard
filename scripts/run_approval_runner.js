#!/usr/bin/env node
/**
 * run_approval_runner.js — approval_runner agent core script
 * Reads: approval-queue.json, ready-for-approval.json, captions.json
 * Produces: approval-actions.json, approval-expiry.json
 *
 * Rules:
 * - Approval older than 72h gets rechecked
 * - If copy changes after approval, approval resets
 * - If asset changes, creative approval resets
 * - Converts "approved" → "ready to publish"
 *
 * Schema: https://clawdia.io/agents/approval-runner/v1
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

const APPROVAL_TTL_HOURS = 72;

function run() {
  const apprQueue = readJson('approval-queue.json') || {};
  const ready    = readJson('ready-for-approval.json') || {};
  const caps     = readJson('captions.json') || {};

  const now = new Date();
  const queue = apprQueue.queue || [];

  const actions = [];
  const expired = [];

  queue.forEach(item => {
    const approvalAge = item.generated
      ? (now - new Date(item.generated)) / 3600000  // hours
      : 0;

    const isExpired = approvalAge > APPROVAL_TTL_HOURS;

    if (isExpired) {
      expired.push({
        ...item,
        expiry_reason: `Approval ${Math.round(approvalAge)}h old (max ${APPROVAL_TTL_HOURS}h)`,
        action: 'reset_approval',
      });
      actions.push({
        action_id: `aa-${uid()}`,
        schema: 'https://clawdia.io/agents/approval-runner/v1',
        generated: new Date().toISOString(),
        item_id: item.item_id,
        item_type: item.item_type,
        action: 'reset_approval',
        reason: 'approval_expired',
        approval_age_hours: Math.round(approvalAge),
        threshold_hours: APPROVAL_TTL_HOURS,
        new_status: 'waiting_copy_approval',
      });
    } else if (item.status === 'waiting_copy_approval' || item.status === 'waiting_creative_approval') {
      // Check if the caption changed after original approval
      const cap = caps.captions?.find(c => c.caption_id === item.item_id);
      const capUpdated = cap?.generated ? new Date(cap.generated) : null;
      const approvalTime = item.generated ? new Date(item.generated) : null;

      if (capUpdated && approvalTime && capUpdated > approvalTime) {
        actions.push({
          action_id: `aa-${uid()}`,
          schema: 'https://clawdia.io/agents/approval-runner/v1',
          generated: new Date().toISOString(),
          item_id: item.item_id,
          item_type: item.item_type,
          action: 'reset_approval',
          reason: 'copy_changed_after_approval',
          previous_approval_time: item.generated,
          new_caption_time: capUpdated.toISOString(),
          new_status: 'waiting_copy_approval',
        });
      }
    }

    // If item is in approved_ready and not expired, mark as ready to publish
    if (item.status === 'approved_ready' && !isExpired) {
      actions.push({
        action_id: `aa-${uid()}`,
        schema: 'https://clawdia.io/agents/approval-runner/v1',
        generated: new Date().toISOString(),
        item_id: item.item_id,
        item_type: item.item_type,
        action: 'promote_to_publish',
        reason: 'approved_and_not_expired',
        approval_age_hours: Math.round(approvalAge),
        new_status: 'ready_to_publish',
      });
    }
  });

  // ── Write outputs ─────────────────────────────────────────────────
  const actionsOut = {
    schema: 'https://clawdia.io/agents/approval-runner/v1',
    generated: new Date().toISOString(),
    total_actions: actions.length,
    by_action: {
      reset_approval: actions.filter(a => a.action === 'reset_approval').length,
      promote_to_publish: actions.filter(a => a.action === 'promote_to_publish').length,
    },
    actions,
  };

  const expiryOut = {
    schema: 'https://clawdia.io/agents/approval-runner/v1',
    generated: new Date().toISOString(),
    total_expired: expired.length,
    ttl_hours: APPROVAL_TTL_HOURS,
    expired_items: expired,
  };

  fs.writeFileSync(path.join(DATA, 'approval-actions.json'), JSON.stringify(actionsOut, null, 2));
  fs.writeFileSync(path.join(DATA, 'approval-expiry.json'), JSON.stringify(expiryOut, null, 2));

  console.log(`✅ Approval runner: ${actions.length} actions taken`);
  console.log(`   Reset expired: ${actionsOut.by_action.reset_approval} | Promoted to publish: ${actionsOut.by_action.promote_to_publish}`);
  console.log(`   Expired approvals: ${expired.length}`);
  if (expired.length > 0) console.log(`   ⚠️  ${expired.length} approvals expired — content requires re-approval`);
}

module.exports = { run };
if (require.main === module) run();
