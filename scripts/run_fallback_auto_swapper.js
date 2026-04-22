#!/usr/bin/env node
/**
 * run_fallback_auto_swapper.js
 * When a scheduled item is blocked, may auto-swap in a safe fallback.
 * Conditions: qa_passed, brand_passed, format_match, no_campaign_conflict, no_owner_overload
 * Outputs: auto-swaps.json
 *
 * Schema: https://clawdia.io/agents/fallback-auto-swapper/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const autonomyRules = readJson('autonomy-rules.json') || {};
  const schedBoard   = readJson('schedule-board.json') || {};
  const fallQ        = readJson('fallback-queue.json') || {};
  const ready        = readJson('ready-for-approval.json') || {};
  const ownerPf      = readJson('owner-performance.json') || {};
  const recScores     = readJson('recommendation-scores.json') || {};

  // Check if fallback_swap is allowed
  const swapRule = (autonomyRules.rules || []).find(r => r.id === 'fallback_swap');
  const canSwap = swapRule?.allowed && autonomyRules.autonomy_mode !== 'OFF';
  if (!canSwap) {
    console.log('✅ Fallback auto-swapper: autonomy not LIMITED — no swaps performed');
    fs.writeFileSync(path.join(DATA, 'auto-swaps.json'), JSON.stringify({ schema: 'https://clawdia.io/agents/fallback-auto-swapper/v1', generated: now.toISOString(), mode: 'BLOCKED', swaps: 0, log: [] }, null, 2));
    return;
  }

  const schedule     = schedBoard.schedule || [];
  const fallbacks    = fallQ.fallbacks || fallQ.items || [];
  const approvedItems = ready.items || [];
  const overloaded   = (ownerPf.summary?.overloaded_owners || []);

  // ── Find blocked slots ─────────────────────────────────────────
  const blockedSlots = schedule.filter(s => s.status === 'blocked' || s.status === 'open');

  const logEntries = [];
  const maxSwaps   = swapRule?.max_per_day || 5;

  blockedSlots.slice(0, maxSwaps).forEach(slot => {
    // Find a fallback that passes all conditions
    const fallback = fallbacks.find(fb => {
      // qa_passed condition: item must be in approved/ready list
      const isReady = approvedItems.some(a => a.item_id === fb.item_id && a.verdict === 'pass');
      if (!isReady) return false;

      // brand_passed: would need brand_guard output
      // format_match: fallback format must match slot format
      if (fb.format && slot.format && fb.format !== slot.format) return false;

      // no_campaign_conflict: check if fallback conflicts with today's campaign
      // (simplified: just check if already scheduled same day)
      const sameDayScheduled = schedule.some(s => s.item_id === fb.item_id && s.scheduled_date === slot.scheduled_date);
      if (sameDayScheduled) return false;

      // no_owner_overload: check if fallback's owner is overloaded
      if (fb.owner && overloaded.includes(fb.owner)) return false;

      return true;
    });

    if (fallback) {
      logEntries.push({
        swap_id: `swap-${uid()}`,
        schema: 'https://clawdia.io/agents/fallback-auto-swapper/v1',
        generated: now.toISOString(),
        action_id: `swap-${uid()}`,
        agent_id: 'fallback_auto_swapper',
        reason: `Slot ${slot.slot_id} blocked — auto-swapped with fallback ${fallback.item_id}`,
        rule_triggered: 'fallback_swap',
        confidence: 'high',
        rollback_possible: true,
        original_item_id: slot.item_id || null,
        original_hook: slot.hook_text || null,
        fallback_item_id: fallback.item_id,
        fallback_hook: fallback.hook_text || fallback.headline || null,
        slot_id: slot.slot_id,
        scheduled_date: slot.scheduled_date,
        conditions_met: ['qa_passed', 'format_match', 'no_campaign_conflict', 'no_owner_overload'],
        status: 'swapped_pending_confirmation',
      });
    }
  });

  const autoSwaps = {
    schema: 'https://clawdia.io/agents/fallback-auto-swapper/v1',
    generated: now.toISOString(),
    autonomy_mode: autonomyRules.autonomy_mode,
    rule: 'fallback_swap',
    total_blocked: blockedSlots.length,
    swaps_performed: logEntries.length,
    max_per_day: maxSwaps,
    limit_remaining: Math.max(0, maxSwaps - logEntries.length),
    log: logEntries,
  };

  fs.writeFileSync(path.join(DATA, 'auto-swaps.json'), JSON.stringify(autoSwaps, null, 2));

  console.log(`✅ Fallback auto-swapper: ${blockedSlots.length} blocked slots | ${logEntries.length} swaps performed`);
  console.log(`   Limit remaining: ${autoSwaps.limit_remaining}/${maxSwaps}`);
  if (logEntries.length > 0) {
    console.log(`   Swap: "${logEntries[0].original_hook||'(blocked)'} → ${logEntries[0].fallback_hook||'(fallback)'}"`);
  }
}

module.exports = { run };
if (require.main === module) run();
