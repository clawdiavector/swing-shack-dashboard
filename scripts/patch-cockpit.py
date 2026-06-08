#!/usr/bin/env python3
"""Patch cockpit-operational.html with real assets from campaign-data.json"""
import json, re, sys

html_path = sys.argv[1] if len(sys.argv) > 1 else 'campaign-os/cockpit-operational.html'
data_path = sys.argv[2] if len(sys.argv) > 2 else 'campaign-os/campaign-data.json'

with open(data_path) as f:
    D = json.load(f)

with open(html_path) as f:
    H = f.read()

assets = D.get('assets', {})
if isinstance(assets, list):
    assets = {a.get('assetId', 'asset-' + str(i)): a for i, a in enumerate(assets)}

complete = sum(1 for a in assets.values() if a.get('status') in ('published', 'approved'))
progress = sum(1 for a in assets.values() if a.get('status') in ('generated', 'pending', 'review', 'rejected'))
blocked = sum(1 for a in assets.values() if a.get('status') == 'blocked')
q_assets = [a for a in assets.values() if a.get('status') not in ('published', 'approved', 'blocked')]

def status_badge(status):
    if status in ('published', 'approved'):
        return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#4488ff22;color:#4488ff">Published</span>'
    elif status == 'review':
        return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ffaa0022;color:#ffaa00">Awaiting Approval</span>'
    elif status == 'generated':
        return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ffaa0022;color:#ffaa00">Generated</span>'
    elif status == 'rejected':
        return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ff445522;color:#ff4455">Rejected</span>'
    else:
        return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#6e6e8222;color:#6e6e82">' + status + '</span>'

def asset_type_icon(assetType):
    icons = {'research': '&#128269;', 'hook': '&#128227;', 'hero-visual': '&#127912;', 'carousel': '&#127912;', 'video': '&#127916;', 'copy': '&#9998;'}
    return icons.get(assetType, '&#128196;')

prod_items = []
for k, v in assets.items():
    name = v.get('name', k)
    asset_type = v.get('assetType', 'unknown')
    status = v.get('status', 'unknown')
    owner = v.get('owner', '')
    caption = v.get('caption', v.get('description', ''))[:100]
    blocked_by = v.get('blockedBy') or []
    blocked_str = ''
    if blocked_by:
        names = [assets.get(ref, {}).get('name', ref) for ref in blocked_by]
        blocked_str = '<div style="margin-top:6px;padding:6px 8px;background:rgba(255,68,85,0.1);border-radius:6px;font-size:10px;color:#ff4455">Blocked by: ' + ', '.join(names) + '</div>'

    item = (
        '<div style="display:flex;gap:14px;padding:12px;background:#18181f;border-radius:8px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.08)">'
        '<div style="width:56px;height:56px;border-radius:6px;background:#111118;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0">' + asset_type_icon(asset_type) + '</div>'
        '<div style="flex:1;min-width:0">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">' + status_badge(status) +
        '<span style="font-size:10px;color:#6e6e82">' + asset_type + '</span>'
        '</div>'
        '<div style="font-size:13px;font-weight:600;margin-bottom:2px">' + name + '</div>'
        '<div style="font-size:10px;color:#6e6e82;margin-bottom:6px">@' + owner + '</div>'
        '<div style="font-size:11px;color:#e8e8ed;margin-top:4px;line-height:1.4">' + caption + '</div>'
        + blocked_str +
        '<div style="margin-top:8px;display:flex;gap:6px"><button style="background:rgba(0,204,119,0.15);color:#00cc77;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Approve</button><button style="background:rgba(255,68,85,0.15);color:#ff4455;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Reject</button></div>'
        '</div></div>'
    )
    prod_items.append(item)

prod_tab_html = ''.join(prod_items) if prod_items else '<div style="text-align:center;padding:48px 0;color:#6e6e82">No assets in production</div>'

# Patch mp-production div (mothership tab version)
H = re.sub(
    r'(<div class="mothership-panel" id="mp-production">)(.*?)(</div>\s*<div class="mothership-panel" id="mp-completion">)',
    r'\g<1>\n  ' + prod_tab_html + '\n  <div style="margin-top:12px;padding:10px;background:#111118;border-radius:8px;font-size:11px;color:#6e6e82">' + str(complete) + ' complete &middot; ' + str(progress) + ' in progress &middot; ' + str(blocked) + ' blocked</div>\n</div>\n<div class="mothership-panel" id="mp-completion">',
    H, flags=re.DOTALL
)

# Update completion counts
old_complete_card = r'(<div class="completion-card"><div class="cc-num" style="color:#00cc77">)\d+()</div><div class="cc-label">Complete</div></div>'
old_progress_card = r'(<div class="completion-card"><div class="cc-num" style="color:#ffaa00">)\d+()</div><div class="cc-label">In Progress</div></div>'
old_blocked_card = r'(<div class="completion-card"><div class="cc-num" style="color:#ff4455">)\d+()</div><div class="cc-label">Blocked</div></div>'
H = re.sub(old_complete_card, r'\g<1>' + str(complete) + r'\2', H)
H = re.sub(old_progress_card, r'\g<1>' + str(progress) + r'\2', H)
H = re.sub(old_blocked_card, r'\g<1>' + str(blocked) + r'\2', H)

# Update queue tab
queue_items = []
for v in q_assets:
    name = v.get('name', v.get('assetId', ''))
    owner = v.get('owner', '')
    status = v.get('status', '')
    queue_items.append('<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px"><strong>' + name + '</strong> <span style="color:#6e6e82">@' + owner + '</span> <span style="color:#ffaa00">(' + status + ')</span></div>')
queue_tab = ''.join(queue_items) if queue_items else '<div style="text-align:center;padding:24px;color:#6e6e82;font-size:12px">No queued assets</div>'
H = re.sub(
    r'<div class="mothership-panel" id="mp-queue">.*?</div>\s*<div class="mothership-panel" id="mp-production">',
    '<div class="mothership-panel" id="mp-queue">\n  ' + queue_tab + '\n</div>\n<div class="mothership-panel" id="mp-production">',
    H, flags=re.DOTALL
)

# Inject assets into window.campaignData
campaign_str = json.dumps(D, separators=(',', ':'))
H = re.sub(
    r'window\.campaignData\s*=\s*\{[^;]*\};',
    'window.campaignData = ' + campaign_str + ';',
    H, flags=re.DOTALL
)

with open(html_path, 'w') as f:
    f.write(H)

print('Patched OK')
print('complete=%d progress=%d blocked=%d queue=%d' % (complete, progress, blocked, len(q_assets)))