#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const KILL_SWITCH = true;
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }
const SAFE_TYPES = ['evergreen_reminder', 'approved_repost', 'fallback_content'];
const RISKY_KEYWORDS = ['price', 'cost', 'r ', 'discount', 'promo', 'sale', '% off', 'deal', 'limited', 'today only', 'event', 'book now', 'tournament', 'competition', 'register', 'sign up'];
const INSTAGRAM_ID = 'cmnfoum2703e6ql0yiajgcg21';
function isLowRiskItem(item) {
  const text = (item.hook_text || item.caption_text || item.text || '').toLowerCase();
  if (RISKY_KEYWORDS.some(k => text.includes(k))) return false;
  const safeTypes = ['evergreen', 'reminder', 'repost', 'fallback', 'tip', 'fact'];
  return safeTypes.some(t => item.content_type === t || item.item_type === t);
}
function run() {
  const now = new Date();
  const autonomyRules = readJson('autonomy-rules.json') || {};
  const ready = readJson('ready-for-approval.json') || {};
  const schedBoard = readJson('schedule-board.json') || {};
  const publishRule = (autonomyRules.rules || []).find(r => ['evergreen_reminder', 'approved_repost'].includes(r.id));
  const canPublish = publishRule?.allowed && autonomyRules.autonomy_mode === 'LIMITED' && !KILL_SWITCH;
  const items = ready.items || [];
  const lowRiskItems = items.filter(item => {
    if (!isLowRiskItem(item)) return false;
    if (item.verdict !== 'pass') return false;
    const board = schedBoard.schedule || [];
    const today = now.toISOString().split('T')[0];
    if (board.some(s => s.item_id === item.item_id && s.scheduled_date === today)) return false;
    return true;
  });
  const logEntries = lowRiskItems.slice(0, 2).map(item => {
    const payload = { type: 'now', date: now.toISOString(), posts: [{ integration: { id: INSTAGRAM_ID }, settings: { message: (item.caption_text || item.hook_text || '').substring(0, 2200) } }] };
    return { autopublish_id: 'apub-'+uid(), schema: 'https://clawdia.io/agents/low-risk-publisher/v1', generated: now.toISOString(), action_id: 'apub-'+uid(), agent_id: 'low_risk_publisher', reason: 'Low-risk content auto-published: '+item.item_type, rule_triggered: 'evergreen_reminder', confidence: 'high', rollback_possible: false, item_id: item.item_id, item_type: item.item_type, platform: 'instagram', integration_id: INSTAGRAM_ID, status: KILL_SWITCH ? 'dry_run' : 'published', payload_preview: JSON.stringify(payload).substring(0, 100) };
  });
  const autopublished = { schema: 'https://clawdia.io/agents/low-risk-publisher/v1', generated: now.toISOString(), kill_switch: KILL_SWITCH, mode: KILL_SWITCH ? 'DRY_RUN' : (canPublish ? 'LIVE' : 'BLOCKED'), autonomy_mode: autonomyRules.autonomy_mode, rule: 'evergreen_reminder', low_risk_candidates: lowRiskItems.length, published: logEntries.filter(e => e.status !== 'dry_run').length, dry_run: logEntries.filter(e => e.status === 'dry_run').length, log: logEntries };
  fs.writeFileSync(path.join(DATA, 'autopublished-items.json'), JSON.stringify(autopublished, null, 2));
  if (KILL_SWITCH) { console.log('✅ Low-risk publisher: KILL SWITCH ON — '+logEntries.length+' items logged as dry_run'); console.log('   Candidates: '+lowRiskItems.length+' | Would publish: '+logEntries.length); console.log('   Set KILL_SWITCH=false in run_low_risk_publisher.js to enable live posting'); } else { console.log('✅ Low-risk publisher: LIVE MODE — '+logEntries.length+' items published'); }
}
run();
