#!/usr/bin/env python3
"""Regenerate cockpit from campaign-data.json"""
import json, math, datetime, pathlib

SRC = pathlib.Path(__file__).parent.parent / 'campaign-os' / 'campaign-data.json'
DST = pathlib.Path(__file__).parent.parent / 'campaign-os' / 'cockpit-operational.html'

with open(SRC) as f:
    D = json.load(f)

c = D['campaign']
metrics = c.get('marketingMetrics', {})
assets = D.get('assets', [])
complete = sum(1 for a in assets if a.get('status') in ('published','approved'))
progress = sum(1 for a in assets if a.get('status') in ('generated','pending'))
blocked = sum(1 for a in assets if a.get('status') == 'blocked')
target = c.get('targetAssets', 12)
not_started = max(0, target - complete - progress - blocked)
total = complete + progress + blocked + not_started or 12

def pct(n):
    v = round(n / total * 100) if total > 0 else 0
    return v if v > 0 else 1

up = c.get('updatedAt','')
if up:
    try:
        d = datetime.datetime.fromisoformat(up.replace('Z','+00:00'))
        up_str = d.strftime('%d %b %Y %H:%M SAST')
    except:
        up_str = up
else:
    up_str = '---'

hs = c.get('healthState','unknown')
score = c.get('healthScore', 0)
hc = {'healthy':'#00cc77','degraded':'#ffaa00','critical':'#ff4455'}.get(hs,'#6e6e82')
diag = c.get('diagnostic','')
circ = 2 * math.pi * 30
offset = circ * (1 - score/100)
bd = c.get('healthBreakdown',{})

def bd_html():
    out = ''
    for k, v in bd.items():
        col = '#00cc77' if v >= 70 else '#ffaa00' if v >= 40 else '#ff4455'
        label = k.replace('_',' ').title()
        out += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:11px"><div style="width:100px;color:#6e6e82">%s</div><div style="flex:1;height:4px;background:#18181f;border-radius:2px"><div style="width:%d%%;height:100%%;background:%s;border-radius:2px"></div></div><div style="width:30px;text-align:right;color:%s;font-weight:600;font-size:10px">%d</div></div>' % (label, v, col, col, v)
    return out or '<div style="font-size:11px;color:#6e6e82">No breakdown data.</div>'

pillars = D.get('strategy',{}).get('pillars',[])
pcols = ['#00cc77','#4488ff','#9966ff']
def pillars_html():
    out = ''
    for i, p in enumerate(pillars):
        col = pcols[i] if i < len(pcols) else '#6e6e82'
        out += '<div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:12px"><div style="width:28px;height:28px;border-radius:6px;background:%s22;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:%s">%s</div><div><div style="font-weight:600;font-size:12px;margin-bottom:2px">%s</div><div style="font-size:11px;color:#6e6e82">%s</div></div></div>' % (col, col, p.get('id',''), p.get('name',''), p.get('description',''))
    return out

strategy = D.get('strategy',{})
strat = ''
if strategy:
    strat = '<div class="card"><div class="card-title">Strategy</div><div style="margin-bottom:10px"><div class="section-label">Positioning</div><div style="font-size:12px">%s</div></div><div style="margin-bottom:10px"><div class="section-label">Target</div><div style="font-size:12px">%s</div></div><div><div class="section-label">Primary Offer</div><div style="font-size:12px;color:#00cc77;font-weight:600">%s</div></div></div>' % (
        strategy.get('positioningStatement','---'),
        strategy.get('targetAudience','---'),
        strategy.get('primaryOffer','---'))

pillars_out = ''
ph = pillars_html()
if ph:
    pillars_out = '<div class="card"><div class="card-title">Pillars</div>%s</div>' % ph

SMAP = {
    'published':('#4488ff','Published'),'approved':('#00cc77','Approved'),
    'review':('#ffaa00','Awaiting Approval'),'draft':('#6e6e82','Draft'),
    'blocked':('#ff4455','Blocked'),'generated':('#ffaa00','Generated'),
    'pending':('#ffaa00','Pending'),
}

