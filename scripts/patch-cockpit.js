const fs = require('fs');
const path = require('path');

const htmlPath = process.argv[2] || path.join(process.cwd(), 'campaign-os/cockpit-operational.html');
const dataPath = process.argv[3] || path.join(process.cwd(), 'campaign-os/campaign-data.json');

const D = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
let H = fs.readFileSync(htmlPath, 'utf8');

const assets = D.assets || {};
const assetKeys = Object.keys(assets);

// Count statuses
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

// Build Production tab items
let prodItems = '';
for (const k of assetKeys) {
  const a = assets[k];
  const name = a.name || k;
  const atype = a.assetType || 'unknown';
  const status = a.status || 'unknown';
  const owner = a.owner || '';
  const caption = (a.caption || a.description || '').slice(0, 120);
  const blockedBy = a.blockedBy || [];
  const blockedStr = blockedBy.length
    ? '<div style="margin-top:6px;padding:6px 8px;background:rgba(255,68,85,0.1);border-radius:6px;font-size:10px;color:#ff4455">Blocked by: ' + blockedBy.join(', ') + '</div>'
    : '';
  const thumbLetter = (name[0] || '?').toUpperCase();

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

// Build Queue tab items
let queueItems = '';
for (const k of assetKeys.filter(k => !['published','approved','blocked'].includes(assets[k].status))) {
  const a = assets[k];
  const status = a.status || '';
  const statusIcon = {generated:'[GEN]',review:'[REV]',rejected:'[NO]',pending:'[...]',draft:'[DRF]'}[status] || '[...]';
  queueItems += '<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#111118;border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:6px">' +
    '<div style="width:40px;height:40px;border-radius:6px;background:#18181f;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#6e6e82;flex-shrink:0;font-family:monospace">' + statusIcon + '</div>' +
    '<div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;margin-bottom:2px">' + (a.name||k) + '</div>' +
    '<div style="font-size:10px;color:#6e6e82">' + (a.owner?'@'+a.owner:'') + '</div></div>' +
    '<div style="font-size:10px;color:#ffaa00;font-weight:600">' + status + '</div></div>';
}

// Patch panel-production (Production tab)
H = H.replace(
  /(<div class="panel" id="panel-production">\s*<div class="card-title"[^>]*>)[^<]*<\/div>\s*(<div style="text-align:center[^>]*>[^<]*<\/div>\s*)?(<div style="font-size:36px[^>]*>[^<]*<\/div>)?/,
  '$1' + 'Production View - ' + assetKeys.length + ' assets</div>\n  ' + prodItems
);

// Patch cc-num green/amber/red in completion section
H = H.replace(/(<div class="cc-num green">)(\d+)/, '$1' + String(complete));
H = H.replace(/(<div class="cc-num amber">)(\d+)/, '$1' + String(progress));
H = H.replace(/(<div class="cc-num red">)(\d+)/, '$1' + String(blocked));

// Patch panel-queue (Asset Queue tab)
if (queueItems) {
  H = H.replace(
    /<div class="panel" id="panel-queue">\s*<div class="card-title"[^>]*>[^<]*<\/div>\s*<div style="text-align:center;padding:50px;color:#6e6e82;font-size:13px">No queued assets\. Generate via Campaign Factory\.<\/div>/,
    '<div class="panel" id="panel-queue">\n  <div class="card-title" style="padding-bottom:12px">Asset Queue - ' + q_assets + ' items</div>\n  ' + queueItems + '\n</div>'
  );
}

// Inject window.campaignData
const campaignStr = JSON.stringify(D);
H = H.replace(
  /window\.campaignData\s*=\s*\{[^;]*\};/,
  'window.campaignData = ' + campaignStr + ';'
);

fs.writeFileSync(htmlPath, H);
console.log('Patched OK');
console.log('  complete=' + complete + ' progress=' + progress + ' blocked=' + blocked + ' queue=' + q_assets);
console.log('  Assets (' + assetKeys.length + '):', assetKeys.join(', '));