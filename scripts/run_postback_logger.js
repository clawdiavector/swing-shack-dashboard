#!/usr/bin/env node
/**
 * run_postback_logger.js — postback_logger agent core script
 * Closes the used-items gap: marks idea/hook used the moment publishing confirms.
 * Reads: published-items.json, scheduled-items.json, publish-failures.json, used-items.json
 * Produces: postback-log.json, updates used-items.json, published-posts.json, recommendation-outcomes.json
 *
 * Schema: https://clawdia.io/agents/postback-logger/v1
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
  const pubItems  = readJson('published-items.json') || {};
  const schedItems = readJson('scheduled-items.json') || {};
  const pubFail   = readJson('publish-failures.json') || {};
  const usedItems = readJson('used-items.json') || { suppressed_ideas: [], suppressed_hooks: [], suppressed_ctas: [] };
  const recOutcomes = readJson('recommendation-outcomes.json') || {};
  const recScores = readJson('recommendation-scores.json') || {};

  const now = new Date().toISOString();

  // ── Build postback log entries ────────────────────────────────────
  const logEntries = [];

  // Process published items
  const published = (pubItems.published || []);
  published.forEach(pub => {
    const entry = {
      log_id: `pbl-${uid()}`,
      schema: 'https://clawdia.io/agents/postback-logger/v1',
      generated: now,
      event: 'published',
      item_id: pub.item_id,
      item_type: pub.item_type,
      linked_blueprint_id: pub.linked_blueprint_id,
      linked_hook_id: pub.linked_hook_id,
      platform: pub.platform,
      owner: pub.owner,
      cta_type: pub.cta_type,
      landing_page: pub.landing_page,
      recommendation_id: pub.recommendation_id,
      publish_timestamp: now,
      postiz_post_id: pub.postiz_post_id || null,
      used_items_marked: false,
      attribution_updated: false,
    };

    // Mark hook as used
    const hookId = pub.linked_hook_id || pub.linked_blueprint_id;
    if (hookId && !usedItems.suppressed_hooks.includes(hookId)) {
      usedItems.suppressed_hooks.push(hookId);
      entry.used_items_marked = true;
    }

    // Mark idea as used (item_id as idea reference)
    if (pub.item_id && !usedItems.suppressed_ideas.includes(pub.item_id)) {
      usedItems.suppressed_ideas.push(pub.item_id);
      entry.used_items_marked = true;
    }

    // Update recommendation outcomes
    const recId = pub.recommendation_id;
    if (recId) {
      const outcomes = recOutcomes.outcomes || [];
      const existing = outcomes.findIndex(o => o.recommendation_id === recId);
      const outcomeEntry = {
        recommendation_id: recId,
        outcome: 'published',
        outcome_timestamp: now,
        platform: pub.platform,
        attribution: 'instagram',
      };
      if (existing >= 0) {
        outcomes[existing] = { ...outcomes[existing], ...outcomeEntry };
      } else {
        outcomes.push(outcomeEntry);
      }
      recOutcomes.outcomes = outcomes;
      entry.attribution_updated = true;
    }

    logEntries.push(entry);
  });

  // Process scheduled items
  const scheduled = (schedItems.scheduled || []);
  scheduled.forEach(sched => {
    const entry = {
      log_id: `pbl-${uid()}`,
      schema: 'https://clawdia.io/agents/postback-logger/v1',
      generated: now,
      event: 'scheduled',
      item_id: sched.item_id,
      item_type: sched.item_type,
      linked_blueprint_id: sched.linked_blueprint_id,
      linked_hook_id: sched.linked_hook_id,
      platform: sched.platform,
      owner: sched.owner,
      scheduled_date: sched.scheduled_date,
      status: 'scheduled_pending',
      postiz_scheduled_id: sched.postiz_post_id || null,
      used_items_marked: false,
      attribution_updated: false,
    };

    // Mark hook as used (scheduled = committed)
    const hookId = sched.linked_hook_id || sched.linked_blueprint_id;
    if (hookId && !usedItems.suppressed_hooks.includes(hookId)) {
      usedItems.suppressed_hooks.push(hookId);
      entry.used_items_marked = true;
    }

    logEntries.push(entry);
  });

  // Process failures
  const fails = (pubFail.failures || []);
  fails.forEach(f => {
    logEntries.push({
      log_id: `pbl-${uid()}`,
      schema: 'https://clawdia.io/agents/postback-logger/v1',
      generated: now,
      event: 'failed',
      item_id: f.item_id,
      item_type: f.item_type,
      failure_reason: f.reason || 'unknown',
      status: 'failed',
      used_items_marked: false,
      attribution_updated: false,
    });
  });

  // ── Update used-items.json ────────────────────────────────────────
  usedItems.updated = now;
  fs.writeFileSync(path.join(DATA, 'used-items.json'), JSON.stringify(usedItems, null, 2));

  // ── Update published-posts.json ─────────────────────────────────
  const pubPosts = readJson('published-posts.json') || { updated: 'never', published: [] };
  published.forEach(pub => {
    // Don't double-add
    if (!pubPosts.published.some(p => p.publish_id === pub.publish_id)) {
      pubPosts.published.unshift({
        publish_id: pub.publish_id || `pub-${uid()}`,
        item_id: pub.item_id,
        item_type: pub.item_type,
        hook_id: pub.linked_hook_id,
        platform: pub.platform,
        owner: pub.owner,
        published_at: now,
        postiz_post_id: pub.postiz_post_id || null,
        cta_type: pub.cta_type,
        caption_preview: (pub.caption_preview || '').substring(0, 100),
      });
    }
  });
  pubPosts.updated = now;
  pubPosts.published = pubPosts.published.slice(0, 200); // keep last 200
  fs.writeFileSync(path.join(DATA, 'published-posts.json'), JSON.stringify(pubPosts, null, 2));

  // ── Update recommendation-outcomes.json ──────────────────────────
  if (!recOutcomes.schema) {
    recOutcomes.schema = 'https://clawdia.io/recommendations/outcomes/v1';
    recOutcomes.generated = now;
  }
  recOutcomes.updated = now;
  fs.writeFileSync(path.join(DATA, 'recommendation-outcomes.json'), JSON.stringify(recOutcomes, null, 2));

  // ── Write postback log ────────────────────────────────────────────
  const postbackLog = {
    schema: 'https://clawdia.io/agents/postback-logger/v1',
    generated: now,
    total_entries: logEntries.length,
    by_event: {
      published: logEntries.filter(e => e.event === 'published').length,
      scheduled: logEntries.filter(e => e.event === 'scheduled').length,
      failed: logEntries.filter(e => e.event === 'failed').length,
    },
    used_items_marked_count: logEntries.filter(e => e.used_items_marked).length,
    entries: logEntries,
  };

  fs.writeFileSync(path.join(DATA, 'postback-log.json'), JSON.stringify(postbackLog, null, 2));

  console.log(`✅ Postback logger: ${logEntries.length} log entries`);
  console.log(`   Published: ${postbackLog.by_event.published} | Scheduled: ${postbackLog.by_event.scheduled} | Failed: ${postbackLog.by_event.failed}`);
  console.log(`   Used items marked: ${postbackLog.used_items_marked_count}`);
  console.log(`   used-items.json updated: ${usedItems.suppressed_hooks.length} total suppressed hooks`);
  console.log(`   published-posts.json: ${pubPosts.published.length} total published`);
}

module.exports = { run };
if (require.main === module) run();
