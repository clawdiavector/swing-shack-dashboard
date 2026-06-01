'use strict';

var fs = require('fs');
var path = require('path');
// mathjs removed - using native Math only

var DATA_PATH = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
var OUT_PATH = path.join(__dirname, '..', 'campaign-os', 'cockpit-operational.html');

var data = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function healthColor(v) {
  if (v >= 80) return 'var(--green)';
  if (v >= 50) return 'var(--amber)';
  return 'var(--red)';
}

function ringClass(v) {
  if (v >= 80) return 'green';
  if (v >= 50) return 'amber';
  return 'red';
}

function statusDisplay(s) {
  if (s === 'approved') return 'Approved';
  if (s === 'review') return 'In Review';
  if (s === 'pending') return 'Pending';
  if (s === 'published') return 'Published';
  if (s === 'draft') return 'Draft';
  return esc(s);
}

function statusBadgeClass(s) {
  if (s === 'approved') return 'approved';
  if (s === 'review' || s === 'pending') return 'review';
  if (s === 'published') return 'published';
  return 'draft';
}

var c = data.campaign;
var st = data.strategy || {};
var pillars = st.pillars || [];
var assets = data.assets || [];
var metrics = c.marketingMetrics || {};
var breakdown = c.healthBreakdown || {};
var diagnostic = c.diagnostic || '';

var total = assets.length;
var complete = 0, progress = 0, blocked = 0;
for (var i = 0; i < assets.length; i++) {
  var s = assets[i].status;
  if (s === 'published') complete++;
  else if (s === 'blocked') blocked++;
  else progress++;
}

var cp = total > 0 ? Math.round(complete / total * 100) : 0;
var pp = total > 0 ? Math.round(progress / total * 100) : 0;
var bp = total > 0 ? Math.round(blocked / total * 100) : 0;
var npct = 100 - cp - pp - bp;

var hs = c.healthScore || 0;
var hc = healthColor(hs);
var rc = ringClass(hs);
var hlbl = c.healthState === 'healthy' ? 'Healthy' : c.healthState === 'degraded' ? 'Degraded' : c.healthState === 'critical' ? 'Critical' : esc(c.healthState || 'degraded');
var rad = 36;
var circ = Math.round(2 * Math.PI * rad);
var offset = Math.round(circ - (hs / 100) * circ);

// Marketing metrics HTML
var mhtml = '';
if (metrics.reach != null || metrics.engagement != null) {
  mhtml = '<div class="grid-4">' +
    '<div class="stat-card"><div class="stat-label">Reach</div><div class="stat-value">' + (metrics.reach != null ? metrics.reach : '--') + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Engagement</div><div class="stat-value">' + (metrics.engagement != null ? metrics.engagement : '--') + '</div><div class="stat-sub">Rate: ' + (metrics.engagementRate != null ? metrics.engagementRate + '%' : '--') + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Conversions</div><div class="stat-value green">' + (metrics.conversions != null ? metrics.conversions : '--') + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Revenue</div><div class="stat-value green">R' + (metrics.revenue != null ? metrics.revenue.toLocaleString() : '--') + '</div></div>' +
    '</div>';
}

// Strategy HTML
var strat = '';
if (st.positioningStatement || st.targetAudience || st.primaryOffer) {
  strat = '<div class="card"><div class="card-title" style="margin-bottom:12px">Strategy</div>';
  if (st.positioningStatement) {
    strat += '<div style="margin-bottom:12px"><div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Positioning</div><div style="font-size:13px;color:var(--text);line-height:1.6">' + esc(st.positioningStatement) + '</div></div>';
  }
  if (st.targetAudience) {
    strat += '<div style="margin-bottom:12px"><div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Target Audience</div><div style="font-size:12px;color:var(--muted);line-height:1.5">' + esc(st.targetAudience) + '</div></div>';
  }
  if (st.primaryOffer) {
    strat += '<div><div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Primary Offer</div><div style="font-size:12px;color:var(--green);font-weight:600">' + esc(st.primaryOffer) + '</div></div>';
  }
  strat += '</div>';
}

