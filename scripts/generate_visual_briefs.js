#!/usr/bin/env node
/**
 * generate_visual_briefs.js — visual_forge agent core script
 * Reads: content-blueprints.json, hook-bank.json, post-plan.json
 * Produces: visual-briefs.json, image-prompts.json, thumbnail-briefs.json
 *
 * Rule: prompts only — briefs and prompts for human/AI to execute, not finished creative.
 * Schema: https://clawdia.io/agents/visual-forge/v1
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
  const blueprints = (bp.blueprints || bp.items || []).slice(0, 20);

  // ── Visual type generators ─────────────────────────────────────────
  const VISUAL_TYPES = ['static', 'carousel', 'reel', 'blog', 'short_script'];

  function statCardBrief(hook, service) {
    return {
      layout: 'data-card-dark',
      bg: '#0a0f1a',
      headline: hook,
      subhead: `${service} · TrackMan Technology`,
      stats: [
        { label: 'YOUR SWING SPEED', value: '83 MPH', benchmark: 'PGA Avg: 112' },
        { label: 'CARRY DISTANCE', value: '217 M', benchmark: 'PGA Avg: 264' },
      ],
      cta: 'Book your TrackMan session · swingshack.co.za',
      mood: 'data-driven, premium, serious',
      fonts: 'Space Grotesk or DM Sans bold',
    };
  }

  function carouselBrief(hook, service) {
    return {
      layout: '10-slide-carousel',
      slide_1: { type: 'hook', text: hook, style: 'bold stat overlay on dark bg' },
      slide_2_9: { type: 'proof', format: 'TrackMan data card with number + bar chart' },
      slide_10: { type: 'cta', text: `${service} · Book at swingshack.co.za`, style: 'full-width dark card' },
      mood: 'educational, data-driven, professional',
      color_palette: ['#0a0f1a', '#00c853', '#ffffff', '#ffa502'],
    };
  }

  function reelBrief(hook, service) {
    return {
      concept: 'POV: you at TrackMan, first session',
      hook_frame: `First 3 seconds: ${hook} — bold text overlay, dark background, impact font`,
      transition: 'Zoom in on TrackMan screen showing club head speed / carry distance',
      body_frames: '3-8s data reveal, 8-15s comparison to PGA average, 15-25s booking CTA',
      ending_frame: 'Book your session · swingshack.co.za',
      trending_audio_suggestion: 'trending golf/sports audio or lo-fi beats',
      caption_text: hook,
      hashtags: '#indoorgolf #trackman #golftok #golfsa',
      mood: 'fast-paced, curious, premium',
    };
  }

  function blogThumbnailBrief(hook, service) {
    return {
      type: 'youtube_thumbnail',
      layout: 'stat-overlay',
      left_panel: 'Golf ball on tee, dark moody indoor lighting',
      right_panel: `Text overlay: "${hook.substring(0, 40)}"`,
      bottom_bar: 'SWING SHACK · TrackMan Technology',
      style: 'High contrast, yellow/gold text on dark background, arrow pointing up',
      aspect: '16:9',
      text_rules: 'Max 5 words large text, use numbers/stats, no full sentences',
    };
  }

  // ── Image prompt generator ─────────────────────────────────────────
  function buildPrompt(brief, format, service) {
    const serviceColors = {
      'Club Fitting': 'professional golf studio, TrackMan screen, data overlays, dark moody lighting',
      'Coaching': 'golf lesson indoor, instructor with student, launch monitor visible, warm lighting',
      'Practice': 'golf simulator bay, HD screen showing ball flight data, clean modern space',
      'Social Play': 'group of friends enjoying indoor golf, social atmosphere, fun energy',
    };
    const style = serviceColors[service] || 'indoor golf simulator, premium, dark modern space';

    const prompts = {
      static: `Golf social media post, ${style}. Bold text overlay at top: "${brief.hook || brief.headline || ''}". Dark background with green/gold accents. Data visualization elements visible. Clean, premium, South African golf aesthetic. No people. 9:16 aspect ratio. High contrast.`,
      carousel: `Golf data presentation slide, ${style}. Clean dark background (#0a0f1a). Large bold white text. Green (#00c853) data bars or stat callouts. Professional, modern, TrackMan aesthetic. No watermark. 1:1 square format.`,
      reel: `Cinematic golf content, ${style}. First frame shows data readout with golf club. Moody indoor lighting with green/blue accent lights. TrackMan or similar launch monitor visible. Premium feel. 9:16 vertical video format.`,
      blog: `Featured image for golf blog article. ${style}. Clean composition, natural lighting. Represents indoor golf technology and improvement. Landscape orientation. 16:9.`,
      short_script: `YouTube thumbnail concept for golf content. High contrast. Yellow bold text on dark background. Golf ball in frame. Dramatic lighting. TrackMan screen glow in background. 16:9.`,
    };
    return prompts[format] || prompts.static;
  }

  // ── Build all outputs ──────────────────────────────────────────────
  const briefs = [];
  const prompts_out = [];
  const thumbnails = [];

  blueprints.forEach((b, i) => {
    const hook = b.hook_overlay_text || b.source_hook_text || '';
    const service = b.service || 'Practice';
    const format = b.format_type || VISUAL_TYPES[i % VISUAL_TYPES.length];
    const id = `vb-${uid()}`;

    // Visual brief
    const visualTypes = {
      static: statCardBrief(hook, service),
      carousel: carouselBrief(hook, service),
      reel: reelBrief(hook, service),
      blog: { layout: 'blog-hero', mood: 'educational, clean, authoritative', style: 'photo with overlay text' },
      short_script: { layout: 'thumbnail-ready', concept: 'stat reveal', style: 'bold text + data visual' },
    };

    briefs.push({
      brief_id: id,
      schema: 'https://clawdia.io/agents/visual-forge/v1',
      generated: new Date().toISOString(),
      linked_blueprint_id: b.blueprint_id || null,
      linked_hook_id: b.source_hook_id || null,
      format_type: format,
      visual_type: format === 'static' ? 'data-card' : format === 'carousel' ? 'carousel' : format === 'reel' ? 'reel-concept' : 'blog-image',
      service,
      hook_text: hook,
      brief: visualTypes[format] || visualTypes.static,
      status: 'draft',
      confidence: b.confidence || 60,
      owner: 'visual_forge',
      ready_for_qa: true,
      next_action: 'Execute prompt via image AI, QA output',
    });

    // Image prompt
    prompts_out.push({
      prompt_id: `ip-${uid()}`,
      schema: 'https://clawdia.io/agents/visual-forge/v1',
      generated: new Date().toISOString(),
      linked_blueprint_id: b.blueprint_id || null,
      linked_brief_id: id,
      format_type: format,
      service,
      hook_text: hook,
      prompt_text: buildPrompt(briefs[briefs.length - 1].brief, format, service),
      aspect_ratio: format === 'reel' || format === 'short_script' ? '9:16' : format === 'blog' ? '16:9' : '1:1',
      quality: 'high',
      style_tags: [service.toLowerCase(), 'indoor-golf', 'data-driven', 'premium'],
      status: 'draft',
      confidence: b.confidence || 60,
      ready_for_qa: true,
      owner: 'visual_forge',
      next_action: 'Run prompt through image AI, QA result',
    });

    // Thumbnail brief
    thumbnails.push({
      thumbnail_id: `tb-${uid()}`,
      schema: 'https://clawdia.io/agents/visual-forge/v1',
      generated: new Date().toISOString(),
      linked_blueprint_id: b.blueprint_id || null,
      linked_hook_id: b.source_hook_id || null,
      platform: format === 'short_script' || format === 'reel' ? 'youtube_shorts' : 'youtube',
      thumbnail: blogThumbnailBrief(hook, service),
      status: 'draft',
      confidence: b.confidence || 60,
      owner: 'visual_forge',
      ready_for_qa: true,
      next_action: 'Design thumbnail, QA against brand rules',
    });
  });

  const briefsResult = {
    schema: 'https://clawdia.io/agents/visual-forge/v1',
    generated: new Date().toISOString(),
    total: briefs.length,
    ready_for_qa: briefs.filter(b => b.ready_for_qa).length,
    briefs,
  };

  const promptsResult = {
    schema: 'https://clawdia.io/agents/visual-forge/v1',
    generated: new Date().toISOString(),
    total: prompts_out.length,
    ready_for_qa: prompts_out.filter(p => p.ready_for_qa).length,
    prompts: prompts_out,
  };

  const thumbsResult = {
    schema: 'https://clawdia.io/agents/visual-forge/v1',
    generated: new Date().toISOString(),
    total: thumbnails.length,
    ready_for_qa: thumbnails.filter(t => t.ready_for_qa).length,
    thumbnails,
  };

  fs.writeFileSync(path.join(DATA, 'visual-briefs.json'), JSON.stringify(briefsResult, null, 2));
  fs.writeFileSync(path.join(DATA, 'image-prompts.json'), JSON.stringify(promptsResult, null, 2));
  fs.writeFileSync(path.join(DATA, 'thumbnail-briefs.json'), JSON.stringify(thumbsResult, null, 2));

  console.log(`✅ Visual briefs: ${briefsResult.total} | ${briefsResult.ready_for_qa} ready for QA`);
  console.log(`   Image prompts: ${promptsResult.total} | ${promptsResult.ready_for_qa} ready for QA`);
  console.log(`   Thumbnail briefs: ${thumbsResult.total}`);
  console.log(`   Top prompt: "${prompts_out[0]?.prompt_text?.substring(0, 80)}..."`);
}

module.exports = { run };
if (require.main === module) run();