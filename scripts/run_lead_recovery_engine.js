#!/usr/bin/env node
/**
 * run_lead_recovery_engine.js
 * Detect booking-intent visitors who did not convert. Map lost demand by page/service/CTA gap.
 * Outputs: lead-recovery.json
 * Schema: https://clawdia.io/agents/lead-recovery-engine/v1
 */
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const funnel = readJson('funnel-leaks.json') || {};
  const missed = readJson('missed-opportunities.json') || {};
  const recSc  = readJson('recommendation-scores.json') || {};
  const convAttr = readJson('conversion-attribution.json') || {};
  const ig     = readJson('ig-analytics.json') || {};
  const webIns = readJson('website-insights.json') || {};
  const recOut = readJson('recommendation-outcomes.json') || {};

  // Leak types
  const leaks = funnel.leaks || missed.by_category?.critical || missed.by_severity?.high || [];

  // Services
  const services = ['Club Fitting', 'Coaching', 'Practice', 'Social Play'];

  // Recovery actions per leak type
  const recoveryMap = {
    booking_drop: { action: 'retargeting_nudge', urgency: 'high', owner: 'clawdia' },
    cta_gap: { action: 'cta_test', urgency: 'medium', owner: 'clawdia' },
    pricing: { action: 'price_clarity_post', urgency: 'medium', owner: 'clawdia' },
    awareness: { action: 'booking_reminder_post', urgency: 'medium', owner: 'clawdia' },
    intent_signal: { action: 'personalised_outreach', urgency: 'high', owner: 'clawdia' },
  };

  const recoveries = [];

  // Process leaks
  leaks.slice(0, 10).forEach((leak, i) => {
    const type = leak.type || leak.leak_type || 'booking_drop';
    const rec = recoveryMap[type] || { action: 'investigate', urgency: 'low', owner: 'clawdia' };
    const service = leak.service || services[i % services.length];
    const intent = leak.lost_sessions || leak.visitors || leak.estimated_value || 0;
    recoveries.push({
      recovery_id: `lr-${uid()}`,
      schema: 'https://clawdia.io/agents/lead-recovery-engine/v1',
      generated: now.toISOString(),
      service,
      leak_type: type,
      leak_description: leak.description || leak.reason || JSON.stringify(leak).substring(0, 100),
      likely_lost_intent: intent,
      recovery_action: rec.action,
      urgency: rec.urgency,
      owner: rec.owner,
      evidence: leak.evidence || leak.source || 'funnel-leaks',
      page: leak.page || null,
      cta_gap: leak.cta_gap || null,
      estimated_recovery_potential: typeof intent === 'number' && intent > 0 ? Math.round(intent * 0.15) : null,
    });
  });

  // Sort by urgency then lost intent
  const urgencyOrder = { high: 0, medium: 1, low: 2 };
  recoveries.sort((a, b) => {
    const uDiff = urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
    if (uDiff !== 0) return uDiff;
    return (b.likely_lost_intent || 0) - (a.likely_lost_intent || 0);
  });

  // Top recovery
  const top = recoveries[0] || {};
  const highCount = recoveries.filter(r => r.urgency === 'high').length;
  const totalIntent = recoveries.reduce((s, r) => s + (r.likely_lost_intent || 0), 0);

  const leadRecovery = {
    schema: 'https://clawdia.io/agents/lead-recovery-engine/v1',
    generated: now.toISOString(),
    summary: {
      total_recoveries: recoveries.length,
      high_urgency: highCount,
      estimated_total_lost_intent: totalIntent,
      top_leak: top.leak_type || null,
      top_recovery_action: top.recovery_action || null,
      top_service: top.service || null,
    },
    recoveries,
  };

  fs.writeFileSync(path.join(DATA, 'lead-recovery.json'), JSON.stringify(leadRecovery, null, 2));
  console.log('✅ Lead recovery engine: ' + recoveries.length + ' recovery items');
  console.log('   High urgency: ' + highCount + ' | Total lost intent: ' + totalIntent);
  if (top.leak_type) console.log('   Top leak: ' + top.leak_type + ' → ' + top.recovery_action + ' (' + top.urgency + ')');
}

run();
