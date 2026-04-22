#!/usr/bin/env node
/**
 * run_autonomy_rules_engine.js
 * The brain for what the system is allowed to do without asking.
 * Reads: agent-scorecards.json, system-health.json, auto-messages.json
 * Produces: autonomy-rules.json, autonomy-decisions.json
 *
 * Trust thresholds:
 *   9-10  = LIMITED autonomy allowed
 *   <8    = live publish disabled
 *   <7    = all autonomy except alerts disabled
 *
 * Schema: https://clawdia.io/agents/autonomy-rules-engine/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }

function run() {
  const now = new Date().toISOString();

  const scorecard = readJson('agent-scorecards.json') || {};
  const sysHealth = readJson('system-health.json') || {};

  // ── Trust score (average of key agent scores) ────────────────────
  const trustScore = scorecard.overall_score || scorecard.trust_score || 8.0;

  // ── Determine autonomy mode ───────────────────────────────────────
  let mode = 'OFF';
  if (trustScore >= 9)      mode = 'LIMITED';
  else if (trustScore >= 8) mode = 'MINIMAL';
  else if (trustScore >= 7) mode = 'ALERTS_ONLY';

  // ── System health risk ───────────────────────────────────────────
  const healthOk = !sysHealth.alerts || sysHealth.alerts.filter(a => a.severity === 'critical').length === 0;

  // ── Define rules ─────────────────────────────────────────────────
  const rules = {
    schema: 'https://clawdia.io/agents/autonomy-rules-engine/v1',
    generated: now,
    trust_score: Math.round(trustScore * 10) / 10,
    autonomy_mode: mode,
    health_ok: healthOk,
    rules: [
      // SAFE TO AUTO
      { id: 'discord_nudge',       action: 'discord_nudge',     allowed: mode !== 'OFF',   risk: 'LOW',  channels: ['ops', 'planning'], require_approval: false, max_per_day: 20 },
      { id: 'fallback_swap',       action: 'fallback_swap',     allowed: mode === 'LIMITED', risk: 'LOW',  conditions: ['qa_passed', 'brand_passed', 'format_match', 'no_campaign_conflict'], max_per_day: 5 },
      { id: 'reschedule_blocked',   action: 'reschedule_blocked', allowed: mode === 'LIMITED', risk: 'LOW',  conditions: ['already_scheduled', 'slot_available'], max_per_day: 3 },
      { id: 'approval_promote',     action: 'approval_promote',  allowed: mode === 'LIMITED', risk: 'LOW',  conditions: ['qa_passed', 'brand_passed', 'asset_approved', 'unchanged_since_approval', 'low_risk_content'], exclusions: ['price', 'promo_code', 'event_promise', 'legal'], max_per_day: 10 },
      { id: 'story_post',          action: 'story_post',        allowed: false,            risk: 'MEDIUM', reason: 'Not yet enabled' },
      { id: 'evergreen_reminder',  action: 'evergreen_reminder', allowed: mode === 'LIMITED', risk: 'LOW', conditions: ['evergreen_content', 'no_pricing', 'no_promo'], max_per_day: 3 },
      { id: 'approved_repost',     action: 'approved_repost',   allowed: false,            risk: 'MEDIUM', reason: 'Requires manual review first' },

      // NOT SAFE YET
      { id: 'high_stakes_promo',   action: 'high_stakes_promo', allowed: false, risk: 'HIGH',   reason: 'Requires human review' },
      { id: 'reddit_post',         action: 'reddit_post',        allowed: false, risk: 'HIGH',   reason: 'Requires manual review' },
      { id: 'blog_publish',        action: 'blog_publish',       allowed: false, risk: 'HIGH',   reason: 'Requires QA pass + brand pass + manual approval' },
      { id: 'ad_budget_change',   action: 'ad_budget_change',  allowed: false, risk: 'CRITICAL', reason: 'Never autonomous' },
      { id: 'gmb_reply',          action: 'gmb_reply',          allowed: false, risk: 'HIGH',   reason: 'Requires manual review' },
      { id: 'price_promo',        action: 'price_promo',        allowed: false, risk: 'HIGH',   reason: 'Never autonomous — pricing risk' },
    ]
  };

  // ── Autonomous decisions log ─────────────────────────────────────
  const decisions = {
    schema: 'https://clawdia.io/agents/autonomy-rules-engine/v1',
    generated: now,
    mode,
    trust_score: rules.trust_score,
    health_ok: healthOk,
    allowed_actions: rules.rules.filter(r => r.allowed).map(r => r.id),
    blocked_actions: rules.rules.filter(r => !r.allowed).map(r => r.id),
    decisions: [
      {
        decision_id: 'mode_decision',
        action: 'determine_autonomy_mode',
        result: mode,
        reason: `Trust score ${trustScore.toFixed(1)} → mode ${mode}`,
        timestamp: now,
      }
    ]
  };

  // ── Write outputs ───────────────────────────────────────────────
  fs.writeFileSync(path.join(DATA, 'autonomy-rules.json'), JSON.stringify(rules, null, 2));
  fs.writeFileSync(path.join(DATA, 'autonomy-decisions.json'), JSON.stringify(decisions, null, 2));

  console.log(`✅ Autonomy rules engine: trust=${trustScore.toFixed(1)} | mode=${mode} | health=${healthOk?'OK':'DEGRADED'}`);
  console.log(`   Allowed: ${rules.rules.filter(r=>r.allowed).length} | Blocked: ${rules.rules.filter(r=>!r.allowed).length}`);
  rules.rules.filter(r=>r.allowed).forEach(r => console.log(`   ✅ ${r.id} (risk: ${r.risk})`));
  rules.rules.filter(r=>!r.allowed && r.risk !== 'LOW').forEach(r => console.log(`   ❌ ${r.id}: ${r.reason||'not enabled'}`));
}

module.exports = { run };
if (require.main === module) run();