def asset_html(a):
    col, lbl = SMAP.get(a.get('status'), ('#6e6e82', a.get('status','')))
    if a.get('thumbnail'):
        thumb = '<img src="%s" alt="" style="width:100%%;height:100%%;object-fit:cover">' % a.get('thumbnail','')
    else:
        n = a.get('name','?')
        thumb = '<span style="font-size:20px;font-weight:700;color:#6e6e82">%s</span>' % (n[0] if n else '?')
    cap = a.get('caption','')
    if cap:
        cp = '<div style="font-size:11px;color:#e8e8ed;margin-top:4px;line-height:1.4">%s</div>' % cap[:100]
        if len(cap) > 100:
            cp += '...'
    else:
        cp = ''
    at = ''
    if a.get('assetType'):
        at = '<span style="font-size:10px;color:#6e6e82">%s</span>' % a.get('assetType','')
    return '<div style="display:flex;gap:14px;padding:12px;background:#18181f;border-radius:8px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.08)"><div style="width:56px;height:56px;border-radius:6px;background:#111118;display:flex;align-items:center;justify-content:center;font-size:10px;color:#6e6e82;flex-shrink:0;overflow:hidden">%s</div><div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap"><span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:%s22;color:%s">%s</span>%s</div><div style="font-size:13px;font-weight:600;margin-bottom:2px">%s</div><div style="font-size:10px;color:#6e6e82">%s</div>%s<div style="margin-top:8px;display:flex;gap:6px"><button style="background:rgba(0,204,119,0.15);color:#00cc77;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Approve</button><button style="background:rgba(255,68,85,0.15);color:#ff4455;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Reject</button></div></div></div>' % (
        thumb, col, col, lbl, at, a.get('name','Unnamed asset'), a.get('platform',''), cp)

def queue_html(a):
    imap = {'generated':'[GEN]','approved':'[OK]','rejected':'[NO]','pending':'[...]','blocked':'[!]','scheduled':'[CAL]','live':'[LIVE]','failed':'[X]'}
    icon = imap.get(a.get('status'),'[...]')
    na = a.get('nextAction','')
    ns = '<div style="font-size:10px;color:#ffaa00;font-weight:600;margin-top:2px">%s</div>' % na if na else ''
    own = a.get('owner','')
    os2 = '<div style="font-size:10px;color:#6e6e82">%s</div>' % own if own else ''
    meta = ' &middot; '.join([x for x in [a.get('platform',''), a.get('assetType','')] if x])
    ms = '<div style="font-size:10px;color:#6e6e82;margin-bottom:2px">%s</div>' % meta if meta else ''
    return '<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#111118;border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:6px"><div style="width:40px;height:40px;border-radius:6px;background:#18181f;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#6e6e82;flex-shrink:0;font-family:monospace">%s</div><div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;margin-bottom:2px">%s</div>%s%s%s</div><button style="background:rgba(0,204,119,0.1);border:1px solid #00cc77;color:#00cc77;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Generate</button></div>' % (
        icon, a.get('name','Unnamed'), ms, ns, os2)

def gap_col(title, cls, items):
    col = '#00cc77' if cls=='green' else '#ffaa00' if cls=='amber' else '#ff4455'
    html = '<div style="background:#111118;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:14px">'
    html += '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;color:%s">%s (%d)</div>' % (col, title, len(items))
    for it in items:
        own = it.get('owner','')
        os2 = '<div style="font-size:10px;color:#6e6e82;flex-shrink:0">%s</div>' % own if own else ''
        html += '<div style="display:flex;align-items:center;gap:8px;padding:5px 0;font-size:11px;border-bottom:1px solid rgba(255,255,255,0.08)"><div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">%s</div>%s</div>' % (it.get('name',''), os2)
    return html + '</div>'

pcomplete = pct(complete)
pprogress = pct(progress)
pblocked = pct(blocked)
pnot = pct(not_started)

