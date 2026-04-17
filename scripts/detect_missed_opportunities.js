#!/usr/bin/env node
/**
 * detect_missed_opportunities.js
 * Finds content gaps: high-performing topics with no follow-up,
 * trending keywords with no post, high-traffic pages with no matching content,
 * hook winners not reused, sale angles not pushed despite demand.
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'missed-opportunities.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const hb   = readJson('hook-bank.json')        || {};
const ci   = readJson('content-ideas.json')     || {};
const ig   = readJson('ig-analytics.json')     || {};
const ga4  = readJson('ga4-metrics.json')       || {};
const wi   = readJson('website-insights.json') || {};
const rd   = readJson('reddit-trends.json')    || {};
const yt   = readJson('youtube-trends.json')   || {};
const seo  = readJson('seo-rankings.json')     || {};

const opportunities = [];

// ── 1. Hook winners not reused ─────────────────────────────────
const winners = (hb.watched_and_worked || []).filter(h => (h.ig_proof_score || 0) >= 8);
winners.forEach(w => {
  const relatedIdeas = (ci.ideas || []).filter(i =>
    (i.title || i.hook || '').toLowerCase().includes(w.youtube_topic_match?.[0] || '')
  );
  if (relatedIdeas.length < 2) {
    opportunities.push({
      type:     'hook_winner_not_reused',
      category: 'follow_up_gap',
      severity: 'high',
      hook:   w.hook_text,
      topic:  w.youtube_topic_match?.[0] || 'unknown',
      ig_score: w.ig_proof_score,
      suggestion: `Hook scored ${w.ig_proof_score} on IG. No follow-up posts found for "${w.youtube_topic_match?.[0]}". Push this angle.`,
      why:    `IG proof: ${w.ig_proof_score} — strong performer with no refresh`,
    });
  }
});

// ── 2. High-traffic page with no matching content ───────────────
const ga4Pages = ga4.pages || wi.top_pages || [];
const igCaps = ((ig.posts || []).map(p => (p.caption || '').toLowerCase()));
ga4Pages.slice(0, 10).forEach(p => {
  const pgPath = (p.path || '/').replace(/\//g, ' ');
  const sessions = parseInt(p.sessions) || 0;
  if (sessions < 20) return;
  const matched = igCaps.filter(c => pgPath.split(' ').some(w => w.length > 3 && c.includes(w)));
  if (matched.length === 0) {
    opportunities.push({
      type:     'traffic_no_content',
      category: 'content_gap',
      severity: sessions > 50 ? 'high' : 'medium',
      page:   p.path || '/',
      sessions,
      suggestion: `Page "${p.path}" gets ${sessions} sessions but no IG post links to it. Create content.`,
      why:    `${sessions} sessions with no social presence`,
    });
  }
});

// ── 3. Reddit pain point with no IG post ────────────────────────
const rdTrends = rd.trends || [];
rdTrends.filter(t => (t.score || 0) >= 30).forEach(t => {
  const title = (t.title || '').toLowerCase();
  const matchedPost = (ig.posts || []).find(p => (p.caption || '').toLowerCase().includes(
    title.split(' ').find(w => w.length > 4) || ''
  ));
  if (!matchedPost) {
    opportunities.push({
      type:     'reddit_pain_no_ig',
      category: 'content_gap',
      severity: (t.score || 0) >= 80 ? 'high' : 'medium',
      reddit_title: t.title,
      subreddit: t.subreddit || 'golf',
      reddit_score: t.score,
      suggestion: `r/${t.subreddit} is discussing "${t.title}". IG hasn't covered this.`,
      why:    `Reddit score: ${t.score} — community pain point uncovered`,
    });
  }
});

// ── 4. Trending YouTube topic with no IG presence ──────────────
const ytTopics = yt.topics || [];
const ytSvcMap = {
  lessons:       ['lessons', 'swing', 'teaching', 'coach'],
  driver:        ['driver', 'drive', 'tee'],
  short_game:    ['putting', 'chipping', 'pitching', 'putt'],
  fitting:       ['fitting', 'fitted', 'clubs', 'irons'],
  slice_fix:     ['slice', 'hook', 'correction', 'fix'],
};
Object.entries(ytSvcMap).forEach(([svc, kwArr]) => {
  const ytMatch = (yt.top_videos || []).filter(v =>
    kwArr.some(k => (v.title || '').toLowerCase().includes(k))
  );
  if (ytMatch.length === 0) return;
  const igMatch = igCaps.filter(c => kwArr.some(k => c.includes(k)));
  if (igMatch.length === 0) {
    opportunities.push({
      type:     'youtube_trend_no_ig',
      category: 'content_gap',
      severity: 'medium',
      topic:  svc,
      yt_video_count: ytMatch.length,
      yt_examples: ytMatch.slice(0, 2).map(v => v.title),
      suggestion: `YouTube has ${ytMatch.length} videos on "${svc}" but IG hasn't covered it.`,
      why:    `${ytMatch.length} YouTube videos trending on this topic`,
    });
  }
});

// ── 5. SEO rising keyword with no IG post ──────────────────────
(seo.rising_keywords || []).slice(0, 5).forEach(kw => {
  const keyword = (kw.keyword || kw.term || '').toLowerCase();
  if (keyword.length < 4) return;
  const matchedPost = (ig.posts || []).find(p => (p.caption || '').toLowerCase().includes(keyword));
  if (!matchedPost) {
    opportunities.push({
      type:     'seo_rising_no_content',
      category: 'seo_gap',
      severity: 'medium',
      keyword,
      rank:   kw.current_rank || '?',
      delta:  kw.delta || kw.delta_7d || 0,
      suggestion: `"${keyword}" is rising in SEO but no IG post covers it.`,
      why:    `Rank: ${kw.current_rank || '?'}, Delta: +${kw.delta || kw.delta_7d || 0}`,
    });
  }
});

// ── 6. Sale/product angle not pushed despite demand ─────────────
const SALE_ANGLES = [
  { id: 'lessons_value',  kw: ['save', 'deal', 'package', 'lesson', 'coach'], label: 'Lessons value proposition' },
  { id: 'fitting_promo',  kw: ['fitting', 'fitted', 'custom'], label: 'Club fitting promotion' },
  { id: 'membership_benefits', kw: ['member', 'membership', 'perks', 'unlimited'], label: 'Membership benefits' },
  { id: 'event_promo',    kw: ['night golf', 'event', 'tournament', 'competition'], label: 'Events promotion' },
];
const igText = (ig.posts || []).map(p => (p.caption || '').toLowerCase()).join(' ');
SALE_ANGLES.forEach(angle => {
  const saleTerms = angle.kw.filter(k => igText.includes(k));
  if (saleTerms.length === 0) {
    opportunities.push({
      type:     'sale_angle_not_pushed',
      category: 'offer_gap',
      severity: 'low',
      angle:  angle.label,
      keywords_found: saleTerms,
      suggestion: `"${angle.label}" hasn't been pushed this week despite relevance.`,
      why:    'No sale/promo angle found in recent IG posts',
    });
  }
});

// ── Deduplicate by type+hook/page ───────────────────────────────
const seen = new Set();
const deduped = opportunities.filter(o => {
  const key = o.type + (o.hook || o.keyword || o.page || o.topic || '').substring(0, 30);
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
}).slice(0, 10); // cap at 10

// Sort by severity then by type
const severityOrder = { high: 0, medium: 1, low: 2 };
deduped.sort((a, b) => {
  if (severityOrder[a.severity] !== severityOrder[b.severity]) {
    return severityOrder[a.severity] - severityOrder[b.severity];
  }
  return 0;
});

// ── Write output ──────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'detect_missed_opportunities.js',
  count:     deduped.length,
  by_severity: {
    high:   deduped.filter(o => o.severity === 'high').length,
    medium: deduped.filter(o => o.severity === 'medium').length,
    low:    deduped.filter(o => o.severity === 'low').length,
  },
  by_category: {
    follow_up_gap:   deduped.filter(o => o.category === 'follow_up_gap').length,
    content_gap:     deduped.filter(o => o.category === 'content_gap').length,
    seo_gap:         deduped.filter(o => o.category === 'seo_gap').length,
    conversion_gap:  deduped.filter(o => o.category === 'conversion_gap').length,
    offer_gap:       deduped.filter(o => o.category === 'offer_gap').length,
  },
  opportunities: deduped,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Missed opportunities detected: ${OUTPUT}`);
console.log(`   Total: ${deduped.length} | High: ${output.by_severity.high} | Medium: ${output.by_severity.medium} | Low: ${output.by_severity.low}`);
console.log(`   Categories: ${Object.entries(output.by_category).filter(([,n]) => n > 0).map(([k,n]) => `${k}×${n}`).join(', ')}`);
deduped.forEach((o, i) => {
  console.log(`   ${i+1}. [${o.severity.toUpperCase()}] ${o.category} → ${o.type}`);
  console.log(`      → ${o.suggestion.substring(0, 75)}`);
});
