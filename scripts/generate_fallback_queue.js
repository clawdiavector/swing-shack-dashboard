#!/usr/bin/env node
/**
 * generate_fallback_queue.js
 * Suggests safe replacements when something is blocked or unavailable.
 * Output: data/fallback-queue.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT  = path.join(DATA_DIR, 'fallback-queue.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const tasks   = readJson('daily-task-cards.json')         || {};
const capSht = readJson('capacity-shift.json')          || {};
const scale  = readJson('scaling-recommendations.json')  || {};
const plan  = readJson('post-plan.json')               || {};

function uid() { return 'fb_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

const allTasks = tasks.all_tasks || [];
const allShift = capSht.shifts || [];

// ── 1. Reel → Static swap ───────────────────────────────────
const reelBlocked = allTasks.filter(t =>
  (t.format === 'reel' || t.format === 'video') &&
  t.status === 'blocked' &&
  t.blockers && t.blockers.some(b => b.includes('asset'))
);
const reelFallbacks = reelBlocked.map(t => {
  const fallbackIdea = (scale.recommendations || []).find(s =>
    s.type === 'hook_series' && !s.already_scheduled
  );
  return {
    fallback_id:      uid(),
    original_task_id:   t.task_id,
    original_hook:     t.title,
    original_format:   t.format,
    blocker:          t.blockers.join(', '),
    swap_to_format:    'static',
    fallback_hook:     fallbackIdea ? fallbackIdea.hook : 'TrackMan reveals your swing truth. One session. From R250.',
    fallback_cta:      'Book your session \u00b7 swingshack.co.za/membership',
    fallback_caption:   (fallbackIdea ? fallbackIdea.hook : t.suggested_hook || t.title) + '\n\nBook your session \u00b7 swingshack.co.za/membership',
    asset_needed:     'High-quality static image',
    why_safe:        'Static is faster to produce and maintains the core message — booking CTA intact',
    owner:            t.owner,
    urgency:          t.urgency,
    quality_loss:    'Medium — Reels get 2x reach but static converts better for booking intent',
  };
});

// ── 2. Coach Cat overloaded → Swing Shack page swap ─────────────
const coachOverloaded = allShift.filter(s =>
  s.action === 'reassign' || s.action === 'reassign_to_page'
);
const coachFallbacks = coachOverloaded.map(s => ({
  fallback_id:      uid(),
  action:          'swap_owner',
  from_owner:       s.from_owner,
  to_owner:         s.to_owner,
  task_title:       s.task_title,
  task_id:          s.task_id,
  blocker:          s.from_owner + ' overloaded — ' + s.reason,
  fallback_owner:    s.to_owner,
  urgency:          s.severity,
  why_safe:        s.to_owner + ' can execute this task without specialist expertise',
  quality_loss:    'Low — content quality maintained, specialist input not required',
}));

// ── 3. No asset → text-led hook card ──────────────────────────
const assetBlock = allTasks.filter(t =>
  t.status === 'blocked' &&
  t.blockers && t.blockers.some(b => b.includes('asset')) &&
  t.source !== 'retarget'
);
const textFallbacks = assetBlock.map(t => ({
  fallback_id:      uid(),
  original_task_id: t.task_id,
  original_hook:   t.title,
  blocker:         t.blockers.join(', '),
  fallback_hook:   t.suggested_hook || t.title,
  fallback_cta:    t.suggested_cta || 'Book your session \u00b7 swingshack.co.za/membership',
  fallback_format: 'text_graphic',
  fallback_caption: (t.suggested_hook || t.title) + '\n\nBook your session \u00b7 swingshack.co.za/membership\n\n#IndoorGolfJohannesburg #TrackMan #SwingShack',
  asset_needed:    'Text only — no photo/video required',
  why_safe:       'Text graphics work well for booking CTAs — no asset dependency',
  owner:           t.owner,
  urgency:         t.urgency,
  quality_loss:    'Low — text-led posts have proven conversion for booking intent',
}));

// ── 4. CTA missing → booking-safe fallback caption ─────────────
const ctaBlock = allTasks.filter(t =>
  t.blockers && t.blockers.some(b => b.includes('cta') || b.includes('booking'))
);
const ctaFallbacks = ctaBlock.map(t => ({
  fallback_id:      uid(),
  original_task_id: t.task_id,
  original_caption: t.suggested_cta || '',
  blocker:         'CTA missing from caption',
  fallback_caption: (t.suggested_hook || t.title) + '\n\nReady to fix your game?\nBook a session \u2192 swingshack.co.za/membership\n\n#IndoorGolf #TrackManGolf #SwingShack',
  fallback_cta:    'Book your session \u00b7 swingshack.co.za/membership',
  why_safe:        'Direct booking CTA is the highest-converting anchor for this audience',
  owner:            t.owner,
  urgency:          t.urgency,
  quality_loss:    'None — adding CTA improves conversion',
}));

// ── 5. Delayed asset → lower-urgency fallback post ─────────────
const delayedAssets = (capSht.shifts || []).filter(s => s.action === 'delay');
const delayFallbacks = delayedAssets.map(s => ({
  fallback_id:      uid(),
  action:          'swap_to_ready_post',
  original_task_id: s.task_id,
  original_asset:  s.asset,
  blocker:         'Asset ' + s.asset + ' delayed — ' + s.reason,
  fallback_task:    s.reason.includes('Swing Shack') || s.reason.includes('Coach Cat')
    ? (s.reason.includes('Swing Shack') ? 'Coach Cat' : 'Swing Shack page') + ' — use page post instead'
    : 'Use a ready post from this week\'s plan',
  fallback_format: 'static',
  fallback_caption: 'Book your indoor golf session \u2192 swingshack.co.za/bookings\nFrom R250/session \u00b7 TrackMan powered \u00b7 Johannesburg',
  why_safe:        'Keeps schedule on track — no asset dependency',
  owner:            s.owner,
  urgency:          s.severity,
  quality_loss:    'Low — static booking CTA post is always executable',
}));

// ── Combine ───────────────────────────────────────────────────
const allFallbacks = [
  ...reelFallbacks,
  ...coachFallbacks,
  ...textFallbacks,
  ...ctaFallbacks,
  ...delayFallbacks,
].filter(Boolean);

allFallbacks.sort((a, b) => {
  const urgOrder = { high: 0, medium: 1, low: 2 };
  return (urgOrder[a.urgency] || 1) - (urgOrder[b.urgency] || 1);
});

const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_fallback_queue.js',
  summary: {
    total:         allFallbacks.length,
    reel_swaps:    reelFallbacks.length,
    owner_swaps:   coachFallbacks.length,
    text_fallbacks: textFallbacks.length,
    cta_fallbacks: ctaFallbacks.length,
    delay_swaps:   delayFallbacks.length,
  },
  fallbacks: allFallbacks,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Fallback queue: ${OUTPUT}`);
console.log(`   Total: ${allFallbacks.length} | Reel→Static: ${reelFallbacks.length} | Owner swaps: ${coachFallbacks.length} | Text fallback: ${textFallbacks.length}`);
allFallbacks.slice(0, 5).forEach(f => {
  console.log(`   [${(f.urgency || 'med').toUpperCase()}] ${f.action || f.original_format || 'swap'} — ${f.fallback_format || 'text'}`);
  console.log(`      Why: ${f.why_safe.substring(0, 70)}`);
});
