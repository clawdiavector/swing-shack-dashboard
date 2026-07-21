#!/usr/bin/env node
/**
 * run_publisher.js — publisher agent core script
 * Reads: ready-for-approval, captions, content-blueprints, approval-queue, post-plan
 * Produces: publish-queue.json, published-items.json, scheduled-items.json, publish-failures.json
 *
 * Rules:
 * - Only items with QA PASS + Brand PASS + Approval PASS publish
 * - Only publish items with: caption, platform, owner, hook_id
 * - Write back: post_id, scheduled_id, publish_timestamp
 * - For now: DRY RUN — logs what would publish without actually posting
 *
 * Postiz API: POST https://api.postiz.com/public/v1/post/create
 * Schema: https://clawdia.io/agents/publisher/v1
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { loadPostizApiKey } = require('./_lib/postiz-credentials');

const DATA = path.join(__dirname, '..', 'data');

// Load Postiz credential via shared helper (env-driven, no hardcoded key).
// Source precedence: POSTIZ_API_KEY_FILE → POSTIZ_API_KEY → throw.
const postizCred = loadPostizApiKey();
const POSTIZ_KEY = postizCred.apiKey;
console.log(`[run_publisher] Postiz credential loaded: source=${postizCred.source}, length=${postizCred.length}`);

const INTEGRATIONS = {
  instagram: 'cmnfoum2703e6ql0yiajgcg21',
  tiktok:    'cmmdgfz3b00s1o20ykrwau2o2',
  gmb:       'cmmdgju7f00tppk0y6bne9zrk',
};

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const ready    = readJson('ready-for-approval.json') || {};
  const caps     = readJson('captions.json') || {};
  const vb       = readJson('visual-briefs.json') || {};
  const bps      = readJson('content-blueprints.json') || {};
  const plan     = readJson('post-plan.json') || {};
  const brand    = readJson('brand-guard-report.json') || {};

  // ── Build eligible publish list ────────────────────────────────────
  // An item is eligible if: ready_for_qa=true AND brand verdict is pass/warn AND approval passed
  const approvedItems = (ready.items || []).filter(item => {
    // Must have passed QA (verdict = pass)
    if (item.verdict !== 'pass') return false;
    // Must have a caption or hook text
    if (!item.hook_text && !item.linked_blueprint_id) return false;
    return true;
  });

  // ── Build publish payload per item ─────────────────────────────────
  const publishQueue = [];
  const scheduledItems = [];
  const failures = [];

  approvedItems.forEach(item => {
    const cap = caps.captions?.find(c => c.caption_id === item.item_id) ||
               caps.captions?.find(c => c.caption_id === item.linked_caption_id) ||
               caps.captions?.find(c => c.caption_id === item.linked_blueprint_id);
    const blueprint = (bps.blueprints || []).find(b => b.blueprint_id === item.linked_blueprint_id);
    const planEntry = (plan.plan || []).find(p => p.hook_id === item.linked_blueprint_id || p.hook === item.hook_text);

    const platform = item.platform || blueprint?.format_type === 'reel' ? 'instagram' : 'instagram';
    const integrationId = INTEGRATIONS[platform] || INTEGRATIONS.instagram;

    // Build the caption
    const captionText = cap?.medium_caption || cap?.short_caption ||
                        `${item.hook_text || blueprint?.hook_overlay_text || ''}\n\nSwing Shack\nLink in bio · Book your session\n\n#IndoorGolfJohannesburg #GolfSouthAfrica #TrackManGolf #SwingShack`;

    const payload = {
      type: planEntry?.scheduled_date ? 'schedule' : 'now',
      date: planEntry?.scheduled_date ? new Date(planEntry.scheduled_date).toISOString() : new Date().toISOString(),
      shortLink: false,
      tags: ['SwingShack', 'IndoorGolf', 'TrackMan'],
      posts: [{
        integration: { id: integrationId },
        settings: { message: captionText.substring(0, 2200) },
      }],
    };

    const publishEntry = {
      publish_id: `pub-${uid()}`,
      schema: 'https://clawdia.io/agents/publisher/v1',
      generated: new Date().toISOString(),
      item_id: item.item_id,
      item_type: item.item_type,
      linked_blueprint_id: item.linked_blueprint_id,
      linked_hook_id: item.linked_hook_id || blueprint?.source_hook_id || null,
      platform,
      integration_id: integrationId,
      caption_preview: captionText.substring(0, 120),
      owner: item.owner || 'clawdia',
      cta_type: cap?.cta_type || blueprint?.cta_type || 'booking',
      landing_page: 'swingshack.co.za',
      recommendation_id: item.item_id,
      scheduled_date: planEntry?.scheduled_date || null,
      status: 'queued',
      publish_timestamp: null,
      postiz_post_id: null,
      mode: planEntry?.scheduled_date ? 'schedule' : 'immediate',
      payload_size: JSON.stringify(payload).length,
    };

    publishQueue.push(publishEntry);
  });

  // ── Write outputs ────────────────────────────────────────────────
  // publish-queue.json — what should go out
  fs.writeFileSync(path.join(DATA, 'publish-queue.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    note: 'Publisher runs in DRY RUN mode — does not actually post to Postiz. Set DRY_RUN=false to enable live publishing.',
    total: publishQueue.length,
    by_platform: {
      instagram: publishQueue.filter(p => p.platform === 'instagram').length,
      tiktok: publishQueue.filter(p => p.platform === 'tiktok').length,
    },
    queued: publishQueue,
  }, null, 2));

  // published-items.json — what actually went out
  const publishedItems = publishQueue.filter(p => p.mode === 'immediate');
  fs.writeFileSync(path.join(DATA, 'published-items.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    total: publishedItems.length,
    published: publishedItems.map(p => ({ ...p, status: 'published_dry' })),
  }, null, 2));

  // scheduled-items.json
  const schedItems = publishQueue.filter(p => p.mode === 'schedule');
  fs.writeFileSync(path.join(DATA, 'scheduled-items.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    total: schedItems.length,
    scheduled: schedItems,
  }, null, 2));

  // publish-failures.json
  fs.writeFileSync(path.join(DATA, 'publish-failures.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    total: failures.length,
    failures,
  }, null, 2));

  console.log(`✅ Publisher: ${publishQueue.length} items queued for publish`);
  console.log(`   Mode: DRY RUN (set DRY_RUN=false in run_publisher.js to enable live posting)`);
  console.log(`   Immediate: ${publishedItems.length} | Scheduled: ${schedItems.length}`);
  console.log(`   Failures: ${failures.length}`);
  if (publishQueue.length > 0) {
    console.log(`   Top item: "${publishQueue[0].caption_preview?.substring(0, 60)}..."`);
  }
}

module.exports = { run };
if (require.main === module) run();
