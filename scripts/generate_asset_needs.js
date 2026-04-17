#!/usr/bin/env node
/**
 * generate_asset_needs.js
 * Aggregates asset needs from post-plan and follow-up-queue.
 * Outputs: data/asset-needs.json
 *
 * Each entry:
 * - owner
 * - asset_type (consolidated)
 * - urgency
 * - linked posts (hook snippets)
 * - count
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'asset-needs.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const postPlan  = readJson('post-plan.json')        || {};
const followUpQ = readJson('follow-up-queue.json')  || {};

// ── Normalise asset types to clean categories ──────────────────
function normaliseAsset(raw) {
  const t = (raw || '').toLowerCase();
  if (/swing.*(clip|photo|video)/.test(t) || /lesson.*(clip|photo)/.test(t)) return 'swing_clip';
  if (/trackman|screenshot|data.*graphic/.test(t)) return 'trackman_screenshot';
  if (/club.*photo|fitting.*photo|equipment.*photo/.test(t)) return 'club_photo';
  if (/simulator.*(photo|footage|image)|bay.*photo/.test(t)) return 'simulator_photo';
  if (/drill.*(clip|demo|diagram)/.test(t)) return 'drill_demo';
  if (/text.*graphic|cta.*image|booking.*image/.test(t)) return 'text_graphic';
  if (/static.*image|high.*quality.*image|image/.test(t)) return 'static_image';
  if (/contest.*(image|graphic)|prize.*image/.test(t)) return 'promo_graphic';
  return 'static_image';
}

function urgencyRank(u) {
  return u === 'today' ? 0 : u === 'this_week' ? 1 : 2;
}

// ── Collect all asset needs ─────────────────────────────────────
const rawNeeds = [];

// From post plan
(postPlan.plan || []).forEach(p => {
  if (p.asset_needed && p.status === 'ready') {
    rawNeeds.push({
      owner:    p.owner,
      asset:    p.asset_needed,
      assetKey: normaliseAsset(p.asset_needed),
      urgency:  p.urgency,
      day:      `${p.day} ${p.date}`,
      hook:     p.hook ? p.hook.substring(0, 50) : null,
      source:   'post_plan',
    });
  }
});

// From follow-up queue
(followUpQ.queue || []).forEach(q => {
  if (q.asset_needed) {
    rawNeeds.push({
      owner:    q.owner,
      asset:    q.asset_needed,
      assetKey: normaliseAsset(q.asset_needed),
      urgency:  q.urgency,
      day:      null,
      hook:     q.suggested_hook ? q.suggested_hook.substring(0, 50) : null,
      source:   'follow_up_queue',
    });
  }
});

// ── Consolidate by owner + asset type ───────────────────────────
const byKey = {};
rawNeeds.forEach(r => {
  const key = `${r.owner}::${r.assetKey}`;
  if (!byKey[key]) {
    byKey[key] = {
      owner:      r.owner,
      asset_type: r.assetKey,
      asset_raw:  r.asset,
      urgency:    r.urgency,
      posts:      [],
      count:      0,
    };
  }
  if (r.hook) byKey[key].posts.push({ hook: r.hook, day: r.day, source: r.source });
  byKey[key].count++;
  // Keep highest urgency
  if (urgencyRank(r.urgency) < urgencyRank(byKey[key].urgency)) {
    byKey[key].urgency = r.urgency;
  }
});

const needs = Object.values(byKey)
  .sort((a, b) => urgencyRank(a.urgency) - urgencyRank(b.urgency));

// ── Summary by owner ─────────────────────────────────────────────
const byOwner = {};
needs.forEach(n => {
  if (!byOwner[n.owner]) byOwner[n.owner] = [];
  byOwner[n.owner].push(n);
});

// ── Asset label map ──────────────────────────────────────────────
const ASSET_LABELS = {
  swing_clip:         '🎬 Swing clip (video or photo)',
  trackman_screenshot:'📊 TrackMan screenshot or data graphic',
  club_photo:         '🛓 Club/equipment photo',
  simulator_photo:    '🏝 Simulator bay photo',
  drill_demo:         '🎯 Drill demonstration (clip or diagram)',
  text_graphic:      '📝 Text graphic / booking CTA image',
  static_image:       '🖼 High-quality static image',
  promo_graphic:      '🎉 Contest/prize graphic',
};

function assetLabel(key) {
  return ASSET_LABELS[key] || `📦 ${key}`;
}

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_asset_needs.js',
  count:     needs.length,
  by_owner: Object.fromEntries(
    Object.entries(byOwner).sort(([a], [b]) => a.localeCompare(b))
  ),
  needs: needs.map(n => ({
    ...n,
    asset_label: assetLabel(n.asset_type),
    posts: n.posts.slice(0, 3), // cap at 3 posts per asset
  })),
  summary: {
    total: needs.length,
    by_owner: Object.fromEntries(
      Object.entries(byOwner).map(([owner, items]) => [owner, items.length])
    ),
    by_urgency: {
      today:     needs.filter(n => n.urgency === 'today').length,
      this_week: needs.filter(n => n.urgency === 'this_week').length,
      flexible:  needs.filter(n => n.urgency === 'flexible').length,
    },
  },
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Asset needs generated: ${OUTPUT}`);
console.log(`   Total: ${needs.length} | Today: ${output.summary.by_urgency.today} | This week: ${output.summary.by_urgency.this_week}`);
Object.entries(byOwner).sort(([a], [b]) => a.localeCompare(b)).forEach(([owner, items]) => {
  console.log(`   ${owner}: ${items.length} asset need(s)`);
  items.forEach(item => {
    console.log(`     → ${assetLabel(item.asset_type).split(' ')[0]} ${assetLabel(item.asset_type).substring(2)} (${item.count} post${item.count > 1 ? 's' : ''}) [${item.urgency}]`);
    item.posts.forEach(p => console.log(`        · ${p.hook?.substring(0, 50)}`));
  });
});
