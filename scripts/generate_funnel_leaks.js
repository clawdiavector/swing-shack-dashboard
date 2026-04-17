#!/usr/bin/env node
/**
 * generate_funnel_leaks.js
 * Detects high-intent traffic leaking before booking.
 * Output: data/funnel-leaks.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'funnel-leaks.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const ga4    = readJson('ga4-metrics.json')          || {};
const ig     = readJson('ig-analytics.json')         || {};
const conv   = readJson('conversion-attribution.json') || {};
const missed = readJson('missed-opportunities.json') || {};

// GA4 pages
const pages = ga4.pages || [];
const igPosts = ig.posts || [];

// Funnel stages
const STAGES = {
  AWARENESS:  ['/', 'home', 'about', 'gallery', 'photo', 'video'],
  INTEREST:   ['lesson', 'coach', 'fitting', 'service', 'price', 'membership', 'program'],
  INTENT:     ['book', 'checkout', 'contact', 'enquiry', 'trial', 'sign up', 'signup', 'register'],
  CONVERSION: ['confirm', 'success', 'paid', 'booking', 'tq', 'thank'],
};

function stageOf(path) {
  const p = (path || '').toLowerCase();
  for (const [stage, keys] of Object.entries(STAGES)) {
    if (keys.some(k => p.includes(k))) return stage;
  }
  return 'AWARENESS';
}

const stageOrder = { INTENT: 0, INTEREST: 1, AWARENESS: 2, CONVERSION: 3 };

// ── Leak 1: High-intent pages with low engagement rate ─────────
const intentPages = pages.filter(p => stageOf(p.path) === 'INTENT');
const intentLeaks = intentPages
  .filter(p => (parseFloat(p.engagement_rate || 0) || 0) < 40)
  .sort((a, b) => (parseInt(b.sessions || 0)) - (parseInt(a.sessions || 0)))
  .slice(0, 4)
  .map(p => ({
    type:      'high_intent_low_engagement',
    page:      p.path,
    sessions:  parseInt(p.sessions) || 0,
    engRate:   parseFloat(p.engagement_rate || 0) || 0,
    severity:  (parseInt(p.sessions || 0) || 0) > 50 ? 'high' : 'medium',
    revenue_impact: 'HIGH — many sessions, low engagement, likely bouncing',
    easy_fix:  'Add stronger CTA or urgency element on this page',
    owner:      p.path?.includes('book') || p.path?.includes('checkout') ? 'Nancy / Front Desk' : 'Swing Shack page',
  }));

// ── Leak 2: High-traffic service pages with no IG posts ────────
const SERVICE_PATTERNS = {
  'Golf Lessons':  ['lesson', 'coach', 'training'],
  'Club Fitting':  ['fitting', 'fitted', 'custom', 'club'],
  'Simulator':     ['simulator', 'sim', 'bay'],
  'Membership':    ['member', 'membership', 'perk'],
  'Events':        ['event', 'competition', 'tournament', 'night'],
};

const igText = igPosts.map(p => (p.caption || '').toLowerCase()).join(' ');
const serviceLeaks = Object.entries(SERVICE_PATTERNS).map(([service, kws]) => {
  const page = pages.find(p => kws.some(k => (p.path || '').toLowerCase().includes(k)));
  const sessions = page ? (parseInt(page.sessions) || 0) : 0;
  const igCovered = kws.some(k => igText.includes(k));
  if (!igCovered && sessions > 20) {
    return {
      type:     'service_page_no_ig',
      service,
      page:     page?.path || kws[0],
      sessions,
      severity: sessions > 80 ? 'high' : sessions > 40 ? 'medium' : 'low',
      revenue_impact: `${sessions} sessions with no IG content pushing this service`,
      easy_fix: `Create IG post about ${service} — GA4 shows ${sessions} sessions this week`,
      owner:    service === 'Golf Lessons' ? 'Coach Cat' : service === 'Club Fitting' ? 'Divan' : 'Swing Shack page',
    };
  }
  return null;
}).filter(Boolean).sort((a, b) => b.sessions - a.sessions).slice(0, 4);

// ── Leak 3: High saves/reach ratio posts with no follow-up CTA ─
const highSavePosts = igPosts
  .filter(p => {
    const reach = parseInt(p.reach) || 0;
    const saves = parseInt(p.saveCount) || 0;
    return reach > 50 && saves / reach > 0.03; // 3%+ save rate
  })
  .sort((a, b) => (parseInt(b.saveCount) || 0) / (parseInt(b.reach) || 1) - (parseInt(a.saveCount) || 0) / (parseInt(a.reach) || 1));

const saveLeaks = highSavePosts.slice(0, 3).map(p => {
  const hasBookingCTA = ['book', 'booking', 'link in bio', 'reserve', 'schedule'].some(
    t => (p.caption || '').toLowerCase().includes(t)
  );
  return {
    type:       'high_save_no_booking_cta',
    post_id:    p.id || 'unknown',
    reach:      parseInt(p.reach) || 0,
    saves:      parseInt(p.saveCount) || 0,
    save_rate:  parseFloat(((parseInt(p.saveCount) || 0) / (parseInt(p.reach) || 1) * 100).toFixed(2)),
    has_booking_cta: hasBookingCTA,
    severity:   hasBookingCTA ? 'low' : 'high',
    caption_preview: (p.caption || '').substring(0, 80),
    revenue_impact: hasBookingCTA ? 'Low — already has booking CTA' : 'HIGH — high save rate but no direct booking path',
    easy_fix:   hasBookingCTA ? 'Already optimised' : 'Add direct booking CTA to caption',
    owner:      'Swing Shack page',
  };
});

// ── Leak 4: Follow-up gap from IG to website ─────────────────────
const followedUp = (missed.opportunities || [])
  .filter(o => o.category === 'follow_up_gap' && (o.ig_score || 0) >= 8);
const followUpLeaks = followedUp.slice(0, 3).map(o => ({
  type:     'hook_winner_no_follow_up',
  topic:    o.topic,
  ig_score: o.ig_score,
  hook:     (o.hook || '').substring(0, 60),
  severity: o.severity,
  revenue_impact: `Strong IG hook (${o.ig_score}) with no booking funnel follow-up`,
  easy_fix:  o.suggested_fix || `Create follow-up post with direct booking CTA for "${o.topic}"`,
  owner:    o.owner || 'Coach Cat',
}));

// ── Leak 5: Booking page traffic but no retargeting push ────────
const bookingPage = pages.find(p => ['book', 'checkout'].some(b => (p.path || '').toLowerCase().includes(b)));
if (bookingPage) {
  const bSessions = parseInt(bookingPage.sessions) || 0;
  if (bSessions > 30) {
    const recentBookingPosts = igPosts.filter(p =>
      ['book', 'booking', 'reserve', 'schedule'].some(t => (p.caption || '').toLowerCase().includes(t))
    ).length;
    if (recentBookingPosts < 2) {
      saveLeaks.push({
        type:     'booking_traffic_no_retargeting',
        page:     bookingPage.path,
        sessions: bSessions,
        severity: bSessions > 80 ? 'high' : 'medium',
        revenue_impact: `${bSessions} sessions on booking page but < 2 booking CTAs in recent IG posts`,
        easy_fix:  'Push booking CTA on IG this week — booking page traffic is there',
        owner:    'Swing Shack page',
      });
    }
  }
}

// ── Rank all leaks by severity + sessions ───────────────────────
const allLeaks = [
  ...intentLeaks,
  ...serviceLeaks,
  ...saveLeaks,
  ...followUpLeaks,
].sort((a, b) => {
  const sevOrder = { high: 0, medium: 1, low: 2 };
  if (sevOrder[a.severity] !== sevOrder[b.severity]) return sevOrder[a.severity] - sevOrder[b.severity];
  return (b.sessions || b.ig_score || 0) - (a.sessions || a.ig_score || 0);
}).slice(0, 10);

// Summary stats
const highLeaks    = allLeaks.filter(l => l.severity === 'high').length;
const mediumLeaks  = allLeaks.filter(l => l.severity === 'medium').length;
const lowLeaks     = allLeaks.filter(l => l.severity === 'low').length;
const mostUrgent   = allLeaks.find(l => l.severity === 'high') || allLeaks[0] || null;

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_funnel_leaks.js',
  summary: {
    total_leaks:    allLeaks.length,
    high:           highLeaks,
    medium:         mediumLeaks,
    low:            lowLeaks,
    most_urgent:    mostUrgent ? `(${mostUrgent.severity}) ${mostUrgent.easy_fix?.substring(0, 60)}` : 'none',
  },
  leaks: allLeaks.map((l, i) => ({ ...l, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Funnel leaks: ${OUTPUT}`);
console.log(`   Total: ${allLeaks.length} | High: ${highLeaks} | Med: ${mediumLeaks} | Low: ${lowLeaks}`);
console.log(`   Most urgent: ${mostUrgent?.easy_fix?.substring(0, 70)}`);
allLeaks.slice(0, 5).forEach((l, i) => {
  console.log(`   ${i+1}. [${l.severity.toUpperCase()}] ${l.type} | ${l.owner}`);
  console.log(`      Fix: ${l.easy_fix?.substring(0, 70)}`);
});
