const fs = require('fs');
const path = require('path');

const htmlPath = process.argv[2] || path.join(process.cwd(), 'campaign-os/cockpit-operational.html');
const dataPath = process.argv[3] || path.join(process.cwd(), 'campaign-os/campaign-data.json');

const D = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
let H = fs.readFileSync(htmlPath, 'utf8');

const assets = D.assets || {};
const assetKeys = Object.keys(assets);

const complete = assetKeys.filter(k => ['published','approved'].includes(assets[k].status)).length;
const progress = assetKeys.filter(k => ['generated','pending','review','rejected'].includes(assets[k].status)).length;
const blocked = assetKeys.filter(k => assets[k].status === 'blocked').length;
const q_assets = assetKeys.filter(k => !['published','approved','blocked'].includes(assets[k].status)).length;

function statusBadge(status) {
  if (['published','approved'].includes(status)) return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#4488ff22;color:#4488ff">Published</span>';
  if (status === 'review') return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ffaa0022;color:#ffaa00">Awaiting Approval</span>';
  if (status === 'generated') return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ffaa0022;color:#ffaa00">Generated</span>';
  if (status === 'rejected') return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#ff445522;color:#ff4455">Rejected</span>';
  return '<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;background:#6e6e8222;color:#6e6e82">' + status + '</span>';
}

const icons = {research:'&#128269;', hook:'&#128227;', 'hero-visual':'&#127912;', carousel:'&#127912;', video:'&#127916;', copy:'&#9998;'};
function assetIcon(t) { return icons[t] || '&#128196;'; }

let prodItems = '';
for (const k of assetKeys) {
  const a = assets[k];
  const name = a.name || k;
  const atype = a.assetType || 'unknown';
  const status = a.status || 'unknown';
  const owner = a.owner || '';
  const caption = (a.caption || a.description || '').slice(0, 100);
  const blockedBy = a.blockedBy || [];
  const blockedStr = blockedBy.length
    ? '<div style="margin-top:6px;padding:6px 8px;background:rgba(255,68,85,0.1);border-radius:6px;font-size:10px;color:#ff4455">Blocked by: ' + blockedBy.join(', ') + '</div>'
    : '';

  prodItems += '<div style="display:flex;gap:14px;padding:12px;background:#18181f;border-radius:8px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.08)">' +
    '<div style="width:56px;height:56px;border-radius:6px;background:#111118;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0">' + assetIcon(atype) + '</div>' +
    '<div style="flex:1;min-width:0">' +
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">' + statusBadge(status) + '<span style="font-size:10px;color:#6e6e82">' + atype + '</span></div>' +
    '<div style="font-size:13px;font-weight:600;margin-bottom:2px">' + name + '</div>' +
    '<div style="font-size:10px;color:#6e6e82;margin-bottom:6px">@' + owner + '</div>' +
    '<div style="font-size:11px;color:#e8e8ed;margin-top:4px;line-height:1.4">' + caption + '</div>' +
    blockedStr +
    '<div style="margin-top:8px;display:flex;gap:6px"><button style="background:rgba(0,204,119,0.15);color:#00cc77;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Approve</button><button style="background:rgba(255,68,85,0.15);color:#ff4455;border:none;padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Reject</button></div>' +
    '</div></div>';
}

// Patch mp-production
H = H.replace(
  /<div class="mothership-panel" id="mp-production">[\s\S]*?<\/div>\s*<div class="mothership-panel" id="mp-completion">/,
  '<div class="mothership-panel" id="mp-production">\n  ' + prodItems + '\n  <div style="margin-top:12px;padding:10px;background:#111118;border-radius:8px;font-size:11px;color:#6e6e82">' + complete + ' complete &middot; ' + progress + ' in progress &middot; ' + blocked + ' blocked</div>\n</div>\n<div class="mothership-panel" id="mp-completion">'
);

// Update completion counts
H = H.replace(/(<div class="cc-num" style="color:#00cc77">)(\d+)(<\/div><div class="cc-label">Complete)/, '$1' + complete + '$3');
H = H.replace(/(<div class="cc-num" style="color:#ffaa00">)(\d+)(<\/div><div class="cc-label">In Progress)/, '$1' + progress + '$3');
H = H.replace(/(<div class="cc-num" style="color:#ff4455">)(\d+)(<\/div><div class="cc-label">Blocked)/, '$1' + blocked + '$3');

// Patch queue
let queueHtml = '';
for (const k of assetKeys.filter(k => !['published','approved','blocked'].includes(assets[k].status))) {
  const a = assets[k];
  queueHtml += '<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px"><strong>' + (a.name||k) + '</strong> <span style="color:#6e6e82">@' + (a.owner||'') + '</span> <span style="color:#ffaa00">(' + (a.status||'') + ')</span></div>';
}
H = H.replace(
  /<div class="mothership-panel" id="mp-queue">[\s\S]*?<\/div>\s*<div class="mothership-panel" id="mp-production">/,
  '<div class="mothership-panel" id="mp-queue">\n  ' + (queueHtml || '<div style="text-align:center;padding:24px;color:#6e6e82;font-size:12px">No queued assets</div>') + '\n</div>\n<div class="mothership-panel" id="mp-production">'
);

// Inject campaignData
const campaignStr = JSON.stringify(D);
H = H.replace(
  /window\.campaignData\s*=\s*\{[^;]*\};/,
  'window.campaignData = ' + campaignStr + ';'
);

fs.writeFileSync(htmlPath, H);
console.log('Patched OK - complete=' + complete + ' progress=' + progress + ' blocked=' + blocked + ' queue=' + q_assets);
console.log('Assets:', assetKeys.join(', '));