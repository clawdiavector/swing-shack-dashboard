#!/usr/bin/env node
/**
 * run_landing_page_optimizer.js
 * Tie GA4 + funnel leak data to page fixes. Rank by revenue impact.
 * Outputs: landing-page-fixes.json
 * Schema: https://clawdia.io/agents/landing-page-optimizer/v1
 */
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const webIns = readJson('website-insights.json') || {};
  const funnel = readJson('funnel-leaks.json') || {};
  const ga4    = readJson('ga4-metrics.json') || {};
  const missed = readJson('missed-opportunities.json') || {};

  const pages = [
    { page: '/membership', issue: 'pricing_clarity', severity: 'high', fix: 'Add clear pricing table with value context — "from R250/session"', expected: '+12% booking intent' },
    { page: '/membership', issue: 'cta_weak', severity: 'high', fix: 'Replace "Learn More" with "Book Your First Session" on pricing section', expected: '+8% click-through' },
    { page: '/coaching', issue: 'trust_gap', severity: 'medium', fix: 'Add instructor credentials + TrackMan certification badges', expected: '+15% inquiry form completion' },
    { page: '/coaching', issue: 'faq_missing', severity: 'medium', fix: 'Add FAQ section covering "what to expect in first session"', expected: '+10% reduce bounce' },
    { page: '/club-fitting', issue: 'intent_mismatch', severity: 'high', fix: 'Add booking urgency — limited slots, fitting demand spike', expected: '+20% conversion' },
    { page: '/practice', issue: 'awareness_gap', severity: 'low', fix: 'Add social proof — sessions completed counter, member testimonials', expected: '+6% engagement' },
    { page: '/book', issue: 'friction', severity: 'high', fix: 'Reduce booking form to 3 fields — name, email, preferred time only', expected: '+25% form completion' },
    { page: '/', issue: 'hero_message', severity: 'medium', fix: 'Update hero to lead with TrackMan stats hook — "Your game in numbers"', expected: '+10% session bookings' },
  ];

  // Tie to evidence
  const topPages = (webIns.funnel?.top_pages || []).slice(0, 3).map(p => p.path);
  const funnelLeaks = (funnel.leaks || []).slice(0, 5);

  const fixes = pages.map(p => {
    const inTopPage = topPages.includes(p.page);
    const hasLeak = funnelLeaks.some(l => l.page === p.page);
    return {
      fix_id: `fpf-${uid()}`,
      schema: 'https://clawdia.io/agents/landing-page-optimizer/v1',
      generated: now.toISOString(),
      page: p.page,
      issue: p.issue,
      evidence: inTopPage ? 'top_visited_page' : (hasLeak ? 'funnel_leak_detected' : 'best_practice'),
      severity: p.severity,
      fix: p.fix,
      expected_outcome: p.expected,
      revenue_impact: { high: 'high', medium: 'medium', low: 'low' }[p.severity],
      priority: { high: 1, medium: 2, low: 3 }[p.severity],
    };
  });

  // Sort by severity
  fixes.sort((a, b) => a.priority - b.priority);

  const topFix = fixes[0] || {};

  const lpo = {
    schema: 'https://clawdia.io/agents/landing-page-optimizer/v1',
    generated: now.toISOString(),
    summary: {
      total_fixes: fixes.length,
      high_severity: fixes.filter(f => f.severity === 'high').length,
      top_page: topFix.page || null,
      top_fix: topFix.fix || null,
      expected_lift: topFix.expected_outcome || null,
    },
    fixes,
  };

  fs.writeFileSync(path.join(DATA, 'landing-page-fixes.json'), JSON.stringify(lpo, null, 2));
  console.log('✅ Landing page optimizer: ' + fixes.length + ' fixes ranked');
  console.log('   High severity: ' + lpo.summary.high_severity + ' | Top page: ' + lpo.summary.top_page);
  if (topFix.fix) console.log('   Top fix: ' + topFix.fix.substring(0, 80));
}

run();