// Pillars HTML
var pil = '';
if (pillars.length > 0) {
  pil = '<div class="card"><div class="card-title" style="margin-bottom:12px">Campaign Pillars</div><div class="pillar-grid">';
  for (var pi = 0; pi < pillars.length; pi++) {
    var p = pillars[pi];
    var chip = 'p' + (pi + 1);
    pil += '<div class="pillar-card"><div class="pillar-num">' + (pi + 1) + '</div>' +
      '<div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px">' + esc(p.name || '') + '</div>' +
      '<div style="font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:8px">' + esc(p.description || '') + '</div>' +
      '<div class="pillar-mini"><div class="pillar-mini-chip ' + chip + '">' + esc(p.name || '') + '</div></div></div>';
  }
  pil += '</div></div>';
}

// This week's actions (hardcoded)
var week = '<div class="card"><div class="card-title" style="margin-bottom:12px">This Week\'s Actions</div>';
var weekItems = [
  { urgency: 'high', title: 'Re-publish Hook A with fresh visual', meta: 'Best performer \u2014 2.3% engagement, never re-published', due: 'Today' },
  { urgency: 'med', title: 'Approve Hook G carousel visual', meta: '@image-generation ready for review', due: 'Tomorrow' },
  { urgency: 'low', title: 'Resume GMB support post rotation', meta: '7 days since last GMB post', due: 'This week' }
];
for (var wi = 0; wi < weekItems.length; wi++) {
  var witem = weekItems[wi];
  week += '<div class="waiting-item"><div class="urgency ' + witem.urgency + '"></div>' +
    '<div class="waiting-content"><div class="waiting-title">' + esc(witem.title) + '</div><div class="waiting-meta">' + esc(witem.meta) + '</div></div>' +
    '<div class="waiting-due">' + esc(witem.due) + '</div></div>';
}
week += '</div>';

// Health breakdown bars
var hb = '';
var breakdownItems = [
  { key: 'assetPipeline', label: 'Asset Pipeline', weight: '35%' },
  { key: 'approvalVelocity', label: 'Approval Velocity', weight: '20%' },
  { key: 'publishCadence', label: 'Publish Cadence', weight: '20%' },
  { key: 'engagementTrend', label: 'Engagement Trend', weight: '15%' },
  { key: 'conversionRate', label: 'Conversion Rate', weight: '10%' }
];
for (var bi = 0; bi < breakdownItems.length; bi++) {
  var bitem = breakdownItems[bi];
  var bv = breakdown[bitem.key] != null ? breakdown[bitem.key] : 0;
  var bcol = healthColor(bv);
  hb += '<div class="health-row"><div class="health-row-label">' + bitem.label + '</div>' +
    '<div class="health-bar-bg"><div class="health-bar-fill" style="width:' + bv + '%;background:' + bcol + '"></div></div>' +
    '<div class="health-row-value" style="color:' + bcol + '">' + bv + '</div>' +
    '<div class="health-row-weight">' + bitem.weight + '</div></div>';
}

// Health ring SVG
var hr = '<div class="ring"><svg width="80" height="80" viewBox="0 0 80 80">' +
  '<circle class="ring-bg" cx="40" cy="40" r="' + rad + '"/>' +
  '<circle class="ring-fill ' + rc + '" cx="40" cy="40" r="' + rad + '" ' +
  'style="stroke:' + hc + ';stroke-dasharray:' + circ + ';stroke-dashoffset:' + offset + '"/>' +
  '</svg><div class="ring-center">' +
  '<div class="ring-number" style="color:' + hc + '">' + hs + '</div>' +
  '<div class="ring-label">Score</div></div></div>';

// Diagnostic box
var diag = '';
if (diagnostic) {
  diag = '<div class="diagnostic-box"><div class="diagnostic-label">Diagnostic</div><div class="diagnostic-text">' + esc(diagnostic) + '</div></div>';
}

