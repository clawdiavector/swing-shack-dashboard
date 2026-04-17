#!/usr/bin/env node
/**
 * generate_scaling_recommendations.js
 * Finds what's working and should be scaled, repeated, or turned into a series.
 * Outputs: data/scaling-recommendations.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'scaling-recommendations.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const hooks    = readJson('hook-bank.json')               || {};
const ig      = readJson('ig-analytics.json')             || {};
const sales   = readJson('sales-priority.json')           || {};
const ctaPerf = readJson('cta-performance.json')         || {};
const conv    = readJson('conversion-attribution.json')   || {};
const outcomes= readJson('recommendation-outcomes.json') || {};
const plan    = readJson('post-plan.json')               || {};

const igPosts = ig.posts || [];
const ww      = hooks.watched_and_worked || [];

// ── Proven winners ─────────────────────────────────────────────
// Win rate by type from outcomes
const winRates  = {};
(outcomes.type_win_rates || []).forEach(r => { winRates[r.type] = r; });

// ── 1. Hooks to repeat as a series ───────────────────────────
const provenAndTrending = ww.filter(h =>
  (h.ig_proof_score || 0) >= 8 &&
  (h.cross_signal_score || 0) >= 6
).slice(0, 4);

const hookSeries = provenAndTrending.map(h => {
  const topic = h.youtube_topic_match?.[0] || 'golf';
  // Check if this topic already has a series scheduled
  const scheduled = (plan.plan || []).filter(p =>
    (p.hook || '').toLowerCase().includes(topic.toLowerCase())
  );
  return {
    type:          'hook_series',
    action:        'Turn into recurring series',
    topic,
    hook:          h.hook_text,
    ig_score:      h.ig_proof_score,
    cross_score:   parseFloat((h.cross_signal_score || 0).toFixed(1)),
    reason:        `IG ${h.ig_proof_score} + cross-signal ${(h.cross_signal_score || 0).toFixed(1)} — proven on multiple channels`,
    recommended_schedule: '1x per week for 4 weeks',
    scale_action:   'Post same angle weekly, vary the data point each time',
    owner:          topic.includes('lesson') || topic.includes('putt') ? 'Coach Cat' : 'Swing Shack page',
    channel:        topic.includes('lesson') || topic.includes('putt') ? 'IG Reel' : 'IG Static',
    urgency:        (h.ig_proof_score || 0) >= 9 ? 'today' : 'this_week',
    confidence:    5,
    already_scheduled: scheduled.length > 0,
  };
});

// ── 2. CTAs to scale ──────────────────────────────────────────
const topCTA = (ctaPerf.cta_rankings || [])[0];
const ctaScale = topCTA ? [{
  type:          'cta_scale',
  action:        `Scale ${topCTA.label} across all posts`,
  cta_type:      topCTA.cta_type,
  current_perf: `eng ${topCTA.avg_engagement_rate}% | save rate ${topCTA.avg_save_rate}% | signal ${topCTA.conversion_signal}`,
  recommendation: `Increase ${topCTA.label.toLowerCase()} CTA usage by 40% — highest conversion signal of all CTA types`,
  expected_impact: 'save_rate +0.3% | booking_intent +15%',
  owner:         'Swing Shack page',
  urgency:       'this_week',
  confidence:    4,
  why:           `${topCTA.cta_type} has best conversion signal (${topCTA.conversion_signal})`,
}] : [];

// ── 3. Service pushes to scale ──────────────────────────────────
const topSvc = (sales.priorities || [])[0];
const serviceScale = topSvc ? [{
  type:          'service_scale',
  action:        `Push ${topSvc.label} harder this week`,
  service:       topSvc.label,
  score:         topSvc.score,
  reason:        `${topSvc.score}/10 — ${topSvc.reasons?.[0] || ''}`,
  recommendation: `Create ${topSvc.score >= 7 ? 3 : 2} posts this week around ${topSvc.label}`,
  expected_impact: 'booking sessions +20-30%',
  owner:          topSvc.label === 'Golf Lessons' ? 'Coach Cat' : topSvc.label === 'Club Fitting' ? 'Divan' : 'Swing Shack page',
  urgency:        topSvc.score >= 8 ? 'today' : 'this_week',
  confidence:    4,
  why:           `Service priority #1 with score ${topSvc.score}/10 — strong multi-signal consensus`,
}] : [];

// ── 4. Winning retargeting patterns ─────────────────────────────
const winningRetarget = (outcomes.type_win_rates || [])
  .filter(r => r.win_rate >= 60 && r.total >= 1)
  .slice(0, 2)
  .map(r => ({
    type:          'retarget_pattern_scale',
    action:        `Scale winning retargeting pattern: ${r.type}`,
    retarget_type: r.type,
    win_rate:      r.win_rate,
    total_executed: r.total,
    recommendation: `Repeat the "${r.type}" pattern — ${r.win_rate}% win rate from ${r.total} executions`,
    expected_impact: 'win rate sustains above 60% if pattern is maintained',
    owner:         'Swing Shack page',
    urgency:       'today',
    confidence:    4,
    why:           `${r.type} has ${r.win_rate}% win rate — clear winner among retargeting types`,
  }));

// ── 5. Hook angles to turn into landing pages ──────────────────
const topHook = ww[0];
const landingPageCandidates = topHook && topHook.ig_proof_score >= 9 ? [{
  type:          'landing_page',
  action:        `Turn "${(topHook.youtube_topic_match?.[0] || 'top hook').substring(0, 30)}" into a landing page`,
  hook:          topHook.hook_text,
  ig_score:      topHook.ig_proof_score,
  recommendation: `Create dedicated landing page for ${topHook.youtube_topic_match?.[0]} topic — high IG scorer deserves a conversion page`,
  suggested_url: `/trackman-${(topHook.youtube_topic_match?.[0] || 'golf').toLowerCase().replace(/\s/g, '-')}`,
  owner:         'Swing Shack page',
  urgency:       'this_week',
  confidence:    3,
  why:           `Hook scored ${topHook.ig_proof_score} on IG — high intent audience deserves a landing destination`,
}] : [];

// ── 6. Email nurture candidates ─────────────────────────────────
const highSavePosts = igPosts
  .filter(p => (parseInt(p.saveCount) || 0) > 5 && (parseInt(p.reach) || 0) > 50)
  .sort((a, b) => (parseInt(b.saveCount) || 0) / (parseInt(b.reach) || 1) - (parseInt(a.saveCount) || 0) / (parseInt(a.reach) || 1))
  .slice(0, 2);

const emailCandidates = highSavePosts.map(p => ({
  type:          'email_nurture',
  action:        `Nurture people who saved this post — start email sequence`,
  post_caption:  (p.caption || '').substring(0, 60),
  saves:         parseInt(p.saveCount) || 0,
  reach:        parseInt(p.reach) || 0,
  recommendation: `People who saved this post are high-intent. Send a 3-email sequence: value + CTA + urgency`,
  email_theme:   (p.caption || '').substring(0, 40),
  owner:        'Swing Shack page',
  urgency:       'this_week',
  confidence:    3,
  why:           `${parseInt(p.saveCount) || 0} saves — these users took action, nurture them to book`,
}));

// ── Combine ─────────────────────────────────────────────────────
const allScale = [
  ...winningRetarget,
  ...ctaScale,
  ...serviceScale,
  ...hookSeries.filter(h => !h.already_scheduled),
  ...landingPageCandidates,
  ...emailCandidates,
].slice(0, 8);

allScale.sort((a, b) => (b.confidence || 3) - (a.confidence || 3));

// ── Write ───────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_scaling_recommendations.js',
  summary: {
    total:           allScale.length,
    hook_series:     hookSeries.filter(h => !h.already_scheduled).length,
    cta_scales:      ctaScale.length,
    service_scales:  serviceScale.length,
    retarget_scales: winningRetarget.length,
    landing_pages:   landingPageCandidates.length,
    email_nurtures:  emailCandidates.length,
  },
  recommendations: allScale.map((r, i) => ({ ...r, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Scaling recommendations: ${OUTPUT}`);
console.log(`   Total: ${allScale.length}`);
allScale.slice(0, 5).forEach((r, i) => {
  console.log(`   ${i+1}. [${r.type}] ${r.action} | ${r.owner} | conf:${r.confidence}`);
  console.log(`      Why: ${(r.why || '').substring(0, 70)}`);
});
