#!/usr/bin/env python3
"""Regenerate cockpit from campaign-data.json (V2 schema)
Reads campaigns dict, builds portfolio + detail views with Campaign Brief card.
"""
import json, datetime, pathlib

SRC = pathlib.Path(__file__).parent.parent / 'campaign-os' / 'campaign-data.json'
DST = pathlib.Path(__file__).parent.parent / 'campaign-os' / 'cockpit-operational.html'

with open(SRC) as f:
    D = json.load(f)

campaigns = D.get('campaigns', {})
active = D.get('activeCampaignId', 'trackman-intelligence')

n_complete = sum(1 for c in campaigns.values() for a in c.get('assets', {}).values() if a.get('status') in ('published', 'approved'))
n_progress = sum(1 for c in campaigns.values() for a in c.get('assets', {}).values() if a.get('status') in ('generated', 'pending', 'review', 'rejected'))
n_total = sum(len(c.get('assets', {})) for c in campaigns.values())
states = {cid: (c.get('identity', {}).get('healthState') or 'degraded') for cid, c in campaigns.items()}
green = sum(1 for s in states.values() if s == 'healthy')
amber = sum(1 for s in states.values() if s == 'degraded')
red = sum(1 for s in states.values() if s == 'critical')

card_rows = ''
for cid, c in campaigns.items():
    i = c.get('identity', {})
    na = i.get('name', cid)
    goal = i.get('goal', '')[:55]
    n_assets = len(c.get('assets', {}))
    st = states[cid]
    stcol = '#00cc77' if st == 'healthy' else '#ffaa00' if st == 'degraded' else '#ff4455'
    card_rows += (
        '<div class="ccard" onclick="selectCampaign(\'' + cid + '\')" style="cursor:pointer">'
        '<div class="ccard-name">' + na + '</div>'
        '<div class="ccard-meta">' + goal + '</div>'
        '<div class="ccard-assetcount" style="color:' + stcol + '">' + str(n_assets) + ' assets &middot; ' + st.title() + '</div>'
        '</div>'
    )

try:
    up_raw = D.get('portfolioMetadata', {}).get('lastUpdated', '---')
    if up_raw and up_raw != '---':
        d = datetime.datetime.fromisoformat(up_raw.replace('Z', '+00:00'))
        up_str = d.strftime('%d %b %Y %H:%M SAST')
    else:
        up_str = '---'
except:
    up_str = str(up_raw) if up_raw else '---'

campaign_str = json.dumps(D, separators=(',', ':'))

