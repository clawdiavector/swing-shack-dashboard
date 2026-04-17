#!/usr/bin/env node
/**
 * generate_recommendation_outcomes.js
 * Compares recommendations against executed posts to measure what actually worked.
 * Practical attribution: hook/CTA match + GA4 booking traffic movement.
 * Output: data/recommendation-outcomes.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'recommendation-outcomes.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const ig        = readJson('ig-analytics.json')                 || {};
const ga4       = readJson('ga4-metrics.json')                  || {};
const retarget  = readJson('retargeting-recommendations.json') || {};
const plan      = readJson('post-plan.json')                    || {};
const sales     = readJson('sales-priority.json')              || {};
const recScores = readJson('recommendation-scores.json')       || {};

const igPosts = ig.posts || [];
const ga4Pages = ga4.pages || [];

// ── Stable ID generation ─────────────────────────────────────────
function makeRecId(type, topic, hook) {
  const str = `${type}:${(topic || hook || '').substring(0, 30).toLowerCase().trim()}`;
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // keep as 32-bit int
  }
  return `rec_${Math.abs(hash).toString(16).padStart(8, '0')}`;
}

// ── Assign IDs to all recommendations ─────────────────────────
const allRecommendations = [];

// Post-plan recommendations
(plan.plan || []).forEach(p => {
  if (!p.hook) return;
  const rec = {
    recommendation_id: makeRecId('post_plan', p.hook, null),
    source:          'post_plan',
    type:            'post_plan',
    topic:           p.topics?.[0] || p.objective || 'general',
    hook:            p.hook,
    cta:             p.cta,
    channel:         'IG Static',
    objective:       p.objective,
    day:             p.day,
    date:            p.date,
    owner:           p.owner,
    urgency:         p.urgency,
    score:           p.freshness_score || 5,
    expiration_window: 'today',
    expected_outcome: { type: 'awareness', label: 'reach + engagement' },
    source_evidence:  `Post plan: ${p.day} · ${p.format}`,
    created_at:      new Date().toISOString(),
    status:          'recommended',
  };
  allRecommendations.push(rec);
});

// Retargeting recommendations
(retarget.recommendations || []).forEach(r => {
  const rec = {
    recommendation_id: makeRecId(r.type, r.topic || r.service, r.suggested_hook),
    source:           'retarget',
    type:             r.type,
    topic:            r.topic || r.service,
    hook:             r.suggested_hook || r.hook,
    cta:              r.suggested_cta,
    channel:          r.channel,
    urgency:          r.urgency,
    score:            r.score,
    expiration_window: r.expiration_window,
    expected_outcome: r.expected_outcome,
    source_evidence:   r.source_evidence,
    created_at:       r.updated || new Date().toISOString(),
    status:           'recommended',
  };
  allRecommendations.push(rec);
});

// Service push recommendations
(sales.priorities || []).slice(0, 3).forEach((s, i) => {
  const rec = {
    recommendation_id: makeRecId('service_push', s.label, null),
    source:           'service_push',
    type:             'service_push',
    topic:            s.label,
    hook:             `Push ${s.label} — ${s.reasons?.[0] || ''}`,
    cta:              s.recommended_cta,
    channel:          'IG Static',
    urgency:          s.priority_level === 'HIGH' ? 'today' : 'this_week',
    score:            s.score,
    expiration_window: s.priority_level === 'HIGH' ? 'today' : '48h',
    expected_outcome: { type: 'bookings', label: '+10-20% booking rate' },
    source_evidence:  `Service priority #${i+1} · score ${s.score}/10`,
    created_at:       new Date().toISOString(),
    status:           'recommended',
  };
  allRecommendations.push(rec);
});

// ── Practical attribution matching ──────────────────────────────
const igCaps = igPosts.map(p => ({
  ...p,
  captionLower: (p.caption || '').toLowerCase(),
  hook:        (p.caption || '').substring(0, 80),
}));

// Baseline averages (last 30 posts)
const baseline = {
  avgEngRate:  igCaps.slice(0, 30).reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / Math.max(igCaps.slice(0, 30).length, 1),
  avgReach:    igCaps.slice(0, 30).reduce((s, p) => s + (parseInt(p.reach) || 0), 0) / Math.max(igCaps.slice(0, 30).length, 1),
  avgSaves:    igCaps.slice(0, 30).reduce((s, p) => s + (parseInt(p.saveCount) || 0), 0) / Math.max(igCaps.slice(0, 30).length, 1),
  avgLikes:    igCaps.slice(0, 30).reduce((s, p) => s + (parseInt(p.likeCount) || 0), 0) / Math.max(igCaps.slice(0, 30).length, 1),
};

// GA4 booking page sessions
const bookingPage = ga4Pages.find(p => (p.path || '').toLowerCase().includes('book'));
const bookingSessions = parseInt(bookingPage?.sessions) || 0;

// ── Match each recommendation to an IG post ──────────────────
function hookSimilarity(rHook, pCaption) {
  if (!rHook || !pCaption) return 0;
  const rWords = new Set((rHook || '').toLowerCase().split(' ').filter(w => w.length > 3));
  const pWords = new Set((pCaption || '').toLowerCase().split(' ').filter(w => w.length > 3));
  let match = 0;
  rWords.forEach(w => { if (pWords.has(w)) match++; });
  return rWords.size > 0 ? match / rWords.size : 0;
}

function ctaMatch(rCta, pCaption) {
  if (!rCta || !pCaption) return 0;
  const rCtaLower = (rCta || '').toLowerCase();
  const pCapLower = (pCaption || '').toLowerCase();
  const ctaTerms = ['book', 'booking', 'lesson', 'coach', 'fitting', 'swingshack', 'membership', 'simulator'];
  const rMatches = ctaTerms.filter(t => rCtaLower.includes(t)).length;
  const pMatches = ctaTerms.filter(t => pCapLower.includes(t)).length;
  return rMatches > 0 && pMatches > 0 ? 1 : 0;
}

function engDelta(engRate, reach) {
  // How much did this post over/underperform baseline?
  const delta = ((parseFloat(engRate) || 0) - baseline.avgEngRate);
  return parseFloat(delta.toFixed(2));
}

function outcomeStatus(engRate, reach, saves, rec) {
  // rec has expected_outcome.type
  const expectedType = rec.expected_outcome?.type || 'awareness';
  const delta = engDelta(engRate, reach);
  const saveRate = (parseInt(reach) || 0) > 0 ? (parseInt(saves) || 0) / (parseInt(reach) || 1) * 100 : 0;

  if (expectedType === 'bookings') {
    // For booking CTAs, saves + comments matter more than likes
    if (saveRate > 2 || delta > 1) return 'won';
    if (saveRate > 0.5 || delta > -1) return 'neutral';
    return 'lost';
  }
  if (expectedType === 'clicks') {
    if (saveRate > 1.5) return 'won';
    if (saveRate > 0.5) return 'neutral';
    return 'lost';
  }
  // awareness
  if (delta > 1.5) return 'won';
  if (delta > 0)   return 'neutral';
  if (delta > -2)  return 'neutral';
  return 'lost';
}

// ── Evaluate each recommendation ───────────────────────────────
const evaluated = allRecommendations.map(rec => {
  // Skip very old recs (more than 14 days old)
  const created = new Date(rec.created_at || 0);
  const daysOld = (Date.now() - created.getTime()) / 86400000;
  if (daysOld > 14) {
    return { ...rec, status: 'stale', executed: false, outcome_status: 'not_executed' };
  }

  // Find best matching IG post
  let bestMatch = null;
  let bestScore = 0;

  igCaps.slice(0, 30).forEach(post => {
    const hSim = hookSimilarity(rec.hook, post.caption);
    const cMatch = ctaMatch(rec.cta, post.caption);
    // rec type match bonus
    let typeBonus = 0;
    if (rec.type === 'post_plan' && rec.topic) {
      if (post.captionLower.includes(rec.topic.toLowerCase())) typeBonus = 0.2;
    }
    const score = hSim * 0.6 + cMatch * 0.3 + typeBonus;
    if (score > bestScore && score > 0.2) {
      bestScore = score;
      bestMatch = post;
    }
  });

  if (!bestMatch) {
    return {
      ...rec,
      status:          'not_executed',
      executed:        false,
      outcome_status:  'not_executed',
      matched_post_id: null,
      match_confidence: parseFloat(bestScore.toFixed(2)),
    };
  }

  const engRate = parseFloat(bestMatch.engagementRate || 0) || 0;
  const reach   = parseInt(bestMatch.reach) || 0;
  const likes   = parseInt(bestMatch.likeCount) || 0;
  const saves   = parseInt(bestMatch.saveCount) || 0;
  const comments = parseInt(bestMatch.commentsCount || bestMatch.commentCount) || 0;
  const delta   = engDelta(engRate, reach);
  const ost     = outcomeStatus(engRate, reach, saves, rec);

  return {
    ...rec,
    status:           'executed',
    executed:         true,
    outcome_status:   ost,
    matched_post_id:  bestMatch.id || 'unknown',
    match_confidence: parseFloat(bestScore.toFixed(2)),
    metrics: {
      reach:          reach,
      likes:          likes,
      saves:          saves,
      comments:       comments,
      engagement_rate: engRate,
      delta_vs_baseline: delta,
      save_rate:      reach > 0 ? parseFloat((saves / reach * 100).toFixed(2)) : 0,
    },
    posted_at: bestMatch.timestamp || bestMatch.created_at || rec.created_at,
  };
});

// ── Win rate by type ───────────────────────────────────────────
const executedRecs = evaluated.filter(r => r.executed);
const byType = {};
executedRecs.forEach(r => {
  if (!byType[r.type]) byType[r.type] = { total: 0, won: 0, neutral: 0, lost: 0 };
  byType[r.type].total++;
  if (r.outcome_status === 'won')    byType[r.type].won++;
  if (r.outcome_status === 'neutral') byType[r.type].neutral++;
  if (r.outcome_status === 'lost')   byType[r.type].lost++;
});

const typeWinRates = Object.entries(byType).map(([type, data]) => ({
  type,
  total:    data.total,
  won:      data.won,
  neutral:  data.neutral,
  lost:     data.lost,
  win_rate: parseFloat((data.won / data.total * 100).toFixed(1)),
})).sort((a, b) => b.win_rate - a.win_rate);

// ── Summary ────────────────────────────────────────────────────
const won    = evaluated.filter(r => r.outcome_status === 'won').length;
const neutral= evaluated.filter(r => r.outcome_status === 'neutral').length;
const lost   = evaluated.filter(r => r.outcome_status === 'lost').length;
const notExec= evaluated.filter(r => r.outcome_status === 'not_executed').length;
const stale  = evaluated.filter(r => r.status === 'stale').length;
const execRate = evaluated.length > 0 ? parseFloat((executedRecs.length / evaluated.filter(r => r.status !== 'stale').length * 100).toFixed(1)) : 0;

// Top performers and worst
const performedRecs = executedRecs.filter(r => r.metrics).sort((a, b) =>
  (b.metrics?.delta_vs_baseline || 0) - (a.metrics?.delta_vs_baseline || 0)
);
const bestRec  = performedRecs[0] || null;
const worstRec = performedRecs[performedRecs.length - 1] || null;
const ignoredRecs = evaluated.filter(r => r.status === 'not_executed' && r.status !== 'stale').slice(0, 5);
const underperformed = executedRecs.filter(r => r.outcome_status === 'lost').slice(0, 3);

// ── Learned signals for scoring ────────────────────────────────
const learnedSignals = {
  best_channel:     typeWinRates[0]?.type || 'retarget_existing',
  best_channel_rate: typeWinRates[0]?.win_rate || 0,
  worst_channel:    typeWinRates[typeWinRates.length - 1]?.type || 'unknown',
  worst_channel_rate: typeWinRates[typeWinRates.length - 1]?.win_rate || 0,
  confidence_adjustments: Object.fromEntries(
    typeWinRates.map(r => [r.type, {
      observed_win_rate: r.win_rate,
      expected_won:      r.won > r.lost ? 'confidence_appropriate' : r.won < r.lost ? 'confidence_too_high' : 'neutral',
      adjustment: r.win_rate > 60 ? '+0.5' : r.win_rate < 30 ? '-1.0' : 'none',
    }])
  ),
  overall_win_rate:   executedRecs.length > 0 ? parseFloat((won / executedRecs.length * 100).toFixed(1)) : 0,
  exec_rate: execRate,
};

// ── Write output ────────────────────────────────────────────────
const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_recommendation_outcomes.js',
  summary: {
    total_recommended:  evaluated.length,
    executed:           executedRecs.length,
    won:                won,
    neutral:            neutral,
    lost:               lost,
    not_executed:       notExec,
    stale:              stale,
    exec_rate:execRate,
    overall_win_rate:   learnedSignals.overall_win_rate,
    baseline_eng_rate:  parseFloat(baseline.avgEngRate.toFixed(2)),
    booking_sessions:   bookingSessions,
  },
  type_win_rates:      typeWinRates,
  learned_signals:     learnedSignals,
  best_recommendation: bestRec ? {
    id:          bestRec.recommendation_id,
    hook:        bestRec.hook,
    type:        bestRec.type,
    delta:       bestRec.metrics?.delta_vs_baseline,
    eng_rate:    bestRec.metrics?.engagement_rate,
    reach:       bestRec.metrics?.reach,
  } : null,
  worst_recommendation: worstRec ? {
    id:          worstRec.recommendation_id,
    hook:        worstRec.hook,
    type:        worstRec.type,
    delta:       worstRec.metrics?.delta_vs_baseline,
    eng_rate:    worstRec.metrics?.engagement_rate,
  } : null,
  ignored: ignoredRecs.map(r => ({ id: r.recommendation_id, hook: r.hook, type: r.type, reason: 'no_matching_post_found' })),
  underperformed: underperformed.map(r => ({ id: r.recommendation_id, hook: r.hook, type: r.type, delta: r.metrics?.delta_vs_baseline, reason: 'below_baseline_engagement' })),
  all_evaluated: evaluated,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Recommendation outcomes: ${OUTPUT}`);
console.log(`   Recommended: ${evaluated.length} | Executed: ${executedRecs.length} | Exec rate: ${execRate}%`);
console.log(`   Won: ${won} | Neutral: ${neutral} | Lost: ${lost} | Not executed: ${notExec}`);
console.log(`   Overall win rate: ${learnedSignals.overall_win_rate}%`);
if (bestRec) console.log(`   🏆 Best: ${bestRec.hook?.substring(0, 50)} (delta: +${bestRec.metrics?.delta_vs_baseline} eng)`);
if (worstRec && worstRec !== bestRec) console.log(`   ⚠️ Worst: ${worstRec.hook?.substring(0, 50)} (delta: ${worstRec.metrics?.delta_vs_baseline} eng)`);
console.log(`   Win rates by type:`);
typeWinRates.forEach(r => console.log(`     ${r.type}: ${r.win_rate}% (${r.won}W/${r.total})`));