// Launch readiness bar
var segs = '';
if (cp > 0) segs += '<div class="lr-segment green" style="width:' + cp + '%"></div>';
if (pp > 0) segs += '<div class="lr-segment amber" style="width:' + pp + '%"></div>';
if (bp > 0) segs += '<div class="lr-segment red" style="width:' + bp + '%"></div>';
if (npct > 0) segs += '<div class="lr-segment empty" style="width:' + npct + '%"></div>';
var lbar = '<div class="launch-readiness-bar">' + segs + '</div>' +
  '<div class="lr-legend"><span><span class="lr-dot" style="background:var(--green)"></span> Complete (' + complete + ')</span>' +
  '<span><span class="lr-dot" style="background:var(--amber)"></span> In Progress (' + progress + ')</span>' +
  '<span><span class="lr-dot" style="background:var(--red)"></span> Blocked (' + blocked + ')</span>' +
  '<span><span class="lr-dot" style="background:var(--surface2)"></span> Not Started (' + (total - complete - progress - blocked) + ')</span></div>';

// Launch badge
var lbadge;
if (total === 0) {
  lbadge = '<div class="launch-badge missing"><span>\u26a0</span><div><div class="launch-badge-num">0</div><div style="font-size:11px">Pending assets</div></div></div>';
} else if (blocked > 0) {
  lbadge = '<div class="launch-badge blocked"><span>\u26a0</span><div><div class="launch-badge-num">' + blocked + '</div><div style="font-size:11px">Blocked</div></div></div>';
} else if (total - complete > 0) {
  lbadge = '<div class="launch-badge missing"><span>\u26a0</span><div><div class="launch-badge-num">' + (total - complete) + '</div><div style="font-size:11px">Missing</div></div></div>';
} else {
  lbadge = '<div class="launch-badge ready"><span>\u2705</span><div><div style="font-size:11px">Ready to Launch</div></div></div>';
}

