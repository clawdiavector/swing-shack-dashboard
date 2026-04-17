#!/usr/bin/env node
/**
 * generate_follow_up_queue.js
 * Takes hook winners with no follow-up (from missed-opportunities.json)
 * and generates a ready-to-use follow-up queue.
 *
 * Each item:
 * - original_hook: the proven hook
 * - suggested_follow_up: what to post next on this topic
 * - why_now: why this follow-up matters
 * - owner: who should create this
 * - asset_needed: what asset to use
 * - angle: what makes this follow-up different from the original
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'follow-up-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const hb       = readJson('hook-bank.json')        || {};
const missed   = readJson('missed-opportunities.json') || {};
const ig       = readJson('ig-analytics.json')     || {};
const ci       = readJson('content-ideas.json')    || {};
const postPlan = readJson('post-plan.json')        || {};

// ── Follow-up angles per topic ───────────────────────────────────
const TOPIC_FOLLOW_UP_ANGLES = {
  driver: [
    {
      angle: 'lesson CTA from data',
      hook:  'Your driver data tells a story. TrackMan tells you how to fix it.',
      cta:   'Book a lesson · Link in bio',
      why:   'Data hook created curiosity — now offer the solution',
    },
    {
      angle: 'equipment endorsement',
      hook:  'Custom fitting unlocked an extra 20 yards. Here\'s what TrackMan found.',
      cta:   'Book your fit · swingshack.co.za/membership',
      why:   'Proof point from fitting converts better than generic',
    },
    {
      angle: 'competition angle',
      hook:  'Lowest net score wins a new custom fitted driver. TrackMan included.',
      cta:   'Enter now · Link in bio',
      why:   'Winner hook already proven — now add prize urgency',
    },
  ],
  lessons: [
    {
      angle: 'result/social proof',
      hook:  'Zero to 18 handicap in 6 months. Cat breaks down the sessions that made it happen.',
      cta:   'Book your first lesson · swingshack.co.za/membership',
      why:   'Social proof from lessons is the strongest converter',
    },
    {
      angle: 'data-backed coaching',
      hook:  'TrackMan showed exactly what needed fixing. Three swings later — the difference was real.',
      cta:   'Book with Cat · swingshack.co.za/membership',
      why:   'Combines the data angle with human coaching story',
    },
  ],
  short_game: [
    {
      angle: 'quick win lesson',
      hook:  'One putting session with Cat changed everything. Here\'s the drill she used first.',
      cta:   'Book a lesson · swingshack.co.za/membership',
      why:   'Short game hooks attract beginners — high conversion potential',
    },
    ],
  simulator: [
    {
      angle: 'experience call-out',
      hook:  'Not practicing. Simulating. There\'s a difference and it shows in your score.',
      cta:   'Book a session · swingshack.co.za/practice',
      why:   'Targets the aspirational golfer who wants results',
    },
  ],
  slice_fix: [
    {
      angle: 'drill/demo',
      hook:  'TrackMan found your slice in 3 swings. One drill fixed it. Here\'s the drill.',
      cta:   'Book a lesson · swingshack.co.za/membership',
      why:   'Offers immediate value + booking CTA in one post',
    },
    {
      angle: 'competition setup',
      hook:  'Swing Shack\'s next competition: fix your slice, win a free month.',
      cta:   'Enter · swingshack.co.za',
      why:   'Converts curiosity into competitive engagement',
    },
  ],
  fitness: [
    {
      angle: 'golf-specific fitness',
      hook:  'Golf fitness isn\'t gym bros — it\'s Range to Round faster. Here\'s where to start.',
      cta:   'Book a TPI assessment · swingshack.co.za/membership',
      why:   'Connects fitness to the actual game',
    },
  ],
};

// Default follow-up for unknown topics
const DEFAULT_ANGLES = [
  {
    angle: 'data + coaching combo',
    hook:  'TrackMan shows you exactly what\'s costing you yards. Cat shows you how to fix it.',
    cta:   'Book a lesson · swingshack.co.za/membership',
    why:   'Combines the best performing elements',
  },
  {
    angle: 'lesson result',
    hook:  'A few sessions with Cat and TrackMan. The numbers don\'t argue.',
    cta:   'Book your session · swingshack.co.za/membership',
    why:   'Social proof from results is the strongest booking driver',
  },
];

// ── Owner assignment ───────────────────────────────────────────────
function assignOwner(topic) {
  const t = (topic || '').toLowerCase();
  if (/\b(driver|fitting|fitted|clubs?|irons|woods|wedge|putter)\b/.test(t)) return 'Divan';
  if (/\b(lessons?|coach|teaching|cat|dave|swing|tempo|short_game|putting|chipping|pitching)\b/.test(t)) return 'Coach Cat';
  if (/\b(simulator|practice|indoor|net)\b/.test(t)) return 'Divan';
  if (/\b(fitness|strength|mobility|TPI)\b/.test(t)) return 'Coach Cat';
  return 'Swing Shack page';
}

// ── Asset needed ──────────────────────────────────────────────────
function assetFor(topic) {
  const t = (topic || '').toLowerCase();
  if (/\b(driver|clubs?|fitting|fitted|equipment)\b/.test(t)) return 'Club/fitting photo or TrackMan data screenshot';
  if (/\b(lessons?|swing|coach|cat|short_game|putting|tempo)\b/.test(t)) return 'Swing clip or lesson photo';
  if (/\b(simulator|practice|indoor)\b/.test(t)) return 'Simulator bay photo or session footage';
  if (/\b(slice_fix|drill|fix)\b/.test(t)) return 'Drill demonstration clip or diagram';
  return 'Static image with data overlay';
}

// ── Build queue ───────────────────────────────────────────────────
// Get hook winners that were tagged as follow_up_gap
const followUpGaps = (missed.opportunities || []).filter(o => o.category === 'follow_up_gap');

// Also include any ww hooks with ig >= 8 that don't already have a planned post
const wwHookIds = new Set((hb.watched_and_worked || []).map(h => h.hook_id));
const plannedHookIds = new Set((postPlan.plan || []).filter(p => p.hook_id).map(p => p.hook_id));

const queue = [];
const seenTopics = new Set();

followUpGaps.forEach(gap => {
  const topic = gap.topic;
  if (seenTopics.has(topic)) return;
  seenTopics.add(topic);

  // Find the original proven hook from WATCHED+WORKED
  const originalHook = (hb.watched_and_worked || []).find(h =>
    (h.youtube_topic_match || []).includes(topic) && (h.ig_proof_score || 0) >= 8
  );

  // Get follow-up angles for this topic
  const angles = TOPIC_FOLLOW_UP_ANGLES[topic] || DEFAULT_ANGLES;
  // Pick the first angle as the suggested follow-up
  const angle = angles[0];
  if (!angle) return;

  // Flag if already in this week's post plan
  const already_planned = plannedHookIds.has(originalHook?.hook_id);

  const hasAsset = assetFor(topic) && !assetFor(topic).includes('generic');
  const hasOwner = !!assignOwner(topic);
  let reason_blocked = 'ready_now';
  if (already_planned)          reason_blocked = 'in_plan';
  else if (!hasAsset)          reason_blocked = 'needs_asset';
  else if (!hasOwner)           reason_blocked = 'needs_owner';

  queue.push({
    topic,
    original_hook:     originalHook?.hook_text || null,
    original_ig_score: originalHook?.ig_proof_score || gap.ig_score || null,
    suggested_hook:    angle.hook,
    suggested_cta:     angle.cta,
    angle:              angle.angle,
    why_now:            already_planned ? `Topic already scheduled this week — follow-up CTA still recommended` : angle.why,
    owner:               assignOwner(topic),
    asset_needed:       assetFor(topic),
    suggested_format:  topic === 'lessons' || topic === 'short_game' ? 'reel' : 'static',
    urgency:             originalHook?.ig_proof_score >= 9 ? 'high' : 'medium',
    reason_blocked,
    already_planned,
  });
});

// Sort by urgency then by IG score
const urgencyOrder = { high: 0, medium: 1, low: 2 };
queue.sort((a, b) => {
  if (urgencyOrder[a.urgency] !== urgencyOrder[b.urgency]) return urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
  return (b.original_ig_score || 0) - (a.original_ig_score || 0);
});

// Group by owner
const byOwner = {};
queue.forEach(item => {
  if (!byOwner[item.owner]) byOwner[item.owner] = [];
  byOwner[item.owner].push(item);
});

// ── Write output ──────────────────────────────────────────────────
const output = {
  updated:    new Date().toISOString(),
  generated:  'generate_follow_up_queue.js',
  count:      queue.length,
  by_owner:   byOwner,
  queue,
  meta: {
    high_urgency: queue.filter(q => q.urgency === 'high').length,
    medium_urgency: queue.filter(q => q.urgency === 'medium').length,
    owners: Object.keys(byOwner),
  },
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Follow-up queue generated: ${OUTPUT}`);
console.log(`   Items: ${queue.length} | High: ${output.meta.high_urgency} | Medium: ${output.meta.medium_urgency}`);
console.log(`   By owner: ${Object.entries(byOwner).map(([o,n]) => `${o}×${n.length}`).join(', ')}`);
queue.forEach((q, i) => {
  const rb = { in_plan: '📅 in_plan', needs_asset: '📦 needs_asset', needs_owner: '👤 needs_owner', ready_now: '✅ ready_now' }[q.reason_blocked] || q.reason_blocked;
  console.log(`   ${i+1}. [${q.urgency.toUpperCase()}] ${q.owner} | ${q.topic} | ${rb}`);
  console.log(`      Suggested: ${q.suggested_hook.substring(0, 60)}`);
  console.log(`      CTA: ${q.suggested_cta}`);
  console.log(`      Asset: ${q.asset_needed}`);
});
