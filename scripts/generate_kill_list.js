#!/usr/bin/env node
/**
 * generate_kill_list.js
 * Identifies what to stop, pause, or rewrite before reusing.
 * Outputs: data/kill-list.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'kill-list.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const ig      = readJson('ig-analytics.json')               || {};
const hooks   = readJson('hook-bank.json')                  || {};
const sales   = readJson('sales-priority.json')            || {};
const ctaPerf = readJson('cta-performance.json')          || {};
const outcomes= readJson('recommendation-outcomes.json')    || {};
const missed  = readJson('missed-opportunities.json')     || {};

const igPosts = ig.posts || [];

// ── 1. Hooks that consistently lose ────────────────────────────
const lostRecs = (outcomes.underperformed || []).slice(0, 4);
const lostHooks = lostRecs
  .filter(r => r.delta !== undefined && r.delta < -1.5)
  .map(r => ({
    type:        'hook_lose',
    action:      'Stop posting this hook angle',
    hook:        r.hook,
    delta:       r.delta,
    outcome_type: r.type,
    severity:    r.delta < -3 ? 'high' : 'medium',
    fix:         'Rewrite angle or retire this hook — performance below baseline',
    confidence:  4,
    why:         `Hook underperformed baseline by ${Math.abs(r.delta)}% engagement`,
  }));

// ── 2. CTAs that never convert ─────────────────────────────────
const ctaRank = ctaPerf.cta_rankings || [];
const worstCTA = ctaRank[ctaRank.length - 1];
const ctaKills = worstCTA && worstCTA.conversion_signal < 1 ? [{
  type:        'cta_kill',
  action:      `Stop using ${worstCTA.label} as primary CTA`,
  cta_type:    worstCTA.cta_type,
  signal:      worstCTA.conversion_signal,
  eng_rate:   worstCTA.avg_engagement_rate,
  severity:   worstCTA.conversion_signal < 0.5 ? 'high' : 'medium',
  fix:        `Replace with ${(ctaRank[0] || {}).label || 'best performing CTA'} — weak conversion signal`,
  confidence:  5,
  why:        `${worstCTA.label} has lowest conversion signal (${worstCTA.conversion_signal}) — stop using as primary`,
}] : [];

// ── 3. Content themes with no engagement ────────────────────────
const SERVICE_KEYWORDS = {
  'Simulator':    ['simulator', 'sim', 'indoor', 'rain', 'weather'],
  'Membership':   ['member', 'membership', 'perk', 'unlimited'],
  'Events':       ['event', 'competition', 'tournament', 'night golf'],
};
const igText = igPosts.map(p => (p.caption || '').toLowerCase()).join(' ');

const themeKills = Object.entries(SERVICE_KEYWORDS).map(([svc, kws]) => {
  const posts = igPosts.filter(p => kws.some(k => (p.caption || '').toLowerCase().includes(k)));
  if (posts.length === 0) return null;
  const avgEng = posts.reduce((s, p) => s + (parseFloat(p.engagementRate || 0) || 0), 0) / posts.length;
  const avgSaveRate = posts.reduce((s, p) => {
    const reach = parseInt(p.reach) || 0;
    return s + (reach > 0 ? (parseInt(p.saveCount) || 0) / reach * 100 : 0);
  }, 0) / posts.length;
  if (avgEng > 1.5 || avgSaveRate > 0.5) return null; // still performing
  return {
    type:       'content_theme_kill',
    action:     `Pause "${svc}" content or rewrite angle`,
    service:    svc,
    posts_count: posts.length,
    avg_eng:    parseFloat(avgEng.toFixed(2)),
    avg_save_rate: parseFloat(avgSaveRate.toFixed(2)),
    severity:   avgEng < 0.5 ? 'high' : 'medium',
    fix:        avgEng < 0.5
      ? `Stop posting ${svc} with current angle — test problem-aware angle instead`
      : `Redesign ${svc} posts — current format is not converting`,
    confidence: 4,
    why:        `${svc} posts avg ${avgEng}% eng and ${avgSaveRate}% save rate — below threshold`,
  };
}).filter(Boolean).slice(0, 3);

// ── 4. Services to de-prioritise ───────────────────────────────
const lowestSvc = (sales.priorities || []).slice(-1)[0];
const svcKills = lowestSvc && lowestSvc.score < 2 && (sales.priorities || []).length > 3 ? [{
  type:       'service_deprioritise',
  action:     `Stop actively pushing ${lowestSvc.label}`,
  service:    lowestSvc.label,
  score:     lowestSvc.score,
  reason:    lowestSvc.reasons?.[0] || '',
  severity:  lowestSvc.score < 1 ? 'high' : 'medium',
  fix:       `Move ${lowestSvc.label} to bottom of priority list — weak demand signal`,
  confidence: 4,
  why:       `Service priority #${(sales.priorities || []).length} with score ${lowestSvc.score}/10 — low ROI on promotion`,
}] : [];

// ── 5. Hook themes in retirement ────────────────────────────────
const retire = (hooks.hooks || []).filter(h =>
  (h.output_bucket === 'retire' || h.score <= 1) &&
  (h.ig_proof_score || 0) < 3
).slice(0, 3).map(h => ({
  type:       'hook_retire',
  action:     `Retire hook: "${(h.hook_text || h.hook || '').substring(0, 50)}"`,
  hook:       h.hook_text || h.hook,
  score:     h.score || h.ig_proof_score,
  bucket:    h.output_bucket,
  severity:  'low',
  fix:       'Archive — do not reuse without significant rewrite',
  confidence: 5,
  why:       `Hook in "${h.output_bucket || 'retire'}" bucket with score ${h.score || h.ig_proof_score} — proven low performer`,
}));

// ── 6. Low-value posting patterns ─────────────────────────────
const lowValuePatterns = [];
// Check for very low reach posts
const lowReachPosts = igPosts.filter(p => (parseInt(p.reach) || 0) < 30 && (parseInt(p.likeCount) || 0) < 2);
if (lowReachPosts.length > 5) {
  lowValuePatterns.push({
    type:       'posting_pattern_kill',
    action:     `Stop posting without proper hook — ${lowReachPosts.length} low-reach posts this month`,
    pattern:    'low_reach_posts',
    count:      lowReachPosts.length,
    avg_reach:  parseInt(lowReachPosts.reduce((s, p) => s + (parseInt(p.reach) || 0), 0) / lowReachPosts.length),
    severity:   'medium',
    fix:        'Always run new posts through hook bank before publishing — do not post raw',
    confidence: 4,
    why:        `${lowReachPosts.length} posts with <30 reach this month — posting without hook validation`,
  });
}

// ── Combine ───────────────────────────────────────────────────
const allKills = [
  ...lostHooks,
  ...ctaKills,
  ...themeKills,
  ...svcKills,
  ...retire,
  ...lowValuePatterns,
].filter(Boolean);

allKills.sort((a, b) => {
  const sevOrder = { high: 0, medium: 1, low: 2 };
  return sevOrder[a.severity] - sevOrder[b.severity];
});

// ── Write ───────────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_kill_list.js',
  summary: {
    total:         allKills.length,
    high_urgency:  allKills.filter(k => k.severity === 'high').length,
    medium_urgency: allKills.filter(k => k.severity === 'medium').length,
    low_urgency:   allKills.filter(k => k.severity === 'low').length,
    by_type:       Object.fromEntries(
      [...new Set(allKills.map(k => k.type))].map(t => [t, allKills.filter(k => k.type === t).length])
    ),
  },
  items: allKills.map((k, i) => ({ ...k, rank: i + 1 })),
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Kill list: ${OUTPUT}`);
console.log(`   Total: ${allKills.length} | High: ${output.summary.high_urgency} | Med: ${output.summary.medium_urgency}`);
allKills.slice(0, 5).forEach((k, i) => {
  console.log(`   ${i+1}. [${k.severity.toUpperCase()}] ${k.type} | ${k.action.substring(0, 60)}`);
  console.log(`      Fix: ${k.fix.substring(0, 70)}`);
});