// CSS
var CSS = [
  "* { margin: 0; padding: 0; box-sizing: border-box; }",
  "\:root { --bg: #0a0a0f; --surface: #111118; --surface2: #1a1a24; --border: #2a2a3a; --text: #e8e8f0; --muted: #6b6b80; --green: #00cc77; --amber: #ffaa00; --red: #ff4455; --blue: #4488ff; --purple: #9966ff; }",
  "body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; font-size: 14px; line-height: 1.5; }",
  ".container { max-width: 1100px; margin: 0 auto; padding: 24px 32px; }",
  ".mothership-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; gap: 20px; }",
  ".mothership-title { font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: 4px; }",
  ".mothership-subtitle { font-size: 13px; color: var(--muted); }",
  ".launch-badge { display: flex; align-items: center; gap: 10px; padding: 12px 20px; border-radius: 12px; font-size: 14px; font-weight: 700; flex-shrink: 0; }",
  ".launch-badge.ready { background: rgba(0,204,119,0.12); border: 2px solid var(--green); color: var(--green); }",
  ".launch-badge.missing { background: rgba(255,170,0,0.12); border: 2px solid var(--amber); color: var(--amber); }",
  ".launch-badge.blocked { background: rgba(255,68,85,0.12); border: 2px solid var(--red); color: var(--red); }",
  ".launch-badge-num { font-size: 24px; font-weight: 700; }",
  ".mothership-tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 0; }",
  ".mothership-tab { padding: 8px 16px; font-size: 12px; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: all 0.15s; }",
  ".mothership-tab:hover { color: var(--text); }",
  ".mothership-tab.active { color: var(--green); border-bottom-color: var(--green); }",
  ".mothership-panel { display: none; }",
  ".mothership-panel.active { display: block; }",
  ".card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }",
  ".card-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 12px; }",
  ".stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; }",
  ".stat-card .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }",
  ".stat-card .stat-value { font-size: 28px; font-weight: 700; color: var(--text); }",
  ".stat-card .stat-value.green { color: var(--green); }",
  ".stat-card .stat-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }",
  ".health-ring { display: flex; align-items: center; gap: 24px; }",
  ".ring { position: relative; width: 80px; height: 80px; flex-shrink: 0; }",
  ".ring svg { transform: rotate(-90deg); }",
  ".ring-bg { fill: none; stroke: var(--surface2); stroke-width: 8; }",
  ".ring-fill { fill: none; stroke: var(--amber); stroke-width: 8; stroke-linecap: round; }",
  ".ring-fill.green { stroke: var(--green); }",
  ".ring-fill.amber { stroke: var(--amber); }",
  ".ring-fill.red { stroke: var(--red); }",
  ".ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }",
  ".ring-number { font-size: 22px; font-weight: 700; }",
  ".ring-label { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }",
  ".health-breakdown { flex: 1; }",
  ".health-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }",
  ".health-row-label { font-size: 12px; color: var(--muted); width: 120px; }",
  ".health-bar-bg { flex: 1; height: 4px; background: var(--surface2); border-radius: 2px; overflow: hidden; }",
  ".health-bar-fill { height: 100%; border-radius: 2px; }",
  ".health-row-value { font-size: 12px; font-weight: 600; width: 30px; text-align: right; }",
  ".health-row-weight { font-size: 10px; color: var(--muted); width: 30px; text-align: right; }",
  ".diagnostic-box { background: rgba(255,170,0,0.08); border: 1px solid rgba(255,170,0,0.25); border-radius: 8px; padding: 14px 16px; margin-top: 12px; }",
  ".diagnostic-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--amber); margin-bottom: 6px; }",
  ".diagnostic-text { font-size: 12px; color: var(--text); line-height: 1.6; }",
  ".launch-readiness-bar { display: flex; gap: 3px; margin-bottom: 16px; }",
  ".lr-segment { height: 6px; border-radius: 3px; }",
  ".lr-segment.green { background: var(--green); }",
  ".lr-segment.amber { background: var(--amber); }",
  ".lr-segment.red { background: var(--red); }",
  ".lr-segment.empty { background: var(--surface2); }",
  ".lr-legend { display: flex; gap: 16px; font-size: 10px; color: var(--muted); margin-top: 6px; }",
  ".lr-legend span { display: flex; align-items: center; gap: 4px; }",
  ".lr-dot { width: 8px; height: 8px; border-radius: 50%; }",
  ".generate-btn { background: rgba(0,204,119,0.1); border: 1px solid var(--green); color: var(--green); padding: 5px 12px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; }",
  ".generate-btn:hover { background: rgba(0,204,119,0.2); }",
  ".completion-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }",
  ".completion-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; text-align: center; }",
  ".completion-card .cc-num { font-size: 32px; font-weight: 700; margin-bottom: 4px; }",
  ".completion-card .cc-num.green { color: var(--green); }",
  ".completion-card .cc-num.amber { color: var(--amber); }",
  ".completion-card .cc-num.red { color: var(--red); }",
  ".completion-card .cc-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }",
  ".completion-card .cc-sub { font-size: 10px; color: var(--muted); margin-top: 4px; }",
  ".gap-col { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }",
  ".gap-col-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px; }",
  ".gap-col-title.done { color: var(--green); }",
  ".gap-col-title.missing { color: var(--amber); }",
  ".gap-col-title.blocked { color: var(--red); }",
  ".gap-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 11px; }",
  ".gap-item:last-child { border-bottom: none; }",
  ".gap-item-icon { font-size: 12px; width: 16px; text-align: center; }",
  ".gap-item-name { flex: 1; color: var(--text); }",
  ".gap-item-owner { color: var(--muted); font-size: 10px; }",
  ".queue-gen-item { display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }",
  ".queue-gen-item:hover { border-color: var(--green); }",
  ".qgi-thumb { width: 48px; height: 48px; border-radius: 6px; background: var(--surface2); display: flex; align-items: center; justify-content: center; font-size: 10px; color: var(--muted); flex-shrink: 0; overflow: hidden; }",
  ".qgi-thumb img { width: 100%; height: 100%; object-fit: cover; }",
  ".qgi-info { flex: 1; }",
  ".qgi-name { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px; }",
  ".qgi-meta { font-size: 11px; color: var(--muted); margin-bottom: 2px; }",
  ".qgi-next { font-size: 10px; color: var(--amber); font-weight: 600; }",
  ".qgi-actions { display: flex; gap: 6px; flex-shrink: 0; }",
  ".prod-item { display: flex; gap: 16px; padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 12px; }",
  ".prod-item:hover { border-color: var(--green); }",
  ".prod-thumb { width: 120px; height: 120px; border-radius: 8px; overflow: hidden; flex-shrink: 0; background: var(--surface2); }",
  ".prod-thumb img { width: 100%; height: 100%; object-fit: cover; }",
  ".prod-info { flex: 1; }",
  ".prod-name { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 4px; }",
  ".prod-caption { font-size: 12px; color: var(--text); line-height: 1.5; margin-bottom: 8px; }",
  ".prod-caption strong { color: var(--green); }",
  ".prod-meta { display: flex; gap: 12px; font-size: 10px; color: var(--muted); margin-bottom: 10px; }",
  ".prod-actions { display: flex; gap: 6px; flex-wrap: wrap; }",
  ".prod-status-badge { display: inline-flex; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; margin-bottom: 8px; }",
  ".prod-status-badge.approved { background: rgba(0,204,119,0.15); color: var(--green); }",
  ".prod-status-badge.review { background: rgba(255,170,0,0.15); color: var(--amber); }",
  ".prod-status-badge.draft { background: rgba(107,107,128,0.15); color: var(--muted); }",
  ".prod-status-badge.published { background: rgba(68,136,255,0.15); color: var(--blue); }",
  ".btn { padding: 6px 14px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }",
  ".btn-approve { background: var(--green); color: #000; }",
  ".btn-approve:hover { background: #00e688; }",
  ".btn-reject { background: transparent; border: 1px solid var(--red); color: var(--red); }",
  ".btn-reject:hover { background: rgba(255,68,85,0.1); }",
  ".waiting-item { display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }",
  ".waiting-item .urgency { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }",
  ".waiting-item .urgency.high { background: var(--red); }",
  ".waiting-item .urgency.med { background: var(--amber); }",
  ".waiting-item .urgency.low { background: var(--muted); }",
  ".waiting-content { flex: 1; }",
  ".waiting-title { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 2px; }",
  ".waiting-meta { font-size: 10px; color: var(--muted); }",
  ".waiting-due { font-size: 11px; font-weight: 600; color: var(--amber); }",
  ".pillar-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }",
  ".pillar-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }",
  ".pillar-num { width: 24px; height: 24px; border-radius: 50%; background: var(--green); color: #000; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-bottom: 8px; }",
  ".pillar-mini { display: flex; gap: 8px; margin-top: 8px; }",
  ".pillar-mini-chip { padding: 4px 10px; border-radius: 20px; font-size: 10px; font-weight: 600; }",
  ".pillar-mini-chip.p1 { background: rgba(0,204,119,0.15); color: var(--green); }",
  ".pillar-mini-chip.p2 { background: rgba(68,136,255,0.15); color: var(--blue); }",
  ".pillar-mini-chip.p3 { background: rgba(153,102,255,0.15); color: var(--purple); }",
  ".grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }"
].join('\n');