lr_bar = ('<div style="display:flex;gap:3px;margin-bottom:8px">'
    '<div style="flex:%d;height:6px;background:#00cc77;border-radius:3px;min-width:0"></div>'
    '<div style="flex:%d;height:6px;background:#ffaa00;border-radius:3px;min-width:0"></div>'
    '<div style="flex:%d;height:6px;background:#ff4455;border-radius:3px;min-width:0"></div>'
    '<div style="flex:%d;height:6px;background:#18181f;border-radius:3px;min-width:0"></div>'
    '</div>'
    '<div style="display:flex;gap:14px;font-size:10px;color:#6e6e82">'
    '<span><span style="display:inline-block;width:8px;height:8px;border-radius:50%%;background:#00cc77"></span> Complete (%d%%)</span>'
    '<span><span style="display:inline-block;width:8px;height:8px;border-radius:50%%;background:#ffaa00"></span> In Progress (%d%%)</span>'
    '<span><span style="display:inline-block;width:8px;height:8px;border-radius:50%%;background:#ff4455"></span> Blocked (%d%%)</span>'
    '<span><span style="display:inline-block;width:8px;height:8px;border-radius:50%%;background:#18181f"></span> Not Started (%d%%)</span>'
    '</div>') % (pcomplete, pprogress, pblocked, pnot, pcomplete, pprogress, pblocked, pnot)

badge_state = 'blocked' if blocked > 0 else ('missing' if (not_started + progress) > 0 else 'ready')
badge_num = str(blocked) + ' blocked' if blocked > 0 else str(not_started + progress) + ' missing'
badge_label = 'Blocked' if blocked > 0 else ('Missing Assets' if (not_started + progress) > 0 else 'Ready To Launch')

q_assets = [a for a in assets if a.get('status') not in ('published','approved')]
queue_tab_html = ''.join(queue_html(a) for a in q_assets) if q_assets else '<div style="text-align:center;padding:50px;color:#6e6e82;font-size:13px">No queued assets. Generate via Campaign Factory.</div>'
prod_tab_html = ''.join(asset_html(a) for a in assets) if assets else '<div style="text-align:center;padding:60px"><div style="font-size:36px;margin-bottom:12px">[IMG]</div><div style="font-size:14px;color:#6e6e82">No assets yet.</div><div style="font-size:12px;color:#6e6e82;margin-top:8px">Use Campaign Factory to generate first hooks and visuals.</div></div>'

complete_gap = [{'name':x.get('name',''),'owner':x.get('owner','')} for x in assets if x.get('status') in ('published','approved')]
progress_gap = [{'name':x.get('name',''),'owner':x.get('owner','')} for x in assets if x.get('status') in ('generated','pending')]
blocked_gap = [{'name':x.get('name',''),'owner':x.get('owner','')} for x in assets if x.get('status') == 'blocked']
gap_analysis = ('<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">'
    '%s%s%s</div>') % (
    gap_col('Complete','green', complete_gap if complete_gap else [{'name':'---','owner':''}]),
    gap_col('In Progress','amber', progress_gap if progress_gap else [{'name':'---','owner':''}]),
    gap_col('Blocked','red', blocked_gap if blocked_gap else [{'name':'---','owner':''}]))

completion_tab = ('<div class="grid-3" style="margin-bottom:16px">'
    '<div class="completion-card"><div class="cc-num" style="color:#00cc77">%d</div><div class="cc-label">Complete</div></div>'
    '<div class="completion-card"><div class="cc-num" style="color:#ffaa00">%d</div><div class="cc-label">In Progress</div></div>'
    '<div class="completion-card"><div class="cc-num" style="color:#ff4455">%d</div><div class="cc-label">Blocked</div></div>'
    '</div>%s') % (complete, progress, blocked, gap_analysis)

