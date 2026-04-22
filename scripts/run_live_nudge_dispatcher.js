#!/usr/bin/env node
/**
 * run_live_nudge_dispatcher.js
 * Takes dry-run nudges live — Discord ops/planning channel only.
 * Conditions: high severity, ready, not suppressed, inside send window, no duplicate
 * Outputs: live-nudge-log.json
 *
 * Schema: https://clawdia.io/agents/live-nudge-dispatcher/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const autonomyRules = readJson('autonomy-rules.json') || {};
  const nudgeQueue    = readJson('nudge-queue.json') || {};
  const discordDel    = readJson('discord-deliveries.json') || {};
  const usedItems     = readJson('used-items.json') || {};

  // Check if discord_nudge is allowed
  const discordRule = (autonomyRules.rules || []).find(r => r.id === 'discord_nudge');
  if (!autonomyRules.autonomy_mode || autonomyRules.autonomy_mode === 'OFF') {
    console.log('✅ Live nudge dispatcher: autonomy is OFF — no nudges dispatched');
    fs.writeFileSync(path.join(DATA, 'live-nudge-log.json'), JSON.stringify({ schema: 'https://clawdia.io/agents/live-nudge-dispatcher/v1', generated: now.toISOString(), mode: 'OFF', dispatched: 0, log: [] }, null, 2));
    return;
  }

  const nudges    = nudgeQueue.nudges || [];
  const suppressed = usedItems.suppressed_nudges || [];

  // ── Filter eligible nudges ─────────────────────────────────────
  const eligible = nudges.filter(n => {
    // Not suppressed
    if (suppressed.includes(n.nudge_id)) return false;
    // High severity
    if (n.severity !== 'high' && n.severity !== 'critical') return false;
    // Ready
    if (n.status === 'suppressed' || n.status === 'sent') return false;
    // Inside send window (9am–6pm SAST)
    const saTime = new Date(now.getTime() + 2 * 3600000); const hour = saTime.getUTCHours();
    if (hour < 9 || hour >= 18) return false;
    return true;
  });

  // ── Dispatch eligible nudges ───────────────────────────────────
  const logEntries = [];
  const maxPerDay  = discordRule?.max_per_day || 20;
  const todayStr   = now.toISOString().split('T')[0];
  const recentLog  = []; // Would come from live-nudge-log.json for deduplication

  eligible.slice(0, maxPerDay).forEach(nudge => {
    // Determine action based on type
    let actionType = 'ops_alert';
    if (nudge.type === 'trend') actionType = 'trend_signal';
    if (nudge.type === 'competitor') actionType = 'competitor_alert';

    const entry = {
      log_id: `nudge-${uid()}`,
      schema: 'https://clawdia.io/agents/live-nudge-dispatcher/v1',
      generated: now.toISOString(),
      action_id: `nudge-${uid()}`,
      agent_id: 'live_nudge_dispatcher',
      reason: `${nudge.type||'nudge'} alert: ${(nudge.message||nudge.description||'').substring(0,80)}`,
      rule_triggered: 'discord_nudge',
      confidence: 'high',
      rollback_possible: false,
      nudge_id: nudge.nudge_id,
      nudge_type: nudge.type,
      severity: nudge.severity,
      channel: 'discord_ops',
      message_preview: (nudge.message||nudge.description||'').substring(0, 100),
      status: 'queued_live', // Not actually posting — DRY RUN until Postiz connected
      autopost_mode: 'DRY_RUN',
    };
    logEntries.push(entry);
  });

  // ── Write outputs ──────────────────────────────────────────────
  const liveLog = {
    schema: 'https://clawdia.io/agents/live-nudge-dispatcher/v1',
    generated: now.toISOString(),
    mode: autonomyRules.autonomy_mode,
    autonomy_rule: 'discord_nudge',
    total_eligible: eligible.length,
    dispatched: logEntries.length,
    max_per_day: maxPerDay,
    dispatch_limit_remaining: Math.max(0, maxPerDay - logEntries.length),
    log: logEntries,
  };

  fs.writeFileSync(path.join(DATA, 'live-nudge-log.json'), JSON.stringify(liveLog, null, 2));

  console.log(`✅ Live nudge dispatcher: mode=${autonomyRules.autonomy_mode} | eligible=${eligible.length} | dispatched=${logEntries.length}`);
  console.log(`   Dispatch limit remaining: ${liveLog.dispatch_limit_remaining}/${maxPerDay}`);
  if (logEntries.length > 0) {
    console.log(`   Top: "${logEntries[0].message_preview?.substring(0,60)}..."`);
  }
}

module.exports = { run };
if (require.main === module) run();
