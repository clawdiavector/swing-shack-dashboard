#!/usr/bin/env node
/**
 * run_trend_delta_reporter.js
 * Reads: recommendation-scores.json, reddit-trends.json, blog-trends.json, ig-analytics.json, published-posts.json
 * Produces: trend-delta.json
 *
 * Schema: https://clawdia.io/agents/trend-delta-reporter/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const weekAgo  = new Date(now - 7 * 86400000);
  const prevWeek = new Date(now - 14 * 86400000);

  const recSc    = readJson('recommendation-scores.json') || {};
  const reddit   = readJson('reddit-trends.json') || {};
  const blog     = readJson('blog-trends.json') || {};
  const ig       = readJson('ig-analytics.json') || {};
  const pubPost  = readJson('published-posts.json') || {};

  // ── Hook patterns ────────────────────────────────────────────────
  const doFirst = recSc.do_first || [];
  const topHookNow = doFirst.filter(i => i.type === 'hook').slice(0, 3).map(i => i.recommendation_id);

  // ── CTA patterns ────────────────────────────────────────────────
  const topCTANow = recSc.summary?.top_cta || null;

  // ── Services gaining/losing ─────────────────────────────────────
  const services = recSc.summary?.service_breakdown || {};
  const serviceGain = Object.entries(services).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 3).map(([k]) => k);
  const serviceLose = Object.entries(services).sort((a, b) => (a[1] || 0) - (b[1] || 0)).slice(0, 2).map(([k]) => k);

  // ── Reddit trends ────────────────────────────────────────────────
  const redditTrends = reddit.trends || reddit.hot_pain_points || [];
  const redditNow    = redditTrends.filter(t => !t.fetched_at || new Date(t.fetched_at) >= weekAgo);
  const redditPrev   = redditTrends.filter(t => t.fetched_at && new Date(t.fetched_at) >= prevWeek && new Date(t.fetched_at) < weekAgo);

  // ── IG analytics trend ───────────────────────────────────────────
  const igMetrics = ig.data || [];
  const igNow    = igMetrics.filter(m => m.timestamp && new Date(m.timestamp) >= weekAgo);
  const igPrev    = igMetrics.filter(m => m.timestamp && new Date(m.timestamp) >= prevWeek && new Date(m.timestamp) < weekAgo);

  // Avg engagement
  const avgEngNow = igNow.length > 0 ? Math.round(igNow.reduce((s,m) => s+(m.engagement||0), 0)/igNow.length) : 0;
  const avgEngPrev= igPrev.length > 0 ? Math.round(igPrev.reduce((s,m) => s+(m.engagement||0), 0)/igPrev.length) : 0;
  const engDelta  = avgEngPrev > 0 ? Math.round(((avgEngNow - avgEngPrev) / avgEngPrev) * 100) : (avgEngNow > 0 ? 100 : 0);

  // ── Blog trends ─────────────────────────────────────────────────
  const blogTrends = blog.top_queries || blog.trends || [];
  const topQueryNow = blogTrends.slice(0, 3).map(q => typeof q === 'string' ? q : q.query);

  // ── Published posts delta ───────────────────────────────────────
  const published = pubPost.published || [];
  const pubNow    = published.filter(p => p.published_at && new Date(p.published_at) >= weekAgo);
  const pubPrev   = published.filter(p => p.published_at && new Date(p.published_at) >= prevWeek && new Date(p.published_at) < weekAgo);
  const pubDelta  = pubPrev.length > 0 ? Math.round(((pubNow.length - pubPrev.length) / pubPrev.length) * 100) : (pubNow.length > 0 ? 100 : 0);

  // ── Format distribution shift ────────────────────────────────────
  const formatNow = {};
  pubNow.forEach(p => { const f = p.format || 'static'; formatNow[f] = (formatNow[f]||0) + 1; });
  const formatPrev = {};
  pubPrev.forEach(p => { const f = p.format || 'static'; formatPrev[f] = (formatPrev[f]||0) + 1; });
  const formatShift = Object.keys({ ...formatNow, ...formatPrev }).map(f => ({
    format: f,
    current: formatNow[f] || 0,
    previous: formatPrev[f] || 0,
    delta: (formatNow[f]||0) - (formatPrev[f]||0),
  })).sort((a, b) => b.delta - a.delta);

  // ── Booking intent ──────────────────────────────────────────────
  const bookingSignal = igNow.filter(m => m.booking_intent_signals || m.book_now_clicks).length;
  const bookingDelta  = igNow.length > 0 ? Math.round((bookingSignal / igNow.length) * 100) : 0;

  const trendDelta = {
    schema: 'https://clawdia.io/agents/trend-delta-reporter/v1',
    generated: now.toISOString(),
    period_from: weekAgo.toISOString().split('T')[0],
    period_to: now.toISOString().split('T')[0],
    summary: {
      hook_patterns_rising: topHookNow,
      cta_pattern_rising: topCTANow,
      services_gaining: serviceGain,
      services_losing: serviceLose,
    },
    hook_trends: topHookNow.map(h => ({ hook_id: h, status: 'rising' })),
    cta_trends: topCTANow ? [{ cta: topCTANow, status: 'rising' }] : [],
    service_trends: {
      gaining: serviceGain.map(s => ({ service: s, direction: 'up' })),
      losing: serviceLose.map(s => ({ service: s, direction: 'down' })),
    },
    platform_metrics: {
      instagram: {
        avg_engagement: avgEngNow,
        engagement_delta_pct: engDelta,
        posts_this_week: pubNow.length,
        posts_delta_pct: pubDelta,
        booking_intent_pct: bookingDelta,
      },
    },
    content_format_shift: formatShift,
    reddit_trends: {
      active_topics: redditNow.slice(0,5).map(t => typeof t === 'string' ? t : (t.topic || t.title || '')),
      total_this_week: redditNow.length,
      total_prev_week: redditPrev.length,
    },
    blog_seo_trends: {
      top_queries: topQueryNow,
    },
    week_over_week: {
      published_delta: pubDelta + '%',
      engagement_delta: engDelta + '%',
    },
  };

  fs.writeFileSync(path.join(DATA, 'trend-delta.json'), JSON.stringify(trendDelta, null, 2));
  console.log(`✅ Trend delta reporter`);
  console.log(`   Hooks rising: ${topHookNow.join(', ') || 'none'}`);
  console.log(`   CTA: ${topCTANow || 'none'} | Services gaining: ${serviceGain.join(', ') || 'none'}`);
  console.log(`   IG engagement: ${avgEngNow} (${engDelta > 0 ? '+' : ''}${engDelta}% vs last week) | Booking intent: ${bookingDelta}%`);
  console.log(`   Format shifts: ${formatShift.map(f => `${f.format}:${f.delta > 0 ? '+' : ''}${f.delta}`).join(', ')}`);
}

module.exports = { run };
if (require.main === module) run();