gap_tab = ('<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">'
    '%s%s%s</div>'
    '<div class="card" style="margin-top:16px"><div class="card-title">Launch Readiness Assessment</div>'
    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px">'
    '<div style="text-align:center;padding:16px;background:rgba(255,68,85,0.08);border:1px solid rgba(255,68,85,0.2);border-radius:8px"><div style="font-size:28px;font-weight:700;color:#ff4455;margin-bottom:4px">%d</div><div style="font-size:11px;color:#ff4455">Critical Blockers</div></div>'
    '<div style="text-align:center;padding:16px;background:rgba(255,170,0,0.08);border:1px solid rgba(255,170,0,0.2);border-radius:8px"><div style="font-size:28px;font-weight:700;color:#ffaa00;margin-bottom:4px">%d</div><div style="font-size:11px;color:#ffaa00">Missing Assets</div></div>'
    '<div style="text-align:center;padding:16px;background:rgba(0,204,119,0.08);border:1px solid rgba(0,204,119,0.2);border-radius:8px"><div style="font-size:28px;font-weight:700;color:#00cc77;margin-bottom:4px">%d</div><div style="font-size:11px;color:#00cc77">Approved Assets</div></div>'
    '</div>'
    '<div class="diagnostic-box"><div class="diagnostic-label">Path to Launch</div><div class="diagnostic-text">'
    '1. @image-gen generates Hook A hero visual &rarr; today<br>'
    '2. @image-gen generates Hook G hero visual &rarr; today<br>'
    '3. Christelle approves Hook G carousel &rarr; today<br>'
    '4. @publisher publishes Hook A + Hook G &rarr; tomorrow<br><br>'
    '<span style="background:rgba(0,204,119,0.15);color:#00cc77;padding:1px 4px;border-radius:3px">the campaign transitions to Ready to Launch</span>'
    '</div></div></div>') % (
    gap_col('Complete','green',[{'name':'Hook A copy (published)','owner':'Live'},{'name':'Hook E copy (published)','owner':'Live'},{'name':'Hook G copy (approved)','owner':'Christelle'}]),
    gap_col('Missing','amber',[{'name':'Hook G carousel visual','owner':'@image-gen'},{'name':'Hook G hero visual','owner':'Brief needed'},{'name':'Hook A hero visual','owner':'Brief needed'}]),
    gap_col('Critical Blockers','red',[{'name':'Hook A re-publish: no visual assigned','owner':'Critical'},{'name':'Hook G publish: no visual','owner':'Critical'},{'name':'GMB rotation lapsed 7 days','owner':'High'}]),
    blocked, not_started + progress, complete)

weekly_actions = ('<div class="priority-item">'
    '<div style="width:6px;height:6px;border-radius:50%%;flex-shrink:0;margin-top:5px;background:#ff4455"></div>'
    '<div class="waiting-content"><div class="waiting-title">Re-publish Hook A (best performer, unpublished 14 days)</div><div class="waiting-sub">High leverage &middot; @image-gen needs brief</div></div>'
    '<button class="action-btn">Assign Brief</button></div>'
    '<div class="priority-item">'
    '<div style="width:6px;height:6px;border-radius:50%%;flex-shrink:0;margin-top:5px;background:#ffaa00"></div>'
    '<div class="waiting-content"><div class="waiting-title">Publish Hook G (approved 14 days, no visual)</div><div class="waiting-sub">High leverage &middot; @image-gen assigned</div></div>'
    '<button class="action-btn">Generate Visual</button></div>'
    '<div class="priority-item">'
    '<div style="width:6px;height:6px;border-radius:50%%;flex-shrink:0;margin-top:5px;background:#6e6e82"></div>'
    '<div class="waiting-content"><div class="waiting-title">Resume GMB rotation (7 days lapsed)</div><div class="waiting-sub">Weekly cadence &middot; @publisher</div></div>'
    '<button class="action-btn">Resume</button></div>') % {}

rev = metrics.get('revenue', 0)
rev_str = 'R %d' % rev if rev else '---'

diag_warn = ''
if diag:
    diag_warn = '<div style="font-size:11px;color:var(--amber);margin-top:4px">WARNING: %s</div>' % diag

