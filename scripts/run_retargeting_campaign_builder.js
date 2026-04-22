#!/usr/bin/env node
/**
 * run_retargeting_campaign_builder.js
 * Package recovery actions into campaign-ready briefs — social retargeting, reminder posts, booking nudges.
 * Outputs: retargeting-campaigns.json
 * Schema: https://clawdia.io/agents/retargeting-campaign-builder/v1
 */
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const leadRec = readJson('lead-recovery.json') || {};
  const recSc   = readJson('recommendation-scores.json') || {};
  const recOut   = readJson('recommendation-outcomes.json') || {};
  const lpo      = readJson('landing-page-fixes.json') || {};

  const recoveries = leadRec.recoveries || [];
  const topHook = (recSc.summary?.top_hook || 'YOUR GAME IN NUMBERS');
  const topCTA  = (recSc.summary?.top_cta || 'Book Your Session');
  const topService = (recSc.summary?.top_service || 'Practice');

  const campaigns = [];

  // Campaign 1: Booking abandonment — "didn't book" retargeting
  if (recoveries.some(r => r.leak_type === 'booking_drop')) {
    campaigns.push({
      campaign_id: `rtc-${uid()}`,
      schema: 'https://clawdia.io/agents/retargeting-campaign-builder/v1',
      generated: now.toISOString(),
      name: 'Booking Abandonment Retargeting',
      objective: 'recover_lost_bookings',
      audience: 'visitors_who_viewed_pricing_not_booked',
      hook_type: 'urgency_reminder',
      hook: 'Still thinking about your session? Your spot is waiting.',
      caption: 'You viewed Swing Shack but didn\'t book yet. Here\'s what you get: TrackMan-powered coaching, certified instructors, indoor comfort. From R250.',
      cta: topCTA,
      landing_page: 'swingshack.co.za/book',
      platform: 'instagram',
      format: 'static',
      service: topService,
      priority: 'high',
      reason: 'Booking drop leak detected — high urgency',
    });
  }

  // Campaign 2: CTA test reminder — for low-cta pages
  if (recoveries.some(r => r.leak_type === 'cta_gap')) {
    campaigns.push({
      campaign_id: `rtc-${uid()}`,
      schema: 'https://clawdia.io/agents/retargeting-campaign-builder/v1',
      generated: now.toISOString(),
      name: 'CTA Gap Recovery',
      objective: 'cta_ctr_improvement',
      audience: 'visitors_who_left_pricing_page',
      hook_type: 'value_reminder',
      hook: topHook,
      caption: 'Your numbers are talking. TrackMan makes them impossible to ignore. Book a session and start decoding your swing.',
      cta: topCTA,
      landing_page: 'swingshack.co.za/membership',
      platform: 'instagram',
      format: 'static',
      service: 'Practice',
      priority: 'medium',
      reason: 'CTA gap detected — test new booking prompt',
    });
  }

  // Campaign 3: Service awareness — for intent visitors
  const topServiceRec = recoveries.filter(r => r.service)[0];
  if (topServiceRec) {
    campaigns.push({
      campaign_id: `rtc-${uid()}`,
      schema: 'https://clawdia.io/agents/retargeting-campaign-builder/v1',
      generated: now.toISOString(),
      name: 'Service Demand Recovery: ' + topServiceRec.service,
      objective: 'recover_service_intent',
      audience: 'visitors_interested_in_' + (topServiceRec.service || 'all_services').replace(' ', '_').toLowerCase(),
      hook_type: 'service_proof',
      hook: topServiceRec.leak_description ? topServiceRec.leak_description.substring(0, 60) : topServiceRec.service + ' — here\'s what you\'re missing.',
      caption: 'The gap between where your game is and where it could be starts with one session. ' + topServiceRec.service + ' from R250.',
      cta: topCTA,
      landing_page: 'swingshack.co.za/' + (topServiceRec.service || 'membership').toLowerCase().replace(' ', '-'),
      platform: 'instagram',
      format: 'static',
      service: topServiceRec.service,
      priority: topServiceRec.urgency || 'medium',
      reason: 'Service intent leak — ' + (topServiceRec.likely_lost_intent || 'N') + ' visitors lost',
    });
  }

  // Campaign 4: Social proof — default evergreen
  campaigns.push({
    campaign_id: `rtc-${uid()}`,
    schema: 'https://clawdia.io/agents/retargeting-campaign-builder/v1',
    generated: now.toISOString(),
    name: 'Evergreen Awareness — Social Proof',
    objective: 'build_awareness_and_trust',
    audience: 'lookalike_engaged_users',
    hook_type: 'social_proof',
    hook: 'Pros trust TrackMan. Now so can you.',
    caption: 'TrackMan is the gold standard in golf improvement. Swing Shack brings that same technology to every session. From R250.',
    cta: topCTA,
    landing_page: 'swingshack.co.za',
    platform: 'instagram',
    format: 'static',
    service: 'Practice',
    priority: 'low',
    reason: 'Evergreen — always running to maintain awareness pipeline',
  });

  const rtb = {
    schema: 'https://clawdia.io/agents/retargeting-campaign-builder/v1',
    generated: now.toISOString(),
    summary: {
      total_campaigns: campaigns.length,
      high_priority: campaigns.filter(c => c.priority === 'high').length,
      medium_priority: campaigns.filter(c => c.priority === 'medium').length,
    },
    campaigns,
  };

  fs.writeFileSync(path.join(DATA, 'retargeting-campaigns.json'), JSON.stringify(rtb, null, 2));
  console.log('✅ Retargeting campaign builder: ' + campaigns.length + ' campaigns');
  console.log('   High: ' + rtb.summary.high_priority + ' | Medium: ' + rtb.summary.medium_priority);
  campaigns.filter(c => c.priority === 'high').forEach(c => console.log('   HIGH: ' + c.name));
}

run();