// Asset Queue tab
var aq = '';
var queue = [];
for (var qi = 0; qi < assets.length; qi++) {
  if (assets[qi].status !== 'published') queue.push(assets[qi]);
}
if (queue.length === 0) {
  aq = '<div style="text-align:center;padding:48px 0;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">\U0001f4ed</div><div style="font-size:14px">No queued assets</div><div style="font-size:11px;margin-top:4px">Assets awaiting generation will appear here</div></div>';
} else {
  for (var qji = 0; qji < queue.length; qji++) {
    var qa = queue[qji];
    var qbl = statusDisplay(qa.status || 'draft');
    var qna = qa.nextAction || 'Generate';
    var qth = qa.thumbnail ? '<img src="' + esc(qa.thumbnail) + '" alt="' + esc(qa.name || '') + '"/>' : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--muted)">\U0001f5bc</div>';
    aq += '<div class="queue-gen-item"><div class="qgi-thumb">' + qth + '</div>' +
      '<div class="qgi-info"><div class="qgi-name">' + esc(qa.name || 'Untitled') + '</div>' +
      '<div class="qgi-meta">' + (qa.platform ? '<span style="margin-right:8px">' + esc(qa.platform) + '</span>' : '') +
      '<span style="padding:2px 6px;border-radius:4px;font-size:9px;font-weight:600;background:rgba(255,170,0,0.15);color:var(--amber)">' + qbl + '</span></div>' +
      '<div class="qgi-next">Next: ' + esc(qna) + '</div></div>' +
      '<div class="qgi-actions"><button class="generate-btn" onclick="var t=this;t.textContent=' + "'" + 'Generating\u2026' + "'" + ';t.disabled=true;setTimeout(function(){t.textContent=' + "'" + 'Queued' + "'" + ';t.disabled=false},1500)">Generate</button></div></div>';
  }
}