STYLE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
:root { --bg: #0a0a0f; --surface: #111118; --surface2: #18181f; --border: rgba(255,255,255,0.08); --text: #e8e8ed; --col-muted: #6e6e82; --col-green: #00cc77; --col-amber: #ffaa00; --col-red: #ff4455; --col-blue: #4488ff; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; gap: 16px; }
.header-left { display: flex; flex-direction: column; gap: 4px; }
.header-title { font-size: 22px; font-weight: 700; }
.header-subtitle { font-size: 12px; color: var(--col-muted); }
.view-toggle { display: flex; gap: 4px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 4px; }
.view-btn { padding: 6px 14px; font-size: 11px; font-weight: 600; color: var(--col-muted); cursor: pointer; border-radius: 6px; border: none; background: transparent; transition: all 0.15s; }
.view-btn:hover { color: var(--text); }
.view-btn.active { background: rgba(0,204,119,0.15); color: var(--col-green); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--col-muted); margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; }
.stat-card .stat-label { font-size: 11px; color: var(--col-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
.stat-card .stat-value { font-size: 28px; font-weight: 700; }
.stat-card .stat-value.green { color: var(--col-green); }
.stat-card .stat-sub { font-size: 11px; color: var(--col-muted); margin-top: 4px; }
.health-ring { display: flex; align-items: center; gap: 24px; }
.ring { position: relative; width: 80px; height: 80px; flex-shrink: 0; }
.ring svg { transform: rotate(-90deg); display: block; }
.ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.ring-number { font-size: 22px; font-weight: 700; }
.ring-label { font-size: 10px; color: var(--col-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.view-panel { display: none; }
.view-panel.active { display: block; }
.detail-back { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--col-muted); cursor: pointer; margin-bottom: 16px; padding: 8px 12px; background: var(--surface); border-radius: 6px; width: fit-content; }
.detail-back:hover { color: var(--text); }
.campaign-selector-wrap { display: flex; align-items: center; gap: 12px; }
.campaign-selector-label { font-size: 11px; color: var(--col-muted); text-transform: uppercase; letter-spacing: 0.08em; }
.campaign-selector { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px 16px; color: var(--text); font-size: 13px; font-weight: 600; cursor: pointer; min-width: 220px; }
.campaign-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.ccard { background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 16px; transition: all 0.15s; }
.ccard:hover { border-color: var(--col-green); }
.ccard-name { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.ccard-meta { font-size: 11px; color: var(--col-muted); margin-bottom: 8px; line-height: 1.4; }
.ccard-assetcount { font-size: 11px; font-weight: 600; }
.dna-panel { background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.dna-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--col-amber); margin-bottom: 8px; }
.dna-row { display: flex; gap: 8px; margin-bottom: 6px; font-size: 12px; }
.dna-key { color: var(--col-muted); width: 120px; flex-shrink: 0; }
.dna-value { color: var(--text); }
.memory-panel { background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.memory-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--col-blue); margin-bottom: 8px; }
.memory-lesson { font-size: 12px; color: var(--text); padding: 6px 0; border-bottom: 1px solid var(--border); }
.memory-lesson:last-child { border-bottom: none; }
.brief-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.brief-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--col-green); margin-bottom: 12px; }
.brief-row { margin-bottom: 10px; }
.brief-key { font-size: 10px; color: var(--col-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 3px; }
.brief-value { font-size: 12px; color: var(--text); line-height: 1.5; }
.prod-item { display: flex; gap: 16px; padding: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 10px; }
.prod-thumb { width: 48px; height: 48px; border-radius: 8px; background: var(--surface2); display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
.prod-thumb img { width: 100%; height: 100%; object-fit: cover; }
.prod-info { flex: 1; }
.prod-name { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
.prod-meta { font-size: 10px; color: var(--col-muted); margin-bottom: 4px; }
.prod-meta span { color: var(--text); }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.footer { text-align: center; font-size: 10px; color: var(--col-muted); padding: 20px 0; margin-top: 16px; border-top: 1px solid var(--border); }
"""

def renderCampaign(id):
    """Returns HTML for a campaign detail view."""
    c = campaigns[id]
    i = c.get('identity', {})
    b = c.get('brief', {})
    vd = c.get('visualDirection', {})
    mem = c.get('memory', {}) or {}
    
    assets = c.get('assets', {})
    if isinstance(assets, dict):
        asset_list = list(assets.values())
    else:
        asset_list = assets or []
    
    n_complete = sum(1 for a in asset_list if a.get('status') in ('published', 'approved'))
    n_progress = sum(1 for a in asset_list if a.get('status') in ('generated', 'pending', 'review', 'rejected'))
    n_blocked = sum(1 for a in asset_list if a.get('status') == 'blocked')
    
    hs_raw = i.get('healthScore')
    hs = 50 if hs_raw is None else hs_raw
    st = (i.get('healthState') or 'degraded').replace('unknown', 'degraded')
    hcol = '#00cc77' if st == 'healthy' else '#ff4455' if st == 'critical' else '#ffaa00'
    name = i.get('name', id)
    goal = i.get('goal', '')
    up = i.get('updatedAt', '---')
    
    # Campaign Brief Card
    primaryGoal = b.get('primaryGoal') or 'Custom'
    successTarget = b.get('successTarget') or '---'
    goalNotes = b.get('goalNotes') or ''
    duration = i.get('duration') or i.get('campaignType') or '---'
    priority = (i.get('priority') or 'medium').title()
    platforms = ', '.join(i.get('platforms', [])) or 'All'
    offer = (c.get('strategy') or {}).get('primaryOffer') or '---'
    
    brief_card = (
        '<div class="brief-card" style="background:linear-gradient(135deg,#0d2b1a 0%,#0a1f15 100%);border:1px solid #00cc7733;border-radius:12px;padding:20px;margin-bottom:20px">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;color:#00cc77;text-transform:uppercase">Campaign Brief</div>'
        '<div style="display:flex;gap:8px">'
        '<span style="font-size:10px;padding:3px 10px;border-radius:20px;background:#00cc7722;color:#00cc77;font-weight:600">' + priority + '</span>'
        '<span style="font-size:10px;padding:3px 10px;border-radius:20px;background:#4488ff22;color:#4488ff;font-weight:600">' + duration + '</span>'
        '</div></div>'
        '<div style="font-size:18px;font-weight:700;margin-bottom:10px">' + (i.get('name') or id) + '</div>'
        '<div style="font-size:12px;color:#6e6e82;margin-bottom:16px;line-height:1.5">' + (b.get('purpose') or goal or 'No description yet') + '</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
        '<div><div style="font-size:10px;color:#6e6e82;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Goal</div><div style="font-size:13px;font-weight:600;color:#00cc77">' + primaryGoal + '</div></div>'
        '<div><div style="font-size:10px;color:#6e6e82;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Success Target</div><div style="font-size:13px;font-weight:600">' + successTarget + '</div></div>'
        '<div><div style="font-size:10px;color:#6e6e82;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Audience</div><div style="font-size:12px">' + (b.get('audience') or '---')[:60] + '</div></div>'
        '<div><div style="font-size:10px;color:#6e6e82;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Platforms</div><div style="font-size:12px">' + platforms + '</div></div>'
        '</div>'
    )
    if goalNotes:
        brief_card += '<div style="margin-top:12px;padding:10px;background:rgba(255,255,255,0.04);border-radius:8px;font-size:11px;color:#e8e8ed"><span style="color:#6e6e82">Goal Notes: </span>' + goalNotes + '</div>'
    brief_card += '<div style="margin-top:12px;font-size:11px;color:#6e6e82">Primary Offer: <span style="color:#e8e8ed">' + offer + '</span></div></div>'
    
    # Assets
    if asset_list:
        aRows = ''
        for a in asset_list:
            s = a.get('status', '')
            bcol = '#4488ff' if s == 'published' else '#00cc77' if s == 'approved' else '#ff4455' if s == 'rejected' else '#ffaa00'
            badge = s.title() if s else '---'
            na = a.get('name', '?')
            atype = a.get('assetType', '')
            owner = a.get('owner', '')
            aRows += (
                '<div class="prod-item"><div class="prod-thumb"><span style="font-size:20px;color:#6e6e82">' + na[0] + '</span></div>'
                '<div class="prod-info"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
                '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:' + bcol + '22;color:' + bcol + '">' + badge + '</span>'
                '<span style="font-size:10px;color:#6e6e82">' + atype + '</span></div>'
                '<div class="prod-name">' + na + '</div>'
                '<div class="prod-meta">@ <span>' + owner + '</span></div></div></div>'
            )
    else:
        aRows = '<div style="text-align:center;padding:48px;color:#6e6e82">No assets in production</div>'
    
    # DNA
    dnaRows = ''
    for key, label in [('campaignType','Type'),('priority','Priority'),('owner','Owner'),('status','Status')]:
        val = i.get(key, '---')
        if isinstance(val, list):
            val = ', '.join(val)
        dnaRows += '<div class="dna-row"><div class="dna-key">' + label + '</div><div class="dna-value">' + str(val) + '</div></div>'
    
    mood = vd.get('mood') or ''
    if mood:
        dnaRows += '<div class="dna-row"><div class="dna-key">Mood</div><div class="dna-value">' + mood + '</div></div>'
    
    dnaHtml = '<div class="dna-panel"><div class="dna-title">Campaign DNA</div>' + dnaRows + '</div>'
    
    # Visual Direction
    visRows = ''
    if vd.get('mood'):
        visRows += '<div class="dna-row"><div class="dna-key">Mood</div><div class="dna-value">' + vd['mood'] + '</div></div>'
    if vd.get('creativeDirection'):
        visRows += '<div class="dna-row" style="display:block"><div class="dna-key" style="width:auto;margin-bottom:4px">Creative Direction</div><div class="dna-value" style="font-size:11px">' + vd['creativeDirection'] + '</div></div>'
    visDirHtml = '<div class="dna-panel"><div class="dna-title">Visual Direction</div>' + visRows + '</div>' if visRows else ''
    
    # Brief rows
    brief_fields = [
        ('purpose','Purpose'),('audience','Audience'),('bigIdea','Big Idea'),
        ('successMetric','Success Metric'),('primaryGoal','Primary Goal'),
        ('goalNotes','Goal Notes'),('successTarget','Success Target')
    ]
    briefRows = ''
    for key, label in brief_fields:
        val = b.get(key)
        if val:
            briefRows += '<div class="brief-row"><div class="brief-key">' + label + '</div><div class="brief-value">' + val + '</div></div>'
    briefHtml = '<div id="campaign-brief-section" class="brief-panel"><div class="brief-title">Campaign Brief</div>' + briefRows + '</div>'
    
    # Memory
    lessons = mem.get('lessonsLearned') or []
    if lessons:
        lessonList = ''.join('<div class="memory-lesson">' + l + '</div>' for l in lessons)
    else:
        lessonList = '<div style="font-size:12px;color:#6e6e82;padding:6px 0">No lessons recorded yet.</div>'
    memoryHtml = '<div class="memory-panel"><div class="memory-title">Campaign Memory</div>' + lessonList + '</div>'
    
    # Stats grid
    grid3 = (
        '<div class="grid-3" style="margin-top:12px">'
        '<div class="stat-card"><div class="stat-value green">' + str(n_complete) + '</div><div class="stat-label" style="color:#00cc77">Published</div></div>'
        '<div class="stat-card"><div class="stat-value" style="color:#ffaa00">' + str(n_progress) + '</div><div class="stat-label" style="color:#ffaa00">In Progress</div></div>'
        '<div class="stat-card"><div class="stat-value" style="color:#ff4455">' + str(n_blocked) + '</div><div class="stat-label" style="color:#ff4455">Blocked</div></div>'
        '</div>'
    )
    
    # Health ring SVG
    dashoffset = str(round(201 * (1 - hs / 100)))
    
    return (
        brief_card +
        '<div class="card"><div class="card-title">' + name + ' — Campaign Detail</div>'
        '<div class="stat-card" style="margin-bottom:16px">'
        '<div class="stat-label">Campaign Health</div>'
        '<div class="health-ring">'
        '<div class="ring" style="display:inline-block">'
        '<svg width="80" height="80" viewBox="0 0 80 80">'
        '<circle cx="40" cy="40" r="32" fill="none" stroke="var(--surface2)" stroke-width="8"/>'
        '<circle cx="40" cy="40" r="32" fill="none" stroke="' + hcol + '" stroke-width="8" stroke-dasharray="201" stroke-dashoffset="' + dashoffset + '" stroke-linecap="round" transform="rotate(-90 40 40)"/>'
        '</svg>'
        '<div class="ring-center"><div class="ring-number" style="color:' + hcol + '">' + str(hs) + '</div><div class="ring-label">' + st + '</div></div>'
        '</div>'
        '<div><div style="font-size:14px;font-weight:700;text-transform:capitalize;color:' + hcol + '">' + st + '</div>'
        '<div style="font-size:12px;color:var(--col-muted);margin-top:4px">' + goal + '</div>'
        '<div style="font-size:11px;color:var(--col-muted);margin-top:4px">Updated ' + up + '</div></div>'
        '</div>' + grid3 + '</div>'
        '<div class="card"><div class="card-title">Production Assets — ' + str(len(asset_list)) + ' total</div>' + aRows + '</div>'
        + dnaHtml + visDirHtml + memoryHtml + briefHtml
    )

BODY = '''<div class="container">
<div class="header">
<div class="header-left">
<div class="header-title">Campaign Mothership</div>
<div class="header-subtitle" id="header-subtitle">Portfolio Overview</div>
</div>
<div style="display:flex;align-items:center;gap:16px">
<div class="view-toggle">
<button class="view-btn active" id="btn-portfolio" onclick="showView('portfolio')">Portfolio</button>
<button class="view-btn" id="btn-detail" onclick="showView('detail')">Campaign</button>
</div>
<div class="campaign-selector-wrap" id="campaignSelectorWrap" style="display:none">
<span class="campaign-selector-label">Campaign:</span>
<select class="campaign-selector" id="campaignSelector" onchange="selectCampaign(this.value)"></select>
</div>
</div>
</div>
<div id="view-portfolio" class="view-panel active">
<div class="card">
<div class="card-title">Campaign Portfolio — ''' + str(len(campaigns)) + ''' campaigns</div>
<div class="stat-card" style="margin-bottom:16px">
<div class="stat-label">Portfolio Health</div>
<div style="display:flex;gap:20px;margin-top:8px;flex-wrap:wrap">
<div><div class="stat-value green">''' + str(green) + '''</div><div class="stat-sub">Healthy</div></div>
<div><div class="stat-value" style="color:var(--col-amber)">''' + str(amber) + '''</div><div class="stat-sub">Degraded</div></div>
<div><div class="stat-value" style="color:var(--col-red)">''' + str(red) + '''</div><div class="stat-sub">Critical</div></div>
<div><div class="stat-value">''' + str(n_total) + '''</div><div class="stat-sub">Total Assets</div></div>
<div><div class="stat-value green">''' + str(n_complete) + '''</div><div class="stat-sub">Published</div></div>
<div><div class="stat-value" style="color:var(--col-amber)">''' + str(n_progress) + '''</div><div class="stat-sub">In Progress</div></div>
</div>
</div>
<div class="campaign-cards">''' + card_rows + '''</div>
</div>
</div>
<div id="view-detail" class="view-panel">
<div class="detail-back" onclick="showView('portfolio')">&#8592; Back to Portfolio</div>
<div id="detail-content"></div>
</div>
</div>
<div class="footer">Campaign OS v2 &middot; Portfolio &middot; Updated ''' + up_str + ''' &middot; Source: campaign-data.json</div>'''

SCRIPT = '''window.campaignData = ''' + campaign_str + ''';
var activeView = 'portfolio';
function showView(name) {
  activeView = name;
  document.getElementById('view-portfolio').classList.toggle('active', name === 'portfolio');
  document.getElementById('view-detail').classList.toggle('active', name === 'detail');
  document.getElementById('btn-portfolio').classList.toggle('active', name === 'portfolio');
  document.getElementById('btn-detail').classList.toggle('active', name === 'detail');
  document.getElementById('campaignSelectorWrap').style.display = (name === 'detail') ? 'flex' : 'none';
  if (name === 'portfolio') document.getElementById('header-subtitle').textContent = 'Portfolio Overview';
}
function getCampaign(id) { return (window.campaignData && window.campaignData.campaigns) ? window.campaignData.campaigns[id] : null; }
function initSelector() {
  var sel = document.getElementById('campaignSelector');
  var ids = Object.keys(window.campaignData.campaigns).sort();
  sel.innerHTML = ids.map(function(cid) {
    var name = (window.campaignData.campaigns[cid].identity || {}).name || cid;
    return '<option value="' + cid + '">' + name + '</option>';
  }).join('');
  var active = window.campaignData.activeCampaignId;
  if (active && window.campaignData.campaigns[active]) { sel.value = active; renderCampaign(active); }
}
function selectCampaign(id) {
  if (!id || !window.campaignData.campaigns[id]) return;
  window.campaignData.activeCampaignId = id;
  document.getElementById('campaignSelector').value = id;
  renderCampaign(id);
  showView('detail');
  document.getElementById('header-subtitle').textContent = (window.campaignData.campaigns[id].identity || {}).name || id;
}
function renderCampaign(id) {
  var D = window.campaignData;
  var c = D.campaigns[id];
  if (!c) return;
  document.getElementById('detail-content').innerHTML = window.renderFns[id](c);
}
window.renderFns = {};
'''

# Register render functions for each campaign
for cid in campaigns:
    SCRIPT += 'window.renderFns["' + cid + '"] = function(c) { return \'' + renderCampaign(cid).replace("'", "\\'") + '\'; }; '

SCRIPT += '''
document.addEventListener('DOMContentLoaded', initSelector);
'''

HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Campaign Mothership — Portfolio</title>\n<style>\n' + STYLE + '\n</style>\n</head>\n<body>\n' + BODY + '\n<script>\n' + SCRIPT + '\n</script>\n</body>\n</html>'

with open(DST, 'w') as f:
    f.write(HTML)

print('OK Written:', DST)
print('Size:', len(HTML), 'bytes')
print('Campaigns:', list(campaigns.keys()))
print('Takomo assets:', len(campaigns.get('takomo-101t', {}).get('assets', {})))
print('TrackMan assets:', len(campaigns.get('trackman-intelligence', {}).get('assets', {})))
print('Updated:', up_str)