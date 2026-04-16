#!/usr/bin/env node
/**
 * update_used_items.js
 * Tracks which ideas/hooks have been used and manages cooldowns
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const USED_FILE = path.join(DATA_DIR, 'used-items.json');
const LOG_FILE = path.join(DATA_DIR, 'used-log.json');
const PUBLISHED_FILE = path.join(DATA_DIR, 'published-posts.json');

// Cooldowns in days
const COOLDOWNS = {
  hook: 45,
  post_idea: 60,
  trend_cluster: 14,
  evergreen: 21,
};

function today() {
  return new Date().toISOString().split('T')[0];
}

function addDays(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function markAsUsed(id, type, reason) {
  const used = fs.existsSync(USED_FILE) ? JSON.parse(fs.readFileSync(USED_FILE, 'utf8')) : { suppressed_ideas: [], suppressed_hooks: [] };
  const log = fs.existsSync(LOG_FILE) ? JSON.parse(fs.readFileSync(LOG_FILE, 'utf8')) : { log: [] };
  
  // Check if already suppressed
  const cooldown = COOLDOWNS[type] || COOLDOWNS.evergreen;
  
  const entry = {
    id,
    type,
    reason: reason || 'published',
    used_on: today(),
    release_on: addDays(cooldown),
  };
  
  if (type === 'hook' || type === 'hook_formula') {
    if (!used.suppressed_hooks.find(h => h.id === id)) {
      used.suppressed_hooks.push(entry);
    }
  } else {
    if (!used.suppressed_ideas.find(i => i.id === id)) {
      used.suppressed_ideas.push(entry);
    }
  }
  
  log.log.push({ ...entry, action: 'suppressed', timestamp: new Date().toISOString() });
  
  // Keep only last 200 log entries
  if (log.log.length > 200) log.log = log.log.slice(-200);
  
  fs.writeFileSync(USED_FILE, JSON.stringify(used, null, 2));
  fs.writeFileSync(LOG_FILE, JSON.stringify(log, null, 2));
}

function releaseExpired() {
  const used = JSON.parse(fs.readFileSync(USED_FILE, 'utf8'));
  const now = today();
  
  const beforeHooks = used.suppressed_hooks.length;
  const beforeIdeas = used.suppressed_ideas.length;
  
  used.suppressed_hooks = used.suppressed_hooks.filter(h => h.release_on > now);
  used.suppressed_ideas = used.suppressed_ideas.filter(i => i.release_on <= now);
  
  const released = (beforeHooks - used.suppressed_hooks.length) + (beforeIdeas - used.suppressed_ideas.length);
  
  fs.writeFileSync(USED_FILE, JSON.stringify(used, null, 2));
  return released;
}

function markPostPublished(postId, ideaId, hookId, caption) {
  const published = fs.existsSync(PUBLISHED_FILE) ? JSON.parse(fs.readFileSync(PUBLISHED_FILE, 'utf8')) : { published: [] };
  
  const entry = {
    postId,
    ideaId: ideaId || 'unknown',
    hookId: hookId || 'unknown',
    caption_preview: (caption || '').substring(0, 80),
    published_on: today(),
  };
  
  published.published.push(entry);
  
  // Keep last 100
  if (published.published.length > 100) {
    published.published = published.published.slice(-100);
  }
  
  fs.writeFileSync(PUBLISHED_FILE, JSON.stringify(published, null, 2));
  
  // Also suppress the idea/hook
  if (ideaId) markAsUsed(ideaId, 'post_idea', `post: ${postId}`);
  if (hookId) markAsUsed(hookId, 'hook', `post: ${postId}`);
  
  return entry;
}

function getCooldowns() {
  const used = JSON.parse(fs.readFileSync(USED_FILE, 'utf8'));
  const now = today();
  
  const onCooldown = [
    ...used.suppressed_hooks.map(h => ({ id: h.id, type: 'hook', until: h.release_on })),
    ...used.suppressed_ideas.map(i => ({ id: i.id, type: i.type || 'idea', until: i.release_on })),
  ];
  
  const readySoon = onCooldown
    .filter(c => {
      const daysLeft = Math.ceil((new Date(c.until).getTime() - Date.now()) / 86400000);
      return daysLeft <= 7;
    })
    .map(c => ({ ...c, days_left: Math.ceil((new Date(c.until).getTime() - Date.now()) / 86400000) }));
  
  return { on_cooldown: onCooldown.length, ready_soon: readySoon };
}

function run() {
  // Release any expired cooldowns
  const released = releaseExpired();
  
  // Mark this as updated
  const usedData = JSON.parse(fs.readFileSync(USED_FILE, 'utf8'));
  usedData.updated = new Date().toISOString();
  fs.writeFileSync(USED_FILE, JSON.stringify(usedData, null, 2));
  
  // Read current status
  const usedStatus = JSON.parse(fs.readFileSync(USED_FILE, 'utf8'));
  const cooldowns = getCooldowns();
  
  console.log(`✅ Used items updated:`);
  console.log(`   Suppressed hooks: ${usedStatus.suppressed_hooks.length}`);
  console.log(`   Suppressed ideas: ${usedStatus.suppressed_ideas.length}`);
  console.log(`   Released this run: ${released}`);
  console.log(`   On cooldown: ${cooldowns.on_cooldown}`);
  console.log(`   Ready soon: ${cooldowns.ready_soon.length}`);
  
  return { released, ...cooldowns };
}

module.exports = { markAsUsed, markPostPublished, releaseExpired, getCooldowns };
if (require.main === module) run();