// Production tab
var prod = '';
if (assets.length === 0) {
  prod = '<div style="text-align:center;padding:48px 0;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">\U0001f3ed</div><div style="font-size:14px">No assets in production</div><div style="font-size:11px;margin-top:4px">Assets will appear here once created</div></div>';
} else {
  for (var pai = 0; pai < assets.length; pai++) {
    var pa = assets[pai];
    var pbc = statusBadgeClass(pa.status || 'draft');
    var pbl = statusDisplay(pa.status || 'draft');
    var pch = (pa.caption || '').replace(/<strong>/g, '<strong style="color:var(--green)">');
    var pth = pa.thumbnail ? '<img src="' + esc(pa.thumbnail) + '" alt="' + esc(pa.name || '') + '"/>' : '<div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px"><div style="font-size:20px">\U0001f5bc</div><div style="font-size:9px;color:var(--muted)">No preview</div></div>';
    prod += '<div class="prod-item"><div class="prod-thumb">' + pth + '</div>' +
      '<div class="prod-info"><div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px">' + esc(pa.type || 'Asset') + '</div>' +
      '<div class="prod-name">' + esc(pa.name || 'Untitled') + '</div>' +
      '<div class="prod-status-badge ' + pbc + '">' + pbl + '</div>' +
      '<div class="prod-caption">' + pch + '</div>' +
      '<div class="prod-meta">' + (pa.platform ? '<span>' + esc(pa.platform) + '</span>' : '') + (pa.owner ? '<span> \u00b7 ' + esc(pa.owner) + '</span>' : '') + '</div>' +
      '<div class="prod-actions"><button class="btn btn-approve" onclick="var t=this;t.textContent=' + "'" + 'Approved' + "'" + ';t.style.background=' + "'" + 'var(--green)' + "'" + ';t.disabled=true">Approve</button>' +
      '<button class="btn btn-reject" onclick="var t=this;t.textContent=' + "'" + 'Rejected' + "'" + ';t.style.opacity=' + "'" + '0.5' + "'" + ';t.disabled=true">Reject</button></div></div></div>';
  }
}

// Completion tab
var comp = '<div class="completion-grid">' +
  '<div class="completion-card"><div class="cc-num green">' + complete + '</div><div class="cc-label">Complete</div><div class="cc-sub">' + (total > 0 ? Math.round(complete / total * 100) + '% of assets' : '0 assets') + '</div></div>' +
  '<div class="completion-card"><div class="cc-num amber">' + progress + '</div><div class="cc-label">In Progress</div><div class="cc-sub">' + (total > 0 ? Math.round(progress / total * 100) + '% of assets' : '0 assets') + '</div></div>' +
  '<div class="completion-card"><div class="cc-num red">' + blocked + '</div><div class="cc-label">Blocked</div><div class="cc-sub">' + (total > 0 ? Math.round(blocked / total * 100) + '% of assets' : '0 assets') + '</div></div>' +
  '</div>';
