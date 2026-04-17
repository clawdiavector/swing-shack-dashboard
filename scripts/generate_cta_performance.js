#!/usr/bin/env node
/**
 * generate_cta_performance.js
 * Ranks CTA types by performance.
 * Output: data/cta-performance.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'cta-performance.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const conv  = readJson('conversion-attribution.json') || {};
const ig    = readJson('ig-analytics.json')           || {};
const sales = readJson('sales-priority.json')         || {};

// ── CTA Type Definitions ────────────────────────────────────────
const CTA_TYPES = {
  BOOKING: {
    label:  'Booking CTA',
    terms:  ['book', 'booking', 'reserve', 'schedule', 'get started', 'secure your'],
    color:  '#ff4757',
    intent: 'high',
  },
  LESSONS: {
    label:  'Lessons CTA',
    terms:  ['lesson', 'coach', 'cat', 'dave', 'training', 'with catherine', 'with dave'],
    color:  '#2ed573',
    intent: 'high',
  },
  FITTING: {
    label:  'Fitting CTA',
    terms:  ['fitting', 'fitted', 'custom driver', 'custom iron', 'get fitted', 'club fitting'],
    color:  '#ffa502',
    intent: 'high',
  },
  PROMO: {
    label:  'Promo / Contest CTA',
    terms:  ['discount', 'save', 'deal', 'offer', 'prize', 'win', 'free', 'off', '%'],
    color:  '#9c88ff',
    intent: 'medium',
  },
  SOFT: {
    label:  'Soft / Engagement CTA',
    terms:  ['link in bio', 'comment', 'share', 'tag', 'dm', 'follow', 'swingshack', 'visit'],
    color:  '#748ffc',
    intent: 'low',
  },
  MEMBER: {
    label:  'Membership CTA',
    terms:  ['member', 'membership', 'perk', 'unlimited', 'join', 'sign up'],
    color:  '#ff6b81',
    intent: 'medium',
  },
};

function detectCTA(caption) {
  const lower = (caption || '').toLowerCase();
  // Try more specific first
  if (['fitting', 'fitted', 'custom driver', 'custom iron', 'club fitting'].some(t => lower.includes(t))) return 'FITTING';
  if (['book', 'booking', 'reserve', 'schedule', 'get started', 'secure your'].some(t => lower.includes(t))) return 'BOOKING';
  if (['lesson', 'coach', 'cat', 'dave', 'with catherine', 'with dave', 'training'].some(t => lower.includes(t))) return 'LESSONS';
  if (['member', 'membership', 'perk', 'unlimited', 'join'].some(t => lower.includes(t))) return 'MEMBER';
  if (['discount', 'save', 'deal', 'offer', 'prize', 'win', 'free', ' off '].some(t => lower.includes(t))) return 'PROMO';
  if (['link in bio', 'comment', 'share', 'tag', 'dm', 'follow', 'swingshack', 'visit'].some(t => lower.includes(t))) return 'SOFT';
  return 'SOFT';
}

const igPosts = ig.posts || [];

// ── Per-CTA analysis ─────────────────────────────────────────────
const ctaData = {};
Object.keys(CTA_TYPES).forEach(t => {
  ctaData[t] = { posts: [], reach: 0, likes: 0, saves: 0, comments: 0, reach_raw: 0 };
});

igPosts.slice(0, 30).forEach(p => {
  const ctaType = detectCTA(p.caption || '');
  const reach    = parseInt(p.reach) || 0;
  const likes    = parseInt(p.likeCount) || 0;
  const saves    = parseInt(p.saveCount) || 0;
  const comments = parseInt(p.commentsCount || p.commentCount) || 0;
  const engRate  = parseFloat(p.engagementRate || 0) || 0;

  ctaData[ctaType].posts.push({ id: p.id, reach, likes, saves, comments, engRate, caption: (p.caption || '').substring(0, 80) });
  ctaData[ctaType].reach     += reach;
  ctaData[ctaType].likes    += likes;
  ctaData[ctaType].saves     += saves;
  ctaData[ctaType].comments += comments;
});

const ctaResults = Object.entries(ctaData)
  .filter(([, d]) => d.posts.length > 0)
  .map(([type, d]) => {
    const count = d.posts.length;
    const avgReach  = d.reach / count;
    const avgLikes  = d.likes / count;
    const avgSaves  = d.saves / count;
    const avgComm   = d.comments / count;
    const avgEng    = d.posts.reduce((s, p) => s + p.engRate, 0) / count;
    const saveRate  = avgReach > 0 ? avgSaves / avgReach * 100 : 0;
    const clickProxy = avgSaves * 3 + avgComm * 2 + avgLikes * 0.5; // weighted engagement
    const conversion_signal = parseFloat((saveRate * 3 + avgEng * 0.5).toFixed(2));

    return {
      cta_type:           type,
      label:              CTA_TYPES[type].label,
      color:              CTA_TYPES[type].color,
      intent:             CTA_TYPES[type].intent,
      post_count:         count,
      total_reach:        d.reach,
      avg_reach:          parseFloat(avgReach.toFixed(0)),
      avg_likes:          parseFloat(avgLikes.toFixed(1)),
      avg_saves:          parseFloat(avgSaves.toFixed(1)),
      avg_comments:       parseFloat(avgComm.toFixed(1)),
      avg_engagement_rate: parseFloat(avgEng.toFixed(2)),
      save_rate:          parseFloat(saveRate.toFixed(2)),
      click_proxy:        parseFloat(clickProxy.toFixed(1)),
      conversion_signal,
    };
  })
  .sort((a, b) => b.conversion_signal - a.conversion_signal)
  .map((r, i) => ({ ...r, rank: i + 1 }));

// ── Best and worst ───────────────────────────────────────────────
const bestCTA  = ctaResults[0] || null;
const worstCTA = ctaResults[ctaResults.length - 1] || null;

// ── What to test next ─────────────────────────────────────────────
// Rank CTA types not yet heavily tested by conversion signal
const testedTypes = new Set(ctaResults.map(r => r.cta_type));
const allTypes    = Object.keys(CTA_TYPES);
const untested     = allTypes.filter(t => !testedTypes.has(t) && CTA_TYPES[t].intent === 'high');

const testsToRun = [
  ...ctaResults.filter(r => r.intent === 'high' && r.conversion_signal < 5).slice(0, 2).map(r => ({
    action:  'Test stronger version',
    current: `${r.label} (eng:${r.avg_engagement_rate}% save:${r.save_rate}%)`,
    why:     `${r.label} has high intent but underperforming — test a more direct booking path`,
    owner:   'Swing Shack page',
  })),
  ...untested.slice(0, 1).map(t => ({
    action:   'Start testing',
    current:  `${CTA_TYPES[t].label} — ${0} posts in sample`,
    why:      `High intent CTA type with no performance data yet`,
    owner:    'Swing Shack page',
  })),
].slice(0, 3);

// ── Recommendations ───────────────────────────────────────────────
const recommendations = ctaResults.slice(0, 3).map(r => ({
  cta_type:   r.cta_type,
  label:      r.label,
  rank:       r.rank,
  signal:     r.conversion_signal,
  verdict:    r.rank === 1 ? '🏆 Best performer — push this CTA style' :
              r.rank === 2 ? '📈 Solid — worth keeping in rotation' :
              '⚠️ Underperforming — test a variation',
  action:     r.rank === 1 ? `Scale ${r.label} posts — eng ${r.avg_engagement_rate}%, save rate ${r.save_rate}%` :
              r.rank === 2 ? `Maintain ${r.label} presence` :
              `Rework ${r.label} — try more specific language or swap to ${bestCTA?.label}`,
  owner:      r.cta_type === 'LESSONS' ? 'Coach Cat' :
              r.cta_type === 'FITTING' ? 'Divan' : 'Swing Shack page',
}));

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_cta_performance.js',
  summary: {
    ctas_analysed: ctaResults.length,
    best_cta:      bestCTA?.label || 'n/a',
    best_signal:   bestCTA?.conversion_signal || 0,
    worst_cta:     worstCTA?.label || 'n/a',
    worst_signal:  worstCTA?.conversion_signal || 0,
    tests_to_run:  testsToRun.length,
  },
  cta_rankings: ctaResults,
  best_cta:     bestCTA,
  worst_cta:    worstCTA,
  recommendations,
  tests_to_run: testsToRun,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ CTA performance: ${OUTPUT}`);
console.log(`   ${ctaResults.length} CTA types ranked:`);
ctaResults.forEach(r => {
  console.log(`   ${r.rank}. ${r.label} — eng:${r.avg_engagement_rate}% save:${r.save_rate}% signal:${r.conversion_signal}`);
});
if (bestCTA) console.log(`   🏆 Best: ${bestCTA.label} (${bestCTA.conversion_signal} signal)`);
if (worstCTA && worstCTA.cta_type !== bestCTA?.cta_type) console.log(`   ⚠️ Worst: ${worstCTA.label} (${worstCTA.conversion_signal} signal)`);
