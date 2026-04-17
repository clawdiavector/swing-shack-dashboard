#!/usr/bin/env node
/**
 * generate_retargeting_recommendations.js
 * Turns detected funnel leaks and high-intent signals into actionable
 * retargeting content with channel, outcome, expiration and evidence.
 * Output: data/retargeting-recommendations.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'retargeting-recommendations.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const leaks    = readJson('funnel-leaks.json')          || {};
const conv     = readJson('conversion-attribution.json') || {};
const ig      = readJson('ig-analytics.json')           || {};
const plan    = readJson('post-plan.json')              || {};
const sales   = readJson('sales-priority.json')        || {};
const missed  = readJson('missed-opportunities.json')  || {};
const ctaPerf = readJson('cta-performance.json')        || {};

const igPosts     = ig.posts || [];
const plannedHooks = new Set((plan.plan || []).map(p => p.hook?.toLowerCase().substring(0, 40)));

// ── 1. RETARGET EXISTING POSTS ──────────────────────────────────
const followUpGaps = (missed.opportunities || [])
  .filter(o => o.category === 'follow_up_gap' && (o.ig_score || 0) >= 7)
  .slice(0, 4)
  .map(o => {
    const topicKw  = o.topic || '';
    const score    = o.ig_score || 0;
    const alreadyPlanned = Array.from(plannedHooks).some(h =>
      (o.hook || '').toLowerCase().substring(0, 40).includes(h.substring(0, 20))
    );
    const channel = topicKw.includes('lesson') || topicKw.includes('putt') || topicKw.includes('short') ? 'IG Reel' : 'IG Static';
    const expDays = score >= 9 ? 'today' : score >= 8 ? '48h' : 'this_week';
    return {
      type:              'retarget_existing',
      action:            'Re-run with booking CTA',
      topic:             topicKw,
      original_hook:      o.hook,
      original_score:     score,
      suggested_hook:     buildRetargetHook(o),
      suggested_cta:      'Book your session \u00b7 swingshack.co.za/membership',
      format:            channel === 'IG Reel' ? 'reel' : 'static',
      channel,
      expected_outcome:   { type: 'bookings', delta: '+15-25%', label: '+15-25% bookings vs. no CTA' },
      expiration_window: expDays,
      source_evidence:    `Hook scored ${score} on IG but no booking follow-up exists`,
      urgency:            score >= 9 ? 'today' : 'this_week',
      owner:              o.owner || 'Coach Cat',
      why:                `IG score ${score} with no conversion CTA in follow-up`,
      already_planned:    alreadyPlanned,
    };
  });

// ── 2. ADD BOOKING CTA ──────────────────────────────────────────
const saveGaps = (leaks.leaks || [])
  .filter(l => l.type === 'high_save_no_booking_cta' && !l.has_booking_cta)
  .slice(0, 3)
  .map(l => {
    const saveRate = l.save_rate || 0;
    const saves    = l.saves || 0;
    const channel  = saveRate > 4 ? 'IG Story' : 'IG Caption update';
    return {
      type:              'add_booking_cta',
      action:            'Add booking CTA to high-save content',
      post_id:           l.post_id,
      reach:             l.reach,
      saves:             saves,
      save_rate:         saveRate,
      caption_preview:   l.caption_preview,
      suggested_hook:    null,
      suggested_cta:     'Ready to fix your game? Book a session \u2192 swingshack.co.za/membership',
      format:            'caption_update',
      channel,
      expected_outcome:  { type: 'clicks', delta: '+8-12%', label: '+8-12% link clicks from saves' },
      expiration_window: saves > 10 ? 'today' : '48h',
      source_evidence:   `${saves} saves (${saveRate}%) but no booking path`,
      urgency:           saveRate > 5 ? 'today' : 'this_week',
      owner:             'Swing Shack page',
      why:               `${saves} saves leaking without a booking path`,
    };
  });

// ── 3. SERVICE REMINDER POSTS ───────────────────────────────────
const serviceReminders = (leaks.leaks || [])
  .filter(l => l.type === 'service_page_no_ig')
  .slice(0, 3)
  .map(l => {
    const sessions = l.sessions || 0;
    const expDays  = sessions > 80 ? 'today' : sessions > 40 ? '48h' : 'this_week';
    const svcMap   = { 'Golf Lessons': 'IG Reel', 'Club Fitting': 'IG Static', 'Simulator': 'IG Story', 'Membership': 'IG Static', 'Events': 'IG Static' };
    return {
      type:              'new_service_reminder',
      action:            'Publish service reminder post',
      service:           l.service,
      page:              l.page,
      sessions,
      suggested_hook:    buildServiceHook(l),
      suggested_cta:     buildServiceCTA(l.service),
      format:            'static',
      channel:           svcMap[l.service] || 'IG Static',
      expected_outcome:  { type: 'bookings', delta: '+10-20%', label: '+10-20% sessions from IG push' },
      expiration_window: expDays,
      source_evidence:   `${sessions} GA4 sessions on ${l.page} with no IG coverage this week`,
      urgency:           sessions > 80 ? 'today' : sessions > 40 ? 'this_week' : 'flexible',
      owner:             l.owner,
      why:               `${sessions} sessions with no social conversion path`,
    };
  });

// ── 4. BOOKING PAGE RETARGET ─────────────────────────────────────
const bookingRetarget = (leaks.leaks || [])
  .filter(l => l.type === 'booking_traffic_no_retargeting')
  .slice(0, 1)
  .map(l => ({
    type:              'push_booking_cta',
    action:            'Push booking CTA — traffic is hot',
    sessions:          l.sessions,
    suggested_hook:    'Your clubs are waiting. Your handicap won\'t fix itself. \u26f3',
    suggested_cta:    'Book a session \u00b7 swingshack.co.za/bookings \u00b7 From R250',
    format:            'static',
    channel:           'IG Static',
    expected_outcome:  { type: 'bookings', delta: '+20-35%', label: '+20-35% booking rate from IG push' },
    expiration_window: 'today',
    source_evidence:   `${l.sessions} sessions on booking page but 0 booking CTAs in recent IG posts`,
    urgency:           l.severity,
    owner:             l.owner,
    why:               'Booking page traffic hot with no retargeting',
  }));

// ── 5. WIN-BACK / REWORK ──────────────────────────────────────────
const winBack = (missed.opportunities || [])
  .filter(o => o.category === 'follow_up_gap' && (o.ig_score || 0) >= 6 && (o.ig_score || 0) < 8)
  .slice(0, 2)
  .map(o => ({
    type:              'rework_angle',
    action:            'Rework hook angle for stronger booking intent',
    topic:             o.topic,
    original_hook:     o.hook,
    original_score:    o.ig_score,
    suggested_hook:    reworkHook(o.hook || '', o.topic || ''),
    suggested_cta:     'Book your lesson \u00b7 swingshack.co.za/membership \u00b7 Catherine & Dave',
    format:            'static',
    channel:           'IG Static',
    expected_outcome:  { type: 'bookings', delta: '+8-15%', label: '+8-15% bookings from stronger hook' },
    expiration_window: 'this_week',
    source_evidence:   `Hook scored ${o.ig_score} — moderate, needs booking intent upgrade`,
    urgency:           'this_week',
    owner:             o.owner || 'Swing Shack page',
    why:               `Score ${o.ig_score} — reword with direct booking urgency`,
  }));

// ── 6. PROMO + BOOKING ───────────────────────────────────────────
const promoGaps = (missed.opportunities || [])
  .filter(o => o.category === 'offer_gap' || (o.type || '').includes('contest'))
  .slice(0, 2)
  .map(o => ({
    type:              'promo_plus_booking',
    action:            'Pair contest hook with direct booking CTA',
    topic:             o.topic || o.angle_label || 'contest',
    hook:              o.hook || o.suggestion,
    suggested_hook:    'Lowest net score wins a custom driver fitting. Or get one anyway.',
    suggested_cta:     'Enter now \u00b7 Or book your fitting \u2192 swingshack.co.za/membership',
    format:            'static',
    channel:           'IG Static',
    expected_outcome:  { type: 'awareness', delta: '+reach + bookings', label: '+reach (contest) + bookings (CTA)' },
    expiration_window: 'this_week',
    source_evidence:   'Contest drives reach; booking CTA converts high-intent audience',
    urgency:           'this_week',
    owner:             'Swing Shack page',
    why:               'Contest hooks get reach but no conversion — pair with direct CTA',
  }));

// ── Combine & deduplicate ───────────────────────────────────────
const allRecs = [
  ...bookingRetarget,
  ...saveGaps,
  ...serviceReminders,
  ...followUpGaps.filter(f => !f.already_planned),
  ...winBack,
  ...promoGaps,
].slice(0, 12);

const seen = new Set();
const deduped = allRecs.filter(r => {
  const key = r.type + (r.topic || r.service || r.post_id || '').substring(0, 20);
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
});

const urgencyOrder = { today: 0, '48h': 1, this_week: 2, flexible: 3 };
deduped.sort((a, b) => {
  if (urgencyOrder[a.expiration_window] !== urgencyOrder[b.expiration_window]) {
    return urgencyOrder[a.expiration_window] - urgencyOrder[b.expiration_window];
  }
  return 0;
});

// Summary stats
const expWindow = {};
deduped.forEach(r => {
  const w = r.expiration_window;
  expWindow[w] = (expWindow[w] || 0) + 1;
});

// ── Helpers ──────────────────────────────────────────────────────
function buildRetargetHook(o) {
  const topic = o.topic || '';
  if (topic.includes('lesson'))   return 'Still working on your swing? Here\'s what actually changes it.';
  if (topic.includes('driver'))   return 'Your driver data is telling a story. TrackMan tells you how to fix it.';
  if (topic.includes('putt'))     return 'One putting session changed everything. Here\'s what Cat found.';
  return `One session. Major difference. Book yours.`;
}

function buildServiceHook(l) {
  const svc = l.service || '';
  const map = {
    'Golf Lessons':  'Your handicap didn\'t drop by itself. Here\'s what actually changes it.',
    'Club Fitting':  'Off-the-rack clubs are costing you yards. Here\'s what TrackMan found.',
    'Simulator':     'Rain, heat, winter \u2014 the sim doesn\'t care. Your game still improves.',
    'Membership':    'Unlimited practice. 15% off everything. The membership that pays for itself.',
    'Events':        'This week\'s competition: lowest net score wins a custom driver fitting.',
  };
  return map[svc] || `You\'ve been thinking about ${svc} long enough. Here\'s where to start.`;
}

function buildServiceCTA(svc) {
  const map = {
    'Golf Lessons':  'Book your first lesson \u00b7 swingshack.co.za/membership \u00b7 Coach Cat & Dave',
    'Club Fitting':  'Get your clubs custom fitted \u00b7 swingshack.co.za/membership \u00b7 TrackMan powered',
    'Simulator':     'Practice year-round in the sim \u00b7 swingshack.co.za/book \u00b7 From R250/session',
    'Membership':    'Unlimited practice \u00b7 15% off everything \u00b7 swingshack.co.za/membership',
    'Events':        'Enter this week\'s competition \u00b7 swingshack.co.za/events \u00b7 Prizes every week',
  };
  return map[svc] || 'Book your session \u00b7 swingshack.co.za/membership';
}

function reworkHook(hook, topic) {
  if ((hook || '').toLowerCase().includes('trackman') || (hook || '').toLowerCase().includes('meter')) {
    return `Your numbers don\'t lie. Neither does the fix. One TrackMan session \u2014 book it.`;
  }
  if (hook.includes('?')) {
    return hook.replace(/\?$/, '? Here\'s exactly how to fix it. Book your session.');
  }
  return `${hook.substring(0, 50)} \u2014 and here\'s exactly how to fix it. Book your session.`;
}

// ── Write ────────────────────────────────────────────────────────
const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_retargeting_recommendations.js',
  summary: {
    total:              deduped.length,
    by_channel:         Object.fromEntries(
      [...new Set(deduped.map(r => r.channel))].sort().map(ch => [ch, deduped.filter(r => r.channel === ch).length])
    ),
    by_expiration:      expWindow,
    by_urgency:         { today: deduped.filter(r => r.urgency === 'today').length, this_week: deduped.filter(r => r.urgency === 'this_week').length, flexible: deduped.filter(r => r.urgency === 'flexible').length },
    owner_count:        [...new Set(deduped.map(r => r.owner))].length,
    top_action:         deduped[0] ? `${deduped[0].action} (${deduped[0].channel})` : 'none',
  },
  recommendations: deduped.map((r, i) => ({ ...r, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Retargeting recommendations: ${OUTPUT}`);
console.log(`   Total: ${deduped.length} | Channels: ${Object.keys(output.summary.by_channel).join(', ')}`);
console.log(`   Expiration: ${Object.entries(expWindow).map(([k,v]) => `${k}×${v}`).join(', ')}`);
deduped.slice(0, 5).forEach((r, i) => {
  const exp = r.expiration_window;
  const planned = r.already_planned ? ' [📅 in plan]' : '';
  console.log(`   ${i+1}. [${exp.toUpperCase()}] ${r.action} | ${r.channel} | ${r.owner}${planned}`);
  console.log(`      Hook: ${(r.suggested_hook || r.hook || '—').substring(0, 60)}`);
  console.log(`      Evidence: ${r.source_evidence}`);
  console.log(`      Expected: ${r.expected_outcome.label}`);
});