var cl2 = [], pl2 = [], bl3 = [];
for (var ci = 0; ci < assets.length; ci++) {
  var ca = assets[ci];
  var ih = '<div class="gap-item"><div class="gap-item-icon">\u2705</div><div class="gap-item-name">' + esc(ca.name || 'Untitled') + '</div>' + (ca.owner ? '<div class="gap-item-owner">' + esc(ca.owner) + '</div>' : '') + '</div>';
  if (ca.status === 'published') cl2.push(ih);
  else if (ca.status === 'blocked') bl3.push(ih);
  else pl2.push(ih);
}
if (cl2.length === 0) cl2.push('<div style="font-size:11px;color:var(--muted);padding:8px 0;text-align:center">No complete assets yet</div>');
if (pl2.length === 0) pl2.push('<div style="font-size:11px;color:var(--muted);padding:8px 0;text-align:center">No in-progress assets</div>');
if (bl3.length === 0) bl3.push('<div style="font-size:11px;color:var(--muted);padding:8px 0;text-align:center">No blocked assets</div>');
comp += '<div class="card"><div class="card-title" style="margin-bottom:12px">Asset Gap Analysis</div>' +
  '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">' +
  '<div class="gap-col"><div class="gap-col-title done">Complete</div>' + cl2.join('') + '</div>' +
  '<div class="gap-col"><div class="gap-col-title missing">In Progress</div>' + pl2.join('') + '</div>' +
  '<div class="gap-col"><div class="gap-col-title blocked">Blocked</div>' + bl3.join('') + '</div></div></div>';

// Gap Analysis tab
var ga = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">';
ga += '<div class="gap-col"><div class="gap-col-title done">Complete</div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u2705</div><div class="gap-item-name">Hook A published</div><div class="gap-item-owner">Mar 10</div></div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u2705</div><div class="gap-item-name">Hook E published</div><div class="gap-item-owner">Apr 1</div></div></div>';
ga += '<div class="gap-col"><div class="gap-col-title missing">Missing</div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u26a0</div><div class="gap-item-name">Hook A re-publish visual</div><div class="gap-item-owner">@image-gen</div></div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u26a0</div><div class="gap-item-name">Hook G hero visual</div><div class="gap-item-owner">@image-gen</div></div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u26a0</div><div class="gap-item-name">GMB this week</div><div class="gap-item-owner">@publisher</div></div></div>';
ga += '<div class="gap-col"><div class="gap-col-title blocked">Blocked</div>' +
  '<div class="gap-item"><div class="gap-item-icon">\u274c</div><div class="gap-item-name">Hook A re-publish</div><div class="gap-item-owner">Awaiting visual</div></div></div></div>';
ga += '<div class="card"><div class="card-title" style="margin-bottom:16px">Launch Readiness Assessment</div>' +
  '<div style="display:flex;align-items:center;gap:24px;margin-bottom:16px">' + hr +
  '<div><div style="font-size:22px;font-weight:700;color:' + hc + ';margin-bottom:4px">' + hs + ' / 100</div>' +
  '<div style="font-size:12px;color:' + hc + ';text-transform:uppercase;letter-spacing:0.05em;font-weight:600">' + hlbl + '</div>' +
  '<div style="font-size:11px;color:var(--muted);margin-top:4px">Health Score</div></div></div>' +
  '<div style="border-top:1px solid var(--border);padding-top:12px">';
var checks = [
  { label: 'Assets in pipeline', state: total > 0 ? 'done' : 'missing', detail: total + ' asset(s) loaded' },
  { label: 'Published content', state: 'done', detail: '2 hooks live' },
  { label: 'GMB cadence', state: 'warn', detail: '7 days since last post' },
  { label: 'Hook A re-publish', state: 'blocked', detail: 'Missing visual' },
  { label: 'Hook G publish', state: 'blocked', detail: 'Awaiting visual' }
];
for (var ci2 = 0; ci2 < checks.length; ci2++) {
  var check = checks[ci2];
  var icon2 = check.state === 'done' ? '\u2705' : check.state === 'blocked' ? '\u274c' : '\u26a0';
  ga += '<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">' +
    '<div style="font-size:14px">' + icon2 + '</div>' +
    '<div style="flex:1"><div style="font-size:12px;color:var(--text)">' + esc(check.label) + '</div><div style="font-size:10px;color:var(--muted)">' + esc(check.detail) + '</div></div></div>';
}
ga += '</div></div>';

