#!/usr/bin/env python3
"""Gate 3: Pipeline Visibility UI.
Adds pipeline status display (idle / running / failed) to campaign detail view.
Reads from window.campaignData.campaigns[id].pipeline (real schema).
No real campaign data modified. No fake state injected."""
import re

HTML = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/cockpit-operational.html'
BACKUP = HTML + '.gate3.bak'

with open(HTML, 'r') as f:
    h = f.read()

with open(BACKUP, 'w') as f:
    f.write(h)
print(f'Backup: {BACKUP}')

# --- 1. CSS for pipeline UI ---
pipeline_css = """.pipeline-bar{border-radius:12px;padding:20px;margin-bottom:20px}
.pipeline-bar.idle{background:#111118;border:1px solid rgba(255,255,255,0.08)}
.pipeline-bar.running{background:linear-gradient(135deg,#1a2b1a 0%,#0d1f15 100%);border:1px solid #00cc7744}
.pipeline-bar.failed{background:linear-gradient(135deg,#2b1a1a 0%,#1f0d0d 100%);border:1px solid #ff445544}
.pipeline-bar.ready{background:linear-gradient(135deg,#1a2b0d 0%,#0d1f15 100%);border:1px solid #00cc7744}
.pipeline-label{font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px}
.pipeline-label.idle{color:#6e6e82}.pipeline-label.running{color:#00cc77}.pipeline-label.failed{color:#ff4455}.pipeline-label.ready{color:#00cc77}
.pipeline-step{font-size:13px;font-weight:600;margin-bottom:4px}
.pipeline-agent{font-size:12px;color:#6e6e82;margin-bottom:12px}
.pipeline-progress{display:flex;gap:8px;margin-bottom:8px}
.pipeline-dot{width:28px;height:6px;border-radius:3px;background:rgba(255,255,255,0.1)}
.pipeline-dot.done{background:#00cc77}.pipeline-dot.active{background:#ffaa00}
.pipeline-dot-label{font-size:11px;color:#6e6e82;margin-bottom:12px}
.pipeline-error{color:#ff4455;font-size:12px;padding:10px;background:rgba(255,68,85,0.1);border-radius:6px;margin-top:8px}
.pipeline-retry{margin-top:12px;padding:8px 16px;font-size:12px;font-weight:600;color:#ff4455;background:rgba(255,68,85,0.1);border:1px solid #ff445544;border-radius:6px;cursor:pointer;display:inline-block}
.pipeline-retry:hover{background:rgba(255,68,85,0.2)}"""

if '.pipeline-bar' not in h:
    h = h.replace('</style>', pipeline_css + '\n</style>')
    print('Pipeline CSS injected')

