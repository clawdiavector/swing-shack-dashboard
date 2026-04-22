#!/usr/bin/env node
/**
 * run_approval_captain.js — approval_captain agent core script
 * Reads: ready-for-approval.json, qa-failures.json, post-plan.json
 * Produces: approval-queue.json, approval-summary.json
 *
 * Schema: https://clawdia.io/agents/approval-captain/v1
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
  const ready   = readJson('ready-for-approval.json') || {};
  const failures = readJson('qa-failures.json') || {};
  const plan    = readJson('post-plan.json') || {};
  const caps    = readJson('captions.json') || {};
  const vb      = readJson('visual-briefs.json') || {};

  // ── Categorise by what they're waiting on ─────────────────────────
  const waiting_copy = [];      // captions waiting for copy approval
  const waiting_creative = []; // visual briefs / prompts waiting for creative signoff
  const waiting_pricing = [];   // anything with pricing / offer confirmation needed
  const approved_ready = [];    // passed QA, ready to schedule
  const blocked = [];           // failed QA, needs fix first

  // Approved items (passed QA)
  (ready.items || []).forEach(item => {
    if (item.item_type === 'caption' || item.item_type === 'caption_variant') {
      const cap = caps.captions?.find(c => c.caption_id === item.item_id);
      waiting_copy.push({
        approval_id: `ap-${uid()}`,
        schema: 'https://clawdia.io/agents/approval-captain/v1',
        generated: new Date().toISOString(),
        item_id: item.item_id,
        item_type: item.item_type,
        linked_blueprint_id: item.linked_blueprint_id,
        status: 'waiting_copy_approval',
        priority: 'normal',
        hook_text: cap?.hook_text || item.hook_text || null,
        caption_preview: cap?.short_caption?.substring(0, 80) || null,
        qa_verdict: 'pass',
        days_in_queue: 0,
        owner: 'approval_captain',
      });
    } else if (item.item_type === 'image_prompt' || item.item_type === 'visual_brief') {
      const brief = vb.briefs?.find(b => b.brief_id === item.item_id);
      waiting_creative.push({
        approval_id: `ap-${uid()}`,
        schema: 'https://clawdia.io/agents/approval-captain/v1',
        generated: new Date().toISOString(),
        item_id: item.item_id,
        item_type: item.item_type,
        linked_blueprint_id: item.linked_blueprint_id,
        status: 'waiting_creative_approval',
        priority: 'normal',
        format: brief?.format_type || item.format_type || null,
        qa_verdict: 'pass',
        days_in_queue: 0,
        owner: 'approval_captain',
      });
    } else {
      // Blog drafts and reddit replies — default to copy approval
      waiting_copy.push({
        approval_id: `ap-${uid()}`,
        schema: 'https://clawdia.io/agents/approval-captain/v1',
        generated: new Date().toISOString(),
        item_id: item.item_id,
        item_type: item.item_type,
        status: 'waiting_copy_approval',
        priority: 'normal',
        qa_verdict: 'pass',
        days_in_queue: 0,
        owner: 'approval_captain',
      });
    }
  });

  // Blocked items (failed QA)
  (failures.failures || []).forEach(item => {
    blocked.push({
      approval_id: `ap-${uid()}`,
      schema: 'https://clawdia.io/agents/approval-captain/v1',
      generated: new Date().toISOString(),
      item_id: item.item_id,
      item_type: item.item_type,
      status: 'blocked_qa_fail',
      priority: item.verdict === 'reject' ? 'high' : 'normal',
      issues: item.issues,
      fix_required: item.issues?.map(i => i.msg).join('; ') || 'See qa-failures.json',
      qa_verdict: item.verdict,
      owner: 'approval_captain',
    });
  });

  // Check post plan for already-scheduled items
  const scheduledHooks = (plan.plan || []).map(p => p.hook_id || p.hook).filter(Boolean);
  waiting_copy.forEach(item => {
    if (scheduledHooks.includes(item.linked_blueprint_id) || scheduledHooks.includes(item.hook_text)) {
      item.already_scheduled = true;
      item.status = 'scheduled';
    }
  });

  // Prioritise: high priority = recently failed reject, high engagement signals
  waiting_copy.sort((a, b) => {
    if (a.priority === 'high' && b.priority !== 'high') return -1;
    if (b.priority === 'high' && a.priority !== 'high') return 1;
    return 0;
  });
  blocked.sort((a, b) => {
    if (a.priority === 'high' && b.priority !== 'high') return -1;
    if (b.priority === 'high' && a.priority !== 'high') return 1;
    return 0;
  });

  const allItems = [...waiting_copy, ...waiting_creative, ...waiting_pricing, ...approved_ready, ...blocked];

  const approvalQueue = {
    schema: 'https://clawdia.io/agents/approval-captain/v1',
    generated: new Date().toISOString(),
    total: allItems.length,
    categories: {
      waiting_copy: waiting_copy.length,
      waiting_creative: waiting_creative.length,
      waiting_pricing: waiting_pricing.length,
      approved_ready: approved_ready.length,
      blocked: blocked.length,
    },
    queue: allItems,
    high_priority_count: allItems.filter(i => i.priority === 'high').length,
  };

  const summary = {
    schema: 'https://clawdia.io/agents/approval-captain/v1',
    generated: new Date().toISOString(),
    total_items: allItems.length,
    actionable: waiting_copy.length + waiting_creative.length,
    blocked: blocked.length,
    approved_and_ready: approved_ready.length,
    high_priority: approvalQueue.high_priority_count,
    top_blocked_issue: blocked.length > 0
      ? blocked[0].fix_required
      : null,
    message: blocked.length > 0
      ? `${blocked.length} item(s) blocked by QA failures — fix before approval`
      : `${allItems.length} item(s) in approval queue — awaiting signoff`,
  };

  fs.writeFileSync(path.join(DATA, 'approval-queue.json'), JSON.stringify(approvalQueue, null, 2));
  fs.writeFileSync(path.join(DATA, 'approval-summary.json'), JSON.stringify(summary, null, 2));

  console.log(`✅ Approval queue: ${allItems.length} items`);
  console.log(`   Waiting copy: ${waiting_copy.length} | Waiting creative: ${waiting_creative.length} | Blocked: ${blocked.length}`);
  console.log(`   High priority: ${approvalQueue.high_priority_count}`);
  if (blocked.length > 0) console.log(`   ⚠️  Top blocked: "${blocked[0].fix_required}"`);
}

module.exports = { run };
if (require.main === module) run();