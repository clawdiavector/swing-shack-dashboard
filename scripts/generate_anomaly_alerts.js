#!/usr/bin/env node
/**
 * generate_anomaly_alerts.js
 * Catches anomalies: sudden drops, spikes, collapses.
 * Outputs: data/anomaly-alerts.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'anomaly-alerts.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const ig      = readJson('ig-analytics.json')             || {};
const ga4     = readJson('ga4-metrics.json')             || {};
const seo     = readJson('seo-rankings.json')             || {};
const outcomes= readJson('recommendation-outcomes.json')   || {};

const igPosts  = ig.posts || [];
const ga4Pages = ga4.pages || [];

// ── 1. IG performance drop ──────────────────────────────────────
const sortedByDate = [...igPosts].sort((a, b) =>
  new Date(b.timestamp || b.created_at || 0) - new Date(a.timestamp || a.created_at || 0)
);

const recentPosts = sortedByDate.slice(0, 7);    // last 7 posts
const olderPosts  = sortedByDate.slice(7, 21);  // posts 8-21

const avgRecentEng = recentPosts.length > 0
  ? recentPosts.reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / recentPosts.length
  : 0;
const avgOlderEng = olderPosts.length > 0
  ? olderPosts.reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / olderPosts.length
  : 0;

const igDrop = avgRecentEng < avgOlderEng * 0.7 && avgOlderEng > 1 ? {
  type:       'ig_performance_drop',
  alert:     'Instagram engagement rate dropping',
  severity:  avgRecentEng < avgOlderEng * 0.5 ? 'high' : 'medium',
  evidence:  `Recent 7-post avg: ${avgRecentEng.toFixed(2)}% | Previous avg: ${avgOlderEng.toFixed(2)}% | Drop: -${((1 - avgRecentEng/avgOlderEng)*100).toFixed(0)}%`,
  likely_cause: 'Hook quality drop OR algorithm shift OR audience fatigue',
  action:     'Check last 3 posts for hook quality — compare to top-performing historical posts',
  owner:      'Swing Shack page',
  urgency:    'today',
  confidence: 5,
} : null;

// ── 2. Booking page traffic collapse ───────────────────────────
const bookingPage = ga4Pages.find(p => (p.path || '').toLowerCase().includes('book'));
if (bookingPage) {
  var bookingSessions = parseInt(bookingPage.sessions) || 0;
}
const nonBookingPages = ga4Pages.filter(p => !(p.path || '').toLowerCase().includes('book'));
const avgOtherSessions = nonBookingPages.length > 0
  ? nonBookingPages.reduce((s, p) => s + (parseInt(p.sessions) || 0), 0) / nonBookingPages.length
  : 0;

const bookingCollapse = bookingSessions < avgOtherSessions * 0.3 && avgOtherSessions > 10 ? {
  type:       'booking_traffic_collapse',
  alert:     'Booking page traffic abnormally low',
  severity:  bookingSessions === 0 ? 'high' : 'medium',
  evidence:  `Booking sessions: ${bookingSessions} | Site average: ${avgOtherSessions.toFixed(0)}`,
  likely_cause: 'No recent IG booking CTA posts OR website UX issue OR booking page down',
  action:     'Check: (1) Is booking page accessible? (2) Did IG posts with booking CTAs go out recently?',
  owner:      'Swing Shack page / Nancy',
  urgency:    'today',
  confidence: 4,
} : null;

// ── 3. GA4 source/method swing ─────────────────────────────────
const ga4Sources = ga4.source_medium || [];
const topSources = [...ga4Sources].sort((a, b) => (parseInt(b.sessions || 0)) - (parseInt(a.sessions || 0))).slice(0, 5);
const socialSource = topSources.find(s => (s.source || '').toLowerCase().includes('social') || (s.source || '').toLowerCase().includes('instagram'));
const directSource = topSources.find(s => (s.source || '').toLowerCase().includes('direct') || (s.source || '').toLowerCase().includes('google'));

const sourceSwing = socialSource && directSource ? {
  type:       'source_swing',
  alert:     'Social traffic share shifted significantly',
  severity:  'medium',
  evidence:  `Social: ${socialSource.sessions} sessions | Direct: ${directSource.sessions} sessions`,
  likely_cause: 'IG posting schedule change OR Reels vs static mix shift OR reach algorithm change',
  action:     'Compare last 7 days IG posting cadence to previous 7 days',
  owner:      'Swing Shack page',
  urgency:    'this_week',
  confidence: 3,
} : null;

// ── 4. SEO ranking drop ────────────────────────────────────────
const fallingKeywords = (seo.rankings || seo.organic_keywords || [])
  .filter(k => {
    const current = parseInt(k.current_rank || k.rank || 999);
    const delta   = parseFloat(k.delta || k.delta_7d || 0);
    return current <= 20 && delta < -3; // top 20, dropped more than 3 positions
  })
  .slice(0, 3)
  .map(k => ({
    keyword:    k.keyword || k.term,
    rank:       k.current_rank || k.rank,
    delta:      parseFloat(k.delta || k.delta_7d || 0),
  }));

const seoDrop = fallingKeywords.length > 0 ? {
  type:       'seo_ranking_drop',
  alert:     `${fallingKeywords.length} top keyword(s) dropping in rankings`,
  severity:  fallingKeywords.some(k => k.delta < -5) ? 'high' : 'medium',
  evidence:  fallingKeywords.map(k => `"${k.keyword}": ${k.rank} (${k.delta > 0 ? '+' : ''}${k.delta})`).join(' | '),
  likely_cause: 'Competitor outranking OR content freshness drop OR backlink loss',
  action:     'Audit top dropping pages — add fresh IG content linking to those pages this week',
  owner:      'Swing Shack page',
  urgency:    'this_week',
  confidence: 4,
} : null;

// ── 5. Sudden theme spike ──────────────────────────────────────
const THEME_KEYWORDS = {
  'slice_fix':     ['slice', 'hook', 'correction', 'right', 'left'],
  'putting':       ['putting', 'putt', 'green'],
  'fitness':       ['fitness', 'gym', 'flexibility', 'body'],
  'simulator':     ['simulator', 'sim', 'indoor'],
  'tournament':    ['tournament', 'competition', 'event'],
};
const now = Date.now();
const recentWeek = igPosts.filter(p => {
  const age = (now - new Date(p.timestamp || p.created_at || 0).getTime()) / 86400000;
  return age <= 7;
});
const older = igPosts.filter(p => {
  const age = (now - new Date(p.timestamp || p.created_at || 0).getTime()) / 86400000;
  return age > 7 && age <= 28;
});

const themeSpikes = [];
Object.entries(THEME_KEYWORDS).forEach(([theme, kws]) => {
  const recentCount = recentWeek.filter(p => kws.some(k => (p.caption || '').toLowerCase().includes(k))).length;
  const olderCount  = older.filter(p => kws.some(k => (p.caption || '').toLowerCase().includes(k))).length;
  if (recentCount >= 3 && recentCount > olderCount * 2) {
    themeSpikes.push({
      type:       'theme_spike',
      alert:     `"${theme}" posting suddenly increased`,
      severity:  'low',
      evidence:  `${recentCount} posts in last 7 days vs ${olderCount} in prior 3 weeks`,
      likely_cause: 'Trending topic OR competitor posting OR seasonal shift',
      action:     'Review — if genuine trend, create more content. If over-posting, throttle.',
      owner:      'Swing Shack page',
      urgency:    'this_week',
      confidence: 3,
    });
  }
});

// ── 6. Exec rate collapse ──────────────────────────────────────
const execRate = outcomes.summary?.exec_rate || 0;
const execCollapse = execRate < 20 && (outcomes.summary?.total_recommended || 0) >= 5 ? {
  type:       'exec_rate_collapse',
  alert:     `Recommendation execution rate critically low: ${execRate}%`,
  severity:  execRate < 10 ? 'high' : 'medium',
  evidence:  `${outcomes.summary?.executed || 0} of ${outcomes.summary?.total_recommended || 0} recommended actions executed`,
  likely_cause: 'Recommendations not being actioned OR publishing pipeline bottleneck',
  action:     'Review DO THIS FIRST list — are recommendations reaching the right people?',
  owner:      'Swing Shack page',
  urgency:    'today',
  confidence: 5,
} : null;

// ── Combine ───────────────────────────────────────────────────
const allAlerts = [igDrop, bookingCollapse, sourceSwing, seoDrop, execCollapse, ...themeSpikes]
  .filter(Boolean)
  .sort((a, b) => {
    const sevOrder = { high: 0, medium: 1, low: 2 };
    return sevOrder[a.severity] - sevOrder[b.severity];
  });

// ── Write ───────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_anomaly_alerts.js',
  summary: {
    total_alerts:     allAlerts.length,
    high_urgency:     allAlerts.filter(a => a.severity === 'high').length,
    medium_urgency:   allAlerts.filter(a => a.severity === 'medium').length,
    low_urgency:      allAlerts.filter(a => a.severity === 'low').length,
    today_urgency:    allAlerts.filter(a => a.urgency === 'today').length,
  },
  alerts: allAlerts.map((a, i) => ({ ...a, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Anomaly alerts: ${OUTPUT}`);
console.log(`   Total: ${allAlerts.length} | High: ${output.summary.high_urgency} | Today: ${output.summary.today_urgency}`);
allAlerts.slice(0, 5).forEach((a, i) => {
  console.log(`   ${i+1}. [${a.severity.toUpperCase()}] ${a.alert}`);
  console.log(`      Cause: ${a.likely_cause}`);
  console.log(`      Action: ${a.action.substring(0, 70)}`);
});
