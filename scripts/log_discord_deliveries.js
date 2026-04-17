#!/usr/bin/env node
/**
 * log_discord_deliveries.js
 * Tracks every nudge attempt: sent / skipped / suppressed / failed
 * Output: data/discord-deliveries.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'discord-deliveries.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

function uid() { return 'dld_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

// Load current nudge queue and suppression rules for baseline
const nudges   = readJson('nudge-queue.json')        || {};
const suppr    = readJson('suppression-rules.json')  || {};
const fallbacks = readJson('fallback-queue.json')   || {};

const now = new Date().toISOString();
const today = now.split('T')[0];

// Load existing deliveries or start fresh
const existing = readJson('discord-deliveries.json') || { deliveries: [], summary: {} };

// Filter to only today's deliveries for the rolling log
const todayDeliveries = existing.deliveries.filter(d => d.sent_at && d.sent_at.split('T')[0] === today);

// Build summary counts
const summary = {
  updated:       now,
  generated:    'log_discord_deliveries.js',
  total_today:  todayDeliveries.length,
  by_status: {
    sent:       todayDeliveries.filter(d => d.delivery_status === 'sent').length,
    skipped:    todayDeliveries.filter(d => d.delivery_status === 'skipped').length,
    suppressed: todayDeliveries.filter(d => d.delivery_status === 'suppressed').length,
    failed:     todayDeliveries.filter(d => d.delivery_status === 'failed').length,
    dry_run:    todayDeliveries.filter(d => d.delivery_status === 'dry_run').length,
  },
  by_owner: {},
  by_type: {},
};

todayDeliveries.forEach(d => {
  summary.by_owner[d.owner] = (summary.by_owner[d.owner] || 0) + 1;
  summary.by_type[d.type]   = (summary.by_type[d.type]   || 0) + 1;
});

const output = {
  ...existing,
  updated:  now,
  summary,
  deliveries: todayDeliveries,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Discord deliveries log: ${OUTPUT}`);
console.log(`   Today: ${summary.total_today} | Sent: ${summary.by_status.sent} | Dry-run: ${summary.by_status.dry_run} | Suppressed: ${summary.by_status.suppressed} | Failed: ${summary.by_status.failed}`);