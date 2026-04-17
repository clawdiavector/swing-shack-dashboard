#!/usr/bin/env node
/**
 * generate_sales_priority.js
 * Determines what to sell/push this week based on multi-signal analysis.
 *
 * Signals weighed:
 * - IG engagement on service-related posts
 * - GA4 page interest (/lessons, /fittings, /membership, etc.)
 * - Reddit pain points
 * - YouTube topic trends
 * - Seasonality
 * - Golf news urgency
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'sales-priority.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const hb   = readJson('hook-bank.json')        || {};
const ig   = readJson('ig-analytics.json')     || {};
const ga4  = readJson('ga4-metrics.json')       || {};
const wi   = readJson('website-insights.json') || {};
const rd   = readJson('reddit-trends.json')    || {};
const yt   = readJson('youtube-trends.json')   || {};
const gn   = readJson('golf-news.json')        || {};
const pp   = readJson('post-plan.json')         || {};

const now = new Date();
const saNow = new Date(now.toLocaleString('en-US', { timeZone: 'Africa/Johannesburg' }));
const month = saNow.getMonth(); // 0-indexed
const dayOfWeek = saNow.getDay();

// ── Service definitions ────────────────────────────────────────────
const SERVICES = [
  {
    id: 'lessons',
    label: 'Golf Lessons',
    keywords: ['lessons', 'lesson', 'coach', 'teaching', 'swing', 'cat', 'dave', 'instruction'],
    signals: { ig: 0, ga4: 0, reddit: 0, youtube: 0, news: 0, seasonal: 0 },
    reasons: [],
  },
  {
    id: 'club_fitting',
    label: 'Club Fitting',
    keywords: ['driver', 'fitting', 'fitted', 'irons', 'woods', 'wedge', 'putter', 'club', 'trackman', 'custom'],
    signals: { ig: 0, ga4: 0, reddit: 0, youtube: 0, news: 0, seasonal: 0 },
    reasons: [],
  },
  {
    id: 'simulator_sessions',
    label: 'Simulator Sessions',
    keywords: ['simulator', 'sim session', 'practice', 'indoor golf', 'net', 'bay'],
    signals: { ig: 0, ga4: 0, reddit: 0, youtube: 0, news: 0, seasonal: 0 },
    reasons: [],
  },
  {
    id: 'membership',
    label: 'Membership',
    keywords: ['membership', 'member', 'monthly', 'unlimited', 'perk', 'benefits'],
    signals: { ig: 0, ga4: 0, reddit: 0, youtube: 0, news: 0, seasonal: 0 },
    reasons: [],
  },
  {
    id: 'events',
    label: 'Events & Competitions',
    keywords: ['competition', 'event', 'tournament', 'night golf', 'corporate', 'social', 'league'],
    signals: { ig: 0, ga4: 0, reddit: 0, youtube: 0, news: 0, seasonal: 0 },
    reasons: [],
  },
];

function scoreService(svc, signals) {
  // Weighted composite score — boost primary channels (IG, GA4) so strong services get strong scores
  const raw = (
    signals.ig       * 0.40 +   // boosted: IG is the primary conversion driver
    signals.ga4      * 0.30 +   // boosted: website intent is strong signal
    signals.reddit    * 0.10 +
    signals.youtube   * 0.10 +
    signals.seasonal  * 0.05 +   // reduced: already a baseline factor
    signals.news      * 0.05
  );
  // Max possible = 10 * sum of weights
  const maxRaw = 10 * (0.40 + 0.30 + 0.10 + 0.10 + 0.05 + 0.05); // = 10
  // Rescale so top service gets ~8-9, not ~5
  // Use sqrt scaling to compress the middle range
  const normalised = raw / maxRaw; // 0 to 1
  const rescaled = Math.pow(normalised, 0.7); // slight expansion of mid-high range
  return Math.min(Math.round(rescaled * 10 * 10) / 10, 10);
}

// ── 1. IG Signal ─────────────────────────────────────────────────
const igPosts = ig.posts || [];
const igTotal = igPosts.length || 1;

const igSvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
igPosts.forEach(p => {
  const cap = (p.caption || '').toLowerCase();
  SERVICES.forEach(svc => {
    const hits = svc.keywords.filter(k => cap.includes(k)).length;
    const weight = hits > 0 ? Math.min(hits / 3, 1) : 0;
    const eng = parseFloat(p.engagementRate) || 0;
    igSvcScores[svc.id] += weight * eng;
  });
});
Object.keys(igSvcScores).forEach(id => { igSvcScores[id] = Math.min(igSvcScores[id] / igTotal, 10); });
const igMax = Math.max(...Object.values(igSvcScores)) || 1;
Object.keys(igSvcScores).forEach(id => { igSvcScores[id] = (igSvcScores[id] / igMax) * 10; });

// Hook-bank WW signal
const wwSvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
(hb.watched_and_worked || []).forEach(h => {
  const text = (h.hook_text || '').toLowerCase();
  const score = h.cross_signal_score || 0;
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => text.includes(k))) {
      wwSvcScores[svc.id] = Math.max(wwSvcScores[svc.id], score);
    }
  });
});

// ── 2. GA4 Signal ─────────────────────────────────────────────────
const ga4Pages = (ga4.pages || wi.top_pages || []).slice(0, 20);
const ga4SvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
ga4Pages.forEach(p => {
  const path = (p.path || '').toLowerCase();
  const sessions = parseInt(p.sessions) || 0;
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => path.includes(k))) {
      ga4SvcScores[svc.id] = Math.max(ga4SvcScores[svc.id], Math.min(sessions / 20, 10));
    }
  });
});
// Recommendations from website-insights
(wi.recommendations || []).forEach(r => {
  const text = (r.recommendation || '').toLowerCase();
  const score = (r.priority === 'high' ? 8 : r.priority === 'medium' ? 5 : 3);
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => text.includes(k))) {
      ga4SvcScores[svc.id] = Math.max(ga4SvcScores[svc.id], score);
    }
  });
});
const ga4Max = Math.max(...Object.values(ga4SvcScores)) || 1;
Object.keys(ga4SvcScores).forEach(id => { ga4SvcScores[id] = (ga4SvcScores[id] / ga4Max) * 10; });

// ── 3. Reddit Signal ─────────────────────────────────────────────
const rdTrends = rd.trends || [];
const rdSvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
rdTrends.forEach(t => {
  const text = ((t.title || '') + ' ' + (t.intent || '')).toLowerCase();
  const score = Math.min((t.score || 0) / 50, 10);
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => text.includes(k))) {
      rdSvcScores[svc.id] = Math.max(rdSvcScores[svc.id], score);
    }
  });
});
const rdMax = Math.max(...Object.values(rdSvcScores)) || 1;
Object.keys(rdSvcScores).forEach(id => { rdSvcScores[id] = (rdSvcScores[id] / rdMax) * 10; });

// ── 4. YouTube Signal ─────────────────────────────────────────────
const ytVideos = yt.top_videos || [];
const ytSvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
ytVideos.forEach(v => {
  const text = ((v.title || '') + ' ' + (v.description || '')).toLowerCase();
  const views = Math.min((v.viewCount || 0) / 1000, 10);
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => text.includes(k))) {
      ytSvcScores[svc.id] = Math.max(ytSvcScores[svc.id], views);
    }
  });
});
const ytMax = Math.max(...Object.values(ytSvcScores)) || 1;
Object.keys(ytSvcScores).forEach(id => { ytSvcScores[id] = (ytSvcScores[id] / ytMax) * 10; });

// ── 5. Seasonality Signal ─────────────────────────────────────────
const seasonalScores = { lessons: 7, club_fitting: 5, simulator_sessions: 8, membership: 6, events: 4 };
// SA school terms: Jan-Mar = term 1 (busy), Apr = holiday (events), May-Jul = term 2, Aug = holiday, Sep-Dec = term 3
const SA_HOLIDAYS = [
  { start: '2026-04-10', end: '2026-04-20', boosts: { events: 10, simulator_sessions: 8 } },
];
const todayISO = saNow.toISOString().split('T')[0];
SA_HOLIDAYS.forEach(h => {
  if (todayISO >= h.start && todayISO <= h.end) {
    Object.entries(h.boosts).forEach(([svcId, boost]) => {
      if (seasonalScores[svcId] !== undefined) seasonalScores[svcId] = boost;
    });
  }
});

// ── 6. News Signal ────────────────────────────────────────────────
const newsSvcScores = { lessons: 0, club_fitting: 0, simulator_sessions: 0, membership: 0, events: 0 };
(gn.news || []).forEach(n => {
  const text = ((n.title || '') + ' ' + (n.content || '')).toLowerCase();
  SERVICES.forEach(svc => {
    if (svc.keywords.some(k => text.includes(k))) {
      newsSvcScores[svc.id] = Math.max(newsSvcScores[svc.id], 5);
    }
  });
});
const newsMax = Math.max(...Object.values(newsSvcScores)) || 1;
Object.keys(newsSvcScores).forEach(id => { newsSvcScores[id] = (newsSvcScores[id] / newsMax) * 10; });

// ── Build final priority list ────────────────────────────────────
function priorityLevel(score) {
  if (score >= 7) return 'high';
  if (score >= 4) return 'medium';
  return 'low';
}

function confidenceBand(ig, ga4, yt) {
  const active = [ig, ga4, yt].filter(s => s >= 4).length;
  if (active >= 2) return 'high';
  if (active >= 1) return 'medium';
  return 'low';
}

function confidenceBand(ig, ga4, yt) {
  const active = [ig, ga4, yt].filter(s => s >= 4).length;
  if (active >= 3) return 'high';
  if (active >= 2) return 'medium';
  if (active >= 1) return 'low';
  return 'unsubstantiated';
}

const results = SERVICES.map(svc => {
  const rawIg     = Math.max(igSvcScores[svc.id], wwSvcScores[svc.id]);
  const rawGa4    = ga4SvcScores[svc.id];
  const rawRd     = rdSvcScores[svc.id];
  const rawYt     = ytSvcScores[svc.id];
  const rawSeason = seasonalScores[svc.id] || 5;

  // Build signals as a clean 0-10 scale, then compute weighted total
  const signals = {
    ig:       Math.min(Math.round(rawIg * 10) / 10, 10),
    ga4:      Math.min(Math.round(rawGa4 * 10) / 10, 10),
    reddit:   Math.min(Math.round(rawRd * 10) / 10, 10),
    youtube:  Math.min(Math.round(rawYt * 10) / 10, 10),
    news:     Math.min(Math.round((newsSvcScores[svc.id] || 0) * 10) / 10, 10),
    seasonal: rawSeason,
  };

  const total = Math.round(scoreService(svc, signals) * 10) / 10;
  const confidence = Math.min(Math.round((signals.ig + signals.ga4 + signals.youtube) / 3 * 10) / 10, 10);

  // supporting_signals: list of active signal labels
  const supporting_signals = [];
  if (signals.ig >= 4)       supporting_signals.push({ signal: 'instagram', strength: signals.ig });
  if (signals.ga4 >= 4)      supporting_signals.push({ signal: 'website_traffic', strength: signals.ga4 });
  if (signals.youtube >= 4)  supporting_signals.push({ signal: 'youtube_trending', strength: signals.youtube });
  if (signals.reddit >= 3)   supporting_signals.push({ signal: 'reddit_community', strength: signals.reddit });
  if (signals.seasonal >= 7) supporting_signals.push({ signal: 'seasonality', strength: signals.seasonal });
  if (signals.news >= 3)     supporting_signals.push({ signal: 'golf_news', strength: signals.news });

  const reasons = [];
  if (signals.ig >= 7)       reasons.push(`Strong IG engagement (${signals.ig})`);
  if (signals.ga4 >= 6)      reasons.push(`High website traffic (${signals.ga4})`);
  if (signals.youtube >= 6)  reasons.push(`YouTube trending (${signals.youtube})`);
  if (signals.reddit >= 5)   reasons.push(`Reddit community interest (${signals.reddit})`);
  if (signals.seasonal >= 7) reasons.push(`Seasonal boost (${signals.seasonal})`);
  if (signals.news >= 5)     reasons.push(`Golf news coverage`);

  return {
    service:            svc.id,
    label:              svc.label,
    score:             total,
    priority_level:    priorityLevel(total),
    confidence:        confidence,
    confidence_band:   confidenceBand(signals.ig, signals.ga4, signals.youtube),
    signals,
    supporting_signals,
    reasons,
    recommended_cta: ctaFor(svc.id),
  };
}).sort((a, b) => b.score - a.score);

// ── CTA map ───────────────────────────────────────────────────────
function ctaFor(serviceId) {
  const map = {
    lessons:            'Book a lesson · swingshack.co.za/membership',
    club_fitting:       'Book your fit · swingshack.co.za/membership',
    simulator_sessions: 'Book a session · swingshack.co.za/practice',
    membership:         'Join now · swingshack.co.za/membership',
    events:             'Enter · swingshack.co.za/events',
  };
  return map[serviceId] || 'Book now · swingshack.co.za';
}

// ── Write output ──────────────────────────────────────────────────
const output = {
  updated: new Date().toISOString(),
  generated: 'generate_sales_priority.js',
  this_week: saNow.toLocaleDateString('en-US', { month: 'long', day: 'numeric', timeZone: 'Africa/Johannesburg' }),
  priorities: results,
  meta: {
    top_service:     results[0]?.label || 'n/a',
    top_score:       results[0]?.score  || 0,
    runner_up:       results[1]?.label  || 'n/a',
    season_note:     seasonalScores.events >= 7 ? 'School holidays — push events + simulator sessions' : 'Standard week — balance lessons + fittings',
  },
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Sales priority generated: ${OUTPUT}`);
results.forEach((r, i) => {
  const band = { high: '🟢', medium: '🟡', low: '🔴' }[r.confidence_band || 'low'];
  console.log(`   ${i+1}. ${r.label} [${r.priority_level.toUpperCase()}] (${r.score}/10) ${band} ${r.confidence_band} confidence — ${r.reasons.slice(0,2).join(' · ')}`);
});