# --- 2. renderPipeline JS function ---
pipeline_js = """
function renderPipeline(pid) {
    var D = window.campaignData;
    var c = D && D.campaigns && D.campaigns[pid];
    var p = c && c.pipeline;
    if (!p || !p.status) {
        return '<div class="pipeline-bar idle"><div class="pipeline-label idle">Pipeline Status</div><div class="pipeline-step">No active blueprint generation</div><div class="pipeline-agent">Start a campaign to see pipeline progress</div></div>';
    }
    var st = p.status;
    if (st === 'generatingBlueprint') {
        var step = p.currentStep || 1;
        var total = p.totalSteps || 4;
        var agent = p.currentAgent || '---';
        var icons = {Scout:'&#128269;',Copywriter:'&#10000;',ImageGen:'&#127912;',Publisher:'&#128229;',Clawdia:'&#9889;'};
        var icon = icons[agent] || '&#8987;';
        var dots = '';
        for (var i = 0; i < total; i++) {
            dots += '<div class="pipeline-dot' + (i < step - 1 ? ' done' : i === step - 1 ? ' active' : '') + '"></div>';
        }
        return '<div class="pipeline-bar running">' +
            '<div class="pipeline-label running">Generating Blueprint</div>' +
            '<div class="pipeline-step">' + icon + ' ' + agent + ' &#8212; Step ' + step + ' of ' + total + '</div>' +
            '<div class="pipeline-progress">' + dots + '</div>' +
            '<div class="pipeline-dot-label">Campaign Status: <strong style="color:#00cc77">Generating Blueprint</strong></div>' +
            '</div>';
    }
    if (st === 'failed') {
        return '<div class="pipeline-bar failed">' +
            '<div class="pipeline-label failed">Pipeline Failed</div>' +
            '<div class="pipeline-step">Failed at: ' + (p.currentAgent || 'unknown') + '</div>' +
            (p.errorMessage ? '<div class="pipeline-error">Error: ' + p.errorMessage + '</div>' : '') +
            '<a class="pipeline-retry" href="javascript:retryCampaign(\'' + pid + '\')">&#128260; Retry Campaign</a>' +
            '</div>';
    }
    if (st === 'blueprintReady') {
        return '<div class="pipeline-bar ready">' +
            '<div class="pipeline-label ready">Blueprint Ready</div>' +
            '<div class="pipeline-step">&#9989; Campaign blueprint generated</div>' +
            '<div class="pipeline-agent">Ready for production</div>' +
            '</div>';
    }
    return '';
}
function retryCampaign(cid) { alert('Retry: would restart pipeline for campaign ' + cid); }
"""

# Remove old versions if present
h = re.sub(r'function\s+renderPipeline\s*\([^)]*\)\s*\{[\s\S]*?\n\}', '', h, count=1)
h = re.sub(r'function\s+retryCampaign\s*\([^)]*\)\s*\{[\s\S]*?\n\}', '', h, count=1)

if '</script>' in h:
    h = h.replace('</script>', pipeline_js + '\n</script>')
    print('Pipeline JS injected')
else:
    h = h.replace('</body>', '<script>' + pipeline_js + '</script>\n</body>')
    print('Pipeline JS injected (no script tag)')

# --- 3. UPDATE renderCampaign to prepend pipeline HTML ---
old_render = "function renderCampaign(id) {\n  var D = window.campaignData;\n  var c = D.campaigns[id];\n  if (!c) return;\n  document.getElementById('detail-content').innerHTML = window.renderFns[id](c);\n}"
new_render = "function renderCampaign(id) {\n  var D = window.campaignData;\n  var c = D.campaigns[id];\n  if (!c) return;\n  var pipeHtml = renderPipeline(id);\n  document.getElementById('detail-content').innerHTML = pipeHtml + window.renderFns[id](c);\n}"

if old_render in h:
    h = h.replace(old_render, new_render)
    print('renderCampaign updated to prepend pipeline HTML')
else:
    print('WARNING: could not find exact renderCampaign pattern')
    # Try simple replacement
    h = h.replace(
        "document.getElementById('detail-content').innerHTML = window.renderFns[id](c);",
        "var pipeHtml = renderPipeline(id);\n  document.getElementById('detail-content').innerHTML = pipeHtml + window.renderFns[id](c);"
    )
    print('Applied simple replacement for detail-content innerHTML')

# Write
with open(HTML, 'w') as f:
    f.write(h)

# Verify
print('\nVerification:')
checks = {
    'Pipeline CSS (.pipeline-bar.idle)': '.pipeline-bar.idle' in h,
    'renderPipeline function': 'function renderPipeline' in h,
    'retryCampaign function': 'function retryCampaign' in h,
    'Idle state text': 'No active blueprint generation' in h,
    'Generating Blueprint state': 'generatingBlueprint' in h,
    'Failed state': 'Pipeline Failed' in h,
    'Blueprint Ready state': 'blueprintReady' in h,
    'Pipeline prepends detail': 'pipeHtml + window.renderFns' in h,
    'No fake pipeline data': 'status: \'generatingBlueprint\'' not in h and 'pipeline: {' not in h,
}
for k, v in checks.items():
    print(f'  {"PASS" if v else "FAIL"} {k}')