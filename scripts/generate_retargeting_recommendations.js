#!/usr/bin/env node
/**
 * generate_retargeting_recommendations.js
 * Turns detected funnel leaks and high-intent signals into actionable
 * retargeting content: posts to re-run, CTAs to add, second-chance content.
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

const leaks    = readJson('funnel-leaks.json')           || {};
const conv     = readJson('conversion-attribution.json')  || {};
const ig      = readJson('ig-analytics.json')            || {};
const plan    = readJson('post-plan.json')               || {};
const sales   = readJson('sales-priority.json')          || {};
const missed  = readJson('missed-opportunities.json')    || {};
const ctaPerf = readJson('cta-performance.json')        || {};

const igPosts = ig.posts || [];
const plannedHooks = new Set((plan.plan || []).map(p => p.hook?.toLowerCase().substring(0, 40)));

// ── 1. RETARGET EXISTING POSTS ──────────────────────────────────
// Posts that performed well but haven't been pushed as a follow-up
const followUpGaps = (missed.opportunities || [])
  .filter(o => o.category === 'follow_up_gap' && (o.ig_score || 0) >= 7)
  .slice(0, 4)
  .map(o => {
    const topicKw = o.topic || '';
    // Find the original high-performing post
    const originalPost = igPosts.find(p =>
      (p.caption || '').toLowerCase().includes(topicKw.split(' ')[0] || '')
    );
    const alreadyPlanned = Array.from(plannedHooks).some(h =>
      (o.hook || '').toLowerCase().substring(0, 40).includes(h.substring(0, 20))
    );
    return {
      type:           'retarget_existing',
      action:         'Re-run with booking CTA',
      topic:          topicKw,
      original_hook:  o.hook,
      original_score: o.ig_score,
      suggested_caption: buildRetargetCaption(o),
      suggested_cta:  'Book your session · Link in bio · swingshack.co.za/membership',
      format:         topicKw.includes('lesson') || topicKw.includes('putt') ? 'reel' : 'static',
      urgency:        o.ig_score >= 9 ? 'today' : 'this_week',
      owner:          o.owner || 'Coach Cat',
      why:            `Hook scored ${o.ig_score} on IG but no booking follow-up exists`,
      already_planned: alreadyPlanned,
    };
  });

// ── 2. SECOND-CHANCE CONTENT ───────────────────────────────────
// High-save posts that didn't have a booking CTA — add one
const saveGaps = (leaks.leaks || [])
  .filter(l => l.type === 'high_save_no_booking_cta' && !l.has_booking_cta)
  .slice(0, 3)
  .map(l => {
    return {
      type:      'add_booking_cta',
      action:    'Add booking CTA to existing high-save post thread',
      post_id:   l.post_id,
      reach:     l.reach,
      saves:     l.saves,
      save_rate: l.save_rate,
      caption_preview: l.caption_preview,
      suggested_cta:   'Ready to fix your game? Book a session → swingshack.co.za/membership',
      urgency:   l.save_rate > 5 ? 'today' : 'this_week',
      owner:     'Swing Shack page',
      why:       `${l.saves} saves (${l.save_rate}%) but no booking path — add CTA to comments or caption`,
    };
  });

// ── 3. SERVICE REMINDER POSTS ───────────────────────────────────
// Services with high booking page traffic but low IG coverage
const serviceReminders = (leaks.leaks || [])
  .filter(l => l.type === 'service_page_no_ig')
  .slice(0, 3)
  .map(l => {
    const ctaTemplates = {
      'Golf Lessons':  'Book your first lesson · swingshack.co.za/membership · Coach Cat & Dave',
      'Club Fitting':  'Get your clubs custom fitted · swingshack.co.za/membership · TrackMan powered',
      'Simulator':     'Practice year-round in the sim · swingshack.co.za/book · From R250/session',
      'Membership':    'Unlimited practice · 15% off everything · swingshack.co.za/membership',
'Events':        'Enter this week events comp · swingshack.co.za/events · Prizes every week',
    };
    return {
      type:      'new_service_reminder',
      action:    'Publish service reminder post',
      service:   l.service,
      page:      l.page,
      sessions:  l.sessions,
      suggested_hook: buildServiceHook(l),
      suggested_cta:  ctaTemplates[l.service] || 'Book your session · swingshack.co.za/membership',
      format:    l.service === 'Golf Lessons' ? 'reel' : 'static',
      urgency:   l.severity === 'high' ? 'today' : 'this_week',
      owner:     l.owner,
      why:       `${l.sessions} GA4 sessions on ${l.page} but no IG post this week`,
    };
  });

// ── 4. BOOKING PAGE RETARGETING ─────────────────────────────────
// Push booking CTA this week if booking page has traffic
const bookingRetarget = (leaks.leaks || [])
  .filter(l => l.type === 'booking_traffic_no_retargeting')
  .slice(0, 1)
  .map(l => ({
    type:     'push_booking_cta',
    action:   'Push booking CTA — booking page traffic is hot',
    sessions: l.sessions,
    suggested_hook: 'Your clubs are waiting. Your handicap isn\'t going to fix itself. ⛳',
    suggested_cta:  'Book a session · swingshack.co.za/bookings · From R250',
    format:    'static',
    urgency:   l.severity,
    owner:    l.owner,
    why:      `${l.sessions} sessions on booking page but 0 booking CTAs in recent IG`,
  }));

// ── 5. WIN-BACK FOR UNDERPERFORMING HOOKS ───────────────────────
// Hooks that scored 6-7 (good but not great) — rework the angle
const winBack = (missed.opportunities || [])
  .filter(o => o.category === 'follow_up_gap' && (o.ig_score || 0) >= 6 && (o.ig_score || 0) < 8)
  .slice(0, 2)
  .map(o => ({
    type:       'rework_angle',
    action:     'Rework hook angle',
    topic:      o.topic,
    original_hook: o.hook,
    original_score: o.ig_score,
    suggested_hook: reworkHook(o.hook || '', o.topic || ''),
    suggested_cta:  'Book your lesson · swingshack.co.za/membership · Catherine & Dave',
    format:     'static',
    urgency:    'this_week',
    owner:      o.owner || 'Swing Shack page',
    why:        `Hook scored ${o.ig_score} — reword angle for stronger booking intent`,
  }));

// ── 6. COMPETITIVE LOW-COST RETARGET ────────────────────────────
// Contest/prize hooks drive awareness — pair with booking CTA
const promoGaps = (missed.opportunities || [])
  .filter(o => o.category === 'offer_gap' || (o.type || '').includes('contest'))
  .slice(0, 2)
  .map(o => ({
    type:      'promo_plus_booking',
    action:    'Pair promo/contest with direct booking CTA',
    topic:     o.topic || o.angle_label || 'contest',
    hook:      o.hook || o.suggestion,
    suggested_hook: `Win a custom driver fitting — or get one anyway. TrackMan tells you exactly what you need. ⛳`,
    suggested_cta:  'Enter now · Or book your fitting → swingshack.co.za/membership',
    format:    'static',
    urgency:   'this_week',
    owner:     'Swing Shack page',
    why:       'Contest drives reach, booking CTA converts',
  }));

// ── All recommendations ─────────────────────────────────────────
const allRecs = [
  ...bookingRetarget,  // highest intent — push first
  ...saveGaps,
  ...serviceReminders,
  ...followUpGaps.filter(f => !f.already_planned),
  ...winBack,
  ...promoGaps,
].slice(0, 12);

// Sort by urgency then by type
const urgencyOrder = { today: 0, this_week: 1, flexible: 2 };
allRecs.sort((a, b) => {
  if (urgencyOrder[a.urgency] !== urgencyOrder[b.urgency]) {
    return urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
  }
  return 0;
});

// Deduplicate by type+topic
const seen = new Set();
const deduped = allRecs.filter(r => {
  const key = r.type + (r.topic || r.service || r.post_id || '').substring(0, 20);
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
});

// Summary
const todayCount    = deduped.filter(r => r.urgency === 'today').length;
const thisWeekCount = deduped.filter(r => r.urgency === 'this_week').length;
const byOwner = {};
deduped.forEach(r => {
  const o = r.owner || 'Unknown';
  if (!byOwner[o]) byOwner[o] = [];
  byOwner[o].push({ action: r.action, topic: r.topic || r.service, urgency: r.urgency });
});

// ── Helper functions ─────────────────────────────────────────────
function buildRetargetCaption(o) {
  const topic = o.topic || '';
  if (topic.includes('lesson')) {
    return `Still working on your swing? One session with Coach Cat changed everything for us. TrackMan breaks it down in real time. From R250.`;
  }
  if (topic.includes('driver') || topic.includes('slice')) {
    return `Your driver data is telling a story. TrackMan tells you how to fix it. One session. Major difference. Book yours.`;
  }
  if (topic.includes('putt') || topic.includes('short')) {
    return `Short game wins tournaments. One putting session with Cat — here's what she found. ⛳ Book your session.`;
  }
  return `Still thinking about ${topic}? Here's what TrackMan found in one session. From R250. Book yours.`;
}

function buildServiceHook(l) {
  const svc = l.service || '';
  if (svc === 'Golf Lessons') return `Your handicap didn't drop by itself. Here's what actually changes it.`;
  if (svc === 'Club Fitting') return `Off-the-rack clubs are costing you yards. Here's what TrackMan found during fitting.`;
  if (svc === 'Simulator')     return `Rain, heat, winter — the simulator doesn't care. Your game still improves.`;
  if (svc === 'Membership')    return `Unlimited practice. 15% off everything. The membership that pays for itself.`;
  if (svc === 'Events')        return `This week's competition: lowest net score wins a custom driver fitting. Enter now.`;
  return `You've been thinking about it long enough. ${svc} — here's where to start.`;
}

function reworkHook(hook, topic) {
  // If original hook was stats-based, pair with booking urgency
  if (hook.toLowerCase().includes('trackman') || hook.toLowerCase().includes('meter') || hook.toLowerCase().includes('yard')) {
    return `Your numbers don't lie. Neither does the fix. One TrackMan session — book it.`;
  }
  // If it was a question, answer it with booking intent
  if (hook.includes('?')) {
    return hook.replace(/\?$/, "? Here's exactly how to fix it. Book your session.");
  }
  return `${hook.substring(0, 50)} — and here's exactly how to fix it. Book your session.`;
}

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_retargeting_recommendations.js',
  summary: {
    total_recommendations: deduped.length,
    today:     todayCount,
    this_week: thisWeekCount,
    by_type: Object.fromEntries(
      [...new Set(deduped.map(r => r.type))].map(t => [t, deduped.filter(r => r.type === t).length])
    ),
    by_owner: Object.fromEntries(
      Object.entries(byOwner).sort(([a], [b]) => a.localeCompare(b))
    ),
    most_urgent: deduped[0] ? `${deduped[0].urgency}: ${deduped[0].action} (${deduped[0].topic || deduped[0].service || deduped[0].type})` : 'none',
  },
  recommendations: deduped.map((r, i) => ({ ...r, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Retargeting recommendations: ${OUTPUT}`);
console.log(`   Total: ${deduped.length} | Today: ${todayCount} | This week: ${thisWeekCount}`);
console.log(`   Most urgent: ${output.summary.most_urgent}`);
deduped.slice(0, 6).forEach((r, i) => {
  const planned = r.already_planned ? ' [📅 already in plan]' : '';
  console.log(`   ${i+1}. [${r.urgency.toUpperCase()}] ${r.action} | ${r.owner}${planned}`);
  console.log(`      Hook: ${(r.suggested_hook || r.hook || '').substring(0, 60)}`);
  console.log(`      CTA:  ${(r.suggested_cta || '').substring(0, 60)}`);
});
