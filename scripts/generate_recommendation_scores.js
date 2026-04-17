#!/usr/bin/env node
/**
 * generate_recommendation_scores.js
 * Ranks all recommended actions by combined score:
 * revenue_impact × urgency × ease × confidence
 * Output: data/recommendation-scores.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'recommendation-scores.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const retarget = readJson('retargeting-recommendations.json') || {};
const sales    = readJson('sales-priority.json')             || {};
const plan    = readJson('post-plan.json')                   || {};
const conv    = readJson('conversion-attribution.json')     || {};
const leaks   = readJson('funnel-leaks.json')               || {};

// ── Scoring dimensions ──────────────────────────────────────────
// revenue_impact: 1-5 (higher = more revenue potential)
// urgency:        1-5 (1 = today, 5 = flexible)
// ease:           1-5 (1 = complex/requires asset, 5 = caption update)
// confidence:     1-5 (based on signal strength)

const URGENCY_SCORE = { today: 5, '48h': 4, this_week: 3, flexible: 2, evergreen: 1 };
const EASE_SCORE    = { caption_update: 5, 'ig_story': 4, 'ig_reel': 3, 'ig_static': 3, email: 2, website: 2, whatsapp: 2 };
const REVENUE_MAP   = { bookings: 5, clicks: 4, saves: 3, reminders: 3, awareness: 2 };

function easeScore(channel, action) {
  const ch = (channel || '').toLowerCase();
  if (ch.includes('caption'))  return 5;
  if (ch.includes('story'))    return 4;
  if (ch.includes('reel'))     return 3;
  if (ch.includes('carousel')) return 2;
  if (ch.includes('email'))    return 2;
  if (ch.includes('website'))  return 2;
  return 3;
}

function confidenceScore(rec) {
  const src = rec.source_evidence || '';
  // Extract numbers from evidence
  const numMatch = src.match(/(\d+)/);
  const baseNum  = numMatch ? parseInt(numMatch[1]) : 50;
  // Higher session/save numbers = higher confidence
  const signalStrength = Math.min(baseNum / 40, 5); // cap at 5
  // IG score evidence
  const igMatch = src.match(/score\s+(\d+\.?\d*)/i);
  const igScore  = igMatch ? parseFloat(igMatch[1]) : 0;
  if (igScore >= 9) return 5;
  if (igScore >= 7) return 4;
  if (signalStrength >= 4) return 4;
  if (signalStrength >= 2) return 3;
  return 2;
}

function revenueScore(rec) {
  const t = rec.expected_outcome?.type || '';
  return REVENUE_MAP[t] || 3;
}

function urgencyScore(rec) {
  return URGENCY_SCORE[rec.expiration_window] || URGENCY_SCORE[this_week || 3];
}

// ── Score each retargeting rec ───────────────────────────────────
const retargetItems = (retarget.recommendations || []).map(rec => {
  const rev   = revenueScore(rec);
  const urg   = URGENCY_SCORE[rec.expiration_window] || 3;
  const ease  = easeScore(rec.channel, rec.action);
  const conf  = confidenceScore(rec);
  const score = (rev * urg * ease * conf) / 20; // normalise to ~0-25 range

  return {
    ...rec,
    score:       parseFloat(score.toFixed(2)),
    breakdown: {
      revenue_impact: { value: rev,  label: REVENUE_MAP[rec.expected_outcome?.type] ? `${rec.expected_outcome.type} (${rev}/5)` : `${rec.expected_outcome?.type || '?'} (${rev}/5)` },
      urgency:        { value: urg,  label: `${rec.expiration_window} (${urg}/5)` },
      ease:           { value: ease, label: `${rec.channel} (${ease}/5)` },
      confidence:     { value: conf, label: `signal-based (${conf}/5)` },
    },
  };
});

// ── Best post to publish ────────────────────────────────────────
const nextPost = plan.plan?.find(p => p.status === 'ready') || plan.plan?.[0];
const bestPost = nextPost ? {
  ...nextPost,
  score:  nextPost.freshness_score || 7,
  reason: `Freshness ${nextPost.freshness_score || 7}/10 · ${nextPost.objective} · ${nextPost.format}`,
  type:   'post',
} : null;

// ── Best service to push ─────────────────────────────────────────
const topService = sales.priorities?.[0];
const bestService = topService ? {
  service:   topService.label,
  score:     topService.score,
  reason:    `${topService.score}/10 — ${topService.reasons?.[0] || ''}`,
  cta:       topService.recommended_cta,
  priority:  topService.priority_level,
  type:      'service',
} : null;

// ── Best retargeting move ───────────────────────────────────────
const bestRetarget = [...retargetItems].sort((a, b) => b.score - a.score)[0] || null;

// ── Biggest leak fix ─────────────────────────────────────────────
const funnelLeak = (leaks.leaks || [])[0];
const topLeak = funnelLeak ? {
  ...funnelLeak,
  score:    funnelLeak.sessions ? Math.min(funnelLeak.sessions / 20, 10) : 6,
  type:     'funnel_leak',
  reason:   funnelLeak.easy_fix || funnelLeak.suggestion,
  suggested_cta: 'Book a session \u00b7 swingshack.co.za/bookings \u00b7 From R250',
} : null;

// ── "Do This First" stack ───────────────────────────────────────
const doFirst = [
  { slot: 'post',    label: 'Post this first',    emoji: '\ud83c\udfaf', item: bestPost,     score_note: bestPost    ? `Freshness ${bestPost.score}/10` : null },
  { slot: 'service', label: 'Push this service',   emoji: '\ud83d\udcb0', item: bestService,  score_note: bestService ? `${bestService.score}/10` : null },
  { slot: 'retarget',label: 'Retarget this first',  emoji: '\ud83d\udd01', item: bestRetarget, score_note: bestRetarget ? `score ${bestRetarget.score}` : null },
  { slot: 'leak',    label: 'Fix this leak',        emoji: '\u26a0\ufe0f', item: topLeak,     score_note: topLeak?.sessions ? `${topLeak.sessions} sessions` : null },
].filter(d => d.item);

const overallScore = doFirst.length > 0
  ? parseFloat((doFirst.reduce((s, d) => s + (d.item?.score || 0), 0) / doFirst.length).toFixed(1))
  : 0;

// ── All ranked retarget items ───────────────────────────────────
const rankedItems = [...retargetItems].sort((a, b) => b.score - a.score).slice(0, 8);

// ── Write ────────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_recommendation_scores.js',
  summary: {
    overall_priority_score: overallScore,
    do_first_count:        doFirst.length,
    retarget_items_scored: retargetItems.length,
    top_retarget_score:    bestRetarget?.score || 0,
    best_post_score:       bestPost?.score || 0,
    best_service_score:   bestService?.score || 0,
  },
  do_first:      doFirst,
  ranked_items:  rankedItems,
  all_items:     retargetItems.sort((a, b) => b.score - a.score),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Recommendation scores: ${OUTPUT}`);
console.log(`   Overall priority: ${overallScore}/10 | Do first: ${doFirst.length} items`);
doFirst.forEach(d => {
  console.log(`   ${d.emoji} ${d.label}: ${(d.item?.suggested_hook || d.item?.hook || d.item?.service || d.item?.action || '—').substring(0, 55)}`);
  console.log(`      Score: ${d.item?.score} | ${d.score_note}`);
  if (d.item?.suggested_cta) console.log(`      CTA: ${d.item.suggested_cta}`);
});
console.log(`Top retarget:`);
rankedItems.slice(0, 3).forEach((r, i) => {
  console.log(`   ${i+1}. score:${r.score} ${r.action} (${r.channel}) — ${r.source_evidence}`);
});