# Build HTML via string concatenation
H = ''
H += '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>' + c.get('name','Campaign') + ' - Campaign Mothership</title>\n<style>\n:root{--bg:#0a0a0f;--surface:#111118;--surface2:#18181f;--border:rgba(255,255,255,0.08);--text:#e8e8ed;--muted:#6e6e82;--green:#00cc77;--amber:#ffaa00;--red:#ff4455;--blue:#4488ff;--purple:#9966ff}\n*{box-sizing:border-box;margin:0;padding:0}\nbody{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:13px}\n.container{max-width:1100px;margin:0 auto;padding:20px}\n.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}\n.card-title{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}\n.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}\n.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}\n.ring{position:relative;width:70px;height:70px}\n.ring svg{transform:rotate(-90deg);display:block}\n.ring-bg{fill:none;stroke:var(--surface2);stroke-width:6}\n.ring-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}\n.ring-number{font-size:18px;font-weight:700}\n.ring-label{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em}\n.flex{display:flex;align-items:center;gap:14px}\n.metric{text-align:center;padding:12px}\n.metric-num{font-size:24px;font-weight:700;margin-bottom:4px}\n.metric-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em}\n.diagnostic-box{background:rgba(255,170,0,0.08);border:1px solid rgba(255,170,0,0.2);border-radius:8px;padding:10px 12px;margin-top:10px}\n.diagnostic-label{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--amber);margin-bottom:4px}\n.diagnostic-text{font-size:11px;line-height:1.6}\n.launch-badge{display:flex;align-items:center;gap:10px;padding:10px 16px;border-radius:10px;font-size:13px;font-weight:700;flex-shrink:0}\n.launch-badge.ready{background:rgba(0,204,119,0.12);border:2px solid var(--green);color:var(--green)}\n.launch-badge.missing{background:rgba(255,170,0,0.12);border:2px solid var(--amber);color:var(--amber)}\n.launch-badge.blocked{background:rgba(255,68,85,0.12);border:2px solid var(--red);color:var(--red)}\n.launch-badge-num{font-size:22px;font-weight:700}\n.headerBAR{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px;gap:20px}\n.title-xl{font-size:20px;font-weight:700;margin-bottom:4px}\n.subtitle{font-size:12px;color:var(--muted)}\n.section-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);margin-bottom:8px}\n.section-title{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);margin-bottom:8px}\n.nav{display:flex;gap:2px;margin-bottom:20px;padding:8px;background:var(--surface);border-radius:10px;overflow-x:auto}\n.nav li{list-style:none;padding:6px 14px;font-size:12px;color:var(--muted);cursor:pointer;border-radius:6px;white-space:nowrap}\n.nav li:hover{color:var(--text)}\n.nav li.active{background:rgba(0,204,119,0.1);color:var(--green)}\n.panel{display:none}\n.panel.active{display:block}\n.completion-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}\n.cc-num{font-size:28px;font-weight:700;margin-bottom:4px}\n.cc-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em}\n.priority-item{display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:11px}\n.priority-item:last-child{border-bottom:none}\n.waiting-content{flex:1}\n.waiting-title{font-weight:600;margin-bottom:2px}\n.waiting-sub{color:var(--muted);font-size:10px}\n.action-btn{background:rgba(0,204,119,0.1);border:1px solid var(--green);color:var(--green);padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap}\n.footer{text-align:center;font-size:10px;color:var(--muted);padding:20px 0;border-top:1px solid var(--border);margin-top:16px}\n.footer a{color:var(--green);text-decoration:none}\n.mt-8{margin-top:8px}.mt-12{margin-top:12px}\na{color:var(--green)}\n</style>\n</head>\n<body>\n<div class="container">\n'

