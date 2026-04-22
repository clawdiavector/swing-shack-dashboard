#!/usr/bin/env node
/**
 * generate_captions.js — caption_closer agent core script
 * Reads: content-blueprints.json, hook-bank.json, cta-performance.json
 * Produces: captions.json, caption-variants.json
 *
 * Per blueprint produces:
 *   - short caption (IG feed, 150 chars)
 *   - medium caption (IG feed, full)
 *   - strong CTA version (direct booking)
 *   - soft CTA version (link in bio)
 *   - channel adaptations: IG post, Story, Reel, YouTube Shorts
 *
 * Schema: https://clawdia.io/agents/caption-closer/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const bp = readJson('content-blueprints.json') || {};
  const ctaPerf = readJson('cta-performance.json') || {};
  const ctaList = ctaPerf.top_ctas || [
    { cta: 'Link in bio · Book your session', type: 'booking' },
    { cta: 'DM us to get started', type: 'booking' },
    { cta: 'Swipe up · Learn more', type: 'awareness' },
    { cta: 'Drop a 🫂 below', type: 'engagement' },
  ];

  const blueprints = (bp.blueprints || bp.items || []).slice(0, 20);

  // ── Caption templates per format ─────────────────────────────────────
  const TONE_GOLF = 'Indoor golf · TrackMan tech · Johannesburg';
  const TONE_SOCIAL = 'Swing Shack · Sandton';

  function shortCaption(hook, service) {
    const svc = service || 'Swing Shack';
    return `${hook}\n\n${svc}`.substring(0, 150);
  }

  function mediumCaption(hook, service, cta) {
    const ctaText = cta?.cta || 'Link in bio · Book your session';
    const svc = service || 'Swing Shack';
    const emoji = service === 'Coaching' ? '🎯' : service === 'Club Fitting' ? '🏌️' : '🎮';
    return `${hook}\n\n${emoji} ${svc}\n\n${ctaText}\n\n#IndoorGolfJohannesburg #GolfSouthAfrica #TrackManGolf #SwingShack`;
  }

  function strongCTA(hook, service) {
    const svc = service || 'Swing Shack';
    return `${hook}\n\nReady to see what your numbers say?\nBook your TrackMan session at Swing Shack — from R250.\n\nLink in bio or DM us. 🏌️`;
  }

  function softCTA(hook, service) {
    const svc = service || 'Swing Shack';
    return `${hook}\n\nSwipe to see more. 👆\n\n${svc} · Indoor golf has never been this good.`;
  }

  function channelAdapt(hook, service, platform) {
    const svc = service || 'Swing Shack';
    const adapters = {
      'ig_post': mediumCaption(hook, svc, ctaList[0]),
      'story': `${hook}\n\n${svc} 🇿🇦\n\nTap to book.`,
      'reel': `${hook}\n\nThis is what TrackMan sees.\n\nDrop a 🫂 if you want to know your numbers.\n\nSwing Shack · Link in bio. 🎯`,
      'youtube_shorts': `${hook}\n\nTrackMan doesn't lie.\nSwing Shack, Johannesburg.\n\nFull video link in bio.`,
    };
    return adapters[platform] || mediumCaption(hook, svc, ctaList[0]);
  }

  // ── Build captions from blueprints ──────────────────────────────────
  const captions = [];
  const variants = [];

  blueprints.forEach((b, i) => {
    const hook = b.hook_overlay_text || b.source_hook_text || b.caption?.split('\n')[0] || '';
    const service = b.service || 'Practice';
    const cta = ctaList[i % ctaList.length];
    const id = `cap-${new Date().toISOString().split('T')[0]}-${uid()}`;

    captions.push({
      caption_id: id,
      schema: 'https://clawdia.io/agents/caption-closer/v1',
      generated: new Date().toISOString(),
      linked_blueprint_id: b.blueprint_id || null,
      linked_hook_id: b.source_hook_id || null,
      platform: b.platform || 'instagram',
      format_type: b.format_type || 'static',
      hook_text: hook,
      short_caption: shortCaption(hook, service),
      medium_caption: mediumCaption(hook, service, cta),
      status: 'draft',
      confidence: b.confidence || 60,
      owner: 'caption_closer',
      source_section: b.source || 'content_blueprint',
      ready_for_qa: true,
      quality_notes: `Hook confidence: ${b.confidence}/100. Source: ${b.signal_bucket || b.source || 'blueprint'}.`,
      next_action: 'QA review, then approve and post',
    });

    // CTA variants
    const varId = `var-${uid()}`;
    variants.push({
      variant_id: varId,
      schema: 'https://clawdia.io/agents/caption-closer/v1',
      generated: new Date().toISOString(),
      linked_caption_id: id,
      linked_blueprint_id: b.blueprint_id || null,
      hook_text: hook,
      strong_cta: strongCTA(hook, service),
      soft_cta: softCTA(hook, service),
      channels: {
        ig_post: channelAdapt(hook, service, 'ig_post'),
        story: channelAdapt(hook, service, 'story'),
        reel: channelAdapt(hook, service, 'reel'),
        youtube_shorts: channelAdapt(hook, service, 'youtube_shorts'),
      },
      cta_type: cta?.type || 'booking',
      cta_text: cta?.cta || 'Link in bio · Book your session',
      status: 'draft',
      confidence: b.confidence || 60,
      ready_for_qa: true,
      owner: 'caption_closer',
      next_action: 'QA review, pick CTA variant, post',
    });
  });

  const captionsResult = {
    schema: 'https://clawdia.io/agents/caption-closer/v1',
    generated: new Date().toISOString(),
    total: captions.length,
    by_format: {
      static: captions.filter(c => c.format_type === 'static').length,
      carousel: captions.filter(c => c.format_type === 'carousel').length,
      reel: captions.filter(c => c.format_type === 'reel').length,
      blog: captions.filter(c => c.format_type === 'blog').length,
      short_script: captions.filter(c => c.format_type === 'short_script').length,
    },
    by_platform: {
      instagram: captions.filter(c => c.platform === 'instagram').length,
    },
    ready_for_qa: captions.filter(c => c.ready_for_qa).length,
    captions,
  };

  const variantsResult = {
    schema: 'https://clawdia.io/agents/caption-closer/v1',
    generated: new Date().toISOString(),
    total: variants.length,
    ready_for_qa: variants.filter(v => v.ready_for_qa).length,
    variants,
  };

  fs.writeFileSync(path.join(DATA, 'captions.json'), JSON.stringify(captionsResult, null, 2));
  fs.writeFileSync(path.join(DATA, 'caption-variants.json'), JSON.stringify(variantsResult, null, 2));

  console.log(`✅ Captions: ${captionsResult.total} total, ${captionsResult.ready_for_qa} ready for QA`);
  console.log(`   Variants: ${variantsResult.total} total — IG/Story/Reel/YT Shorts per hook`);
  console.log(`   Top caption: "${captions[0]?.short_caption?.substring(0, 60)}..."`);
}

module.exports = { run };
if (require.main === module) run();