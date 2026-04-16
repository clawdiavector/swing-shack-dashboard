#!/usr/bin/env node
/**
 * fetch_website_insights.js
 * Reads GA4 + SEO + GEO data → structured website intelligence
 * Each recommendation has: issue, severity, evidence, recommended_fix, source_metric
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
  const structured_recs = [];
  const weak_ctas = [];

  const pages = ga4.pages || [];
  const totalSessions = ga4.total_sessions || 0;

  // High traffic + low engagement = CTA problem
  const highTrafficLowEng = pages
    .filter(p => {
      const eng = parseFloat(p.engRate) || 0;
      return eng < 35 && p.sessions >= 10;
    })
    .sort((a, b) => b.sessions - a.sessions)
    .slice(0, 5);

  highTrafficLowEng.forEach(p => {
    weak_ctas.push({
      page: p.path,
      sessions: p.sessions,
      engagement: p.engRate,
      severity: p.sessions > 50 ? 'HIGH' : 'MEDIUM',
      likely_issue: parseFloat(p.engRate) < 20 ? 'No CTA visible above fold' : 'Weak or missing CTA',
      fix: 'Add prominent CTA to ' + p.path,
    });
  });

  // Source analysis
  const sources = ga4.sources || [];
  const organic_sessions = sources
    .filter(s => (s.source || '').toLowerCase().includes('google'))
    .reduce((s, x) => s + (x.sessions || 0), 0);
  const direct_sessions = sources
    .filter(s => s.source === 'direct')
    .reduce((s, x) => s + (x.sessions || 0), 0);
  const social_sessions = sources
    .filter(s => ['instagram', 'facebook', 'tiktok', 'twitter', 'linkedin']
      .some(x => (s.source || '').toLowerCase().includes(x)))
    .reduce((s, x) => s + (x.sessions || 0), 0);

  const source_share = {
    organic_pct: totalSessions > 0 ? ((organic_sessions / totalSessions) * 100).toFixed(1) : '0',
    direct_pct: totalSessions > 0 ? ((direct_sessions / totalSessions) * 100).toFixed(1) : '0',
    social_pct: totalSessions > 0 ? ((social_sessions / totalSessions) * 100).toFixed(1) : '0',
    organic_sessions, direct_sessions, social_sessions, total: totalSessions,
  };

  // Funnel
  const bookingPages = pages.filter(p => (p.path || '').includes('book'));
  const checkoutPages = pages.filter(p => (p.path || '').includes('checkout') || (p.path || '').includes('pricing') || (p.path || '').includes('membership'));
  const coachingPages = pages.filter(p => (p.path || '').includes('coach') || (p.path || '').includes('lesson'));
  const fittingPages = pages.filter(p => (p.path || '').includes('fitting') || (p.path || '').includes('club'));

  const funnel = {
    booking_pages: { sessions: bookingPages.reduce((s, p) => s + p.sessions, 0), paths: bookingPages.map(p => p.path) },
    checkout_pages: { sessions: checkoutPages.reduce((s, p) => s + p.sessions, 0), paths: checkoutPages.map(p => p.path) },
    coaching_pages: { sessions: coachingPages.reduce((s, p) => s + p.sessions, 0), paths: coachingPages.map(p => p.path) },
    fitting_pages: { sessions: fittingPages.reduce((s, p) => s + p.sessions, 0), paths: fittingPages.map(p => p.path) },
  };

  // REC 1: Weak CTA pages
  if (weak_ctas.length > 0) {
    const high = weak_ctas.filter(w => w.severity === 'HIGH');
    structured_recs.push({
      issue: 'High-traffic pages with weak CTA',
      severity: high.length > 0 ? 'HIGH' : 'MEDIUM',
      evidence: high.length + ' page(s) with >50 sessions but <20% engagement. Pages: ' + weak_ctas.map(w => w.page + ' (' + w.sessions + ' sess, ' + w.engagement + ' eng)').join('; '),
      recommended_fix: 'Add prominent \"Book Now\" CTA to: ' + weak_ctas.map(w => w.page).join(', ') + '. Test button contrast, size, and above-fold placement.',
      source_metric: 'ga4.pages.engagementRate',
    });
    insights.push('⚠️ ' + weak_ctas.length + ' pages with high traffic but weak CTAs');
  }

  // REC 2: Booking funnel drop-off
  const bookingSess = funnel.booking_pages.sessions;
  const checkoutSess = funnel.checkout_pages.sessions;
  if (bookingSess > 0 && checkoutSess > 0) {
    const ratio = checkoutSess / bookingSess;
    structured_recs.push({
      issue: 'Booking funnel drop-off detected',
      severity: ratio < 0.2 ? 'HIGH' : ratio < 0.3 ? 'MEDIUM' : 'LOW',
      evidence: bookingSess + ' booking page sessions → ' + checkoutSess + ' checkout sessions (' + (ratio * 100).toFixed(1) + '% conversion rate)',
      recommended_fix: ratio < 0.2
        ? 'URGENT: Review booking flow for friction. Likely causes: form too long, page speed, or unclear next step. Test a single-field \"Book a Session\" CTA first.'
        : 'Review booking confirmation flow. Ensure checkout page loads fast and has minimal form fields.',
      source_metric: 'ga4.funnel.booking_to_checkout_ratio',
    });
    insights.push('⚠️ Booking funnel: ' + bookingSess + ' → ' + checkoutSess + ' checkout (' + (ratio * 100).toFixed(0) + '% conv)');
  }

  // REC 3: Organic traffic without clear booking path
  if (organic_sessions > 0) {
    structured_recs.push({
      issue: 'Organic traffic without clear booking path',
      severity: organic_sessions > 50 ? 'MEDIUM' : 'LOW',
      evidence: organic_sessions + ' organic sessions (' + source_share.organic_pct + '% of all traffic)',
      recommended_fix: 'Ensure every high-engagement page has a \"Book a TrackMan Session\" CTA visible in first viewport scroll. TrackMan keyword intent = high commercial intent.',
      source_metric: 'ga4.sessions.organic',
    });
  }

  // REC 4: SEO geo gap
  const missingGeo = (geo.geo_terms || []).filter(t => {
    const term = (t.term || '').toLowerCase();
    return !(pages || []).some(p => (p.path || '').toLowerCase().includes(term.split(' ')[0]));
  }).slice(0, 3);

  if (missingGeo.length > 0) {
    structured_recs.push({
      issue: 'Geo search terms without dedicated landing pages',
      severity: 'MEDIUM',
      evidence: missingGeo.length + ' high-value geo terms with no matching page: ' + missingGeo.map(t => t.term).join(', '),
      recommended_fix: 'Create dedicated landing pages for: ' + missingGeo.map(t => '"' + t.term + '"').join(', ') + '. Use city + service + \"Johannesburg\" in title and H1.',
      source_metric: 'geo.terms.missing_coverage',
    });
    insights.push('📍 ' + missingGeo.length + ' geo targets without dedicated pages');
  }

  // REC 5: GA4 sessions high but no insights
  if (totalSessions > 100 && (!ga4.insights || !ga4.insights.recommendations || ga4.insights.recommendations.length === 0)) {
    structured_recs.push({
      issue: 'High GA4 sessions but zero recommendations generated',
      severity: 'LOW',
      evidence: totalSessions + ' sessions tracked but 0 recommendations in ga4-metrics.json',
      recommended_fix: 'Check GA4 account: ensure engagement events (scroll, CTA click, form submit) are firing. Check Property ID 427380680 has Data API enabled.',
      source_metric: 'ga4.insights.count',
    });
  }

  // REC 6: High sessions but no top pages
  if (totalSessions > 100 && pages.length === 0) {
    structured_recs.push({
      issue: 'GA4 reports sessions but no page data',
      severity: 'MEDIUM',
      evidence: totalSessions + ' total sessions but 0 pages in GA4 response',
      recommended_fix: 'Check GA4 Data API dimensions: pagePath dimension may be blocked or require different scope. Test with sessions dimension only.',
      source_metric: 'ga4.pages.count',
    });
  }

  // Top pages
  const topPages = pages
    .filter(p => parseFloat(p.engRate) > 50 && p.sessions > 10)
    .sort((a, b) => parseFloat(b.engRate) - parseFloat(a.engRate))
    .slice(0, 3);

  if (topPages.length > 0) {
    insights.push('✅ Top: ' + topPages.map(p => p.path + ' (' + p.engRate + ' eng)').join(', '));
  } else {
    insights.push('ℹ️ No pages with >50% engagement and >10 sessions — benchmark is high');
  }

  const result = {
    updated,
    data_window: ga4.data_window || 'last_7_days',
    total_sessions: totalSessions,
    source_share,
    funnel,
    weak_ctas,
    top_pages: topPages.map(p => ({ path: p.path, sessions: p.sessions, engagement: p.engRate })),
    recommendations: structured_recs,
    insights,
    summary: {
      health_score: structured_recs.some(r => r.severity === 'HIGH') ? 'NEEDS_ATTENTION'
        : structured_recs.some(r => r.severity === 'MEDIUM') ? 'FAIR' : 'GOOD',
      critical_count: structured_recs.filter(r => r.severity === 'HIGH').length,
      medium_count: structured_recs.filter(r => r.severity === 'MEDIUM').length,
      low_count: structured_recs.filter(r => r.severity === 'LOW').length,
      top_priority: structured_recs.find(r => r.severity === 'HIGH')?.issue
        || structured_recs.find(r => r.severity === 'MEDIUM')?.issue
        || 'No critical issues',
    },
  };

  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log('Website Insights: ' + totalSessions + ' sessions, recs=' + structured_recs.length + ' (HIGH=' + result.summary.critical_count + ' MED=' + result.summary.medium_count + ')');
  console.log('  Health: ' + result.summary.health_score + ' | Top: ' + result.summary.top_priority?.slice(0, 70));

  return result;
}

module.exports = { run };
if (require.main === module) run();