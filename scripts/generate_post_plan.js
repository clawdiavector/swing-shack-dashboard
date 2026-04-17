#!/usr/bin/env node
/**
 * generate_post_plan.js
 * Builds a 7-day content plan pulling from WATCHED+WORKED, Hook Bank,
 * Content Ideas, Website Insights, and Golf News.
 *
 * Each planned post: day, platform, format, hook, cta, objective,
 *                     why_chosen, evidence, status
 *
 * Objectives: reach | saves | bookings | awareness
 * Status: ready (has hook+CTA) | test (needs CTA) | fallback
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'post-plan.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

function today() {
  const d = new Date();
  const sa = new Date(d.toLocaleString('en-US', { timeZone: 'Africa/Johannesburg' }));
  return sa;
}

// ── Load data sources ─────────────────────────────────────────────
const hb        = readJson('hook-bank.json')        || {};
const ci       = readJson('content-ideas.json')     || {};
const ga4      = readJson('ga4-metrics.json')       || {};
const wi       = readJson('website-insights.json')  || {};
const gn       = readJson('golf-news.json')         || {};
const used     = readJson('used-items.json')         || {};
const ig       = readJson('ig-analytics.json')      || {};

// ── Build candidate pool ──────────────────────────────────────────
const candidates = [];

// 1. WATCHED + WORKED — highest cross_signal_score first
const wwCandidates = (hb.watched_and_worked || []).map(h => ({
  source: 'watched_and_worked',
  hook:   h.hook_text || '',
  hook_id: h.hook_id,
  format: mapFormat(h),
  ig_score: h.ig_proof_score || 0,
  yt_score: h.youtube_alignment_score || 0,
  cross_score: h.cross_signal_score || 0,
  topics: h.youtube_topic_match || [],
  engagementRate: parseFloat(h.engagementRate) || 0,
  contentType: classifyHook(h.hook_text || ''),
  evidence: (h.youtube_evidence_titles || []).slice(0, 2),
  used: isUsed(h.hook_id, used),
})).filter(h => !h.used && h.hook.length > 10)
  .sort((a, b) => b.cross_score - a.cross_score);

// 2. Content Ideas (unused)
const ideaCandidates = (ci.ideas || [])
  .filter(i => !i.used)
  .sort((a, b) => (b.freshness_score || 0) - (a.freshness_score || 0))
  .slice(0, 8)
  .map(i => ({
    source: 'content_idea',
    hook:   i.title || i.hook || '',
    format: i.format || 'static',
    ig_score: 0,
    yt_score: 0,
    cross_score: i.freshness_score || 0,
    topics: [i.topic_cluster || ''].filter(Boolean),
    contentType: classifyHook(i.title || i.hook || ''),
    evidence: [i.source_reason || ''].filter(Boolean),
    cta: i.best_cta || 'Link in bio',
    used: false,
  }));

// 3. Golf News — story/reel angles
const newsCandidates = ((gn.post_ideas || gn.story_today || []).length
  ? (gn.post_ideas || gn.story_today || [])
  : (gn.reel_today || []).map(r => ({ ...r, format: 'reel' })))
  .slice(0, 3).map(n => ({
    source: 'golf_news',
    hook:   n.title || n.headline || n.hook || '',
    format: n.format || 'static',
    ig_score: 0,
    yt_score: 0,
    cross_score: 5,
    topics: [n.topic || n.topic_cluster || ''].filter(Boolean),
    contentType: 'awareness',
    evidence: [n.title || n.headline || ''].filter(Boolean),
    used: false,
  }));

// ── Combine and deduplicate ───────────────────────────────────────
const seen = new Set();
const pool = [...wwCandidates, ...ideaCandidates, ...newsCandidates]
  .filter(c => {
    const key = c.hook.substring(0, 40).toLowerCase().replace(/\s+/g, ' ');
    if (seen.has(key)) return false;
    seen.add(key);
    return c.hook.length > 10;
  });

// ── Objective scoring ─────────────────────────────────────────────
function scoreObjective(candidate) {
  const ig  = candidate.ig_score  || 0;
  const yt  = candidate.yt_score  || 0;
  const eng = candidate.engagementRate || 0;
  const ct  = candidate.contentType;

  return [
    { obj: 'reach',    score: ig * 0.4 + yt * 0.4 + eng * 2   },
    { obj: 'bookings', score: ct === 'cta' ? 8 : ig * 0.3       },
    { obj: 'saves',    score: eng > 3 ? eng * 3 : 1             },
    { obj: 'awareness',score: yt * 0.5 + (ct === 'promo' ? 7 : 0) + ig * 0.2 },
  ].sort((a, b) => b.score - a.score);
}

// ── Assign each day of the week ──────────────────────────────────
const saToday = today();
const dayOfWeek = saToday.getDay(); // 0=Sun, 1=Mon ...

// Build next 7 days starting from today
const days = [];
for (let i = 0; i < 7; i++) {
  const d = new Date(saToday);
  d.setDate(d.getDate() + i);
  const dayName = d.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'Africa/Johannesburg' });
  const dateStr  = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'Africa/Johannesburg' });
  days.push({ dayName, dateStr, index: i, dateISO: d.toISOString().split('T')[0] });
}

// Objective distribution across week (prioritise Mon/Tue for reach, Wed bookings, Thu reach+saves, Fri promo, Sat awareness, Sun rest/leisure)
const WEEK_OBJECTIVES = [
  'reach', 'reach', 'bookings', 'saves', 'awareness', 'awareness', 'awareness'
];

const usedHookIds = new Set();

const plan = days.map((day, i) => {
  const primaryObj = WEEK_OBJECTIVES[i];

  // Find best candidate for this objective
  const scored = pool
    .filter(c => !usedHookIds.has(c.hook.substring(0, 40)))
    .map(c => {
      const objScores = scoreObjective(c);
      const primaryIdx = objScores.findIndex(o => o.obj === primaryObj);
      const primaryScore = primaryIdx >= 0 ? objScores[primaryIdx].score : 0;
      const secondaryScore = objScores[(primaryIdx + 1) % objScores.length].score;
      return { ...c, primaryScore, secondaryScore, allObjScores: objScores };
    })
    .sort((a, b) => {
      if (b.primaryScore !== a.primaryScore) return b.primaryScore - a.primaryScore;
      return b.secondaryScore - a.secondaryScore;
    });

  const top = scored[0];

  if (!top) {
    return {
      day:       day.dayName,
      date:      day.dateStr,
      dateISO:   day.dateISO,
      platform:  'instagram',
      format:    'static',
      hook:      null,
      cta:       null,
      objective: primaryObj,
      why_chosen: 'No unused content available — use fallback',
      evidence:  [],
      status:    'fallback',
      topics:    [],
    };
  }

  usedHookIds.add(top.hook.substring(0, 40));

  const platform = top.format === 'reel' ? 'tiktok' : 'instagram';
  const cta = top.cta || defaultCTA(top.contentType, primaryObj);
  const status = top.hook && cta ? 'ready' : 'test';
  const whyChosen = buildWhy(top, primaryObj);
  const owner = assignOwner(top.contentType, top.topics, top.hook);
  const asset = assetNeeded(top.contentType, platform === 'tiktok' ? 'reel' : top.format, top.topics);
  const urgency = calcUrgency(top.cross_score || 0, day.index);
  const suggestedSection = sourceSection(top.source);

  return {
    day:       day.dayName,
    date:      day.dateStr,
    dateISO:   day.dateISO,
    platform,
    format:    top.format || 'static',
    hook:      top.hook,
    hook_id:   top.hook_id || top.hook.substring(0, 40).replace(/\s+/g, '_'),
    cta,
    objective: primaryObj,
    why_chosen: whyChosen,
    evidence:  top.evidence,
    status,
    topics:    top.topics,
    ig_score:  top.ig_score,
    yt_score:  top.yt_score,
    cross_score: top.cross_score,
    owner,
    asset_needed: asset,
    urgency,
    suggested_source_section: suggestedSection,
  };
});

// ── Helpers ───────────────────────────────────────────────────────
function mapFormat(h) {
  if (h.format_type === 'reel') return 'reel';
  if (h.format_type === 'carousel') return 'carousel';
  if (h.format_type === 'story') return 'story';
  return 'static';
}

function classifyHook(text) {
  const t = text.toLowerCase();
  if (/\b(book|schedule|claim|secure your|book your)\b/.test(t)) return 'cta';
  if (/\b(win|wins|competition|contest|prize|championship|lowest net|closest to)\b/.test(t)) return 'promo';
  if (/\b(new|now available|just dropped|lab golf|la golf|golf bar|putter)\b/.test(t)) return 'product';
  if (/\b(lessons?|coach|teaching|instructor|cat|dave)\b/.test(t)) return 'lessons';
  if (/\b(trackman|swing speed|spin rate|club path|data|stats?)\b/.test(t)) return 'data';
  return 'hook';
}

// Owner assignment based on content type + topics
function assignOwner(contentType, topics, hookText) {
  const t = (hookText || '').toLowerCase();
  // Coaching/lesson content
  if (contentType === 'lessons' || /\b(lessons?|coach|cat |dave |teaching|instructor)\b/.test(t)) {
    return 'Coach Cat';
  }
  // Driver/fitting/equipment
  if (contentType === 'product' || /\b(driver|fitted?|fitting|irons|woods|wedge|putter|club|grip|shaft)\b/.test(t)) {
    return 'Divan';
  }
  // TrackMan/data — could be either, flag for review
  if (contentType === 'data' || /\b(trackman|swing speed|spin rate|stats?)\b/.test(t)) {
    return 'Coach Cat / Divan';
  }
  // Promo/competition
  if (contentType === 'promo' || /\b(competition|win|tournament|prize|championship|league)\b/.test(t)) {
    return 'Swing Shack page';
  }
  // CTA-led
  if (contentType === 'cta') {
    return 'Nancy / Front Desk';
  }
  // Generic brand/awareness
  if (contentType === 'awareness') {
    return 'Swing Shack page';
  }
  return 'Swing Shack page';
}

// Asset needed based on content type + format
function assetNeeded(contentType, format, topics) {
  const hasTopic = (kw) => topics.some(t => t.toLowerCase().includes(kw));

  if (contentType === 'data' || hasTopic('simulator') || hasTopic('trackman')) {
    return 'TrackMan screenshot or data graphic';
  }
  if (contentType === 'lessons') {
    return 'Swing clip or lesson photo';
  }
  if (contentType === 'product') {
    return 'Club/equipment photo or fitting moment';
  }
  if (contentType === 'promo') {
    return 'Contest/prize image or graphic';
  }
  if (contentType === 'cta') {
    return 'Text graphic or booking CTA image';
  }
  if (format === 'reel' || format === 'video') {
    return 'Swing clip or video footage';
  }
  return 'High-quality static image';
}

// Urgency based on cross_score and proximity to today
function calcUrgency(crossScore, daysFromToday) {
  if (daysFromToday === 0 && crossScore >= 8)  return 'today';
  if (daysFromToday <= 1 && crossScore >= 7)    return 'today';
  if (daysFromToday <= 3 && crossScore >= 7)    return 'this_week';
  if (crossScore >= 8)                           return 'this_week';
  return 'flexible';
}

function sourceSection(source) {
  const map = {
    watched_and_worked: 'WATCHED + WORKED',
    content_idea:      'Hook Bank / Content Ideas',
    golf_news:         'Golf News',
  };
  return map[source] || 'Hook Bank';
}

function isUsed(hookId, used) {
  if (!hookId) return false;
  const suppressedHooks = used.suppressed_hooks || [];
  const suppressedIdeas = used.suppressed_ideas || [];
  return suppressedHooks.some(h => h.id === hookId || h.hook_id === hookId)
      || suppressedIdeas.some(i => i.id === hookId);
}

function defaultCTA(contentType, objective) {
  if (contentType === 'cta') return 'Book your session · Link in bio';
  if (objective === 'bookings') return 'Book your session · Link in bio';
  if (objective === 'saves') return 'Save this · Share with a golfer';
  if (contentType === 'promo') return 'Enter now · Link in bio';
  if (contentType === 'product') return 'Shop now · Link in bio';
  return 'Link in bio · Book your session';
}

function buildWhy(c, objective) {
  const parts = [];
  if (c.source === 'watched_and_worked') {
    parts.push(`Cross-signal score ${c.cross_score.toFixed(1)}: IG proof ${c.ig_score} + YouTube alignment ${c.yt_score}`);
  } else if (c.source === 'content_idea') {
    parts.push(`Content idea score ${c.cross_score}/10`);
  } else if (c.source === 'golf_news') {
    parts.push('From golf news — timely angle');
  }
  if (objective === 'reach')    parts.push('optimised for reach');
  if (objective === 'bookings') parts.push('optimised for bookings');
  if (objective === 'saves')    parts.push('optimised for saves');
  if (objective === 'awareness') parts.push('optimised for awareness');
  return parts.join(' · ');
}

// ── Write output ──────────────────────────────────────────────────
const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_post_plan.js',
  plan_length: plan.length,
  plan,
  meta: {
    total_ready:    plan.filter(p => p.status === 'ready').length,
    total_test:     plan.filter(p => p.status === 'test').length,
    total_fallback: plan.filter(p => p.status === 'fallback').length,
    objectives_used: [...new Set(plan.map(p => p.objective))],
    urgency_breakdown: {
      today:      plan.filter(p => p.urgency === 'today').length,
      this_week:  plan.filter(p => p.urgency === 'this_week').length,
      flexible:   plan.filter(p => p.urgency === 'flexible').length,
    },
    owner_breakdown: Object.fromEntries(
      [...new Set(plan.map(p => p.owner))].map(o => [o, plan.filter(p => p.owner === o).length])
    ),
    asset_alerts: plan.filter(p => p.asset_needed && p.status === 'ready').map(p => ({
      owner: p.owner,
      asset: p.asset_needed,
      day: `${p.day} ${p.date}`,
      hook: p.hook ? p.hook.substring(0, 50) : null,
    })),
  },
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Post plan generated: ${OUTPUT}`);
console.log(`   Ready: ${output.meta.total_ready} | Test: ${output.meta.total_test} | Fallback: ${output.meta.total_fallback}`);
console.log(`   Today: ${output.meta.urgency_breakdown.today} | This week: ${output.meta.urgency_breakdown.this_week} | Flexible: ${output.meta.urgency_breakdown.flexible}`);
console.log(`   Owners: ${Object.entries(output.meta.owner_breakdown).map(([o,n]) => `${o}×${n}`).join(', ')}`);
plan.forEach(p => {
  const hook = p.hook ? p.hook.substring(0, 45) : '(none)';
  console.log(`   ${p.day.substring(0,3)} ${p.date} [${p.urgency}] ${p.owner} | ${p.objective.toUpperCase()} | ${hook}`);
});
if (output.meta.asset_alerts.length > 0) {
  console.log('\n   📦 Asset alerts:');
  output.meta.asset_alerts.slice(0,3).forEach(a => {
    console.log(`     ${a.day}: ${a.owner} needs — ${a.asset}`);
  });
}
