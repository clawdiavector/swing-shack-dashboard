#!/usr/bin/env node
/**
 * generate_experiment_queue.js
 * Finds medium-confidence opportunities worth testing next.
 * Outputs: data/experiment-queue.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'experiment-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const ig      = readJson('ig-analytics.json')                || {};
const hooks   = readJson('hook-bank.json')                 || {};
const sales   = readJson('sales-priority.json')           || {};
const ctaPerf = readJson('cta-performance.json')           || {};
const conv    = readJson('conversion-attribution.json')    || {};
const yt      = readJson('youtube-trends.json')            || {};
const outcomes= readJson('recommendation-outcomes.json')   || {};
const missed  = readJson('missed-opportunities.json')      || {};

const igPosts   = ig.posts || [];
const igText    = igPosts.map(p => (p.caption || '').toLowerCase()).join(' ');
const outcomesByType = {};
(outcomes.type_win_rates || []).forEach(r => { outcomesByType[r.type] = r; });

// ── 1. Hook A/B tests ───────────────────────────────────────────
const ww        = hooks.watched_and_worked || [];
const provenHooks = ww.filter(h => (h.ig_proof_score || 0) >= 7 && (h.cross_signal_score || 0) < 8);

const hookTests = provenHooks.slice(0, 3).map(h => {
  // Find a topic variant not yet tested on IG
  const topic = h.youtube_topic_match?.[0] || '';
  const relatedIdeas = (hooks.hooks || []).filter(hook =>
    hook.hook_text && hook.hook_text.includes(topic)
  ).slice(0, 3);

  return {
    test_id:        `hook_test_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
    type:          'hook_ab',
    variable:      'hook_angle',
    description:   `Test TrackMan stats angle vs transformation angle on "${topic}" hook`,
    variant_a:     { hook: h.hook_text, label: 'Stats/TrackMan (proven)' },
    variant_b:     { hook: `Your "${topic}" problem? Here's how TrackMan finds it in one session.`, label: 'Problem-aware (test)' },
    success_metric:'engagement_rate > 3% AND save_rate > 1.5%',
    target_metric:  'engagement_rate',
    current_baseline: parseFloat(h.ig_proof_score || 0),
    owner:          topic.includes('lesson') || topic.includes('putt') ? 'Coach Cat' : 'Swing Shack page',
    channel:        topic.includes('lesson') || topic.includes('putt') ? 'IG Reel' : 'IG Static',
    urgency:        (h.ig_proof_score || 0) >= 9 ? 'today' : 'this_week',
    upside:         `If variant B outperforms by 20%+, upgrade to primary hook template`,
    confidence:    parseFloat(((h.ig_proof_score || 0) * 0.4 + (h.cross_signal_score || 0) * 0.6).toFixed(1)),
    why:            `Hook scored ${h.ig_proof_score} on IG but cross-signal only ${(h.cross_signal_score || 0).toFixed(1)} — angle may not be optimal`,
  };
});

// ── 2. CTA variant tests ────────────────────────────────────────
const ctaRank  = ctaPerf.cta_rankings || [];
const worstCTA = ctaRank[ctaRank.length - 1];
const bestCTA  = ctaRank[0];

const ctaTests = [];
if (worstCTA && worstCTA.cta_type !== bestCTA?.cta_type) {
  // Test replacing worst CTA with best CTA
  ctaTests.push({
    test_id:       `cta_test_${Date.now()}`,
    type:         'cta_ab',
    variable:     'call_to_action',
    description:  `Replace "${worstCTA.label}" with "${bestCTA.label}" on service posts`,
    variant_a:    { cta: worstCTA.label, label: 'Current (weak)', eng: worstCTA.avg_engagement_rate },
    variant_b:    { cta: bestCTA.label,  label: 'Top performer',   eng: bestCTA.avg_engagement_rate },
    success_metric: 'save_rate +0.5% OR click_proxy +20%',
    target_metric: 'save_rate',
    current_baseline: worstCTA.avg_engagement_rate,
    owner:         'Swing Shack page',
    channel:       'IG Static',
    urgency:        'this_week',
    upside:        `+${(bestCTA.avg_engagement_rate - worstCTA.avg_engagement_rate).toFixed(1)}% avg eng gap between best and worst CTA`,
    confidence:   3,
    why:           `CTA type "${worstCTA.label}" has lowest conversion signal — test replacement`,
  });
}

// ── 3. Service demand / weak conversion tests ───────────────────
const serviceCorr = conv.service_correlation || [];
const weakServices = serviceCorr.filter(s => s.ig_signal < 2 && s.post_count > 0).slice(0, 2);

const serviceTests = weakServices.map(svc => ({
  test_id:       `svc_test_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
  type:          'service_conversion',
  variable:      'service_angle',
  description:   `Test stronger booking intent angle for "${svc.service}"`,
  variant_a:     { angle: 'awareness', label: 'Current soft approach', eng: svc.avg_engagement, saves: svc.total_saves },
  variant_b:     { angle: 'booking_intent', label: 'Direct CTA push', eng: 0, saves: 0 },
  success_metric: 'save_rate > 1.5% AND bookings from IG up 10%',
  target_metric: 'save_rate',
  current_baseline: svc.avg_engagement,
  owner:          svc.service === 'Golf Lessons' ? 'Coach Cat' : svc.service === 'Club Fitting' ? 'Divan' : 'Swing Shack page',
  channel:        svc.service === 'Golf Lessons' ? 'IG Reel' : 'IG Static',
  urgency:        'this_week',
  upside:         `Weak IG signal (${svc.ig_signal}) but ${svc.post_count} posts exist — angle may be wrong`,
  confidence:    2,
  why:            `"${svc.service}" has ${svc.post_count} posts but ig_signal only ${svc.ig_signal} — reword for booking intent`,
}));

// ── 4. YouTube-aligned untested angles ─────────────────────────
const ytSvcMap = {
  lessons:    ['lesson', 'swing', 'teaching', 'coach'],
  driver:    ['driver', 'drive', 'tee'],
  short_game: ['putting', 'chipping', 'pitching', 'putt'],
  fitness:   ['fitness', 'gym', 'flexibility', 'body'],
};
const ytVideos = yt.top_videos || [];
const ytTests = Object.entries(ytSvcMap).slice(0, 2).map(([svc, kws]) => {
  const ytMatch = ytVideos.filter(v => kws.some(k => (v.title || '').toLowerCase().includes(k)));
  const ytTitles = ytMatch.slice(0, 2).map(v => v.title);
  const igMentioned = kws.some(k => igText.includes(k));
  return {
    test_id:       `yt_test_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
    type:          'youtube_untested',
    variable:      'youtube_angle_to_ig',
    description:   `Take trending YouTube angle for "${svc}" and port to IG`,
    variant_a:     { hook: ytTitles[0] || `${svc} — what pros don't tell you`, label: 'YouTube angle (proven on YT)' },
    variant_b:     { hook: ytTitles[1] || `Why your ${svc} is costing you strokes`, label: 'Problem angle (IG-native)' },
    yt_evidence:  ytTitles,
    success_metric: 'cross_signal_score > 7 after 2 posts',
    target_metric: 'cross_signal_score',
    owner:         svc === 'lessons' || svc === 'short_game' ? 'Coach Cat' : 'Swing Shack page',
    channel:       svc === 'lessons' || svc === 'short_game' ? 'IG Reel' : 'IG Static',
    urgency:        'this_week',
    upside:        `YouTube has ${ytMatch.length} videos on this — proven interest, untested on IG`,
    confidence:    3,
    why:            `${ytMatch.length} YT videos trending on "${svc}" but ${igMentioned ? 'minimal' : 'no'} IG coverage`,
  };
});

// ── Combine & rank ──────────────────────────────────────────────
const allTests = [...hookTests, ...ctaTests, ...serviceTests, ...ytTests];
allTests.sort((a, b) => {
  // Higher confidence + higher urgency = higher priority
  const scoreA = (a.confidence || 3) * (a.urgency === 'today' ? 2 : 1);
  const scoreB = (b.confidence || 3) * (b.urgency === 'today' ? 2 : 1);
  return scoreB - scoreA;
});

// ── Write ───────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_experiment_queue.js',
  summary: {
    total_tests:     allTests.length,
    hook_tests:     hookTests.length,
    cta_tests:      ctaTests.length,
    service_tests:  serviceTests.length,
    yt_tests:       ytTests.length,
    today_count:    allTests.filter(t => t.urgency === 'today').length,
    this_week_count: allTests.filter(t => t.urgency === 'this_week').length,
  },
  experiments: allTests.map((t, i) => ({ ...t, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Experiment queue: ${OUTPUT}`);
console.log(`   Total: ${allTests.length} | Today: ${output.summary.today_count} | This week: ${output.summary.this_week_count}`);
allTests.slice(0, 5).forEach((t, i) => {
  console.log(`   ${i+1}. [${t.urgency.toUpperCase()}] ${t.type} | ${t.variable} | ${t.owner} | conf:${t.confidence}`);
  console.log(`      Test: ${t.description.substring(0, 70)}`);
  console.log(`      Success: ${t.success_metric}`);
});
