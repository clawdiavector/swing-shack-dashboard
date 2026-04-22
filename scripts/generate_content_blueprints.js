#!/usr/bin/env node
/**
 * generate_content_blueprints.js
 * content_architect agent core script
 * Takes hook bank + post plan + CTA data → produces platform-specific content blueprints
 * Blueprint types: reel concept, carousel, static post, short script, blog outline
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, name), 'utf8')); }
  catch { return null; }
}

function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function run() {
  // ── Normalise hook bank ──────────────────────────────────────────────
  const rawHb = readJson('hook-bank.json') || {};
  const hooks = [
    ...(rawHb.output_buckets?.proven_and_trending || []),
    ...(rawHb.output_buckets?.proven_only || []),
    ...(rawHb.output_buckets?.trending_to_test || []),
  ].slice(0, 20);

  // ── Post plan for context ────────────────────────────────────────────
  const plan = readJson('post-plan.json');
  const planEntries = plan?.plan || [];

  // ── CTA performance ──────────────────────────────────────────────────
  const ctaPerf = readJson('cta-performance.json') || {};
  const topCtas = ctaPerf.top_ctas || [
    { cta: 'Link in bio · Book your session', type: 'booking', score: 8 },
    { cta: 'DM us to get started', type: 'booking', score: 7 },
    { cta: 'Swipe to see more', type: 'awareness', score: 6 },
  ];

  // ── Service topics for content ───────────────────────────────────────
  const services = [
    { name: 'Club Fitting', keywords: ['trackman', 'fitting', 'clubs', 'driver', 'irons', 'custom'], emoji: '🏌️' },
    { name: 'Coaching', keywords: ['lesson', 'coach', 'swing', 'improve', 'technique', 'tpi'], emoji: '🎯' },
    { name: 'Practice', keywords: ['simulator', 'range', 'indoor', 'bucket', 'warm up'], emoji: '🎮' },
    { name: 'Social Play', keywords: ['social', 'fun', 'group', 'event', 'corporate', 'party'], emoji: '🥂' },
  ];

  // ── Format templates ─────────────────────────────────────────────────
  const BLUEPRINT_TYPES = ['static', 'carousel', 'reel', 'blog', 'short_script'];

  function generateCaption(hook, service, cta, format) {
    const ctaText = typeof cta === 'string' ? cta : cta.cta || 'Link in bio · Book your session';
    const hookText = hook.hook_text || hook.headline || '';
    const captions = {
      static: `${hookText}\n\n${service.emoji} ${service.name} at Swing Shack\n\n${ctaText}\n\n#IndoorGolfJohannesburg #GolfSouthAfrica #TrackMan #SwingShack`,
      carousel: `${hookText}\n\nSwipe to see what TrackMan found 👆\n\n${service.emoji} ${service.name} | Swing Shack\n${ctaText}\n\n#IndoorGolf #GolfSA #TrackManGolf`,
      reel: `${hookText}\n\nDrop a 🫂 if you need this.\n\n${service.emoji} ${service.name} at Swing Shack\n${ctaText}\n\n#golf #indoorgolf #golftok #golfsa #trackman`,
      blog: `**${hookText}**\n\nIndoor golf has changed the game for South African golfers — here's why booking a TrackMan session at Swing Shack might be the best decision you make this season.\n\nRead on for the full breakdown.`,
      short_script: `[HOOK - ${hookText}]\n\n[0-3s] ${hookText}\n[3-8s] Here's what that actually means for your game...\n[8-15s] At Swing Shack, TrackMan gives you numbers that don't lie.\n[15-20s] Most golfers who come in for a session are shocked by what they find.\n[20-25s] Book your TrackMan session from R250. Link in bio.`,
    };
    return captions[format] || captions.static;
  }

  function generateHashtags(service, format) {
    const base = ['#IndoorGolfJohannesburg', '#GolfSouthAfrica', '#SwingShack', '#TrackMan'];
    const formatTags = {
      static: ['#IndoorGolf', '#GolfTips', '#TrackManGolf'],
      carousel: ['#GolfTransformation', '#IndoorGolf', '#TrackMan'],
      reel: ['#golf', '#golftok', '#indoorgolf', '#golfsa', '#trackman'],
      blog: ['#IndoorGolf', '#GolfSouthAfrica', '#GolfTips', '#TrackManGolf'],
      short_script: ['#golf', '#golftok', '#indoorgolf'],
    };
    return [...new Set([...base, ...(formatTags[format] || [])])].slice(0, 10);
  }

  function pickServiceForHook(hook) {
    const text = ((hook.hook_text || '') + (hook.topic_cluster || '')).toLowerCase();
    for (const svc of services) {
      if (svc.keywords.some(k => text.includes(k))) return svc;
    }
    return services[Math.floor(Math.random() * services.length)];
  }

  // ── Build blueprints from hook bank ────────────────────────────────
  const blueprints = [];

  hooks.forEach((hook, i) => {
    const format = BLUEPRINT_TYPES[i % BLUEPRINT_TYPES.length];
    const service = pickServiceForHook(hook);
    const cta = topCtas[i % topCtas.length];
    const id = `bp-${new Date().toISOString().split('T')[0]}-${String(i + 1).padStart(3, '0')}`;

    blueprints.push({
      blueprint_id: id,
      schema: 'https://clawdia.io/agents/content-architect/v1',
      generated: new Date().toISOString(),
      source_hook_id: hook.hook_id || (hook.hook_text || '').substring(0, 30),
      source_hook_text: hook.hook_text || hook.headline || '',
      ig_proof_score: hook.ig_proof_score || null,
      format_type: format,
      objective: i % 2 === 0 ? 'booking' : 'awareness',
      target_audience: 'golfers in Johannesburg, 25-55, mid-handicap',
      hook_overlay_text: (hook.hook_text || '').substring(0, 60),
      caption: generateCaption(hook, service, cta, format),
      hashtags: generateHashtags(service, format),
      service: service.name,
      service_emoji: service.emoji,
      cta_type: cta.type || 'booking',
      cta_text: cta.cta || 'Link in bio · Book your session',
      creative_notes: `Hook score: ${hook.ig_proof_score?.toFixed(1) || '?'}/10. Source: ${hook.signal_bucket || 'unknown'}. ${format === 'reel' ? 'Use trending audio.' : format === 'carousel' ? '10 slides, hook on slide 1, proof on slides 2-9, CTA on slide 10.' : 'Static image with data overlay.'}`,
      status: hook.signal_bucket === 'proven_and_trending' ? 'ready' : 'test_next',
      confidence: hook.ig_proof_score ? Math.round(hook.ig_proof_score * 10) : 50,
    });
  });

  // ── Add plan-derived blueprints ─────────────────────────────────────
  planEntries.slice(0, 5).forEach((entry, i) => {
    const id = `bp-plan-${new Date().toISOString().split('T')[0]}-${String(i + 1).padStart(3, '0')}`;
    blueprints.push({
      blueprint_id: id,
      schema: 'https://clawdia.io/agents/content-architect/v1',
      generated: new Date().toISOString(),
      source: 'post_plan',
      format_type: entry.format || 'static',
      objective: entry.objective || 'awareness',
      hook_overlay_text: (entry.hook || '').substring(0, 60),
      caption: `${entry.hook || ''}\n\nSwing Shack\n${entry.cta || 'Link in bio · Book your session'}\n\n#IndoorGolfJohannesburg #GolfSA #SwingShack`,
      hashtags: ['#IndoorGolfJohannesburg', '#GolfSouthAfrica', '#SwingShack', '#TrackManGolf'],
      service: entry.service || 'Practice',
      cta_text: entry.cta || 'Link in bio · Book your session',
      status: 'scheduled',
      confidence: 70,
      planned_date: entry.dateISO,
    });
  });

  const result = {
    schema: 'https://clawdia.io/agents/content-architect/v1',
    generated: new Date().toISOString(),
    blueprint_count: blueprints.length,
    formats: {
      static: blueprints.filter(b => b.format_type === 'static').length,
      carousel: blueprints.filter(b => b.format_type === 'carousel').length,
      reel: blueprints.filter(b => b.format_type === 'reel').length,
      blog: blueprints.filter(b => b.format_type === 'blog').length,
      short_script: blueprints.filter(b => b.format_type === 'short_script').length,
    },
    ready_count: blueprints.filter(b => b.status === 'ready').length,
    test_next_count: blueprints.filter(b => b.status === 'test_next').length,
    scheduled_count: blueprints.filter(b => b.status === 'scheduled').length,
    blueprints: blueprints.sort((a, b) => b.confidence - a.confidence),
  };

  fs.writeFileSync(path.join(DATA, 'content-blueprints.json'), JSON.stringify(result, null, 2));

  console.log(`✅ Content blueprints: ${result.blueprint_count} total`);
  console.log(`   Ready: ${result.ready_count} | Test next: ${result.test_next_count} | Scheduled: ${result.scheduled_count}`);
  console.log(`   Formats: static=${result.formats.static} carousel=${result.formats.carousel} reel=${result.formats.reel} blog=${result.formats.blog} short_script=${result.formats.short_script}`);
  console.log(`   Top blueprint: "${result.blueprints[0]?.hook_overlay_text?.substring(0, 50)}" [${result.blueprints[0]?.format_type}]`);
}

module.exports = { run };
if (require.main === module) run();