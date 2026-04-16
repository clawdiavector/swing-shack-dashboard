#!/usr/bin/env node
/**
 * fetch_website_insights.js
 * Reads GA4 data + SEO data → generates website intelligence and recommendations
 * Adds to pipeline after Audit stage
 * Produces: pages needing attention, source analysis, booking funnel insights
 */
const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(__dirname, '..', 'data', 'website-insights.json');
const GA4_FILE = path.join(__dirname, '..', 'data', 'ga4-metrics.json');
const SEO_FILE = path.join(__dirname, '..', 'data', 'seo-rankings.json');
const GEO_FILE = path.join(__dirname, '..', 'data', 'geo-audit.json');

function readJson(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch(e) { return {}; }
}

function run() {
  const ga4 = readJson(GA4_FILE);
  const seo = readJson(SEO_FILE);
  const geo = readJson(GEO_FILE);

  const updated = new Date().toISOString();
  const insights = [];
  const recommendations = [];
  const priority_pages = [];
  const weak_ctas = [];

  // 1. Page-level analysis from GA4
  const pages = ga4.pages || [];
  const totalSessions = ga4.total_sessions || 0;

  // High traffic pages with low engagement = CTA problem
  const highTrafficLowEng = pages
    .filter(p => {
      const eng = parseFloat(p.engRate) || 0;
      return eng < 35; // Low engagement
    })
    .sort((a, b) => b.sessions - a.sessions)
    .slice(0, 5);

  highTrafficLowEng.forEach(p => {
    if (p.sessions < 10) return; // Only meaningful traffic
    weak_ctas.push({
      page: p.path,
      sessions: p.sessions,
      engagement: p.engRate,
      severity: p.sessions > 50 ? 'HIGH' : 'MEDIUM',
      likely_issue: parseFloat(p.engRate) < 20 ? 'No CTA visible above fold' : 'Weak or missing CTA',
      fix: 'Add prominent CTA to ' + p.path,
    });
    priority_pages.push(p.path);
  });

  if (weak_ctas.length > 0) {
    recommendations.push({
      type: 'weak_cta',
      priority: 'HIGH',
      message: weak_ctas.length + ' high-traffic pages have <35% engagement — CTA placement likely wrong',
      pages: weak_ctas.map(w => w.page),
    });
    insights.push('⚠️ ' + weak_ctas.length + ' pages with high traffic but weak CTAs');
  }

  // 2. Traffic source analysis
  const sources = ga4.sources || [];
  const organic = sources.filter(s => (s.source || '').toLowerCase().includes('google'));
  const direct = sources.filter(s => s.source === 'direct');
  const social = sources.filter(s => ['instagram', 'facebook', 'tiktok', 'twitter', 'linkedin'].some(x => (s.source || '').toLowerCase().includes(x)));

  const organic_sessions = organic.reduce((s, x) => s + (x.sessions || 0), 0);
  const direct_sessions = direct.reduce((s, x) => s + (x.sessions || 0), 0);
  const social_sessions = social.reduce((s, x) => s + (x.sessions || 0), 0);

  const source_share = {
    organic_pct: totalSessions > 0 ? ((organic_sessions / totalSessions) * 100).toFixed(1) : '0',
    direct_pct: totalSessions > 0 ? ((direct_sessions / totalSessions) * 100).toFixed(1) : '0',
    social_pct: totalSessions > 0 ? ((social_sessions / totalSessions) * 100).toFixed(1) : '0',
    organic_sessions,
    direct_sessions,
    social_sessions,
    total: totalSessions,
  };

  if (organic_sessions > 0) {
    recommendations.push({
      type: 'organic_opportunity',
      priority: organic_sessions > 50 ? 'MEDIUM' : 'LOW',
      message: `${organic_sessions} organic sessions (${source_share.organic_pct}%) — ensure booking CTA is prominent`,
    });
  }

  // 3. Booking funnel analysis
  const bookingPages = pages.filter(p => (p.path || '').includes('book'));
  const checkoutPages = pages.filter(p => (p.path || '').includes('checkout') || (p.path || '').includes('pricing') || (p.path || '').includes('membership'));
  const coachingPages = pages.filter(p => (p.path || '').includes('coach') || (p.path || '').includes('lesson'));
  const fittingPages = pages.filter(p => (p.path || '').includes('fitting') || (p.path || '').includes('club'));

  const funnel = {
    booking_pages: {
      sessions: bookingPages.reduce((s, p) => s + p.sessions, 0),
      avg_engagement: bookingPages.length > 0 ? (bookingPages.reduce((s, p) => s + parseFloat(p.engRate || 0), 0) / bookingPages.length).toFixed(1) + '%' : 'N/A',
      paths: bookingPages.map(p => p.path),
    },
    checkout_pages: {
      sessions: checkoutPages.reduce((s, p) => s + p.sessions, 0),
      avg_engagement: checkoutPages.length > 0 ? (checkoutPages.reduce((s, p) => s + parseFloat(p.engRate || 0), 0) / checkoutPages.length).toFixed(1) + '%' : 'N/A',
      paths: checkoutPages.map(p => p.path),
    },
    coaching_pages: {
      sessions: coachingPages.reduce((s, p) => s + p.sessions, 0),
      avg_engagement: coachingPages.length > 0 ? (coachingPages.reduce((s, p) => s + parseFloat(p.engRate || 0), 0) / coachingPages.length).toFixed(1) + '%' : 'N/A',
      paths: coachingPages.map(p => p.path),
    },
    fitting_pages: {
      sessions: fittingPages.reduce((s, p) => s + p.sessions, 0),
      avg_engagement: fittingPages.length > 0 ? (fittingPages.reduce((s, p) => s + parseFloat(p.engRate || 0), 0) / fittingPages.length).toFixed(1) + '%' : 'N/A',
      paths: fittingPages.map(p => p.path),
    },
  };

  // 4. SEO gap analysis
  const seoKeywords = seo.keywords || [];
  const geoTerms = geo.geo_terms || [];

  const missing_geo_targets = geoTerms.filter(t => {
    const term = (t.term || '').toLowerCase();
    const pagesCovered = pages.filter(p => (p.path || '').toLowerCase().includes(term.split(' ')[0]));
    return pagesCovered.length === 0;
  }).slice(0, 3);

  if (missing_geo_targets.length > 0) {
    recommendations.push({
      type: 'seo_gap',
      priority: 'MEDIUM',
      message: missing_geo_targets.length + ' high-value geo terms have no dedicated landing page',
      terms: missing_geo_targets.map(t => t.term),
    });
    insights.push('📍 ' + missing_geo_targets.length + ' geo targets without dedicated pages');
  }

  // 5. Top-performing pages (what to replicate)
  const topPages = pages
    .filter(p => parseFloat(p.engRate) > 50 && p.sessions > 10)
    .sort((a, b) => parseFloat(b.engRate) - parseFloat(a.engRate))
    .slice(0, 3);

  if (topPages.length > 0) {
    insights.push('✅ Top performing: ' + topPages.map(p => p.path + ' (' + p.engRate + ' eng)').join(', '));
  }

  // 6. South Africa market signals
  const sa_signals = {
    local_search_volume: geo?.local_volume || 'unknown',
    top_city: geo?.top_city || 'Johannesburg',
    competitive_geo_terms: geo?.competitive_terms?.length || 0,
    insight: 'SA golfers searching for indoor golf = high intent. Ensure Johannesburg pages rank for "indoor golf johannesburg".',
  };

  // 7. Booking page conversion signal
  const bookingSessions = funnel.booking_pages.sessions;
  const checkoutSessions = funnel.checkout_pages.sessions;
  if (bookingSessions > 0 && checkoutSessions > 0) {
    recommendations.push({
      type: 'booking_funnel',
      priority: checkoutSessions < bookingSessions * 0.3 ? 'HIGH' : 'MEDIUM',
      message: `Booking page: ${bookingSessions} sessions, Checkout: ${checkoutSessions} sessions — ${checkoutSessions > bookingSessions * 0.3 ? 'healthy ratio' : 'checkout drop-off suspected'}`,
    });
  }

  // 8. Top action items sorted by priority
  const topActions = recommendations
    .filter(r => r.priority === 'HIGH')
    .map(r => r.message)
    .concat(
      recommendations
        .filter(r => r.priority === 'MEDIUM')
        .map(r => r.message)
    )
    .slice(0, 5);

  const result = {
    updated,
    data_window: ga4.data_window || 'last_7_days',
    total_sessions: totalSessions,
    source_share,
    funnel,
    weak_ctas,
    top_pages: topPages.map(p => ({ path: p.path, sessions: p.sessions, engagement: p.engRate })),
    seo_gaps: {
      missing_geo_targets: missing_geo_targets.map(t => t.term),
      high_value_keywords: seoKeywords.filter(k => k.position <= 10 && k.position > 0).map(k => k.keyword).slice(0, 5),
    },
    sa_signals,
    recommendations,
    insights: insights.length > 0 ? insights : ['✅ No critical issues found in website data'],
    top_action_items: topActions,
    summary: {
      health_score: weak_ctas.filter(w => w.severity === 'HIGH').length === 0 ? 'GOOD' : 'NEEDS_ATTENTION',
      critical_issues: weak_ctas.filter(w => w.severity === 'HIGH').length,
      medium_issues: weak_ctas.filter(w => w.severity === 'MEDIUM').length,
      next_priority: topActions[0] || 'No critical issues',
    },
  };

  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log('Website Insights: ' + totalSessions + ' sessions, ' + weak_ctas.length + ' weak CTAs, ' + recommendations.length + ' recommendations');
  console.log('  Health: ' + result.summary.health_score + ' | Critical: ' + result.summary.critical_issues + ' | Next: ' + (result.top_action_items[0] || 'none').slice(0, 60));

  return result;
}

module.exports = { run };
if (require.main === module) run();