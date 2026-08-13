#!/usr/bin/env node
/**
 * generate_conversion_attribution.js
 * Ties content themes, hooks, CTAs and landing pages to booking intent signals.
 * Output: data/conversion-attribution.json
 *
 * Signal sources:
 * - GA4: sessions, engagement_rate, conversions by landing page
 * - IG analytics: likes, saves, reach, engagement_rate per post
 * - Hook Bank: hook themes, format types, CTA types per hook
 * - Post Plan: planned CTAs and landing page targets
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'conversion-attribution.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const igRaw      = readJson('ig-analytics.json')           || {};
const igBusiness = readJson('ig-business-analytics.json')  || {};
const ga4        = readJson('ga4-metrics.json')            || {};
const hooks      = readJson('hook-bank.json')              || {};
const sales      = readJson('sales-priority.json')         || {};
const missed     = readJson('missed-opportunities.json')   || {};
const plan       = readJson('post-plan.json')              || {};

// Normalise IG sources - prefer ig-business-analytics (real reach)
// over ig-analytics (often reach=0). Map both onto a uniform shape.
function normaliseIgPosts() {
  const bizMedia = (igBusiness.media || []).filter(m => m && m.metrics && (m.metrics.reach || 0) > 0);
  if (bizMedia.length > 0) {
    return bizMedia.map(m => ({
      id: m.id,
      caption: m.caption_preview || '',
      hook_id: m.hook_id || '',
      timestamp: m.timestamp || '',
      media_type: m.media_type || '',
      reach: parseInt(m.metrics.reach || 0),
      likes: parseInt(m.metrics.likes || 0),
      comments: parseInt(m.metrics.comments || 0),
      saves: parseInt(m.metrics.saved || 0),
      shares: parseInt(m.metrics.shares || 0),
      engagementRate: parseFloat(m.engagement_rate_pct || 0),
      source: 'ig-business-analytics',
    }));
  }
  // Fallback to ig-analytics (daily tracker) - may have reach=0
  return (igRaw.posts || []).map(p => ({
    id: p.id || p.postId,
    caption: p.captionPreview || p.caption || '',
    hook_id: p.hook_id || '',
    timestamp: p.timestamp || '',
    media_type: p.format_type || '',
    reach: parseInt(p.reach || 0),
    likes: parseInt(p.likes || 0),
    comments: parseInt(p.comments || 0),
    saves: parseInt(p.saves || 0),
    shares: parseInt(p.shares || 0),
    engagementRate: parseFloat(p.engagementRate || p.engagement_rate || 0),
    source: 'ig-analytics',
  }));
}

const ig     = { posts: normaliseIgPosts(), source_used: igBusiness.media && igBusiness.media.length > 0 ? 'ig-business-analytics' : 'ig-analytics' };

// ── GA4 Signals ─────────────────────────────────────────────────
const ga4Pages   = ga4.pages || [];
const ga4Conv    = ga4.conversions_by_page || {};
const ga4Traffic = ga4.source_medium || [];

// Normalise GA4 engagement-rate field: fetch_ga4 writes "engRate" as a
// percent string ("76.8%"); the rest of this file expects a number.
ga4Pages.forEach(p => {
  if (typeof p.engagement_rate === 'undefined' && p.engRate) {
    const parsed = parseFloat(String(p.engRate).replace('%', ''));
    p.engagement_rate = isNaN(parsed) ? 0 : parsed / 100;
  }
});

// High-intent pages (booking, checkout, contact, membership)
const BOOKING_PAGES = ['book', 'checkout', 'membership', 'contact', 'lesson', 'fitting', 'pricing', 'coaching'];
const isBooking = p => BOOKING_PAGES.some(bp => (p.path || '').toLowerCase().includes(bp));

const bookingPages = ga4Pages.filter(p => isBooking(p));
const totalBookingSessions = bookingPages.reduce((s, p) => s + (parseInt(p.sessions) || 0), 0);
const avgBookingEngagement = bookingPages.length
  ? bookingPages.reduce((s, p) => s + (parseFloat(p.engagement_rate || 0) || 0), 0) / bookingPages.length
  : 0;

// Top booking pages by sessions
const topBookingPages = [...bookingPages]
  .sort((a, b) => (parseInt(b.sessions) || 0) - (parseInt(a.sessions) || 0))
  .slice(0, 5)
  .map(p => ({
    path:     p.path,
    sessions: parseInt(p.sessions) || 0,
    engRate:  parseFloat(p.engagement_rate || 0) || 0,
    isBooking: true,
  }));

// ── CTA Type Mapping ─────────────────────────────────────────────
const CTA_BUCKETS = {
  BOOKING:      ['book', 'booking', 'book now', 'reserve', 'schedule', 'get started'],
  LESSONS:      ['lesson', 'coach', 'cat', 'dave', 'training', 'learn'],
  FITTING:      ['fitting', 'fitted', 'custom driver', 'custom iron', 'club'],
  PROMO:        ['discount', 'save', 'deal', 'offer', 'prize', 'win', 'free'],
  ENGAGEMENT:   ['link in bio', 'comment', 'share', 'tag', 'dm', 'follow'],
  SOFT:         ['swingshack', 'visit', 'try', 'come', 'experience'],
};

function bucketCTA(caption) {
  const lower = (caption || '').toLowerCase();
  for (const [bucket, terms] of Object.entries(CTA_BUCKETS)) {
    if (terms.some(t => lower.includes(t))) return bucket;
  }
  return 'SOFT';
}

// ── IG Post Analysis ────────────────────────────────────────────
const igPosts = ig.posts || [];

const ctaPerformance = {};  // bucket → { count, totalReach, totalLikes, totalSaves, totalComments, totalEngRate }
igPosts.slice(0, 30).forEach(p => {
  const bucket = bucketCTA(p.caption || '');
  if (!ctaPerformance[bucket]) {
    ctaPerformance[bucket] = { count: 0, totalReach: 0, totalLikes: 0, totalSaves: 0, totalComments: 0, totalEngRate: 0, posts: [] };
  }
  const reach    = parseInt(p.reach) || 0;
  const likes    = parseInt(p.likeCount) || 0;
  const saves    = parseInt(p.saveCount) || 0;
  const comments = parseInt(p.commentsCount || p.commentCount) || 0;
  const engRate  = parseFloat(p.engagementRate || p.engagement_rate || 0) || 0;
  ctaPerformance[bucket].count++;
  ctaPerformance[bucket].totalReach    += reach;
  ctaPerformance[bucket].totalLikes    += likes;
  ctaPerformance[bucket].totalSaves    += saves;
  ctaPerformance[bucket].totalComments += comments;
  ctaPerformance[bucket].totalEngRate   += engRate;
  ctaPerformance[bucket].posts.push({ id: p.id, reach, likes, saves, comments, engRate, caption: (p.caption || '').substring(0, 60) });
});

// Average per bucket
Object.values(ctaPerformance).forEach(b => {
  b.avgReach    = b.count > 0 ? b.totalReach / b.count : 0;
  b.avgLikes    = b.count > 0 ? b.totalLikes / b.count : 0;
  b.avgSaves    = b.count > 0 ? b.totalSaves / b.count : 0;
  b.avgEngRate  = b.count > 0 ? b.totalEngRate / b.count : 0;
  b.saveRate    = b.avgReach > 0 ? (b.avgSaves / b.avgReach * 100) : 0;
  // Conversion proxy: saves + comments as high-intent signal
  b.conversion_signal = (b.avgSaves * 2 + b.avgComments) / b.avgReach * 100 || 0;
});

// ── Service → Content correlation ───────────────────────────────
const SERVICE_KEYWORDS = {
  'Golf Lessons':  ['lesson', 'coach', 'cat', 'dave', 'putting', 'swing', 'short game', 'birdie', 'handicap'],
  'Club Fitting':  ['fitting', 'fitted', 'driver', 'iron', 'club', 'trackman', 'custom'],
  'Simulator':     ['simulator', 'golf simulator', 'sim', 'bay', 'indoor'],
  'Membership':    ['member', 'membership', 'perks', 'unlimited', 'practice'],
  'Events':        ['event', 'competition', 'tournament', 'night golf', 'league'],
};

const igText = igPosts.map(p => (p.caption || '').toLowerCase()).join(' ');

const serviceCorrelation = Object.entries(SERVICE_KEYWORDS).map(([service, kws]) => {
  const matchingPosts = igPosts.filter(p => {
    const cap = (p.caption || '').toLowerCase();
    return kws.some(k => cap.includes(k));
  });
  const avgEng = matchingPosts.length
    ? matchingPosts.reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / matchingPosts.length
    : 0;
  const totalReach = matchingPosts.reduce((s, p) => s + (parseInt(p.reach) || 0), 0);
  const saves      = matchingPosts.reduce((s, p) => s + (parseInt(p.saveCount) || 0), 0);
  const reach30    = igPosts.slice(0, 30).reduce((s, p) => s + (parseInt(p.reach) || 0), 0);
  const reachShare = reach30 > 0 ? (totalReach / reach30 * 100) : 0;
  return {
    service,
    post_count:  matchingPosts.length,
    reach_share: parseFloat(reachShare.toFixed(1)),
    avg_engagement: parseFloat(avgEng.toFixed(2)),
    total_reach: totalReach,
    total_saves: saves,
    save_rate:   totalReach > 0 ? parseFloat((saves / totalReach * 100).toFixed(2)) : 0,
    ig_signal:   parseFloat((avgEng * (matchingPosts.length > 0 ? 1 : 0.3)).toFixed(2)),
  };
}).sort((a, b) => b.ig_signal - a.ig_signal);

// ── Hook Theme → Conversion proxy ───────────────────────────────
const hookThemes = [
  { id: 'stats_trackman', label: 'TrackMan / Stats', keywords: ['trackman', 'data', 'stat', 'number', 'metric', 'spin', 'speed', 'drive', 'yard', 'meter'] },
  { id: 'slice_fix',      label: 'Slice Fix',         keywords: ['slice', 'hook', 'correction', 'fix', 'right', 'left', 'loss', 'straighten'] },
  { id: 'lessons',        label: 'Golf Lessons',     keywords: ['lesson', 'coach', 'cat', 'dave', 'training', 'improve', 'drop', 'handicap'] },
  { id: 'putting',        label: 'Putting',           keywords: ['putting', 'putt', 'green', 'distance', 'reading'] },
  { id: 'fitting',        label: 'Club Fitting',     keywords: ['fitting', 'fitted', 'driver', 'custom', 'iron', 'club', 'spec'] },
  { id: 'contest',        label: 'Contest / Promo',  keywords: ['win', 'prize', 'driver', 'free', 'trophy', 'night', 'event'] },
  { id: 'membership',      label: 'Membership',       keywords: ['member', 'perk', 'unlimited', 'save', 'deal'] },
  { id: 'simulator',      label: 'Simulator',         keywords: ['simulator', 'sim', 'indoor', 'rain', 'weather', 'winter'] },
];

const hookThemePerf = hookThemes.map(theme => {
  const posts = igPosts.filter(p => {
    const cap = (p.caption || '').toLowerCase();
    return theme.keywords.some(k => cap.includes(k));
  });
  const avgEng  = posts.length ? posts.reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / posts.length : 0;
  const avgSave = posts.length ? posts.reduce((s, p) => s + (parseInt(p.saveCount) || 0), 0) / posts.length : 0;
  const totalR  = posts.reduce((s, p) => s + (parseInt(p.reach) || 0), 0);
  return {
    theme_id:     theme.id,
    theme_label:  theme.label,
    post_count:   posts.length,
    avg_engagement: parseFloat(avgEng.toFixed(2)),
    avg_saves:      parseFloat(avgSave.toFixed(1)),
    save_rate:      totalR > 0 ? parseFloat((posts.reduce((s, p) => s + (parseInt(p.saveCount) || 0), 0) / totalR * 100).toFixed(2)) : 0,
    total_reach:    totalR,
    conversion_proxy: parseFloat((avgEng + avgSave * 0.5).toFixed(2)), // engagement + saves weighted
  };
}).sort((a, b) => b.conversion_proxy - a.conversion_proxy);

// ── Top converting CTA ───────────────────────────────────────────
const ctaRankings = Object.entries(ctaPerformance)
  .map(([bucket, data]) => ({
    cta_type:   bucket,
    post_count: data.count,
    avg_eng_rate:  parseFloat(data.avgEngRate.toFixed(2)),
    avg_save_rate: parseFloat(data.saveRate.toFixed(2)),
    conversion_signal: parseFloat(data.conversion_signal.toFixed(3)),
    conversion_rank: 0,
  }))
  .sort((a, b) => b.conversion_signal - a.conversion_signal)
  .map((r, i) => ({ ...r, conversion_rank: i + 1 }));

// ── Booking page coverage ────────────────────────────────────────
// Which services have IG posts pointing to their booking pages?
const serviceCoverage = Object.entries(SERVICE_KEYWORDS).map(([service, kws]) => {
  const bookingKw = service.toLowerCase().split(' ')[0];
  const igMentioned = kws.some(k => igText.includes(k));
  const ga4HasPage  = ga4Pages.some(p => (p.path || '').toLowerCase().includes(bookingKw));
  const postCount   = igPosts.filter(p => kws.some(k => (p.caption || '').toLowerCase().includes(k))).length;
  const sessions    = ga4Pages.filter(p => (p.path || '').toLowerCase().includes(bookingKw))
    .reduce((s, p) => s + (parseInt(p.sessions) || 0), 0);
  return {
    service,
    has_ig_content:  igMentioned,
    has_booking_page: ga4HasPage,
    ig_post_count:   postCount,
    ga4_sessions:    sessions,
    coverage_score: (igMentioned ? 2 : 0) + (ga4HasPage ? 1 : 0),
  };
});

// ── Top converting service ──────────────────────────────────────
const topService = serviceCorrelation[0] || { service: 'n/a', ig_signal: 0 };
const topCTA     = ctaRankings[0]          || { cta_type: 'n/a', conversion_signal: 0 };
const topPage    = topBookingPages[0]      || { path: 'n/a', sessions: 0 };
const topTheme   = hookThemePerf[0]       || { theme_label: 'n/a', conversion_proxy: 0 };

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_conversion_attribution.js',

  // Summary signals
  summary: {
    total_ig_posts_analysed: igPosts.slice(0, 30).length,
    total_ga4_pages:         ga4Pages.length,
    booking_sessions:        totalBookingSessions,
    avg_booking_eng_rate:    parseFloat(avgBookingEngagement.toFixed(2)),
    top_converting_service:  topService.service,
    top_converting_cta:      topCTA.cta_type,
    top_booking_page:        topPage.path,
    top_hook_theme:          topTheme.theme_label,
  },

  // Per-CTA performance
  cta_performance: ctaRankings,

  // Per-service IG correlation
  service_correlation: serviceCorrelation,

  // Hook theme performance
  hook_themes: hookThemePerf,

  // Top booking pages
  top_booking_pages: topBookingPages,

  // Service → booking page coverage
  service_coverage: serviceCoverage,

  // Quick wins: high-signal, low-coverage
  quick_wins: serviceCorrelation
    .filter(s => s.ig_signal > 2 && s.save_rate > 1)
    .slice(0, 3)
    .map(s => ({
      service:     s.service,
      ig_signal:   s.ig_signal,
      save_rate:   s.save_rate,
      action:      `Push ${s.service} - ${s.post_count} posts, ${s.save_rate}% save rate, ${s.avg_engagement}% avg eng`,
    })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Conversion attribution: ${OUTPUT}`);
console.log(`   Booking sessions: ${totalBookingSessions} | Top service: ${topService.service}`);
console.log(`   Top CTA: ${topCTA.cta_type} (signal: ${topCTA.conversion_signal.toFixed(3)}) | Top theme: ${topTheme.theme_label}`);
console.log(`   Top booking page: ${topPage.path} (${topPage.sessions} sessions)`);
console.log(`CTA rankings:`);
ctaRankings.slice(0, 4).forEach(c => console.log(`   ${c.conversion_rank}. ${c.cta_type} - eng:${c.avg_eng_rate}% save:${c.avg_save_rate}% sig:${c.conversion_signal.toFixed(3)}`));
console.log(`Service correlation:`);
serviceCorrelation.slice(0, 4).forEach(s => console.log(`   ${s.service}: sig:${s.ig_signal} eng:${s.avg_engagement}% saves:${s.total_saves}`));