H += '<div class="headerBAR">\n  <div>\n    <div class="title-xl">' + c.get('name','Campaign') + ' - Campaign Mothership</div>\n    <div class="subtitle">' + c.get('goal','Campaign') + ' &middot; Updated ' + up_str + '</div>\n    ' + diag_warn + '\n  </div>\n  <div class="launch-badge ' + badge_state + '">\n    <div class="launch-badge-num">' + badge_num + '</div>\n    <div><div>' + badge_label + '</div><div style="font-size:10px;opacity:0.7">' + str(complete) + '/' + str(total) + ' complete</div></div>\n  </div>\n</div>\n\n' + lr_bar + '\n\n<ul class="nav">\n  <li class="active" onclick="showTab(\'overview\')">Overview</li>\n  <li onclick="showTab(\'queue\')">Asset Queue (' + str(len(q_assets)) + ')</li>\n  <li onclick="showTab(\'production\')">Production (' + str(len(assets)) + ')</li>\n  <li onclick="showTab(\'completion\')">Completion</li>\n  <li onclick="showTab(\'gaps\')">Gap Analysis</li>\n</ul>\n\n<div class="panel active" id="panel-overview">\n<div class="grid-2">\n  <div>\n    <div class="card">\n      <div class="card-title">Campaign Health</div>\n      <div class="flex">\n        <div class="ring">\n          <svg width="70" height="70" viewBox="0 0 70 70">\n            <circle class="ring-bg" cx="35" cy="35" r="30"/>\n            <circle cx="35" cy="35" r="30" stroke-dasharray="' + '%.2f %.2f' % (circ, circ) + '" stroke-dashoffset="%.2f" style="stroke:' + hc + ';fill:none;stroke-width:6;stroke-linecap:round"/>\n          </svg>\n          <div class="ring-center"><div class="ring-number" style="color:' + hc + '">' + str(score) + '</div><div class="ring-label">' + hs.title() + '</div></div>\n        </div>\n        <div style="flex:1">\n          <div style="font-size:14px;font-weight:600;color:' + hc + ';margin-bottom:4px;text-transform:capitalize">' + hs + ' - ' + str(score) + '/100</div>\n          <div style="font-size:10px;color:var(--muted)">Refreshed: ' + up_str + '</div>\n          <div class="diagnostic-box">\n            <div class="diagnostic-label">Diagnostic</div>\n            <div class="diagnostic-text">' + diag + '</div>\n          </div>\n        </div>\n      </div>\n      <div class="mt-12">\n        <div class="section-title">Health Breakdown</div>\n        ' + bd_html() + '\n      </div>\n    </div>\n    <div class="card">\n      <div class="card-title">This Week</div>\n      ' + weekly_actions + '\n    </div>\n  </div>\n  <div>\n    <div class="card">\n      <div class="card-title">Marketing Metrics</div>\n      <div class="grid-3">\n        <div class="metric"><div class="metric-num" style="color:var(--blue)">' + str(metrics.get('reach','---')) + '</div><div class="metric-label">Reach</div></div>\n        <div class="metric"><div class="metric-num" style="color:var(--green)">' + str(metrics.get('engagement','---')) + '</div><div class="metric-label">Engagement</div></div>\n        <div class="metric"><div class="metric-num" style="color:var(--purple)">' + str(metrics.get('conversions','---')) + '</div><div class="metric-label">Conversions</div></div>\n      </div>\n      <div style="text-align:center;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">\n        <div style="font-size:20px;font-weight:700;color:var(--green)">' + rev_str + '</div>\n        <div class="metric-label">Revenue</div>\n      </div>\n    </div>\n    ' + strat + '\n    ' + pillars_out + '\n  </div>\n</div>\n</div>\n\n<div class="panel" id="panel-queue">\n  <div class="card-title" style="padding-bottom:12px">Asset Generation Queue - ' + str(len(q_assets)) + ' items</div>\n  ' + queue_tab_html + '\n</div>\n\n<div class="panel" id="panel-production">\n  <div class="card-title" style="padding-bottom:12px">Production View - ' + str(len(assets)) + ' assets</div>\n  ' + prod_tab_html + '\n</div>\n\n<div class="panel" id="panel-completion">\n  ' + completion_tab + '\n</div>\n\n<div class="panel" id="panel-gaps">\n  <div class="card-title" style="padding-bottom:12px">Gap Analysis - What Is Preventing Launch</div>\n  ' + gap_tab + '\n</div>\n\n<div class="footer">\n  Campaign OS v2 &middot; Operational State &middot; Last updated: ' + up_str + ' &middot;\n  Source: campaign-data.json &middot;\n  <a href="https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/build-board.html">Build Board</a> &middot;\n  <a href="https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/release-plan.html">Release Plan</a>\n</div>\n</div>\n<script>\nfunction showTab(name){\n  document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("active")});\n  document.querySelectorAll(".nav li").forEach(function(t){t.classList.remove("active")});\n  document.getElementById("panel-"+name).classList.add("active");\n  var tabs=document.querySelectorAll(".nav li");\n  var map={overview:0,queue:1,production:2,completion:3,gaps:4};\n  if(map[name]!==undefined&&tabs[map[name]])tabs[map[name]].classList.add("active");\n}\n</script>\n</body>\n</html>'

with open(DST, 'w') as f:
    f.write(H)

print('OK Written:', DST)
print('Size:', len(H), 'bytes')
print('Stats: complete=%d progress=%d blocked=%d notStarted=%d total=%d' % (complete, progress, blocked, not_started, total))
print('Health:', score, hs)
print('Updated:', up_str)