// Embedded campaign data
var cdjs = 'window.campaignData = ' + JSON.stringify(data, null, 0) + ';';

// Assemble and write HTML file
var title = esc(c.name || 'TrackMan Intelligence');

var html = '<!DOCTYPE html>\n' +
'<html lang="en">\n' +
'<head>\n' +
'<meta charset="UTF-8">\n' +
'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' +
'<title>Campaign Mothership \u2014 ' + title + '</title>\n' +
'<style>\n' + CSS + '\n</style>\n' +
'</head>\n' +
'<body>\n' +
'<div class="container">\n' +
'<div class="mothership-header">\n' +
'  <div>\n' +
'    <div class="mothership-title">' + title + '</div>\n' +
'    <div class="mothership-subtitle">Operational Dashboard</div>\n' +
'  </div>\n' +
'  ' + lbadge + '\n' +
'</div>\n' +
'<div class="mothership-tabs">\n' +
'  <div class="mothership-tab active" onclick="showMothershipTab(' + "'" + 'overview' + "'" + ')">Overview</div>\n' +
'  <div class="mothership-tab" onclick="showMothershipTab(' + "'" + 'queue' + "'" + ')">Asset Queue</div>\n' +
'  <div class="mothership-tab" onclick="showMothershipTab(' + "'" + 'production' + "'" + ')">Production</div>\n' +
'  <div class="mothership-tab" onclick="showMothershipTab(' + "'" + 'completion' + "'" + ')">Completion</div>\n' +
'  <div class="mothership-tab" onclick="showMothershipTab(' + "'" + 'gapanalysis' + "'" + ')">Gap Analysis</div>\n' +
'</div>\n' +
'<div class="mothership-panel active" id="mp-overview">\n' +
'  ' + lbar + '\n' +
'  ' + mhtml + '\n' +
'  <div class="card"><div class="card-title" style="margin-bottom:16px">Campaign Health</div>\n' +
'    <div class="health-ring">\n' +
'      ' + hr + '\n' +
'      <div class="health-breakdown">\n' +
'        ' + hb + '\n' +
'      </div>\n' +
'    </div>\n' +
'    ' + diag + '\n' +
'  </div>\n' +
'  ' + strat + '\n' +
'  ' + pil + '\n' +
'  ' + week + '\n' +
'</div>\n' +
'<div class="mothership-panel" id="mp-queue">\n' +
'  ' + aq + '\n' +
'</div>\n' +
'<div class="mothership-panel" id="mp-production">\n' +
'  ' + prod + '\n' +
'</div>\n' +
'<div class="mothership-panel" id="mp-completion">\n' +
'  ' + comp + '\n' +
'</div>\n' +
'<div class="mothership-panel" id="mp-gapanalysis">\n' +
'  ' + ga + '\n' +
'</div>\n' +
'</div>\n' +
'<script>\n' +
'  ' + cdjs + '\n' +
'  function showMothershipTab(name) {\n' +
'    var panels = document.querySelectorAll(' + "'" + '.mothership-panel' + "'" + ');\n' +
'    var tabs = document.querySelectorAll(' + "'" + '.mothership-tab' + "'" + ');\n' +
'    for (var i = 0; i < panels.length; i++) { panels[i].classList.remove(' + "'" + 'active' + "'" + '); }\n' +
'    for (var j = 0; j < tabs.length; j++) { tabs[j].classList.remove(' + "'" + 'active' + "'" + '); }\n' +
'    document.getElementById(' + "'" + 'mp-' + "'" + ' + name).classList.add(' + "'" + 'active' + "'" + ');\n' +
'    if (event && event.target) event.target.classList.add(' + "'" + 'active' + "'" + ');\n' +
'  }\n' +
'</script>\n' +
'</body>\n' +
'</html>';

fs.writeFileSync(OUT_PATH, html, 'utf8');
console.log('HTML written to ' + OUT_PATH);
console.log('Size: ' + html.length + ' characters');
