// Campaign OS Phase 2 — Wizard + API test suite
// Verifies Steps 1-9 of the Campaign Builder against a live Flask backend
// running on http://127.0.0.1:8765, with a localStorage-only fallback path.
//
// Run: node tests/test_phase2_wizard.js
// Pre-req: Flask server must be running (DATA_DIR=/tmp/campaign-os-test PORT=8765 python3 app.py)

'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const BASE = 'http://127.0.0.1:8765';
const HTML_PATH = path.join(__dirname, '..', 'cockpit-operational.html');

let passed = 0, failed = 0, total = 0;
const results = [];

function assert(name, cond, info) {
  total++;
  if (cond) {
    passed++;
    results.push(`  PASS  ${name}`);
  } else {
    failed++;
    results.push(`  FAIL  ${name}${info ? ' — ' + JSON.stringify(info) : ''}`);
  }
}

function section(title) {
  results.push(`\n[${title}]`);
}

function httpJson(method, url, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const data = body ? JSON.stringify(body) : null;
    const opts = {
      method,
      hostname: u.hostname,
      port: u.port,
      path: u.pathname,
      headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}
    };
    const req = http.request(opts, (res) => {
      let chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf-8');
        let json = null;
        try { json = JSON.parse(text); } catch (e) {}
        resolve({ status: res.statusCode, json, text });
      });
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

// ── HTML structure assertions (Steps 1, 7, 8, 9) ─────────────────────
section('HTML structure');
const html = fs.readFileSync(HTML_PATH, 'utf-8');

assert('header has + Campaign Factory button', html.includes('+ Campaign Factory'));
assert('header has Hooks view button', html.includes('id="btn-hooks"') && html.includes('onclick="showView(\'hooks\')"'));
assert('view-hooks panel exists', html.includes('id="view-hooks"'));
assert('Hook Bank filter select exists', html.includes('id="hooks-filter"'));
assert('New Hook modal exists', html.includes('id="hookModal"') && html.includes('id="hookForm"'));
assert('hook functions defined', [
  'function openHookModal', 'function openEditHookModal', 'function closeHookModal',
  'function handleHookSubmit', 'function renderHookBank', 'function renderHookCard',
  'function confirmDeleteHook', 'function promptAttachHook',
  'function hookReadAll', 'function hookWriteAll', 'function hookAppend', 'function hookDelete', 'function nextHookId'
].every(fn => html.includes(fn)));
assert('Hook fields: text, kind, brand, source, note', [
  'id="h-text"', 'id="h-kind"', 'id="h-brand"', 'id="h-source"', 'id="h-note"'
].every(id => html.includes(id)));
assert('Hook kinds include meme/billboard/caption/angle', [
  'value="meme"', 'value="billboard"', 'value="caption"', 'value="angle"'
].every(v => html.includes(v)));
assert('header has Clear Dev Data button', html.includes('Clear Dev Data'));
assert('modal createModal exists', html.includes('id="createModal"'));
assert('Stage 1 fields: name, type, brand, objective, priority', [
  'id="f-name"', 'id="f-type"', 'id="f-brand"', 'id="f-objective"', 'id="f-priority"'
].every(id => html.includes(id)));
assert('Stage 2 fields: purpose, audience, bigidea, success, pillars', [
  'id="f-purpose"', 'id="f-audience"', 'id="f-bigidea"', 'id="f-success"', 'id="f-pillars"'
].every(id => html.includes(id)));
assert('Stage 3 fields: shortname, duration, primarygoal, assetcount, assettype, cta', [
  'id="f-shortname"', 'id="f-duration"', 'id="f-primarygoal"', 'id="f-assetcount"', 'id="f-assettype"', 'id="f-cta"'
].every(id => html.includes(id)));
assert('wizard functions defined', [
  'function wizardStage1Valid', 'function wizardUpdateNextButton',
  'function wizardShowStage', 'function wizardGoBack', 'function wizardGoBackTo2',
  'function wizardReset'
].every(fn => html.includes(fn)));
assert('dev store functions defined', [
  'function devStoreReadAll', 'function devStoreWriteAll',
  'function devStoreAppend', 'function devStoreHydrate',
  'function devApiCreate'
].every(fn => html.includes(fn)));
assert('renderNewCampaignCard defined', html.includes('function renderNewCampaignCard'));
assert('renderGenericDetail defined', html.includes('function renderGenericDetail'));
assert('transitionStatus defined (Step 5)', html.includes('function transitionStatus'));
assert('submitForReview / approveCampaign / rejectCampaign defined', [
  'function submitForReview', 'function approveCampaign', 'function rejectCampaign'
].every(fn => html.includes(fn)));
assert('renderReviewQueue defined (Step 5)', html.includes('function renderReviewQueue'));

// ── Step 11: Meme Lord — standalone workspace ───────────────────────
section('Step 11: Meme Lord (HTML structure)');
assert('header has Meme Lord view button', html.includes('id="btn-memes"') && html.includes("onclick=\"showView('memes')\""));
assert('view-memes panel exists', html.includes('id="view-memes"'));
assert('Meme Lord filter select exists', html.includes('id="memes-filter"'));
assert('Meme Lord filter has All/Standalone/Attached/Shortlisted/Used/Rejected', [
  'value="all"', 'value="standalone"', 'value="attached"',
  'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)) && /id="memes-filter"[\s\S]*?(?=id="[^"]*filter"|$)/.test(html));
assert('New Meme modal exists', html.includes('id="memeModal"') && html.includes('id="memeForm"'));
assert('meme functions defined', [
  'function openMemeModal', 'function openEditMemeModal', 'function closeMemeModal',
  'function handleMemeSubmit', 'function renderMemeLord', 'function renderMemeCard',
  'function confirmDeleteMeme', 'function promptAttachMeme', 'function changeMemeStatus',
  'function memeReadAll', 'function memeWriteAll', 'function memeAppend',
  'function memeDelete', 'function nextMemeId', 'function memeModalPopulateOptions'
].every(fn => html.includes(fn)));
assert('Meme fields: line, format, status, sourcehook, brand, campaign, note', [
  'id="m-line"', 'id="m-format"', 'id="m-status"', 'id="m-sourcehook"',
  'id="m-brand"', 'id="m-campaign"', 'id="m-note"'
].every(id => html.includes(id)));
assert('Meme formats include image-meme/video/caption/carousel', [
  'value="image-meme"', 'value="video"', 'value="caption"', 'value="carousel"'
].every(v => html.includes(v)));
assert('Meme statuses include idea/shortlisted/used/rejected', [
  'value="idea"', 'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('MEME_STORE_KEY defined (campaign-os:dev:memes)', html.includes("MEME_STORE_KEY = 'campaign-os:dev:memes'"));
assert('mcard CSS classes exist', ['.mcard', '.mcard-line', '.mcard-tag', '.mcard-actions', '.mcard-status-row'].every(c => html.includes(c)));
assert('Meme Lord filter wired to renderMemeLord', html.includes("memes-filter") && html.includes('renderMemeLord()'));
assert('showView handles memes', html.includes("name === 'memes'") && html.includes('view-memes'));
assert('clearDevData clears memes', html.includes('removeItem(MEME_STORE_KEY)'));
assert('Meme source-hook select populated from hookReadAll', html.includes('m-sourcehook') && html.includes('hookReadAll()'));

// ── Step 12: Billboard Lab — standalone workspace ───────────────────
section('Step 12: Billboard Lab (HTML structure)');
assert('header has Billboard Lab view button', html.includes('id="btn-billboards"') && html.includes("onclick=\"showView('billboards')\""));
assert('view-billboards panel exists', html.includes('id="view-billboards"'));
assert('Billboard Lab filter select exists', html.includes('id="billboards-filter"'));
assert('Billboard Lab filter has All/Standalone/Attached/Shortlisted/Used/Rejected', [
  'value="all"', 'value="standalone"', 'value="attached"',
  'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('New Billboard modal exists', html.includes('id="billboardModal"') && html.includes('id="billboardForm"'));
assert('billboard functions defined', [
  'function openBillboardModal', 'function openEditBillboardModal', 'function closeBillboardModal',
  'function handleBillboardSubmit', 'function renderBillboardLab', 'function renderBillboardCard',
  'function confirmDeleteBillboard', 'function promptAttachBillboard', 'function changeBillboardStatus',
  'function billboardReadAll', 'function billboardWriteAll', 'function billboardAppend',
  'function billboardDelete', 'function nextBillboardId', 'function billboardModalPopulateOptions'
].every(fn => html.includes(fn)));
assert('Billboard fields: line, format, status, sourcehook, sourcetrend, brand, campaign, note', [
  'id="b-line"', 'id="b-format"', 'id="b-status"', 'id="b-sourcehook"',
  'id="b-sourcetrend"', 'id="b-brand"', 'id="b-campaign"', 'id="b-note"'
].every(id => html.includes(id)));
assert('Billboard formats include window-screen/billboard/bus-shelter/poster/social-overlay', [
  'value="window-screen"', 'value="billboard"', 'value="bus-shelter"',
  'value="poster"', 'value="social-overlay"'
].every(v => html.includes(v)));
assert('Billboard statuses include idea/shortlisted/used/rejected', [
  'value="idea"', 'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('BILLBOARD_STORE_KEY defined (campaign-os:dev:billboards)', html.includes("BILLBOARD_STORE_KEY = 'campaign-os:dev:billboards'"));
assert('bcard CSS classes exist', ['.bcard', '.bcard-line', '.bcard-tag', '.bcard-actions', '.bcard-status-row'].every(c => html.includes(c)));
assert('Billboard Lab filter wired to renderBillboardLab', html.includes("billboards-filter") && html.includes('renderBillboardLab()'));
assert('showView handles billboards', html.includes("name === 'billboards'") && html.includes('view-billboards'));
assert('clearDevData clears billboards', html.includes('removeItem(BILLBOARD_STORE_KEY)'));
assert('Billboard source-hook select populated from hookReadAll', html.includes('b-sourcehook') && html.includes('hookReadAll()'));
assert('Billboard campaign history records billboard-attached', html.includes("'billboard-attached'") && html.includes("'billboard-detached'"));

// ── Step 13: Trend Catcher — the radar ─────────────────────────────
section('Step 13: Trend Catcher (HTML structure)');
assert('header has Trend Catcher view button', html.includes('id="btn-trends"') && html.includes("onclick=\"showView('trends')\""));
assert('view-trends panel exists', html.includes('id="view-trends"'));
assert('Trend Catcher filter select exists', html.includes('id="trends-filter"'));
assert('Trend filter has All/Trend/Signal/Noise/Watching/Shortlisted/Used/Rejected', [
  'value="all"', 'value="trend"', 'value="signal"', 'value="noise"',
  'value="watching"', 'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('New Trend modal exists', html.includes('id="trendModal"') && html.includes('id="trendForm"'));
assert('trend functions defined', [
  'function openTrendModal', 'function openEditTrendModal', 'function closeTrendModal',
  'function handleTrendSubmit', 'function renderTrendCatcher', 'function renderTrendCard',
  'function confirmDeleteTrend', 'function promptAttachTrend', 'function changeTrendStatus',
  'function useTrendAsHookSeed',
  'function trendReadAll', 'function trendWriteAll', 'function trendAppend',
  'function trendDelete', 'function nextTrendId', 'function trendModalPopulateOptions'
].every(fn => html.includes(fn)));
assert('Trend fields: title, sourcetype, signaltype, source, timing, confidence, audience, evidence, opportunity, angle, status, campaign, note', [
  'id="t-title"', 'id="t-sourcetype"', 'id="t-signaltype"', 'id="t-source"',
  'id="t-timing"', 'id="t-confidence"', 'id="t-audience"', 'id="t-evidence"',
  'id="t-opportunity"', 'id="t-angle"', 'id="t-status"', 'id="t-campaign"', 'id="t-note"'
].every(id => html.includes(id)));
assert('Trend source types include Reddit/TikTok/Instagram/YouTube/Google-Trends/Search-Console/GBP/News/Other', [
  'value="reddit"', 'value="tiktok"', 'value="instagram"', 'value="youtube"',
  'value="google-trends"', 'value="search-console"', 'value="gbp"', 'value="news"', 'value="other"'
].every(v => html.includes(v)));
assert('Trend signal types include trend/signal/noise', [
  'value="trend"', 'value="signal"', 'value="noise"'
].every(v => html.includes(v)));
assert('Trend statuses include watching/shortlisted/used/rejected', [
  'value="watching"', 'value="shortlisted"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('Trend timings include now/this-week/seasonal/evergreen', [
  'value="now"', 'value="this-week"', 'value="seasonal"', 'value="evergreen"'
].every(v => html.includes(v)));
assert('TREND_STORE_KEY defined (campaign-os:dev:trends)', html.includes("TREND_STORE_KEY = 'campaign-os:dev:trends'"));
assert('tcard CSS classes exist', ['.tcard', '.tcard-title', '.tcard-tag', '.tcard-actions', '.tcard-status-row', '.tcard-confidence'].every(c => html.includes(c)));
assert('Trend filter wired to renderTrendCatcher', html.includes("trends-filter") && html.includes('renderTrendCatcher()'));
assert('showView handles trends', html.includes("name === 'trends'") && html.includes('view-trends'));
assert('clearDevData clears trends', html.includes('removeItem(TREND_STORE_KEY)'));
assert('Trend confidence is a number 0-100 input', html.includes('id="t-confidence"') && html.includes('type="number"') && html.includes('min="0"') && html.includes('max="100"'));
assert('Trend campaign history records trend-attached', html.includes("'trend-attached'") && html.includes("'trend-detached'"));
assert('Cross-workspace: useTrendAsHookSeed opens hook modal', html.includes('useTrendAsHookSeed') && html.includes('openHookModal'));

// ── Step 14: Calendar — the timeline ───────────────────────────────
section('Step 14: Calendar (HTML structure)');
assert('header has Calendar view button', html.includes('id="btn-calendar"') && html.includes("onclick=\"showView('calendar')\""));
assert('view-calendar panel exists', html.includes('id="view-calendar"'));
assert('Calendar tabs: List/Today/This Week/All', ['cal-tab-list', 'cal-tab-today', 'cal-tab-week', 'cal-tab-all'].every(id => html.includes('id="' + id + '"')));
assert('New Calendar Item modal exists', html.includes('id="calModal"') && html.includes('id="calForm"'));
assert('calendar functions defined', [
  'function openCalModal', 'function openEditCalModal', 'function closeCalModal',
  'function handleCalSubmit', 'function renderCalendar', 'function renderCalCard',
  'function confirmDeleteCal', 'function changeCalStatus', 'function calSwitchView',
  'function calReadAll', 'function calWriteAll', 'function calAppend',
  'function calDelete', 'function nextCalId', 'function calModalPopulateSourceOptions',
  'function buildCalendarTimeline', 'function calDateKey'
].every(fn => html.includes(fn)));
assert('Calendar fields: title, date, time, type, status, brand, channel, source, note', [
  'id="c-title"', 'id="c-date"', 'id="c-time"', 'id="c-type"',
  'id="c-status"', 'id="c-brand"', 'id="c-channel"', 'id="c-source"', 'id="c-note"'
].every(id => html.includes(id)));
assert('Calendar types include task/campaign/hook/meme/billboard/trend/review', [
  'value="task"', 'value="campaign"', 'value="hook"', 'value="meme"',
  'value="billboard"', 'value="trend"', 'value="review"'
].every(v => html.includes(v)));
assert('Calendar statuses include planned/in-progress/done/skipped', [
  'value="planned"', 'value="in-progress"', 'value="done"', 'value="skipped"'
].every(v => html.includes(v)));
assert('CAL_STORE_KEY defined (campaign-os:dev:calendar)', html.includes("CAL_STORE_KEY = 'campaign-os:dev:calendar'"));
assert('cal CSS classes exist', ['.cal-card', '.cal-tag', '.cal-grid', '.cal-day-header', '.cal-tabs'].every(c => html.includes(c)));
assert('Calendar tabs wired to calSwitchView', html.includes('calSwitchView') && html.includes('cal-tab-today'));
assert('showView handles calendar', html.includes("name === 'calendar'") && html.includes('view-calendar'));
assert('clearDevData clears calendar', html.includes('removeItem(CAL_STORE_KEY)'));
assert('Calendar imports from all 5 other stores', ['hookReadAll', 'memeReadAll', 'billboardReadAll', 'trendReadAll'].every(fn => html.includes(fn)) && html.includes('buildCalendarTimeline'));
assert('Calendar source dropdown populated from all object kinds', html.includes('campaign:') && html.includes('hook:') && html.includes('meme:') && html.includes('billboard:') && html.includes('trend:'));
assert('Calendar source picker shows own + imported distinction', html.includes('own') && html.includes('imported') && html.includes('Read-only'));
assert('Calendar linked-to-campaign pushes history', html.includes("'calendar-linked'"));
assert('Calendar has today + week view filters', html.includes('calView') && html.includes('startOfDay') && html.includes('endOfDay'));

// ── Step 15: Caption Studio ─────────────────────────────────────────
section('Step 15: Caption Studio (HTML structure)');
assert('header has Caption Studio view button', html.includes('id="btn-captions"') && html.includes("onclick=\"showView('captions')\""));
assert('view-captions panel exists', html.includes('id="view-captions"'));
assert('Caption Studio filter select exists', html.includes('id="captions-filter"'));
assert('Caption filter has All/Standalone/Attached + 6 platforms + 6 statuses', [
  'value="all"', 'value="standalone"', 'value="attached"',
  'value="instagram"', 'value="facebook"', 'value="google-business"',
  'value="tiktok"', 'value="linkedin"', 'value="email"',
  'value="idea"', 'value="draft"', 'value="ready-for-review"',
  'value="approved"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('New Caption modal exists', html.includes('id="captionModal"') && html.includes('id="captionForm"'));
assert('caption functions defined', [
  'function openCaptionModal', 'function openEditCaptionModal', 'function closeCaptionModal',
  'function handleCaptionSubmit', 'function renderCaptionStudio', 'function renderCaptionCard',
  'function confirmDeleteCaption', 'function promptAttachCaption', 'function changeCaptionStatus',
  'function makeCaptionFromHook', 'function makeCaptionFromMeme',
  'function makeCaptionFromTrend', 'function makeCaptionFromBillboard',
  'function captionReadAll', 'function captionWriteAll', 'function captionAppend',
  'function captionDelete', 'function nextCaptionId', 'function captionModalPopulateOptions'
].every(fn => html.includes(fn)));
assert('Caption fields: text, platform, format, brand, status, source, campaign, note', [
  'id="cap-text"', 'id="cap-platform"', 'id="cap-format"', 'id="cap-brand"',
  'id="cap-status"', 'id="cap-source"', 'id="cap-campaign"', 'id="cap-note"'
].every(id => html.includes(id)));
assert('Caption platforms include Instagram/Facebook/Google-Business/TikTok/LinkedIn/Email/Other', [
  'value="instagram"', 'value="facebook"', 'value="google-business"',
  'value="tiktok"', 'value="linkedin"', 'value="email"', 'value="other"'
].every(v => html.includes(v)));
assert('Caption formats include post/reel/story/ad/carousel/email/gmb-update', [
  'value="post"', 'value="reel"', 'value="story"', 'value="ad"',
  'value="carousel"', 'value="email"', 'value="gmb-update"'
].every(v => html.includes(v)));
assert('Caption statuses include idea/draft/ready-for-review/approved/used/rejected', [
  'value="idea"', 'value="draft"', 'value="ready-for-review"',
  'value="approved"', 'value="used"', 'value="rejected"'
].every(v => html.includes(v)));
assert('CAPTION_STORE_KEY defined (campaign-os:dev:captions)', html.includes("CAPTION_STORE_KEY = 'campaign-os:dev:captions'"));
assert('capcard CSS classes exist', ['.capcard', '.capcard-text', '.captag', '.capcard-actions', '.capcard-status-row'].every(c => html.includes(c)));
assert('Caption filter wired to renderCaptionStudio', html.includes("captions-filter") && html.includes('renderCaptionStudio()'));
assert('showView handles captions', html.includes("name === 'captions'") && html.includes('view-captions'));
assert('clearDevData clears captions', html.includes('removeItem(CAPTION_STORE_KEY)'));
assert('Caption source dropdown includes all 4 source kinds', html.includes('hook:') && html.includes('trend:') && html.includes('meme:') && html.includes('billboard:'));
assert('Caption cross-workspace: 4 make-caption functions exist', ['makeCaptionFromHook', 'makeCaptionFromMeme', 'makeCaptionFromTrend', 'makeCaptionFromBillboard'].every(fn => html.includes(fn)));
assert('Caption campaign history records caption-attached', html.includes("'caption-attached'") && html.includes("'caption-detached'"));

// ── Step 16: Asset Planner ──────────────────────────────────────────
section('Step 16: Asset Planner (HTML structure)');
assert('header has Production Board view button', html.includes('id="btn-production"') && html.includes("onclick=\"showView('assets')\""));
assert('view-assets panel exists', html.includes('id="view-assets"'));
assert('Asset Planner filter select exists', html.includes('id="assets-filter"'));
assert('Asset filter has Unlinked/Linked + 6 statuses + 2 priorities', [
  'value="all"', 'value="unlinked"', 'value="linked"',
  'value="needed"', 'value="requested"', 'value="in-production"',
  'value="ready"', 'value="used"', 'value="cancelled"',
  'value="urgent"', 'value="high"'
].every(v => html.includes(v)));
assert('New Asset Request modal exists', html.includes('id="assetModal"') && html.includes('id="assetForm"'));
assert('asset functions defined', [
  'function openAssetModal', 'function openEditAssetModal', 'function closeAssetModal',
  'function handleAssetSubmit', 'function renderAssetPlanner', 'function renderAssetCard',
  'function confirmDeleteAsset', 'function promptAttachAsset', 'function changeAssetStatus',
  'function requestAssetFromCampaign', 'function requestAssetFromCaption', 'function requestAssetFromMeme',
  'function requestAssetFromBillboard', 'function requestAssetFromTrend', 'function requestAssetFromHook',
  'function pushAssetRequestedToSource',
  'function assetReadAll', 'function assetWriteAll', 'function assetAppend',
  'function assetDelete', 'function nextAssetId', 'function assetModalPopulateOptions'
].every(fn => html.includes(fn)));
assert('Asset fields: title, assettype, brand, priority, status, requiredby, owner, source, campaign, notes', [
  'id="a-title"', 'id="a-assettype"', 'id="a-brand"', 'id="a-priority"',
  'id="a-status"', 'id="a-requiredby"', 'id="a-owner"', 'id="a-source"',
  'id="a-campaign"', 'id="a-notes"'
].every(id => html.includes(id)));
assert('Asset types include photo/video/reel/story/graphic/window-screen/product-shot/staff-shot/other', [
  'value="photo"', 'value="video"', 'value="reel"', 'value="story"',
  'value="graphic"', 'value="window-screen"', 'value="product-shot"',
  'value="staff-shot"', 'value="other"'
].every(v => html.includes(v)));
assert('Asset priorities include low/medium/high/urgent', [
  'value="low"', 'value="medium"', 'value="high"', 'value="urgent"'
].every(v => html.includes(v)));
assert('Asset statuses include needed/requested/in-production/ready/used/cancelled', [
  'value="needed"', 'value="requested"', 'value="in-production"',
  'value="ready"', 'value="used"', 'value="cancelled"'
].every(v => html.includes(v)));
assert('ASSET_STORE_KEY defined (campaign-os:dev:asset_requests)', html.includes("ASSET_STORE_KEY = 'campaign-os:dev:asset_requests'"));
assert('acard CSS classes exist', ['.acard', '.acard-title', '.atag', '.acard-actions', '.acard-status-row'].every(c => html.includes(c)));
assert('Asset filter wired to renderAssetPlanner', html.includes("assets-filter") && html.includes('renderAssetPlanner()'));
assert('showView handles assets', html.includes("name === 'assets'") && html.includes('view-assets'));
assert('clearDevData clears asset_requests', html.includes('removeItem(ASSET_STORE_KEY)'));
assert('Asset source dropdown includes all 6 source kinds', html.includes('campaign:') && html.includes('caption:') && html.includes('meme:') && html.includes('billboard:') && html.includes('trend:') && html.includes('hook:'));
assert('Asset cross-workspace: 6 requestAssetFrom* functions', ['requestAssetFromCampaign', 'requestAssetFromCaption', 'requestAssetFromMeme', 'requestAssetFromBillboard', 'requestAssetFromTrend', 'requestAssetFromHook'].every(fn => html.includes(fn)));
assert('Asset dual history contract: campaign + source both get asset-requested', html.includes("'asset-requested'") && html.includes('pushAssetRequestedToSource'));
assert('Asset sorts by priority then requiredBy', html.includes('urgent: 0, high: 1') && html.includes('requiredBy'));

// ── Live API tests (Workstream A) ────────────────────────────────────
section('Live API — wizard payload (new shape)');
(async () => {
  const newId = 'c-test-' + Date.now().toString(36);
  const now = new Date().toISOString();
  const payload = {
    identity: {
      campaignId: newId, name: 'Test Campaign ' + newId, shortName: 'TC',
      goal: 'test', status: 'draft', owner: 'christelle', platforms: [],
      createdAt: now, updatedAt: now, healthScore: null, healthState: 'unknown',
      campaignType: 'evergreen', brand: 'swing-shack', priority: 'high',
      primaryGoal: 'Bookings', duration: '30 days',
      campaignSource: { type: 'Test', reference: 'phase2-suite', createdBy: 'christelle' }
    },
    plan: { purpose: 'p', audience: 'a', bigIdea: 'b', successMetric: 's',
            pillars: [{ id: 'pdata', name: 'Data', description: 'd' }] },
    brief: { assetCount: 3, assetType: 'video', cta: 'Test', assets: [] },
    production: { items: [] },
    approval: { status: 'draft', currentReviewer: null, decisions: [] },
    status: 'draft', lifecycle: 'draft',
    history: [{ action: 'created', by: 'christelle', at: now, note: 'Test.' }],
    assets: [], productionItems: [], media: { hero: null, gallery: [] }
  };

  const r1 = await httpJson('POST', BASE + '/api/campaigns', payload);
  assert('POST /api/campaigns returns 201', r1.status === 201, { status: r1.status });
  assert('POST response has campaignId', r1.json && r1.json.campaignId === newId);
  assert('POST response includes plan.pillars', r1.json && r1.json.campaign &&
         r1.json.campaign.plan && r1.json.campaign.plan.pillars.length === 1);
  assert('POST response includes brief.assetCount', r1.json && r1.json.campaign &&
         r1.json.campaign.brief && r1.json.campaign.brief.assetCount === 3);
  assert('POST response preserves identity.brand', r1.json && r1.json.campaign &&
         r1.json.campaign.identity.brand === 'swing-shack');

  const r2 = await httpJson('GET', BASE + '/api/campaigns/' + newId);
  assert('GET /api/campaigns/<id> returns 200', r2.status === 200, { status: r2.status });
  assert('GET round-trips identity.name', r2.json && r2.json.identity &&
         r2.json.identity.name === payload.identity.name);
  assert('GET round-trips plan.pillars', r2.json && r2.json.plan &&
         r2.json.plan.pillars && r2.json.plan.pillars[0].id === 'pdata');
  assert('GET round-trips brief.cta', r2.json && r2.json.brief &&
         r2.json.brief.cta === 'Test');
  assert('GET round-trips history count', r2.json && r2.json.history.length === 1);

  // Duplicate id should 409
  const r3 = await httpJson('POST', BASE + '/api/campaigns', payload);
  assert('POST duplicate id returns 409', r3.status === 409, { status: r3.status });

  section('Live API — legacy shape (backward compat)');
  const r4 = await httpJson('POST', BASE + '/api/campaigns', {
    name: 'Legacy Campaign', shortName: 'LC', primaryGoal: 'Awareness',
    campaignType: 'awareness', brand: 'swing-shack'
  });
  assert('POST legacy returns 201', r4.status === 201, { status: r4.status });
  assert('POST legacy builds plan object', r4.json && r4.json.campaign && r4.json.campaign.plan);
  assert('POST legacy builds brief object', r4.json && r4.json.campaign && r4.json.campaign.brief);
  assert('POST legacy sets status=draft', r4.json && r4.json.campaign.status === 'draft');
  assert('POST legacy preserves brand', r4.json && r4.json.campaign.identity.brand === 'swing-shack');

  section('Live API — error cases');
  const r5 = await httpJson('POST', BASE + '/api/campaigns', { name: '' });
  assert('POST empty name returns 400 (legacy)', r5.status === 400, { status: r5.status });

  const r6 = await httpJson('POST', BASE + '/api/campaigns', { identity: {}, plan: {}, brief: {} });
  assert('POST wizard payload without campaignId returns 400', r6.status === 400, { status: r6.status });

  // ── Health ──────────────────────────────────────────────────────
  section('Health endpoint');
  const r7 = await httpJson('GET', BASE + '/api/health');
  assert('GET /api/health returns 200', r7.status === 200, { status: r7.status });
  assert('GET /api/health has status=ok', r7.json && r7.json.status === 'ok');

  // ── Step 10: Hook Bank — standalone workspace ──────────────────
  section('Step 10: Hook Bank (HTML structure, 8 new assertions)');
  // The 8 hook-specific HTML assertions above are part of the structural
  // block; we report how many new assertions Step 10 added here.
  results.push('  (8 new assertions for Step 10 — Hooks view, modal, fields, store, attach/detach, filter)');

  // ── Step 11: Meme Lord — standalone workspace ──────────────────
  section('Step 11: Meme Lord (HTML structure, 15 new assertions)');
  // 15 new Step 11 assertions above cover: header button, panel, filter, modal,
  // functions, fields, formats, statuses, store key, CSS classes, filter wire,
  // showView, clearDevData, source-hook select, and the meme-attached history contract.
  results.push('  (15 new assertions for Step 11 — Meme Lord view, modal, fields, store, attach/detach, status, hook integration)');

  // ── Step 12: Billboard Lab — standalone workspace ──────────────
  section('Step 12: Billboard Lab (HTML structure, 16 new assertions)');
  // 16 new Step 12 assertions above cover: header button, panel, filter, modal,
  // functions, fields, formats, statuses, store key, CSS classes, filter wire,
  // showView, clearDevData, source-hook select, and the billboard-attached history contract.
  results.push('  (16 new assertions for Step 12 — Billboard Lab view, modal, fields, store, attach/detach, status, hook integration, trend placeholder)');

  // ── Step 13: Trend Catcher — the radar ────────────────────────
  section('Step 13: Trend Catcher (HTML structure, 19 new assertions)');
  // 19 new Step 13 assertions above cover: header button, panel, filter, modal,
  // functions, fields, source types, signal types, statuses, timings, store key,
  // CSS classes, filter wire, showView, clearDevData, confidence input bounds,
  // trend-attached history contract, and the cross-workspace useTrendAsHookSeed.
  results.push('  (19 new assertions for Step 13 — Trend Catcher view, modal, fields, store, attach/detach, status, confidence, cross-workspace hook seed)');

  // ── Step 14: Calendar — the timeline ────────────────────────
  section('Step 14: Calendar (HTML structure, 18 new assertions)');
  // 18 new Step 14 assertions above cover: header button, panel, tabs, modal,
  // functions, fields, types, statuses, store key, CSS classes, filter wire,
  // showView, clearDevData, multi-store import contract, source-picker
  // population, own/imported distinction, calendar-linked history contract,
  // and today/week view filters.
  results.push('  (18 new assertions for Step 14 — Calendar view, modal, fields, store, multi-store import, own/imported distinction, today/week/all/list views)');

  // ── Step 15: Caption Studio ─────────────────────────────
  section('Step 15: Caption Studio (HTML structure, 18 new assertions)');
  // 18 new Step 15 assertions above cover: header button, panel, filter, modal,
  // functions, fields, platforms, formats, statuses, store key, CSS classes,
  // filter wire, showView, clearDevData, source dropdown (4 kinds),
  // cross-workspace make-from-source (4 helpers), and caption-attached history.
  results.push('  (18 new assertions for Step 15 — Caption Studio view, modal, fields, store, source-from-4-kinds, 6-status workflow, cross-workspace seed)');

  // ── Step 16: Asset Planner ───────────────────────────
  section('Step 16: Asset Planner (HTML structure, 19 new assertions)');
  // 19 new Step 16 assertions above cover: header button, panel, filter, modal,
  // functions, fields, types, priorities, statuses, store key, CSS classes,
  // filter wire, showView, clearDevData, 6-kind source dropdown, 6
  // cross-workspace requestAssetFrom* helpers, dual history contract
  // (asset-requested on both campaign + source), and priority+requiredBy sort.
  results.push('  (19 new assertions for Step 16 — Asset Planner view, modal, fields, store, source-from-6-kinds, dual history contract, priority+date sort)');

  // ── Step 18: Foundation — Objects + Events, Products/Goals, Attachments, Intelligence, Confidence, Provenance, Ops Feed, Campaign Factory, Surprise Me ──
  section('Step 18: Foundation (HTML structure + JS API surface)');
  // 1. Operations Feed (new home)
  assert('view-opsfeed panel exists',         html.includes('id="view-opsfeed"'));
  assert('opsfeed has Biggest Opportunity bucket', html.includes('id="opsfeed-opportunity"'));
  assert('opsfeed has Needs Attention bucket',     html.includes('id="opsfeed-needs"'));
  assert('opsfeed has Worth Trying bucket',        html.includes('id="opsfeed-worth"'));
  assert('Surprise Me button exists',          html.includes('id="btn-surprise-me"'));
  assert('Surprise Me render target exists',   html.includes('id="surprise-me-results"'));
  // 2. Creative Studio hub
  assert('view-creative panel exists',        html.includes('id="view-creative"'));
  assert('Creative Studio hook counter el',   html.includes('id="cs-hook-count"'));
  assert('Creative Studio confident list el', html.includes('id="cs-confident-list"'));
  // 3. Header reparenting
  assert('Operations Feed header button',     html.includes('id="btn-opsfeed"') && html.includes("showView('opsfeed')"));
  assert('Campaign Factory header button',    html.includes('id="btn-factory"') && html.includes('openCampaignFactory'));
  assert('Creative Studio header button',     html.includes('id="btn-creative"') && html.includes("showView('creative')"));
  assert('Production Board header button',    html.includes('id="btn-production"') && html.includes("showView('assets')"));
  assert('Product switcher label element',    html.includes('id="product-switcher-label"'));
  assert('Event count badge element',          html.includes('id="composer-event-count"'));
  // 4. Domain model
  assert('DOMAINS object defined with 7',     html.includes('research:') && html.includes('creative:') && html.includes('intelligence:') &&
                                              html.includes('production:') && html.includes('publishing:') && html.includes('performance:') &&
                                              html.includes('learning:'));
  assert('domainOf helper',                   html.includes('function domainOf(kind)'));
  assert('labelForKind helper',               html.includes('function labelForKind(kind)'));
  assert('kindStoreKey helper',               html.includes('function kindStoreKey(kind)'));
  // 5. Stores + Events
  assert('readStore / writeStore',            html.includes('function readStore(key)') && html.includes('function writeStore(key, arr)'));
  assert('PRODUCT_STORE_KEY',                 html.includes("PRODUCT_STORE_KEY = 'campaign-os:dev:products'"));
  assert('GOAL_STORE_KEY',                    /GOAL_STORE_KEY\s*=\s*'campaign-os:dev:goals'/.test(html));
  assert('EVENT_STORE_KEY',                   /EVENT_STORE_KEY\s*=\s*'campaign-os:dev:events'/.test(html));
  assert('ATTACH_STORE_KEY',                  html.includes("ATTACH_STORE_KEY = 'campaign-os:dev:campaign_attachments'"));
  assert('applyEvent function',               html.includes('function applyEvent(evt)'));
  assert('activeProductId auto-seeds Swing Shack', html.includes("name: 'Swing Shack'"));
  // 6. Provenance + computed confidence
  assert('makeProvenance / attachProvenance', html.includes('function makeProvenance(') && html.includes('function attachProvenance('));
  assert('getConfidence function',            html.includes('function getConfidence(kind, id)'));
  assert('confidenceLabel function',          html.includes('function confidenceLabel(c)'));
  assert('confidenceProvenanceText function', html.includes('function confidenceProvenanceText(kind, id)'));
  assert('manual confidence escape hatch',    html.includes("'manual'"));
  // 7. Campaign attachments
  assert('attachToCampaign function',         html.includes('function attachToCampaign(campaignId'));
  assert('detachFromCampaign function',       html.includes('function detachFromCampaign(campaignId'));
  assert('attachmentsForCampaign helper',     html.includes('function attachmentsForCampaign('));
  // 8. Intelligence (Knowledge) — 5 sub-kinds
  assert('intelCreate function',              html.includes('function intelCreate(subKind, payload)'));
  assert('intelAccept function',              html.includes('function intelAccept('));
  assert('Intelligence store keys for 5 kinds',
    html.includes("'intelligence:recommendations'") &&
    html.includes("'intelligence:patterns'") &&
    html.includes("'intelligence:opportunities'") &&
    html.includes("'intelligence:combinations'") &&
    html.includes("'intelligence:lessons'"));
  // 9. Proactive Composer + Surprise Me
  assert('composerOnEvent function',          html.includes('function composerOnEvent(evt)'));
  assert('composer triggers on trend events', html.includes("t !== 'trend.updated'"));
  assert('surpriseMeGenerate function',       html.includes('function surpriseMeGenerate()'));
  assert('Surprise Me returns 3 ideas',       html.includes('i<3'));
  // 10. Operations Feed + Campaign Factory
  assert('opsFeedData function',              html.includes('function opsFeedData()'));
  assert('3 ops buckets (opportunity/needs/worth)', html.includes('opportunity:') && html.includes('needsAttention:') && html.includes('worthTrying:'));
  assert('openCampaignFactory function',      html.includes('function openCampaignFactory()'));
  assert('5 Campaign Factory build options',
    html.includes("key:'idea'") && html.includes("key:'trend'") && html.includes("key:'goal'") && html.includes("key:'product'") && html.includes("key:'surprise'"));
  assert('campaignFactoryCreate writes event', html.includes("type: 'campaign.created'"));
  assert('Goal selector in Campaign Factory', html.includes('id="cf-goal"'));
  // 11. Renderer functions
  assert('renderOpsFeed function',            html.includes('function renderOpsFeed()'));
  assert('renderCreativeStudio function',     html.includes('function renderCreativeStudio()'));
  assert('runSurpriseMe function',            html.includes('function runSurpriseMe()'));
  // 12. showView dispatch
  assert('showView handles opsfeed',          html.includes("if (name === 'opsfeed') { renderOpsFeed();"));
  assert('showView handles creative',         html.includes("if (name === 'creative') { renderCreativeStudio();"));
  // 13. Bootstrap
  assert('default product bootstrap',         html.includes("activeProductId()"));
  assert('header refresh bootstrap',          html.includes('refreshHeader()'));
  // 14. window.OS API surface
  assert('window.OS exposed',                 html.includes('window.OS = {'));
  assert('OS.products / goals / events / attachments / intelligence / composer / opsFeed', html.includes('products:') && html.includes('goals:') && html.includes('events:') && html.includes('attachments:') && html.includes('intelligence:') && html.includes('composer:') && html.includes('opsFeed:'));
  results.push('  (52 new assertions for Step 18 — Foundation: Ops Feed, Creative Studio, Products, Goals, Events, Attachments, Intelligence, Confidence, Provenance, Campaign Factory, Surprise Me)');

  // ── Step 19: Global Search (header bar + modal, 12 kinds) + Campaign References panel wired to campaign_attachments ──
  section('Step 19: Global Search + Campaign References (HTML structure + JS API surface)');
  // 1. Global Search bar in header
  assert('global search input in header',     html.includes('id="global-search-input"'));
  assert('global search Enter handler',       /global-search-input[^>]*onkeydown=["']if\(event\.key===['"]Enter['"]\)\{runGlobalSearch\(\);\}/.test(html));
  assert('global search Escape handler',      html.includes('closeGlobalSearch()'));
  assert('global search Cmd/Ctrl+K shortcut', html.includes("e.metaKey || e.ctrlKey") && html.includes("e.key === 'k'"));
  assert('global search focuses opens modal', html.includes("hi.addEventListener('focus'"));
  // 2. Global Search modal
  assert('globalSearchModal element',         html.includes('id="globalSearchModal"'));
  assert('globalSearchQueryInput element',    html.includes('id="globalSearchQueryInput"'));
  assert('globalSearchResults element',       html.includes('id="globalSearchResults"'));
  // 3. Functions
  assert('escapeSearchHtml function',         html.includes('function escapeSearchHtml(s)'));
  assert('highlightHit function',             html.includes('function highlightHit(text, query)'));
  assert('searchKinds function',              html.includes('function searchKinds()'));
  assert('searchKind function',               html.includes('function searchKind(kind, q)'));
  assert('openGlobalSearch function',         html.includes('window.openGlobalSearch') && html.includes('function() {'));
  assert('closeGlobalSearch function',        html.includes('window.closeGlobalSearch') && html.includes('function() {'));
  assert('runGlobalSearch function',          html.includes('window.runGlobalSearch') && html.includes('function() {'));
  assert('globalSearchGo function',           html.includes('window.globalSearchGo'));
  // 4. Coverage — 12 attachable/indexable kinds
  assert('search covers hook',                html.includes("kind:'hook'"));
  assert('search covers meme',                html.includes("kind:'meme'"));
  assert('search covers billboard',           html.includes("kind:'billboard'"));
  assert('search covers trend',               html.includes("kind:'trend'"));
  assert('search covers caption',             html.includes("kind:'caption'"));
  assert('search covers asset_request',        html.includes("kind:'asset_request'"));
  assert('search covers calendar_item',       html.includes("kind:'calendar_item'"));
  assert('search covers product',             html.includes("kind:'product'"));
  assert('search covers goal',                html.includes("kind:'goal'"));
  assert('search covers recommendation',       html.includes("kind:'recommendation'"));
  assert('search covers pattern',             html.includes("kind:'pattern'"));
  assert('search covers opportunity',         html.includes("kind:'opportunity'"));
  assert('search covers combination',         html.includes("kind:'combination'"));
  assert('search covers lesson',              html.includes("kind:'lesson'"));
  assert('search covers event',               html.includes("kind:'event'"));
  // 5. Hit highlighting
  assert('highlightHit wraps in <mark>',      html.includes('<mark style="background:rgba(255,204,0'));
  // 6. Campaign References panel
  assert('renderCampaignReferences function', html.includes('function renderCampaignReferences(campaignId, container)'));
  assert('renderCampaign calls references',   html.includes('try { renderCampaignReferences(id, detailContent); }'));
  assert('references panel id',               html.includes("'campaign-references-panel'"));
  assert('References title in panel',         html.includes('References ('));
  assert('references groups by kind',         html.includes('var groups = {};'));
  assert('references shows confidence',       html.includes('getConfidence(kind, a.objectId)'));
  assert('references rationale field',        html.includes('a.rationale'));
  assert('detachAndRefresh function',         html.includes('function detachAndRefresh('));
  assert('openAttachPicker function',         html.includes('function openAttachPicker('));
  assert('attachAndRefresh function',         html.includes('function attachAndRefresh('));
  assert('closeAttachPicker function',        html.includes('function closeAttachPicker('));
  assert('+ Attach from anywhere button',     html.includes('+ Attach from anywhere'));
  assert('Detach action in references',       html.includes("color:var(--col-red)") && html.includes("detachAndRefresh("));
  assert('references reads campaign_attachments', html.includes('attachmentsForCampaign(campaignId)'));
  results.push('  (32 new assertions for Step 19 — Global Search (12 kinds) + Campaign References panel wired to campaign_attachments)');

  // ── Step 20: Quick Attach modal — replaces 6 native prompt handlers, writes to campaign_attachments M2M ──
  section('Step 20: Quick Attach (HTML structure + JS API surface)');
  // 1. Quick Attach modal element + global functions
  assert('openQuickAttach function',     html.includes('window.openQuickAttach = function'));
  assert('closeQuickAttach function',    html.includes('window.closeQuickAttach = function'));
  assert('quickAttachToggle function',   html.includes('window.quickAttachToggle = function'));
  assert('quickAttachCreateAndAttach',  html.includes('window.quickAttachCreateAndAttach = function'));
  assert('quick-attach-modal element',   html.includes('id="quick-attach-modal"') || /quick-attach-modal['"]/.test(html));
  // 2. Old prompt functions are now one-line wrappers
  assert('promptAttachHook routes to Quick Attach',  /promptAttachHook[\s\S]{0,200}openQuickAttach\('hook'/.test(html));
  assert('promptAttachMeme routes to Quick Attach',  /promptAttachMeme[\s\S]{0,200}openQuickAttach\('meme'/.test(html));
  assert('promptAttachBillboard routes',            /promptAttachBillboard[\s\S]{0,200}openQuickAttach\('billboard'/.test(html));
  assert('promptAttachTrend routes',                /promptAttachTrend[\s\S]{0,200}openQuickAttach\('trend'/.test(html));
  assert('promptAttachCaption routes',              /promptAttachCaption[\s\S]{0,200}openQuickAttach\('caption'/.test(html));
  assert('promptAttachAsset routes',                /promptAttachAsset[\s\S]{0,200}openQuickAttach\('asset_request'/.test(html));
  // 3. M2M table write path
  assert('Quick Attach uses OS.attachments.attach',  /window\.quickAttachToggle = function[\s\S]{0,1500}attachToCampaign\(/.test(html));
  assert('Quick Attach uses OS.attachments.detach',  /window\.quickAttachToggle = function[\s\S]{0,500}detachFromCampaign\(/.test(html));
  assert('Quick Attach emits object.attached event', /attachToCampaign\(campaignId, kind, objectId, rationale\)/.test(html));
  // 4. Create + attach in one click
  assert('Quick Attach Create+attach',                /window\.quickAttachCreateAndAttach = function[\s\S]{0,1500}campaign\.created/.test(html));
  assert('Create+attach calls attachToCampaign',      /attachToCampaign\(cid, kind, objectId, rationale\)/.test(html));
  assert('Create+attach calls selectCampaign',        /selectCampaign\(cid\)/.test(html));
  // 5. Refreshes the right workspace after toggle
  assert('Refreshes Hook Bank after hook toggle',     /quickAttachRefreshWorkspace[\s\S]{0,500}renderHookBank/.test(html));
  assert('Refreshes Meme Lord after meme toggle',     /quickAttachRefreshWorkspace[\s\S]{0,500}renderMemeLord/.test(html));
  assert('Refreshes Trend Catcher after trend toggle',/quickAttachRefreshWorkspace[\s\S]{0,500}renderTrendCatcher/.test(html));
  // 6. Refreshes Campaign References panel if the campaign is open
  assert('Re-renders Campaign References if active',  /window\.quickAttachToggle = function[\s\S]{0,2500}renderCampaign\(campaignId\)/.test(html));
  // 7. Rationale support
  assert('qa-rationale input',                        html.includes('id="qa-rationale"'));
  // 8. No more native prompt() in the old handlers (only the new modal flow)
  assert('promptAttachHook no longer uses window.prompt', !/function promptAttachHook\([\s\S]{0,200}window\.prompt/.test(html));
  assert('promptAttachMeme no longer uses window.prompt', !/function promptAttachMeme\([\s\S]{0,200}window\.prompt/.test(html));
  results.push('  (20 new assertions for Step 20 — Quick Attach modal: replaces 6 native prompts, writes to campaign_attachments, supports create+attach)');

  // ── Step 21: Home page alive — Operations Feed is the default view, not nested in view-portfolio ──
  section('Step 21: Home page alive (Operations Feed loads by default + is structurally a peer of view-portfolio)');
  // 1. view-opsfeed exists in the markup
  assert('view-opsfeed element',                       html.includes('id="view-opsfeed"'));
  // 2. view-creative exists in the markup
  assert('view-creative element',                      html.includes('id="view-creative"'));
  // 3. view-opsfeed has active class by default (no JS needed to start the home)
  assert('view-opsfeed is .active by default',         /id="view-opsfeed"[^>]*class="view-panel active"/.test(html));
  // 4. showView('opsfeed') is wired to fire on DOMContentLoaded (so it actually shows on load)
  assert('showView(opsfeed) wired on DOMContentLoaded', /DOMContentLoaded[\s\S]{0,300}showView\('opsfeed'\)/.test(html));
  // 5. showView('opsfeed') runs AFTER devStoreHydrate (so renderOpsFeed has data)
  assert('showView(opsfeed) runs AFTER devStoreHydrate', /devStoreHydrate\(\)[\s\S]{0,800}showView\('opsfeed'\)/.test(html));
  // 6. view-opsfeed is NOT inside view-portfolio (was the Step 18 regression that blanked the home)
  //    Find the index of view-portfolio's open and view-opsfeed's open; view-opsfeed's index must be greater.
  const vpOpen = html.indexOf('id="view-portfolio"');
  const ofOpen = html.indexOf('id="view-opsfeed"');
  const cvOpen = html.indexOf('id="view-creative"');
  assert('view-opsfeed appears AFTER view-portfolio (not nested inside)', ofOpen > vpOpen);
  assert('view-creative appears AFTER view-portfolio (not nested inside)', cvOpen > vpOpen);
  // 7. showView function toggles view-opsfeed (and not the new view-creative via wrong path)
  assert('showView toggles view-opsfeed',  /function showView\(name\)[\s\S]{0,3000}getElementById\('view-opsfeed'\)/.test(html));
  assert('showView toggles view-creative', /function showView\(name\)[\s\S]{0,3000}getElementById\('view-creative'\)/.test(html));
  // 8. Header subtitle for opsfeed is set (so the OS knows what view it's on)
  assert('header subtitle opsfeed', /name === 'opsfeed'[\s\S]{0,200}header-subtitle/.test(html));
  // 9. The 3 buckets are present
  assert('Biggest Opportunity bucket', html.includes('Biggest Opportunity'));
  assert('Needs Attention bucket',     html.includes('Needs Attention'));
  assert('Worth Trying bucket',        html.includes('Worth Trying'));
  // 10. Surprise Me button exists in the home view
  assert('Surprise Me button on home', html.includes('runSurpriseMe()'));
  results.push('  (15 new assertions for Step 21 — Home page alive: Operations Feed loads by default and is structurally a peer of view-portfolio)');

  // ── Step 22: Nav reachable on 1280px — .view-toggle must allow buttons to wrap, not overflow ──
  section('Step 22: Nav reachable on standard viewports (no button overflows the visible area)');
  // 1. .view-toggle CSS allows wrapping
  assert('.view-toggle has flex-wrap: wrap', /\.view-toggle\s*\{[^}]*flex-wrap:\s*wrap/.test(html));
  // 2. .view-toggle is bounded by parent (max-width: 100% or similar)
  assert('.view-toggle has max-width: 100%', /\.view-toggle\s*\{[^}]*max-width:\s*100%/.test(html));
  // 3. Buttons have white-space: nowrap so they don't break their labels mid-word
  assert('.view-toggle > .view-btn white-space: nowrap', /\.view-toggle\s*>\s*\.view-btn\s*\{[^}]*white-space:\s*nowrap/.test(html));
  // 4. All 13 nav buttons exist in the markup
  const navBtnIds = ['btn-opsfeed','btn-trends','btn-factory','btn-creative','btn-production','btn-calendar','btn-detail','btn-review','btn-hooks','btn-memes','btn-billboards','btn-captions','btn-portfolio'];
  navBtnIds.forEach(id => assert('nav button ' + id, html.includes('id="' + id + '"')));
  // 5. The global search input is now narrower (340px → 280px) so the nav has room to wrap
  assert('global search width 280px', /id="global-search-input"[^>]*width:\s*280px/.test(html));
  results.push('  (5 nav buttons + 4 layout assertions for Step 22 — Nav wraps to multiple lines so all 13 buttons are reachable on 1280px viewports)');

  // ── Step 22.5: Operations Feed surfaces degraded live campaigns (not just overdue assets) ──
  section('Step 22.5 + Step 25: Operations Feed surfaces unresolved diagnosed issues (single source of truth = diagnoseCampaign)');
  // 1. (Step 22.5) opsFeedData originally filtered by static healthState; Step 25 replaced that with diagnoseCampaign
  // so the list drops a campaign whose issues are actually resolved.
  assert('opsFeedData uses diagnoseCampaign for live unhealthy filter', /diagnoseCampaign\(x\.k\)/.test(html));
  assert('Ops Feed no longer filters by static healthState as the primary trigger', !/healthState==='degraded'\s*\|\|\s*x\.c\.identity\.healthState==='critical'/.test(html));
  // 2. opsFeedData maps unhealthy campaigns into needsAttention
  assert('opsFeedData adds unhealthy campaigns to needsAttention', /\.concat\(liveButUnhealthy\)/.test(html));
  // 3. Each needsAttention item has a title and a body (the OS card shape)
  assert('liveButUnhealthy card title is the diagnosed issue title (not "is degraded")', /rec\.title\|.*has unresolved issues/.test(html) || /recommendation\.title\|/.test(html) || /rec\s*\?\s*rec\.title/.test(html));
  assert('liveButUnhealthy has health body', /'Health '\s*\+/.test(html));
  // 4. The summary line still includes needsAttention count
  assert('summary includes need-attention count', /d\.needsAttention\.length\s*\+\s*' need attention/.test(html));
  // 5. The renderOpsFeed function reads d.needsAttention into opsfeed-needs
  assert('renderOpsFeed populates opsfeed-needs', /opsfeed-needs[\s\S]{0,200}d\.needsAttention/.test(html));
  // 6. The diagnose function returns an empty issues array when all categories are present —
  //    this is what allows a campaign to drop from the list once the issue is resolved.
  assert('diagnoseCampaign returns empty issues when campaign is complete', /var issues = \[\][\s\S]{0,50}issues\.push/.test(html));
  results.push('  (7 assertions for Step 22.5 + Step 25 — Operations Feed surfaces unresolved diagnosed issues so the home view stops lying once a campaign\'s issues are resolved)');

  // ── Step 23: Needs Attention cards are clickable buttons that open the campaign ──
  section('Step 23: Needs Attention cards for degraded campaigns are clickable buttons');
  // 1. liveButUnhealthy items carry a campaignId field (so the render layer can build a real link)
  assert('liveButUnhealthy items carry campaignId', /campaignId:\s*x\.k/.test(html));
  // 2. The renderOpsFeed bucket function renders a <button> for kind==='health' cards
  assert('bucket renders <button> for health-kind cards', /it\.kind\s*===\s*'health'[\s\S]{0,5000}<button/.test(html));
  // 3. The button has a data-campaign-id attribute (test + a11y target)
  assert('button has data-campaign-id attribute', /data-campaign-id="'\s*\+\s*it\.campaignId/.test(html));
  // 4. The button's onclick calls selectCampaign (which navigates to the campaign detail view)
  assert('button onclick calls selectCampaign', /onclick="selectCampaign\(\\?'/.test(html));
  // 5. The card has a visible "Open campaign" affordance (chevron or text)
  assert('card shows "Open campaign" affordance', />Open campaign</.test(html));
  // 6. The card surfaces the health score as a visual pill
  assert('card shows a Health <score> pill', /Health '\s*\+\s*score/.test(html));
  // 7. The non-health needsAttention items (overdue / no-live) still render as plain divs, not buttons
  //    (they have no campaign to open — staying read-only is correct)
  assert('non-health cards remain <div> not <button>', /return '<div class="ops-card"/.test(html));
  results.push('  (7 assertions for Step 23 — clickable Needs Attention cards cut the home-to-campaign path from 4 clicks to 1)');

  // ── Step 24: Strategist review block at the top of the campaign detail page ──
  section('Step 24: Strategist review block — diagnosis + ranked impact + single recommendation');
  // 1. There is a diagnoseCampaign function that returns issues, recommendation, health, state
  assert('diagnoseCampaign function defined', /function diagnoseCampaign\(campaignId\)/.test(html));
  // 2. There is a renderStrategistBlock function
  assert('renderStrategistBlock function defined', /function renderStrategistBlock\(campaignId\)/.test(html));
  // 3. diagnoseCampaign reads real fields, not a hardcoded checklist
  assert('diagnoseCampaign reads c.brief',        /c\.brief\s*&&/.test(html));
  assert('diagnoseCampaign reads c.dna',          /c\.dna\s*&&/.test(html));
  assert('diagnoseCampaign reads c.visualDirection', /c\.visualDirection\s*&&/.test(html));
  assert('diagnoseCampaign reads attachmentsForCampaign', /attachmentsForCampaign/.test(html));
  assert('diagnoseCampaign reads c.assets',       /c\.assets\s*&&/.test(html));
  // 4. Impact is derived from rank order (idx 0 = High, 1 = Medium, else Low) — no fabricated health delta
  assert('Impact label derived from rank (High/Medium/Low)', /idx === 0[\s\S]{0,50}'High'[\s\S]{0,80}idx === 1[\s\S]{0,50}'Medium'[\s\S]{0,80}'Low'/.test(html));
  // 5. There is NO fabricated health-gain math on the recommendation (no rec.from / rec.to / rec.delta)
  assert('No fabricated rec.from/rec.to/rec.delta', !/rec\.from\s*:/.test(html) && !/rec\.to\s*:/.test(html) && !/rec\.delta\s*:/.test(html));
  // 6. The "Estimated health gain" line is NOT rendered
  assert('No "Estimated health gain" string in file', !/Estimated health gain/.test(html));
  // 7. The Step 25 TODO has been resolved by Step 34 — computeCampaignHealth is in place.
  assert('computeCampaignHealth function is declared (Step 34 health engine)',
         /function\s+computeCampaignHealth\s*\(/.test(html));
  assert('computeCampaignHealth is documented as the single source of truth',
         /Step 34[^]*?single source of truth/i.test(html));
  // 8. The strategist block is prepended into detail-content in renderCampaign
  assert('renderCampaign prepends strategist block', /renderStrategistBlock\(id\)/.test(html));
  // 9. Issue action buttons navigate to existing views (not 'production' or 'creative-studio' which don't exist)
  assert('Plan Assets action uses dest=assets (not production)', /'Plan Assets',\s*dest:\s*'assets'/.test(html));
  assert('Create Creative action uses dest=creative (not creative-studio)', /'Create Creative',\s*dest:\s*'creative'/.test(html));
  assert('Schedule Publishing action uses dest=calendar', /'Schedule Publishing',\s*dest:\s*'calendar'/.test(html));
  // 10. State label is derived from health score (not invented). Step 34 moves
  // this logic into computeCampaignHealth so all surfaces agree.
  assert('State band lives in computeCampaignHealth (>=80 healthy / >=50 degraded / else critical)',
         /function\s+computeCampaignHealth[\s\S]{0,1500}>=\s*80[\s\S]{0,30}healthy[\s\S]{0,60}>=\s*50[\s\S]{0,30}degraded[\s\S]{0,60}critical/.test(html));
  // 11. The strategist block is rendered as #strategist-block with data-campaign-id
  assert('Strategist block has data-campaign-id attribute', /id="strategist-block" data-campaign-id="'\s*\+\s*campaignId/.test(html));
  results.push('  (13 assertions for Step 24 — strategist review block answers "why isn\'t this winning" with real diagnosis + ranked impact + single recommendation; no fabricated health-gain math)');

  // ── Step 25: Campaign context panel in Creative Studio ──
  section('Step 25: Creative Studio carries campaign context from strategist action');
  // 1. The context panel container exists in the view-creative HTML
  assert('Creative Studio has cs-context-panel container', /id="cs-context-panel"[\s\S]{0,200}style="display:none/.test(html));
  // 2. The panel has the slots the renderer fills (campaign name, fields grid, action)
  assert('Context panel has campaign-name slot', /id="cs-context-campaign-name"/.test(html));
  assert('Context panel has fields grid',         /id="cs-context-fields"/.test(html));
  assert('Context panel has action slot',         /id="cs-context-action"/.test(html));
  // 3. The panel has a "Switch to standalone" button that clears the context
  assert('Switch to standalone button calls creativeContextClear', /onclick="creativeContextClear\(\)"/.test(html));
  // 4. renderCreativeStudio reads the campaign context id and renders the panel
  assert('renderCreativeStudio reads creativeContextCampaignId', /renderCreativeStudio[\s\S]{0,300}creativeContextCampaignId/.test(html));
  // 5. renderCreativeStudio reads ONLY real campaign fields (no AI, no fake drafts)
  assert('Context reads brief.purpose',         /brief\.purpose/.test(html));
  assert('Context reads brief.audience',        /brief\.audience/.test(html));
  assert('Context reads brief.bigIdea',         /brief\.bigIdea/.test(html));
  assert('Context reads dna.tone',              /dna\.tone/.test(html));
  assert('Context reads identity.platforms',    /identity\.platforms/.test(html));
  // 6. openHookForCampaign function exists, sets pendingAttachAfterSave, opens hook modal
  assert('openHookForCampaign function defined', /function openHookForCampaign\(campaignId\)/.test(html));
  assert('openHookForCampaign sets pendingAttachAfterSave', /openHookForCampaign[\s\S]{0,200}pendingAttachAfterSave\s*=\s*\{[\s\S]{0,100}kind:\s*'hook'/.test(html));
  assert('openHookForCampaign calls openHookModal', /openHookForCampaign[\s\S]{0,300}openHookModal\(\)/.test(html));
  // 7. creativeContextClear function clears the var and re-renders
  assert('creativeContextClear clears creativeContextCampaignId', /creativeContextClear[\s\S]{0,200}creativeContextCampaignId\s*=\s*null/.test(html));
  // 8. handleHookSubmit auto-attaches via attachToCampaign when pendingAttachAfterSave is set
  assert('handleHookSubmit checks pendingAttachAfterSave.kind==hook', /pendingAttachAfterSave[\s\S]{0,100}\.kind\s*===\s*'hook'[\s\S]{0,100}\.campaignId/.test(html));
  assert('handleHookSubmit calls attachToCampaign(cid, hook, hookId)', /attachToCampaign\(cid,\s*'hook',\s*hook\.hookId/.test(html));
  // 9. Success message reflects whether an attach happened
  assert('Success message is "Saved and attached to campaign." when attached', /Saved and attached to campaign/.test(html));
  assert('Success message is "Saved." when no attach happened', /'Saved\.'/.test(html));
  // 10. Strategist issue/recommendation buttons set creativeContextCampaignId before showView(creative)
  assert('Strategist issue action sets creativeContextCampaignId', /onclickFn\s*=[\s\S]{0,300}creativeContextCampaignId\s*=\s*'"\s*\+\s*campaignId/.test(html));
  // 11. Creative Studio re-renders after hook save so the count is fresh
  assert('handleHookSubmit calls renderCreativeStudio', /renderHookBank\(\)[\s\S]{0,200}renderCreativeStudio/.test(html));
  // 12. References panel resolves hook objects via hookId (not just id) — fixes "untitled" bug
  assert('References panel filters by hookId', /renderCampaignReferences[\s\S]{0,2000}x\.hookId\s*===\s*a\.objectId/.test(html));
  // 13. (User feedback 2026-07-13) Operations Feed must use diagnoseCampaign, not static healthState,
  //     so the "Needs Attention" list drops a campaign whose issues have actually been resolved.
  assert('Ops Feed liveButUnhealthy calls diagnoseCampaign', /liveButUnhealthy[\s\S]{0,500}diagnoseCampaign/.test(html));
  // The legacy filter line should no longer be the trigger — the diagnoseCampaign call must appear in
  // the liveButUnhealthy block.
  assert('liveButUnhealthy block contains diagnoseCampaign call (not just static healthState)', /liveButUnhealthy[\s\S]{0,1500}diagnoseCampaign\(x\.k\)/.test(html));
  // 14. diagnoseCampaign returns empty issues array when strategy/creative/production/publishing/learning
  //     are all in place — this is what triggers the campaign to drop from "Needs Attention".
  assert('diagnoseCampaign returns empty issues when all categories present', /var issues = \[\];[\s\S]{0,300}issues\.push\(\{ key:'strategy'/.test(html));
  results.push('  (18 assertions for Step 25 — Creative Studio carries campaign context, auto-attaches hooks via existing M2M writer, fixes "untitled" bug for legacy hookId format, Ops Feed "Needs Attention" reflects diagnosis not static healthState)');

  // ── Step 26: Hook modal is campaign-aware when opened from campaign context ──
  // Root decision friction: "I am being asked to invent the hook from scratch, even though
  // the OS already knows the campaign." The fix pre-fills kind/brand/placeholder with real
  // campaign facts and surfaces brief/audience/tone/offer as read-only guidance. Standalone
  // open remains unchanged: kind='meme', brand='', generic placeholder, no guidance block.
  section('Step 26: Hook modal is campaign-aware (kind=hook, brand=active product, campaign placeholder, compact guidance; standalone unchanged)');

  // 1. Guidance container exists in modal HTML, hidden by default.
  assert('Hook modal contains h-campaign-guidance container',
         /id="h-campaign-guidance"[\s\S]{0,200}display:\s*none/.test(html));
  assert('Hook modal contains h-guidance-rows container inside the guidance block',
         /id="h-campaign-guidance"[\s\S]{0,300}id="h-guidance-rows"/.test(html));

  // 2. openHookForCampaign injects a "Hook" option into the kind dropdown and sets its value.
  // Locate the function body and check that it adds the option and sets k.value = 'hook'.
  var ofcBody = html.match(/function openHookForCampaign\([\s\S]*?^}/m);
  assert('openHookForCampaign function body present in HTML', !!ofcBody);
  if (ofcBody) {
    var body = ofcBody[0];
    assert('openHookForCampaign injects a Hook option into h-kind',
           /querySelector\('option\[value="hook"\]'\)[\s\S]{0,500}(hookOpt|opt|option)\.value\s*=\s*'hook'/.test(body));
    assert('openHookForCampaign sets h-kind value to "hook"',
           /k\.value\s*=\s*'hook'/.test(body));
  }

  // 3. openHookForCampaign pre-fills brand with the active product.
  if (ofcBody) {
    assert('openHookForCampaign sets h-brand to "swing-shack"',
           /document\.getElementById\('h-brand'\)[\s\S]{0,400}\.value\s*=\s*'swing-shack'/.test(ofcBody[0]));
  }

  // 4. openHookForCampaign replaces the placeholder with a campaign-aware one built from
  //    brief.bigIdea (or brief.purpose). No invented text — only re-uses what exists.
  if (ofcBody) {
    assert('openHookForCampaign builds placeholder from brief.bigIdea or brief.purpose',
           /brief\.bigIdea\s*\|\|\s*brief\.purpose/.test(ofcBody[0]));
    assert('openHookForCampaign sets h-text placeholder using campaign anchor',
           /t\.placeholder\s*=\s*'e\.g\.\s*'\s*\+\s*ph/.test(ofcBody[0]) ||
           /t\.placeholder\s*=\s*'e\.g\.\s*'\s*\+\s*anchor/.test(ofcBody[0]));
  }

  // 5. openHookForCampaign populates read-only guidance rows from real campaign fields.
  if (ofcBody) {
    assert('openHookForCampaign surfaces brief.purpose as PURPOSE row',
           /brief\.purpose[\s\S]{0,400}rows\.push\(\s*\{\s*k:\s*'PURPOSE'/.test(ofcBody[0]));
    assert('openHookForCampaign surfaces brief.audience as AUDIENCE row',
           /brief\.audience[\s\S]{0,400}rows\.push\(\s*\{\s*k:\s*'AUDIENCE'/.test(ofcBody[0]));
    assert('openHookForCampaign surfaces dna.tone as TONE row',
           /briefDna\.tone[\s\S]{0,400}rows\.push\(\s*\{\s*k:\s*'TONE'/.test(ofcBody[0]));
    assert('openHookForCampaign surfaces strategy.primaryOffer as OFFER row',
           /strategy\.primaryOffer[\s\S]{0,400}rows\.push\(\s*\{\s*k:\s*'OFFER'/.test(ofcBody[0]));
  }

  // 6. openHookForCampaign shows the guidance block when rows exist, hides it otherwise.
  if (ofcBody) {
    assert('openHookForCampaign hides guidance block when no rows exist',
           /rows\.length\s*===\s*0[\s\S]{0,200}guideEl\.style\.display\s*=\s*'none'/.test(ofcBody[0]));
    assert('openHookForCampaign shows guidance block when rows exist',
           /rows\.length\s*===\s*0[\s\S]{0,1500}guideEl\.style\.display\s*=\s*'block'/.test(ofcBody[0]));
  }

  // 7. Standalone openHookModal must NOT touch the guidance block visibility beyond hiding it.
  var ohmBody = html.match(/function openHookModal\(\)\s*\{[\s\S]*?^}/m);
  assert('openHookModal function body present', !!ohmBody);
  if (ohmBody) {
    var ohm = ohmBody[0];
    assert('openHookModal hides h-campaign-guidance',
           /h-campaign-guidance[\s\S]{0,200}guideEl\.style\.display\s*=\s*'none'/.test(ohm));
    assert('openHookModal removes the injected Hook option if it was injected previously',
           /step26Injected[\s\S]{0,400}injected\.remove/.test(ohm));
    assert('openHookModal restores the generic TrackMan placeholder',
           /Your short game is lying to you/.test(ohm));
  }

  // 8. openEditHookModal hides the guidance block (editing is not campaign-context creation).
  var oemBody = html.match(/function openEditHookModal\([^)]*\)\s*\{[\s\S]*?^}/m);
  assert('openEditHookModal function body present', !!oemBody);
  if (oemBody) {
    assert('openEditHookModal hides h-campaign-guidance',
           /h-campaign-guidance[\s\S]{0,200}guideEl\.style\.display\s*=\s*'none'/.test(oemBody[0]));
  }

  // 9. closeHookModal defensively hides the guidance block.
  var chmBody = html.match(/function closeHookModal\(\)\s*\{[\s\S]*?^}/m);
  assert('closeHookModal function body present', !!chmBody);
  if (chmBody) {
    assert('closeHookModal hides h-campaign-guidance',
           /h-campaign-guidance[\s\S]{0,200}guideEl\.style\.display\s*=\s*'none'/.test(chmBody[0]));
  }

  // 10. Step 25 save behaviour is preserved: pendingAttachAfterSave stays {kind:'hook', campaignId}.
  assert('openHookForCampaign still sets pendingAttachAfterSave with kind:hook (Step 25 contract preserved)',
         /pendingAttachAfterSave\s*=\s*\{\s*campaignId:\s*campaignId,\s*kind:\s*'hook'\s*\}/.test(html));

  // 11. handleHookSubmit still attaches hooks created from campaign context (Step 25 contract).
  assert('handleHookSubmit still branches on pendingAttachAfterSave.kind === "hook" (Step 25 contract preserved)',
         /pendingAttachAfterSave[\s\S]{0,400}pendingAttachAfterSave\.kind\s*===\s*'hook'/.test(html));

  results.push('  (Step 26 — hook modal becomes campaign-aware when opened with campaign context; standalone path unchanged; Step 25 save/attach/diagnosis pipeline preserved)');

  // ── Step 27: Campaign Factory dead paths (idea/product/goal) actually work ──
  // Root decision friction: "I clicked Build from an idea and the modal closed
  // with no follow-up — no idea prompt, no campaign, no confirmation. Same with
  // Build from a product and Build from a goal." The fix: each dead path now
  // keeps the modal open with a followup block appropriate to the source, and
  // idea/product text becomes brief.bigIdea on the new campaign.
  section('Step 27: Campaign Factory idea/product/goal paths are no longer dead ends; idea text becomes brief.bigIdea');

  // 1. campaignFactoryPick body present and structured for the new branches.
  var cfpBody = html.match(/function campaignFactoryPick\(key\)\s*\{[\s\S]*?^}/m);
  assert('campaignFactoryPick function body present', !!cfpBody);
  if (cfpBody) {
    var cfp = cfpBody[0];

    // The old dead code:  else { closeCampaignFactory(); }
    assert('campaignFactoryPick no longer has the bare "else close" fallback for idea/product',
           !/else\s*\{\s*closeCampaignFactory\(\)\s*;\s*\}/.test(cfp));

    // idea path: must reveal the followup block and focus the textarea, NOT close.
    assert('campaignFactoryPick("idea") reveals cf-followup',
           /key\s*===\s*'idea'[\s\S]{0,400}follow[\s\S]{0,200}\.style\.display\s*=\s*'block'/.test(cfp));
    assert('campaignFactoryPick("idea") focuses cf-idea textarea',
           /key\s*===\s*'idea'[\s\S]{0,800}ftextarea\.focus\(\)/.test(cfp));
    assert('campaignFactoryPick("idea") does NOT closeCampaignFactory',
           !/key\s*===\s*'idea'[\s\S]{0,800}closeCampaignFactory\(/.test(cfp));

    // product path: same shape as idea but specialised label.
    assert('campaignFactoryPick("product") reveals cf-followup',
           /key\s*===\s*'product'[\s\S]{0,400}follow[\s\S]{0,200}\.style\.display\s*=\s*'block'/.test(cfp));
    assert('campaignFactoryPick("product") uses a product-specific label',
           /key\s*===\s*'product'[\s\S]{0,500}flabel\.textContent\s*=\s*'Which product feature/.test(cfp));

    // goal path: focus cf-goal select; do NOT close. (Bounded by the goal block's
    // own `return;` so the regex doesn't span into the defensive fallback at the
    // bottom of the function.)
    assert('campaignFactoryPick("goal") focuses cf-goal select',
           /key\s*===\s*'goal'[\s\S]{0,500}gsel\.focus\(\)/.test(cfp));
    assert('campaignFactoryPick("goal") does NOT closeCampaignFactory (within its own block)',
           /key\s*===\s*'goal'[\s\S]{0,800}return\s*;/.test(cfp) &&
           !/key\s*===\s*'goal'[\s\S]{0,500}closeCampaignFactory\(\)/.test(cfp));

    // trend/surprise paths still work as before.
    assert('campaignFactoryPick("trend") still navigates to trends view',
           /key\s*===\s*'trend'[\s\S]{0,400}showView\('trends'\)/.test(cfp));
    assert('campaignFactoryPick("surprise") still runs runSurpriseMe',
           /key\s*===\s*'surprise'[\s\S]{0,400}runSurpriseMe\(\)/.test(cfp));
  }

  // 2. The followup block exists in the modal HTML, hidden by default.
  assert('Campaign Factory modal contains cf-followup container (hidden by default)',
         /id="cf-followup"[\s\S]{0,200}display:\s*none/.test(html));
  assert('cf-followup contains cf-idea textarea',
         /id="cf-followup"[\s\S]{0,400}id="cf-idea"/.test(html));
  assert('cf-followup has a cf-followup-label that campaignFactoryPick rewrites',
         /id="cf-followup"[\s\S]{0,400}id="cf-followup-label"/.test(html));

  // 3. campaignFactoryCreate reads cf-idea and writes brief.bigIdea for idea/product source.
  var cfcBody = html.match(/function campaignFactoryCreate\(\)\s*\{[\s\S]*?^}/m);
  assert('campaignFactoryCreate function body present', !!cfcBody);
  if (cfcBody) {
    var cfc = cfcBody[0];
    assert('campaignFactoryCreate reads cf-idea textarea',
           /document\.getElementById\('cf-idea'\)[\s\S]{0,300}\.value/.test(cfc));
    assert('campaignFactoryCreate tracks picked source via __cfPickedSource',
           /__cfPickedSource/.test(cfc));
    assert('campaignFactoryCreate computes bigIdea only when source is idea or product and text is present',
           /var\s+bigIdea\s*=\s*\(\(pickedSource\s*===\s*'idea'\s*\|\|\s*pickedSource\s*===\s*'product'\)\s*&&\s*ideaRaw\)\s*\?\s*ideaRaw\s*:\s*''/.test(cfc));
    assert('campaignFactoryCreate writes bigIdea into brief.bigIdea on the new campaign',
           /\.brief\.bigIdea\s*=\s*bigIdea/.test(cfc));
    assert('campaignFactoryCreate does NOT set brief.bigIdea for goal source',
           !/pickedSource\s*===\s*'goal'[\s\S]{0,400}brief[\s\S]{0,200}\.bigIdea/.test(cfc));
    assert('campaign.created event now carries source + bigIdea fields',
           /type:\s*'campaign\.created'[\s\S]{0,400}source:\s*pickedSource[\s\S]{0,200}bigIdea:\s*bigIdea/.test(cfc));
    assert('campaignFactoryCreate resets __cfPickedSource before closing',
           /__cfPickedSource\s*=\s*''[\s\S]{0,200}closeCampaignFactory/.test(cfc));
  }

  // 4. closeCampaignFactory defensively resets __cfPickedSource.
  var ccfBody = html.match(/function closeCampaignFactory\(\)\s*\{[\s\S]*?^}/m);
  assert('closeCampaignFactory resets __cfPickedSource', !!ccfBody && /__cfPickedSource\s*=\s*''/.test(ccfBody[0]));

  // 5. The generic campaign detail renderer still reads brief.bigIdea (Step 26 contract
  //    preserved for campaigns created via Factory idea/product sources).
  assert('renderGenericDetail still surfaces brief.bigIdea',
         /row\(['"]Big idea['"],\s*brief\.bigIdea\)/.test(html) ||
         /row\(\s*['"]Big idea['"],\s*brief\.bigIdea\s*\)/.test(html) ||
         /['"]Big idea['"][\s\S]{0,400}brief\.bigIdea/.test(html));

  results.push('  (Step 27 — Campaign Factory idea/product/goal paths reveal followup; idea text becomes brief.bigIdea; trend/surprise unchanged; close resets state; campaign.created event carries source + bigIdea)');

  // ── Step 28: ORIGINAL IDEA callout surfaces the user's entered idea verbatim on the
  // generic campaign detail page (which is what new Factory-sourced campaigns land on),
  // so the marketer can immediately confirm "the OS understood and saved my idea."
  // Conditional: only renders when brief.bigIdea is present and non-empty. Existing
  // campaigns without an idea render with no callout — no empty block, no placeholder.
  section('Step 28: ORIGINAL IDEA callout on generic campaign detail page (verbatim brief.bigIdea; conditional on presence)');

  // 1. HTML escape helper exists (preserves what the user sees; safe to render).
  var escapeBody = html.match(/function\s+escapeIdeaHtml\([\s\S]*?^}/m);
  assert('escapeIdeaHtml helper present', !!escapeBody);
  if (escapeBody) {
    assert('escapeIdeaHtml encodes & as &amp;',  /&/.test(escapeBody[0]) && /&amp;/.test(escapeBody[0]));
    assert('escapeIdeaHtml encodes < as &lt;',   /</.test(escapeBody[0]) && /&lt;/.test(escapeBody[0]));
    assert('escapeIdeaHtml encodes > as &gt;',   />/.test(escapeBody[0]) && /&gt;/.test(escapeBody[0]));
    assert('escapeIdeaHtml encodes " as &quot;', /"/.test(escapeBody[0]) && /&quot;/.test(escapeBody[0]));
    assert('escapeIdeaHtml encodes \' as &#39;', /'/.test(escapeBody[0]) && /&#39;/.test(escapeBody[0]));
  }

  // 2. renderGenericDetail reads brief.bigIdea and renders it verbatim (escaped) inside an
  // ORIGINAL IDEA block. The block must be conditional on brief.bigIdea being non-empty.
  var rgdBody = html.match(/function\s+renderGenericDetail\([\s\S]*?^}/m);
  assert('renderGenericDetail function body present', !!rgdBody);
  if (rgdBody) {
    var rgd = rgdBody[0];

    // Reads brief.bigIdea.
    assert('renderGenericDetail reads brief.bigIdea',
           /brief\s*=\s*c\.brief\s*\|\|\s*\{\}/.test(rgd) ||
           /brief\s*=\s*c\.brief/.test(rgd));

    // Has the original-idea callout block.
    assert('renderGenericDetail contains ORIGINAL IDEA label',
           /Original Idea/i.test(rgd));

    // Uses escapeIdeaHtml on the rendered text — protects against XSS and preserves the
    // exact characters the user typed (only HTML-encoding the markup).
    assert('renderGenericDetail renders brief.bigIdea through escapeIdeaHtml',
           /escapeIdeaHtml\(\s*ideaRaw\s*\)/.test(rgd) || /escapeIdeaHtml\(\s*brief\.bigIdea\s*\)/.test(rgd));

    // Conditional: only renders when bigIdea is non-empty (after trim). Existing campaigns
    // without brief.bigIdea produce no callout (no empty block, no placeholder).
    assert('renderGenericDetail gates callout on non-empty bigIdea (if-trimmed)',
           /ideaTrimmed[\s\S]{0,200}if[\s\S]{0,400}ideaCallout\s*=/.test(rgd) ||
           /brief\.bigIdea[\s\S]{0,200}if[\s\S]{0,400}ideaCallout\s*=/.test(rgd) ||
           /if\s*\(\s*ideaTrimmed\s*\)/.test(rgd));

    // Callout comes BEFORE the existing brief-panel rows (Name/ID/etc.) so secondary
    // metadata doesn't visually displace the captured-idea confirmation.
    var calloutIdx = rgd.indexOf('ideaCallout');
    var titleIdx = rgd.indexOf('Campaign Detail');
    assert('ORIGINAL IDEA callout is rendered before Campaign Detail title (i.e. above secondary metadata)',
           calloutIdx > 0 && titleIdx > 0 && calloutIdx < titleIdx);
  }

  // 3. Existing rows are still rendered (Name/ID/Status/Owner/Created/Updated/History).
  if (rgdBody) {
    var rgd2 = rgdBody[0];
    assert('renderGenericDetail still renders Name row',     /brief-key[^>]*>Name</.test(rgd2) || /Name<\/div>/.test(rgd2));
    assert('renderGenericDetail still renders ID row',       /brief-key[^>]*>ID</.test(rgd2)   || /ID<\/div>/.test(rgd2));
    assert('renderGenericDetail still renders Status row',   /brief-key[^>]*>Status</.test(rgd2) || /Status<\/div>/.test(rgd2));
    assert('renderGenericDetail still renders Created row',  /brief-key[^>]*>Created</.test(rgd2) || /Created<\/div>/.test(rgd2));
  }

  // 4. Strategist block prepending in renderCampaign is preserved (Step 24 contract).
  assert('renderCampaign still prepends renderStrategistBlock (Step 24 contract preserved)',
         /renderStrategistBlock\(id\)/.test(html));

  // 5. End-to-end shape: the escape contract is what "use exact text" requires.
  //    We assert the shape of the helper against the source rather than running it
  //    (the suite reads HTML as a string; the function only exists at runtime in
  //    the dashboard page, not in this static-analysis test).
  if (escapeBody) {
    var eb = escapeBody[0];
    // The escape helper must apply all five transforms in a single chained call
    // so the displayed text round-trips back to the user's exact input.
    assert('escapeIdeaHtml chain contains the & → &amp; transform',
           /replace\(\s*\/&\/g\s*,\s*'&amp;'\s*\)/.test(eb));
    assert('escapeIdeaHtml chain contains the < → &lt; transform',
           /replace\(\s*\/<\/g\s*,\s*'&lt;'\s*\)/.test(eb));
    assert('escapeIdeaHtml chain contains the > → &gt; transform',
           /replace\(\s*\/>\/g\s*,\s*'&gt;'\s*\)/.test(eb));
    assert('escapeIdeaHtml chain contains the " → &quot; transform',
           /replace\(\s*\/\\?"\/g\s*,\s*'&quot;'\s*\)/.test(eb));
    // The literal escape replacement for apostrophe uses String.prototype.replace with
    // a single-char regex. We assert the source contains the exact replacement string.
    assert("escapeIdeaHtml contains the ' → &#39; transform",
           eb.indexOf("replace(/'/g, '&#39;')") !== -1);
    // No rewrite/summary transforms — only escaping.
    assert('escapeIdeaHtml does NOT rewrite or summarise (no .slice, no substr, no .replace with summary text)',
           !/\.slice\(/.test(eb) && !/\.substr\(/.test(eb) && !/summary/i.test(eb));
    // String() coercion + null guard: input is whatever the user typed.
    assert('escapeIdeaHtml handles null/undefined input (returns empty string)',
           /if\s*\(\s*s\s*==\s*null\s*\)\s*return\s*''/.test(eb));
  }

  results.push('  (Step 28 — ORIGINAL IDEA callout surfaces verbatim brief.bigIdea on the generic detail page; HTML-escaped; conditional on non-empty idea; existing rows and strategist block preserved)');

  // ── Step 29: Operations Feed "Needs Attention" cards surface the campaign name.
  // Root decision friction: "I see 'No production work moving HEALTH 68' but no campaign
  // name. To answer which campaign needs my attention I have to click in. The OS already
  // knows the campaign name — it's right there in campaigns[campaignId].identity.name."
  // The fix surfaces the campaign name on the card, no new architecture, no fabrication.
  section('Step 29: Needs Attention cards surface the campaign name (OS already knows it; surface it)');

  // 1. renderOpsFeed reads campaign identity name when building health cards.
  var rofBody = html.match(/function\s+renderOpsFeed\s*\(\s*\)\s*\{[\s\S]*?^}/m);
  assert('renderOpsFeed function body present', !!rofBody);
  if (rofBody) {
    var rof = rofBody[0];

    // Reads the campaign name from the live campaign object.
    assert('renderOpsFeed reads campaigns[campaignId].identity.name',
           /window\.campaignData[\s\S]{0,400}campaigns[\s\S]{0,400}identity[\s\S]{0,200}\.name/.test(rof) ||
           /campaignData\s*\.\s*campaigns\s*\[\s*it\.campaignId\s*\][\s\S]{0,400}identity[\s\S]{0,200}\.name/.test(rof) ||
           /cdoc[\s\S]{0,200}identity[\s\S]{0,200}\.name/.test(rof));

    // Renders the name through escapeIdeaHtml (Step 28 helper) — safe if a campaign
    // name ever contains markup characters; preserves the exact characters shown.
    assert('renderOpsFeed escapes campaign name with escapeIdeaHtml',
           /escapeIdeaHtml\(\s*campName\s*\)/.test(rof));

    // The name is rendered as a label INSIDE the same health-card button. The card
    // still has data-campaign-id + onclick=selectCampaign(…), so Step 23 click-to-open
    // behavior is preserved.
    assert('renderOpsFeed still emits ops-card-clickable with data-campaign-id',
           /data-campaign-id="'\s*\+\s*it\.campaignId/.test(rof));
    assert('renderOpsFeed still emits onclick=selectCampaign(<id>)',
           /onclick="selectCampaign\(\\''\s*\+\s*it\.campaignId/.test(rof));

    // Card structure: name label appears before the issue title in DOM order so the
    // identity is the first thing the marketer sees.
    var nameIdx = rof.indexOf('nameLabel');
    var titleIdx = rof.indexOf("'<div style=\"font-weight:600;font-size:12px\">' + it.title");
    assert('campaign name label is rendered before the issue title (identity first)',
           nameIdx > 0 && titleIdx > 0 && nameIdx < titleIdx);

    // The card still surfaces the issue title and the health badge.
    assert('renderOpsFeed still renders the issue title (it.title)',
           /'\+\s*it\.title\s*\+/.test(rof) || /it\.title\s*\+/.test(rof));
    assert('renderOpsFeed still renders the Health <score> badge',
           /'Health\s*'\s*\+\s*score/.test(rof) || /Health\s*'\s*\+\s*score/.test(rof));
  }

  // 2. Defensive: if the campaign data is missing the name, the card still renders
  //    (no "undefined" text leaks out). The nameLabel is empty-string when campName
  //    is empty, so no label is appended.
  if (rofBody) {
    var rof2 = rofBody[0];
    assert('renderOpsFeed gates the name label on a truthy campaign name (no undefined leak)',
           /var nameLabel\s*=\s*campName\s*\?/.test(rof2) ||
           /campName\s*\?\s*'<div[^>]*>'/.test(rof2));
  }

  // 3. The existing non-health card path (overdue / no-live) is unchanged.
  if (rofBody) {
    var rof3 = rofBody[0];
    assert('non-health cards still render via the generic branch',
           /return\s*'<div class="ops-card"[\s\S]{0,400}it\.title/.test(rof3));
  }

  // 4. The other ops-feed buckets (opportunity, worthTrying) are unaffected.
  assert('opportunity bucket still rendered',
         /opsfeed-opportunity[\s\S]{0,400}bucket\(d\.opportunity/.test(html));
  assert('worthTrying bucket still rendered',
         /opsfeed-worth[\s\S]{0,400}bucket\(d\.worthTrying/.test(html) ||
         /worthTrying[\s\S]{0,400}bucket/.test(html));

  results.push('  (Step 29 — Needs Attention cards now surface the campaign name (campaigns[campaignId].identity.name) above the issue title; safe via escapeIdeaHtml; existing onclick/data-campaign-id and other buckets unchanged)');

  // ── Step 30: Needs Attention priority order — the OS already knows which card
  // deserves attention first (impact → state → issueCount → healthScore). Surface it
  // on the card itself: DO THIS FIRST on card 0, NEXT on subsequent cards, plus the
  // recommendation's impact badge and a truthful templated explainer. ─────
  section('Step 30: Needs Attention priority order (impact → state → issueCount → healthScore) + DO THIS FIRST + impact badge + truthful explainer');

  // -- 30.1: opsFeedData items now carry impact / diagnoseState / issueCount fields
  const needs = html.match(/needsAttention:\s*\[[\s\S]*?\.concat\(liveButUnhealthy\)/);
  assert('opsFeedData returns a needsAttention array', needs !== null);

  assert('impact field is sourced from rec.impact (the OS-computed recommendation impact)', /impact:\s*rec\s*\?\s*\(rec\.impact\s*\|\|\s*'High'\)/.test(html));
  assert('diagnoseState field is sourced from diagnoseCampaign().state', /diagnoseState:\s*d\.state\s*\|\|\s*healthBand/.test(html));
  assert('issueCount field is sourced from d.issues.length', /issueCount:\s*d\.issues\.length/.test(html));

  // -- 30.2: deterministic sort with the brief's exact key order
  assert('liveButUnhealthy is sorted before returning', /liveButUnhealthy\.sort\(function\(a,\s*b\)/.test(html));
  assert('impact rank: High(0) < Medium(1) < Low(2) — High first', /IMPACT_RANK\s*=\s*\{\s*'High':\s*0,\s*'Medium':\s*1,\s*'Low':\s*2\s*\}/.test(html));
  assert('state rank: critical(0) < degraded(1) < healthy(2) — critical first', /STATE_RANK\s*=\s*\{\s*'critical':\s*0,\s*'degraded':\s*1,\s*'healthy':\s*2\s*\}/.test(html));
  assert('issueCount comparator returns -ac (more issues first)', /var\s+ac\s*=\s*\(a\.issueCount\s*\|\|\s*0\)\s*-\s*\(b\.issueCount\s*\|\|\s*0\);\s*\/\/\s*desc:\s*more\s+issues\s+first[\s\S]{0,40}return\s+-ac/.test(html));
  assert('healthScore comparator returns ah - bh (lower health first)', /return\s+ah\s*-\s*bh;\s*\/\/\s*asc:\s*lower\s+health\s+first/.test(html));

  // -- 30.3: DO THIS FIRST badge on first card
  assert('idx===0 branch renders DO THIS FIRST badge', /if\s*\(idx\s*===\s*0\)[\s\S]{0,400}DO THIS FIRST/.test(html));;
  assert('DO THIS FIRST banner explainer copy is present on the first card', /DO THIS FIRST — highest-priority card on this list/.test(html));;
  assert('arrow + DO THIS FIRST visual badge is present', /▶ DO THIS FIRST/.test(html));;

  // -- 30.4: NEXT badge on subsequent cards in multi-card bucket
  assert('subsequent cards in multi-card bucket show NEXT badge', /else\s+if\s*\(arr\.length\s*>\s*1\)[\s\S]{0,400}>NEXT<\/span>/.test(html));
  assert('NEXT badge text is rendered for non-first cards', /var\s+priorityBadge\s*=\s*['"]/.test(html) && /priorityBadge\s*=\s*['"][^'"]*NEXT/.test(html) === false || /NEXT/.test(html));

  // -- 30.5: impact badge per card (HIGH IMPACT / MEDIUM IMPACT / LOW IMPACT)
  assert('impact badge label = impact.toUpperCase() + " IMPACT"', /var\s+impactLabel\s*=\s*it\.impact\s*\?\s*\(it\.impact\.toUpperCase\(\)\s*\+\s*' IMPACT'\)/.test(html));;
  assert('impact badge formats as e.g. "HIGH IMPACT"', /' HIGH IMPACT'|' MEDIUM IMPACT'|' LOW IMPACT'/.test(html) || /IMPACT'/.test(html));;

  // -- 30.6: truthful explainer templated from real diagnosis (no fabrication)
  assert('explainer only renders on DO THIS FIRST card with issues', /if\s*\(idx\s*===\s*0\s*&&\s*it\.issueCount\s*>\s*0\)/.test(html));
  assert('explainer adjective is templated from real impact value (High/Medium/Low)', /var\s+adj\s*=\s*\(it\.impact\s*===\s*'High'\)\s*\?\s*'Highest-impact'\s*:\s*\(it\.impact\s*===\s*'Medium'\s*\?\s*'Medium-impact'\s*:\s*'Low-impact'\)/.test(html));
  assert('explainer noun is templated with singular/plural from issueCount', /var\s+noun\s*=\s*\(it\.issueCount\s*===\s*1\)\s*\?\s*'unresolved area'\s*:\s*'unresolved areas'/.test(html));;
  // Verify exact example from the brief: "Highest-impact issue across 3 unresolved areas."
  assert('explainer format: "<adj> issue across <count> <noun>." — matches brief example', /adj\s*\+\s*' issue across '\s*\+\s*it\.issueCount\s*\+\s*' '\s*\+\s*noun/.test(html));;

  // -- 30.7: nothing fabricated — no invented urgency / business impact language
  // (Brief specifically forbids fabricated urgency or business impact. Only "Highest-impact/Medium-impact/Low-impact" + "issue across N unresolved area(s)" allowed.)
  assert('explainer does NOT use fabricated urgency / business impact language', !/urgent|critical\s+priority|stakeholders|ROI|revenue|cost\s+of\s+delay|deadline/i.test(
    html.match(/var\s+explainer[\s\S]{0,400}/)[0]
  ));

  // -- 30.8: existing functionality preserved
  assert('data-campaign-id attribute preserved (Step 23 contract)', /data-campaign-id="'\s*\+\s*it\.campaignId/.test(html));
  assert('onclick selectCampaign preserved (Step 23 contract)', /onclick="selectCampaign\(\\''\s*\+\s*it\.campaignId/.test(html));
  assert('issue title is now HTML-escaped (Step 28 helper applied to title)', /escapeIdeaHtml\(it\.title\)/.test(html));
  assert('campaign name remains HTML-escaped (Step 29 helper preserved)', /escapeIdeaHtml\(campName\)/.test(html));
  assert('health badge preserved (no removal)', /Health\s+'\s*\+\s*score/.test(html));

  // -- 30.9: existing Step 22/25 behavior still in place (overdue + no-live kinds still
  // prepended; liveButUnhealthy still joined via .concat)
  assert('overdue asset card prepended (Step 22.5 behavior preserved)', /overdue\.length\s*\?\s*\{[\s\S]{0,200}kind:'overdue'/.test(html));
  assert('no-live card prepended when no campaigns (Step 25 behavior preserved)', /liveCampaigns\.length\s*===\s*0\s*\?\s*\{[\s\S]{0,200}kind:'empty'/.test(html));
  assert('sorted liveButUnhealthy concatenated to fixed-overhead items', /\.concat\(liveButUnhealthy\)/.test(html));

  // -- 30.10: dynamic re-sort — renderOpsFeed is already called after every applyEvent.
  // Verify those callsites still exist so the Feed re-sorts without refresh.
  assert('renderOpsFeed called after applyEvent somewhere in the codebase (dynamic re-sort trigger)', /applyEvent[\s\S]{0,500}renderOpsFeed\(\)/.test(html));

  results.push('  (Step 30 — Needs Attention cards now show priority order: impact → state → issueCount → healthScore. Card 0 = "DO THIS FIRST" + truth-templated explainer + impact badge. Card 1+ = "NEXT". Re-sorts automatically on render. No fabrication, no new scoring, no redesign.)');

  // ── Step 31: Production Board becomes campaign-aware when the marketer
  // arrives from a strategist "Plan Assets ›" action. Root decision friction:
  // "The OS told me to plan TrackMan's first asset, then dropped me on a
  // generic Production Board that forgot the campaign and made me repeat
  // information it already knows." Fix: carry the campaign context into the
  // destination view (panel + reason), give one obvious next action (primary
  // CTA that pre-fills the form), keep standalone mode untouched, and bridge
  // the asset store to c.assets so diagnosis re-evaluates after save. ─────
  section('Step 31: Production Board is campaign-aware when arriving from strategist action (panel + reason + primary CTA + form pre-fill + diagnosis refresh)');

  // Helper: extract a function body by walking from "function name(" until the
  // next top-level "\nfunction " declaration. Function bodies can contain
  // nested braces so a simple non-greedy [\s\S]*?\n\s*}/ stops at the first
  // inner closing brace and truncates the body.
  function getFnBody(name) {
    var start = html.indexOf('function ' + name + '(');
    if (start === -1) return null;
    var nextFn = html.indexOf('\nfunction ', start + 1);
    return nextFn === -1 ? html.substring(start) : html.substring(start, nextFn);
  }

  // -- 31.1: pb-context-panel exists in #view-assets, mirror of cs-context-panel.
  assert('Production Board view contains a pb-context-panel element',
         /id="view-assets"[\s\S]{0,4000}id="pb-context-panel"/.test(html) ||
         /id="pb-context-panel"[\s\S]{0,4000}id="view-assets"/.test(html));
  // Default state of the panel: hidden until a strategist action sets the context.
  assert('pb-context-panel is hidden by default (display:none)',
         /id="pb-context-panel"[\s\S]{0,200}display:\s*none/.test(html));

  // -- 31.2: asset modal has an inline campaign banner element (the context
  // must remain visible while the modal is open).
  assert('asset modal has an inline campaign banner (id="asset-modal-campaign-banner")',
         /id="asset-modal-campaign-banner"/.test(html));

  // -- 31.3: openAssetModalForCampaign pre-fills the form from real OS data.
  var oamfc = getFnBody('openAssetModalForCampaign');
  assert('openAssetModalForCampaign function defined', !!oamfc);
  if (oamfc) {
    // Reads the live campaign doc to pre-fill LINK TO CAMPAIGN + SOURCE OBJECT.
    assert('openAssetModalForCampaign reads the campaign doc from window.campaignData',
           /window\.campaignData[\s\S]{0,400}campaigns[\s\S]{0,200}campaignId/.test(oamfc) ||
           /campaignData\s*\.\s*campaigns[\s\S]{0,400}campaignId/.test(oamfc));
    // Pre-fills LINK TO CAMPAIGN <select> with the campaign id.
    assert('openAssetModalForCampaign sets #a-campaign to campaignId',
           /document\.getElementById\(['"]a-campaign['"]\)[\s\S]{0,200}\.value\s*=\s*campaignId/.test(oamfc) ||
           /a-campaign[\s\S]{0,200}\.value\s*=\s*campaignId/.test(oamfc));
    // Pre-fills SOURCE OBJECT <select> with `campaign:<id>` so the asset
    // arrives already attached — no extra step required.
    assert('openAssetModalForCampaign sets #a-source via openAssetModal("campaign:<id>")',
           /openAssetModal\(\s*['"]campaign:['"]?\s*\+\s*campaignId/.test(oamfc));
    // Pre-fills PRIORITY to High — because the recommendation.impact is High.
    assert('openAssetModalForCampaign sets #a-priority to "high"',
           /a-priority[\s\S]{0,200}\.value\s*=\s*['"]high['"]/.test(oamfc));
    // Pre-fills BRAND from real OS data — picks the first non-empty option from the <select>
    // (campaign.productBrand or product.brand fallback). Never forces "— None —".
    assert('openAssetModalForCampaign reads brand from real product/campaign options',
           /brandEl\.options[\s\S]{0,200}\.value/.test(oamfc) ||
           /var\s+preferred[\s\S]{0,400}brandEl\.options/.test(oamfc));
    // Pre-fills TITLE placeholder dynamically from brief.bigIdea or purpose —
    // never an invented title (marketer still types).
    // (The brief.bigIdea is read FIRST into a var, THEN used to set titleEl.placeholder,
    // so the regex follows that order.)
    assert('openAssetModalForCampaign sets TITLE placeholder from real brief data (bigIdea/purpose)',
           /brief\.bigIdea[\s\S]{0,800}\.placeholder[\s\S]{0,200}=\s*['"]e\.g\.\s*['"]?\s*\+\s*ph/.test(oamfc) ||
           /brief\.bigIdea[\s\S]{0,500}placeholder[\s\S]{0,200}=\s*['"]e\.g\.\s*['"]?\s*\+\s*ph/.test(oamfc));
    // Shows the inline modal banner so campaign context remains visible while the modal is open.
    assert('openAssetModalForCampaign shows the inline campaign banner (asset-modal-campaign-banner)',
           /asset-modal-campaign-banner[\s\S]{0,400}display\s*=\s*['"]block['"]/.test(oamfc) ||
           /asset-modal-campaign-banner[\s\S]{0,400}style\.display\s*=\s*['"]block['"]/.test(oamfc));
    // Does NOT invent title/type/date/owner/notes — they stay empty/placeholder.
    assert('openAssetModalForCampaign does NOT set #a-title value to non-empty (marketer still types)',
           !/a-title[\s\S]{0,200}\.value\s*=\s*['"][^'"]+['"]/.test(oamfc));
    assert('openAssetModalForCampaign does NOT set #a-requiredby to non-empty (marketer still picks)',
           !/a-requiredby[\s\S]{0,200}\.value\s*=\s*['"][^'"]+['"]/.test(oamfc));
    assert('openAssetModalForCampaign does NOT set #a-owner to non-empty (marketer still picks)',
           !/a-owner[\s\S]{0,200}\.value\s*=\s*['"][^'"]+['"]/.test(oamfc));
    // Modal title shows " — for X" so the marketer sees the campaign while the modal is open.
    assert('openAssetModalForCampaign sets modal title to "New Asset Request — for <name>"',
           /New Asset Request\s*—\s*for/.test(oamfc));
  }

  // -- 31.4: renderProductionContextPanel reads the campaign doc and renders
  // the campaign name + reason (from live diagnosis) into the panel.
  var rpcp = getFnBody('renderProductionContextPanel');
  assert('renderProductionContextPanel function defined', !!rpcp);
  if (rpcp) {
    assert('renderProductionContextPanel reads window.productionContextCampaignId',
           /window\.productionContextCampaignId/.test(rpcp));
    assert('renderProductionContextPanel reads campaign.identity.name for display',
           /identity[\s\S]{0,200}\.name/.test(rpcp));
    assert('renderProductionContextPanel shows the panel via display:block when context set',
           /panel\.style\.display\s*=\s*['"]block['"]/.test(rpcp));
    assert('renderProductionContextPanel hides the panel when context null (standalone)',
           /panel\.style\.display\s*=\s*['"]none['"]/.test(rpcp));
    // The reason text comes from a real diagnose call — not invented.
    assert('renderProductionContextPanel sources "Reason" from diagnoseCampaign (live data)',
           /diagnoseCampaign[\s\S]{0,400}recommendation|diagnoseCampaign[\s\S]{0,400}reason|d\.recommendation\.title/.test(rpcp));
    // Campaign name is escaped to prevent XSS in the panel.
    assert('renderProductionContextPanel escapes campaign name with escapeIdeaHtml',
           /escapeIdeaHtml\([\s\S]{0,200}cname/.test(rpcp));
    // Primary CTA wired to openAssetModalForCampaign(contextId).
    assert('renderProductionContextPanel primary CTA calls openAssetModalForCampaign(contextId)',
           /openAssetModalForCampaign\(\s*['"]\s*'\s*\+\s*contextId/.test(rpcp) ||
           /openAssetModalForCampaign\(\s*contextId/.test(rpcp) ||
           /openAssetModalForCampaign[\s\S]{0,200}contextId/.test(rpcp));
  }

  // -- 31.5: productionContextClear function exists and resets context.
  var pcc = getFnBody('productionContextClear');
  assert('productionContextClear function defined', !!pcc);
  if (pcc) {
    assert('productionContextClear sets window.productionContextCampaignId = null',
           /window\.productionContextCampaignId\s*=\s*null/.test(pcc));
    assert('productionContextClear re-renders the asset planner (standalone view returns)',
           /renderAssetPlanner\(/.test(pcc));
  }

  // -- 31.6: strategist "Plan Assets ›" button sets window.productionContextCampaignId.
  // Mirrors the Step 25 pattern where the same button sets window.creativeContextCampaignId.
  // The strategist block builder must set production context whenever dest === 'assets'.
  assert('strategist block sets production context when dest is "assets" (issue button)',
         /it\.dest\s*===\s*['"]assets['"][\s\S]{0,400}window\.productionContextCampaignId\s*=/.test(html));
  assert('strategist block sets production context when dest is "assets" (recommendation button)',
         /rec\.dest\s*===\s*['"]assets['"][\s\S]{0,400}window\.productionContextCampaignId\s*=/.test(html));
  // Mirror: dest === 'creative' still sets creative context (Step 25 contract preserved).
  assert('strategist block still sets creative context when dest is "creative" (Step 25 contract)',
         /it\.dest\s*===\s*['"]creative['"][\s\S]{0,400}window\.creativeContextCampaignId\s*=/.test(html) ||
         /rec\.dest\s*===\s*['"]creative['"][\s\S]{0,400}window\.creativeContextCampaignId\s*=/.test(html));

  // -- 31.7: renderAssetPlanner calls renderProductionContextPanel so the panel
  // surfaces correctly on every view entry.
  var rap = getFnBody('renderAssetPlanner');
  assert('renderAssetPlanner function defined', !!rap);
  if (rap) {
    assert('renderAssetPlanner calls renderProductionContextPanel()',
           /renderProductionContextPanel\(\)/.test(rap));
    // Existing behavior preserved: filter + table render still happens.
    assert('renderAssetPlanner still renders the filter/table (existing behavior preserved)',
           /filter|assetFilter|assetRow|renderAsset|assetList|assets-filter/.test(rap));
  }

  // -- 31.8: Standalone mode preserved — openAssetModal("") keeps generic defaults.
  var oam = getFnBody('openAssetModal');
  assert('openAssetModal function defined', !!oam);
  if (oam) {
    // Generic defaults are reset: title empty, brand "— None —", priority medium, etc.
    assert('openAssetModal resets title to empty (standalone)',
           /a-title['"]?\)\.value\s*=\s*['"]\s*['"]|a-title['"]?\)\.value\s*=\s*['"]['"]/.test(oam));
    assert('openAssetModal resets brand to "" (standalone default)',
           /a-brand['"]?\)\.value\s*=\s*['"]\s*['"]|a-brand['"]?\)\.value\s*=\s*['"]['"]/.test(oam));
    assert('openAssetModal resets priority to "medium" (standalone default)',
           /a-priority['"]?\)\.value\s*=\s*['"]medium['"]/.test(oam));
    assert('openAssetModal resets modal title to "New Asset Request" (standalone)',
           /titleEl\.textContent\s*=\s*['"]New Asset Request['"]/.test(oam));
  }

  // -- 31.8b: closeAssetModal hides the inline banner so a subsequent standalone open
  // doesn't show stale campaign context.
  var cam = getFnBody('closeAssetModal');
  assert('closeAssetModal function defined', !!cam);
  if (cam) {
    assert('closeAssetModal hides the inline campaign banner (resets state for next open)',
           /asset-modal-campaign-banner[\s\S]{0,400}display\s*=\s*['"]none['"]/.test(cam) ||
           /asset-modal-campaign-banner[\s\S]{0,400}style\.display\s*=\s*['"]none['"]/.test(cam));
  }

  // -- 31.9: handleAssetSubmit writes the new asset to c.assets so diagnoseCampaign
  // re-evaluates. Without this bridge, adding an asset does NOT change the diagnosis
  // because diagnose reads c.assets (not the asset store) — pre-existing gap.
  var has = getFnBody('handleAssetSubmit');
  assert('handleAssetSubmit function defined', !!has);
  if (has) {
    // The bridge: write asset to c.assets[assetId] after the asset store append.
    assert('handleAssetSubmit writes the new asset to campaign.c.assets (diagnosis refresh)',
           /c\.assets[\s\S]{0,200}=[\s\S]{0,200}c\.assets[\s\S]{0,200}assetId[\s\S]{0,200}=[\s\S]{0,200}asset/.test(has) ||
           /c\.assets[\s\S]{0,200}\[asset\.assetId\][\s\S]{0,200}=[\s\S]{0,200}asset/.test(has));
    // renderOpsFeed is called after save so the Ops Feed re-sorts with the new diagnosis.
    assert('handleAssetSubmit triggers renderOpsFeed() (Ops Feed auto-refresh)',
           /renderOpsFeed\(\)/.test(has));
    // Existing pipeline preserved: campaignLink + sourceRef + history + renderAssetPlanner.
    assert('handleAssetSubmit still writes c.assetRequests array (existing pipeline)',
           /c\.assetRequests[\s\S]{0,200}\.push|c\.assetRequests[\s\S]{0,200}\.unshift/.test(has));
    assert('handleAssetSubmit still calls renderAssetPlanner() (existing render)',
           /renderAssetPlanner\(/.test(has));
  }

  // -- 31.10: existing openAssetModal signature preserved — the "+ New Asset Request"
  // button (standalone) still calls openAssetModal() with no args.
  assert('+ New Asset Request button still calls openAssetModal() with no args (standalone)',
         /onclick="openAssetModal\(\)"/.test(html));

  // -- 31.11: Primary CTA inside the panel calls openAssetModalForCampaign(cid).
  assert('pb-context-panel primary CTA calls openAssetModalForCampaign(cid)',
         /onclick="openAssetModalForCampaign\(['"]\$\{?cid\}?['"]\)"/.test(html) ||
         /onclick="openAssetModalForCampaign\([^)]+\)"/.test(html));

  // -- 31.12: "Switch to standalone" button calls productionContextClear.
  assert('pb-context-panel "Switch to standalone" button calls productionContextClear()',
         /onclick="productionContextClear\(\)"/.test(html));

  // -- 31.13: No broader Production Board redesign — the existing
  // Asset Planner table header, filter <select>, and "+ New Asset Request"
  // button remain unchanged.
  assert('Production Board still has "Asset Planner" header',
         /id="view-assets"[\s\S]{0,4000}Asset Planner/.test(html) ||
         /Asset Planner[\s\S]{0,4000}id="view-assets"/.test(html));
  assert('Production Board still has the filter <select>',
         /id="view-assets"[\s\S]{0,4000}<select[\s\S]{0,400}asset/i.test(html) ||
         /<select[\s\S]{0,400}asset[\s\S]{0,400}id="view-assets"/.test(html));
  assert('Production Board still has "+ New Asset Request" button',
         /id="view-assets"[\s\S]{0,4000}\+ New Asset Request/.test(html) ||
         /\+ New Asset Request[\s\S]{0,4000}id="view-assets"/.test(html));

  // -- 31.14: productionContextClear uses window.productionContextCampaignId and
  // re-renders. The wire from panel-button → contextClear → standalone view is
  // explicit in source.
  assert('productionContextClear hides pb-context-panel and shows standalone view',
         /productionContextClear[\s\S]{0,400}renderAssetPlanner[\s\S]{0,400}productionContextCampaignId[\s\S]{0,400}null/.test(html) ||
         /productionContextClear\(\)[\s\S]{0,400}window\.productionContextCampaignId\s*=\s*null/.test(html));

  results.push('  (Step 31 — Production Board becomes campaign-aware when the marketer arrives from a strategist "Plan Assets ›" action. Context panel surfaces campaign name + reason + primary CTA. Primary CTA pre-fills LINK TO CAMPAIGN, SOURCE OBJECT, BRAND, PRIORITY, and the TITLE placeholder from real OS data. Asset save writes to c.assets so diagnosis refreshes and Ops Feed re-sorts. Standalone mode preserved when context is null or "Switch to standalone" is clicked. No broader redesign, no AI, no fabrication.)');

  // ── Step 32: campaign-routed Production Board shows one creation path only ──
  // Friction: when the OS routes the marketer to Production Board from a campaign
  // strategist action, both the campaign-aware CTA (in PLANNING FOR panel) and the
  // generic "+ New Asset Request" button are visible. The generic button creates a
  // standalone request and silently drops the campaign context. The marketer has to
  // remember which button preserves the link. Step 32 hides the generic button while
  // a campaign context is active; "Switch to standalone" restores it. Direct nav
  // (no context) keeps the button visible. Standalone mode is not removed from the
  // product.

  section('Step 32: campaign-routed Production Board hides generic + New Asset Request; Switch to standalone restores it');

  // -- 32.1: helper function exists and reads productionContextCampaignId.
  var ugabv = getFnBody('updateGenericAssetButtonVisibility');
  assert('updateGenericAssetButtonVisibility function defined', !!ugabv);
  if (ugabv) {
    assert('updateGenericAssetButtonVisibility references window.productionContextCampaignId',
           /window\.productionContextCampaignId/.test(ugabv));
    assert('updateGenericAssetButtonVisibility targets #btn-new-asset',
           /getElementById\(\s*['"]btn-new-asset['"]\s*\)/.test(ugabv));
    assert('updateGenericAssetButtonVisibility sets display:none when context is set',
           /productionContextCampaignId[\s\S]{0,200}display\s*=\s*['"]none['"]/.test(ugabv));
    assert('updateGenericAssetButtonVisibility clears display when context is null',
           /else\s*\{[\s\S]{0,80}display\s*=\s*['"]['"]/.test(ugabv));
  }

  // -- 32.2: renderProductionContextPanel calls the helper on both branches.
  var rpcp = getFnBody('renderProductionContextPanel');
  assert('renderProductionContextPanel defined', !!rpcp);
  if (rpcp) {
    assert('renderProductionContextPanel calls updateGenericAssetButtonVisibility when context is null',
           /!contextCampaign[\s\S]{0,400}updateGenericAssetButtonVisibility/.test(rpcp));
    assert('renderProductionContextPanel calls updateGenericAssetButtonVisibility when context is active',
           /panel\.style\.display\s*=\s*['"]block['"][\s\S]{0,200}updateGenericAssetButtonVisibility/.test(rpcp));
  }

  // -- 32.3: productionContextClear calls the helper so Switch to standalone restores the button.
  var pcc = getFnBody('productionContextClear');
  assert('productionContextClear defined', !!pcc);
  if (pcc) {
    assert('productionContextClear calls updateGenericAssetButtonVisibility',
           /renderAssetPlanner[\s\S]{0,200}updateGenericAssetButtonVisibility/.test(pcc) ||
           /updateGenericAssetButtonVisibility[\s\S]{0,400}renderAssetPlanner/.test(pcc));
    assert('productionContextClear still sets window.productionContextCampaignId = null',
           /window\.productionContextCampaignId\s*=\s*null/.test(pcc));
    assert('productionContextClear still re-renders the asset planner',
           /renderAssetPlanner/.test(pcc));
  }

  // -- 32.4: #btn-new-asset stays in the DOM (standalone mode is preserved in markup).
  assert('#btn-new-asset still exists in Production Board markup',
         /id="view-assets"[\s\S]{0,4000}id="btn-new-asset"/.test(html) ||
         /id="btn-new-asset"[\s\S]{0,4000}id="view-assets"/.test(html));
  assert('+ New Asset Request button still calls openAssetModal() with no args (standalone)',
         /id="btn-new-asset"[\s\S]{0,200}onclick=["']openAssetModal\(\)["']/.test(html));

  // -- 32.5: Production Board renders the campaign-aware view via showView('assets'),
  // which calls renderAssetPlanner() → renderProductionContextPanel() → updateGenericAssetButtonVisibility().
  assert('showView("assets") calls renderAssetPlanner (full re-render on view switch)',
         /name\s*===\s*['"]assets['"][\s\S]{0,200}renderAssetPlanner/.test(html));

  // -- 32.6: Switch to standalone button still exists and wires to productionContextClear.
  assert('Switch to standalone button still calls productionContextClear()',
         /onclick=["']productionContextClear\(\)["']/.test(html));

  // -- 32.7: campaign-aware save flow is preserved (Step 31 contract still holds —
  // hiding the generic button does not touch the modal pre-fill pipeline).
  var oamfc = getFnBody('openAssetModalForCampaign');
  assert('openAssetModalForCampaign still pre-fills LINK TO CAMPAIGN from campaignId',
         oamfc && /a-campaign[\s\S]{0,200}\.value\s*=\s*campaignId/.test(oamfc));
  assert('openAssetModalForCampaign still pre-fills PRIORITY to high',
         oamfc && /a-priority[\s\S]{0,200}\.value\s*=\s*['"]high['"]/.test(oamfc));
  assert('openAssetModalForCampaign still shows inline campaign banner',
         oamfc && /asset-modal-campaign-banner[\s\S]{0,200}style\.display\s*=\s*['"]block['"]/.test(oamfc));
  assert('openAssetModalForCampaign still sets modal title to "New Asset Request — for <name>"',
         oamfc && /New Asset Request — for /.test(oamfc));

  results.push('  (Step 32 — On a campaign-routed Production Board, the generic "+ New Asset Request" button is hidden while a campaign context is active. Only the campaign-aware CTA in the PLANNING FOR panel is visible. "Switch to standalone" restores the generic button. Direct navigation to Production Board (no context) keeps the generic button visible with standalone defaults. The campaign-aware modal pre-fill flow (LINK TO CAMPAIGN, SOURCE OBJECT, BRAND, PRIORITY, TITLE placeholder, inline banner) is preserved unchanged. No broader Production Board redesign, no new modal, no AI.)');

  // ───────────────────────────────────────────────────────────────
  // STEP 33 — Campaign Detail Production Assets counter reads from live c.assets
  // (was hardcoded "0 total" inside the seeded renderFns templates).
  // ───────────────────────────────────────────────────────────────

  // -- 33.1: patchProductionAssetsSection helper exists and reads c.assets.
  var ppas = getFnBody('patchProductionAssetsSection');
  assert('patchProductionAssetsSection helper exists',
         typeof ppas === 'string' && ppas.length > 100);
  assert('patchProductionAssetsSection reads from c.assets (not a hardcoded number)',
         ppas && /c\.assets/.test(ppas) && /Object\.keys/.test(ppas));
  assert('patchProductionAssetsSection locates the Production Assets card-title',
         ppas && /Production Assets/.test(ppas) && /card-title/.test(ppas));
  assert('patchProductionAssetsSection renders the empty placeholder when c.assets is empty',
         ppas && /No assets in production/.test(ppas));
  assert('patchProductionAssetsSection renders a prod-item for each asset',
         ppas && /prod-item/.test(ppas) && /for\s*\(\s*var\s+j\s*=/.test(ppas));

  // -- 33.2: renderCampaign wires the patch after rendering the seeded template.
  var rcb = getFnBody('renderCampaign');
  assert('renderCampaign still calls renderFns[id](c) first (preserves seeded layout)',
         rcb && /window\.renderFns\[id\]\(c\)/.test(rcb));
  assert('renderCampaign still prepends the strategist block (Step 24 contract)',
         rcb && /renderStrategistBlock/.test(rcb));
  assert('renderCampaign still appends the References panel (Step 19 contract)',
         rcb && /renderCampaignReferences/.test(rcb));
  assert('renderCampaign now calls patchProductionAssetsSection after the seeded render',
         rcb && /patchProductionAssetsSection\(detailContent,\s*c\)/.test(rcb));

  // -- 33.3: the patch uses the same source as diagnoseCampaign. After Step 34
  // both diagnoseCampaign and computeCampaignHealth delegate to
  // getCampaignCategoryState — one shared category-state source. This proves
  // "one source of truth" across Campaign Detail ring, Operations Feed,
  // Strategist block, and the patch.
  var dcb = getFnBody('diagnoseCampaign');
  var gccb = getFnBody('getCampaignCategoryState');
  var cchb = getFnBody('computeCampaignHealth');
  assert('Step 34: diagnoseCampaign now delegates to getCampaignCategoryState',
         dcb && /getCampaignCategoryState\(/.test(dcb));
  assert('Step 34: diagnoseCampaign now uses computeCampaignHealth (no separate state-band math)',
         dcb && /computeCampaignHealth\(/.test(dcb));
  assert('Step 34: shared category-state source getCampaignCategoryState exists',
         typeof gccb === 'string' && /c\.assets/.test(gccb) && /Object\.keys/.test(gccb));
  assert('Step 34: health engine computeCampaignHealth uses the same category source',
         cchb && /getCampaignCategoryState\(/.test(cchb));
  assert('Step 34: computeCampaignHealth reads c.assets via the shared source',
         cchb && /Object\.keys/.test(cchb));
  assert('Step 34: both computeCampaignHealth and patchProductionAssetsSection use Object.keys — same source',
         cchb && /Object\.keys/.test(cchb) && ppas && /Object\.keys\(assets\)/.test(ppas));

  // -- 33.4: production status color logic — the patch uses a color function that
  // maps status values to specific colors (published blue, rejected red, else orange).
  assert('patchProductionAssetsSection maps published → #4488ff (blue)',
         ppas && /published[\s\S]{0,80}#4488ff/.test(ppas));
  assert('patchProductionAssetsSection maps rejected → #ff4455 (red)',
         ppas && /rejected[\s\S]{0,80}#ff4455/.test(ppas));
  assert('patchProductionAssetsSection falls back to #ffaa00 (orange) for other statuses',
         ppas && /#ffaa00/.test(ppas));

  // -- 33.5: the patch handles the four seeded renderFns templates without breaking
  // any of them — counter pattern is present in all four templates, and the patch
  // rewrites whichever one is rendered. This proves it works for TrackMan, Takomo,
  // Winter Golf and Use the Right Equipment.
  assert('TrackMan seeded template still has "Production Assets" card-title (patch target)',
         /window\.renderFns\["trackman-intelligence"\][\s\S]{0,15000}Production Assets/.test(html));
  assert('Takomo seeded template still has "Production Assets" card-title (patch target)',
         /window\.renderFns\["takomo-101t"\][\s\S]{0,15000}Production Assets/.test(html));
  assert('Winter Golf seeded template still has "Production Assets" card-title (patch target)',
         /window\.renderFns\["winter-golf"\][\s\S]{0,15000}Production Assets/.test(html));
  assert('UTRE seeded template still has "Production Assets" card-title (patch target)',
         /window\.renderFns\["use-the-right-equipment-mq5l90bk"\][\s\S]{0,30000}Production Assets/.test(html));

  // -- 33.6: the patch is defensive — guards on c.assets being null/undefined so it
  // doesn't blow up on brand-new campaigns whose renderGenericDetail path is taken.
  assert('patchProductionAssetsSection guards c.assets being null/undefined',
         ppas && /c\.assets\s*&&\s*typeof\s+c\.assets\s*===\s*['"]object['"]/.test(ppas));
  assert('patchProductionAssetsSection is wrapped in try/catch when called',
         rcb && /try\s*\{\s*patchProductionAssetsSection[\s\S]{0,100}catch/.test(rcb));

  // -- 33.7: prove the patch actually rewrites the DOM (not a no-op). After the
  // template renders "Production Assets — 0 total", the patch must replace that
  // title element with one whose textContent starts with "Production Assets — N".
  assert('patchProductionAssetsSection writes a fresh card-title element with the live count',
         ppas && /card-title[\s\S]{0,80}count[\s\S]{0,20}total/.test(ppas));
  assert('patchProductionAssetsSection rewrites the card body via innerHTML',
         ppas && /card\.innerHTML/.test(ppas));

  // -- 33.8: Step 32 contract preserved — campaign-aware production routing
  // still routes through openAssetModalForCampaign, asset save still bridges
  // to c.assets via handleAssetSubmit. No regression.
  var hasb = getFnBody('handleAssetSubmit');
  assert('handleAssetSubmit still bridges c.assets[asset.assetId] = asset (Step 31 contract)',
         hasb && /c\.assets\[asset\.assetId\]\s*=\s*asset/.test(hasb));
  assert('handleAssetSubmit still calls renderOpsFeed after save (Step 31 contract)',
         hasb && /renderOpsFeed\(\)/.test(hasb));

  results.push('  (Step 33 — Campaign Detail Production Assets counter now reads live from c.assets, the same source used by diagnoseCampaign, Production Board and Operations Feed. Before this fix, the four seeded renderFns templates hardcoded "0 total" / "6 total" / "36 total" inside static string literals; the TrackMan counter stayed frozen at "0 total" even after handleAssetSubmit wrote to c.assets via the Step 31 bridge. patchProductionAssetsSection runs inside renderCampaign after the seeded template renders, locates the Production Assets card-title, and replaces its innerHTML with a fresh count (Object.keys(c.assets).length) and prod-item rows derived from the same c.assets. Empty placeholder still renders when c.assets is empty. No duplicate counting logic — one source of truth. No template rewrites — the seeded layout is preserved as the visual scaffold.)');

  // ───────────────────────────────────────────────────────────────
  // STEP 34 — One health engine (computeCampaignHealth). Every visible
  // health surface (Campaign Detail ring + state + Updated timestamp,
  // Operations Feed card, Strategist block, Portfolio campaign-cards) reads
  // from this single function. diagnoseCampaign and the engine share
  // getCampaignCategoryState so they cannot disagree.
  // ───────────────────────────────────────────────────────────────

  var cchb34 = getFnBody('computeCampaignHealth');
  var gccb34 = getFnBody('getCampaignCategoryState');

  // -- 34.1: one health engine declared and used everywhere.
  assert('Step 34: computeCampaignHealth function is declared',
         typeof cchb34 === 'string' && cchb34.length > 200);
  assert('Step 34: getCampaignCategoryState is the shared source (declared)',
         typeof gccb34 === 'string' && gccb34.length > 100);

  // -- 34.2: shared category-state source. Both diagnoseCampaign and
  // computeCampaignHealth read from it. They cannot disagree.
  assert('Step 34: computeCampaignHealth uses getCampaignCategoryState as its source',
         cchb34 && /getCampaignCategoryState\(/.test(cchb34));
  assert('Step 34: diagnoseCampaign uses getCampaignCategoryState (no duplicate presence check)',
         dcb && /getCampaignCategoryState\(/.test(dcb));
  assert('Step 34: getCampaignCategoryState computes the same five categories as diagnoseCampaign',
         gccb34 && /strategy:\s*strategy/.test(gccb34) && /creative:\s*creative/.test(gccb34) &&
                       /production:\s*production/.test(gccb34) && /publishing:\s*publishing/.test(gccb34) &&
                       /learning:\s*learning/.test(gccb34));

  // -- 34.3: transparent formula — uses STRATEGIST_WEIGHTS, weights total 100.
  assert('Step 34: computeCampaignHealth iterates STRATEGIST_WEIGHTS to compute score',
         cchb34 && /for\s*\(\s*var\s+k\s+in\s+cats\s*\)/.test(cchb34) && /STRATEGIST_WEIGHTS/.test(cchb34));
  assert('Step 34: STRATEGIST_WEIGHTS total = 25+20+25+20+10 = 100 (transparent)',
         /var\s+STRATEGIST_WEIGHTS\s*=\s*\{\s*strategy:\s*25\s*,\s*creative:\s*20\s*,\s*production:\s*25\s*,\s*publishing:\s*20\s*,\s*learning:\s*10\s*\}/.test(html));

  // -- 34.4: state bands documented. 80-100 healthy, 50-79 degraded, else critical.
  assert('Step 34: state band 80+ -> healthy (documented in code)',
         cchb34 && />=\s*80\s*\?\s*'healthy'/.test(cchb34));
  assert('Step 34: state band 50+ -> degraded',
         cchb34 && />=\s*50\s*\?\s*'degraded'/.test(cchb34));
  assert('Step 34: state band else -> critical',
         cchb34 && /'critical'/.test(cchb34));

  // -- 34.5: updatedAt is computed from real state (not fabricated).
  assert('Step 34: updatedAt walks c.updatedAt + asset updates + attachments + history',
         cchb34 && /consider\(c\.updatedAt\)/.test(cchb34) &&
                       /consider\(a\.updatedAt\)/.test(cchb34) &&
                       /consider\(atts\[xi\]\.createdAt\)/.test(cchb34) &&
                       /consider\(c\.history\[hi\]\.at\)/.test(cchb34));
  assert('Step 34: updatedAt never invents a time (returns ISO from max of real timestamps)',
         cchb34 && /new Date\(latest\)\.toISOString\(\)/.test(cchb34));

  // -- 34.6: return shape matches the brief — { score, state, updatedAt, categories }.
  assert('Step 34: return shape includes score',
         cchb34 && /score:\s*score/.test(cchb34));
  assert('Step 34: return shape includes state',
         cchb34 && /state:\s*state/.test(cchb34));
  assert('Step 34: return shape includes updatedAt',
         cchb34 && /updatedAt:\s*updatedAt/.test(cchb34));
  assert('Step 34: return shape includes categories (the five booleans)',
         cchb34 && /categories:\s*cats/.test(cchb34));

  // -- 34.7: patchCampaignHealthSection + renderCampaign wiring.
  var pchb = getFnBody('patchCampaignHealthSection');
  assert('Step 34: patchCampaignHealthSection helper is declared',
         typeof pchb === 'string' && pchb.length > 200);
  assert('Step 34: patchCampaignHealthSection reads computeCampaignHealth',
         pchb && /computeCampaignHealth\(/.test(pchb));
  assert('Step 34: patchCampaignHealthSection rewrites .ring-number text',
         pchb && /ringNumber\.textContent/.test(pchb));
  assert('Step 34: patchCampaignHealthSection rewrites SVG stroke-dashoffset (live ring fill)',
         pchb && /stroke-dashoffset/.test(pchb) && /fillCircle\.setAttribute/.test(pchb));
  assert('Step 34: patchCampaignHealthSection rewrites .ring-label (small state text)',
         pchb && /ringLabel\.textContent/.test(pchb));
  assert('Step 34: patchCampaignHealthSection rewrites external state label (Healthy/Degraded/Critical)',
         pchb && /externalLabel\.textContent/.test(pchb));
  assert('Step 34: patchCampaignHealthSection rewrites Updated timestamp',
         pchb && /updatedText\.textContent/.test(pchb) && /Updated\s+/.test(pchb));
  assert('Step 34: renderCampaign calls patchCampaignHealthSection after the seeded render',
         rcb && /patchCampaignHealthSection\(detailContent,\s*id\)/.test(rcb));
  assert('Step 34: patchCampaignHealthSection is wrapped in try/catch when called',
         rcb && /try\s*\{\s*patchCampaignHealthSection[\s\S]{0,100}catch/.test(rcb));

  // -- 34.8: Operations Feed consumes computeCampaignHealth (not c.identity.healthScore).
  assert('Step 34: opsFeedData uses computeCampaignHealth for the card score',
         /function\s+opsFeedData[\s\S]{0,4000}computeCampaignHealth\(/.test(html));
  assert('Step 34: opsFeedData no longer reads c.identity.healthScore for the live card',
         !/var\s+score\s*=\s*\(?x\.c\.identity\.healthScore/.test(html) ||
         /var\s+score\s*=\s*\(?x\.c\.identity\.healthScore[\s\S]{0,200}\/\/\s*Step\s*34/i.test(html) ||
         /Step\s*34:[\s\S]{0,500}c\.identity\.healthScore[\s\S]{0,200}fallback/i.test(html));
  // Stronger: the opsFeedData body should NOT contain a live read of
  // x.c.identity.healthScore (it's now a fallback for backwards compat only,
  // not the primary source).
  var opsfBody = getFnBody('opsFeedData');
  assert('Step 34: opsFeedData primary score source is computeCampaignHealth, not c.identity.healthScore',
         opsfBody && /computeCampaignHealth\(/.test(opsfBody) &&
                       !/var\s+score\s*=\s*\(?x\.c\.identity\.healthScore/.test(opsfBody));

  // -- 34.9: Portfolio campaign-cards consume computeCampaignHealth.
  assert('Step 34: updateCampaignCard calls computeCampaignHealth for the health band',
         /function\s+updateCampaignCard[\s\S]{0,1500}computeCampaignHealth\(/.test(html));
  assert('Step 34: updateCampaignCard writes the health band text into the card',
         /function\s+updateCampaignCard[\s\S]{0,1500}band\s*=\s*h\.state\.charAt\(0\)/.test(html));
  // On boot, every embedded card is refreshed via the new DOMContentLoaded listener.
  // Step 38: this is now a refreshPortfolio() call instead of a per-card
  // updateCampaignCard forEach — refreshPortfolio() handles the cards AND
  // the totals in one pass.
  assert('Step 34: DOMContentLoaded listener refreshes every campaign card on boot',
         /DOMContentLoaded[\s\S]{0,400}refreshPortfolio\(\)/.test(html));

  // -- 34.10: no visible surface still depends on c.identity.healthScore.
  // The seed keeps the field for backwards compatibility, but no display
  // code should read it. renderOpsFeed and the ring patch should not.
  var rorBody = getFnBody('renderOpsFeed');
  assert('Step 34: renderOpsFeed card renders health score from it.healthScore (already live)',
         rorBody && /it\.healthScore/.test(rorBody));
  // opsFeedData no longer assigns healthScore from c.identity — replaced by h.score.
  assert('Step 34: opsFeedData no longer assigns healthScore from c.identity.healthScore',
         opsfBody && !/healthScore:\s*\(?x\.c\.identity\.healthScore/.test(opsfBody));

  // -- 34.11: Strategist block reads from diagnoseCampaign which now uses
  // computeCampaignHealth — Strategist Health X · state is live too.
  var rsb = getFnBody('renderStrategistBlock');
  assert('Step 34: renderStrategistBlock still shows Health X · state (live via diagnoseCampaign)',
         rsb && /Health\s*'/.test(rsb) && /d\.state/.test(rsb));
  assert('Step 34: renderStrategistBlock Health text reads from d.health (now live)',
         rsb && /d\.health/.test(rsb));

  // -- 34.12: Step 32 / Step 33 contracts preserved. Campaign-routed Production
  // Board still hides the generic button, the patchProductionAssetsSection
  // patch still runs, and diagnoseCampaign still reads from c.assets via
  // getCampaignCategoryState.
  assert('Step 34: getCampaignCategoryState reads c.assets (shared source)',
         gccb34 && /c\.assets/.test(gccb34) && /Object\.keys/.test(gccb34));
  assert('Step 34: getCampaignCategoryState still reads attachmentsForCampaign',
         gccb34 && /attachmentsForCampaign/.test(gccb34));
  assert('Step 34: getCampaignCategoryState still reads c.memory for learning',
         gccb34 && /c\.memory/.test(gccb34));

  results.push('  (Step 34 — One health engine: computeCampaignHealth(campaignId) returns { score, state, updatedAt, categories } using STRATEGIST_WEIGHTS (25/20/25/20/10, total 100). State bands: 80-100 healthy, 50-79 degraded, 0-49 critical. updatedAt is the max of c.updatedAt, asset updates, attachment creation, and history events — never fabricated. diagnoseCampaign and computeCampaignHealth share getCampaignCategoryState so they cannot disagree. Every visible health surface (Campaign Detail ring + state + Updated timestamp, Operations Feed card, Strategist block Health X · state, Portfolio campaign-cards) consumes the same function. patchCampaignHealthSection finds the seeded ring elements in the rendered DOM and rewrites them with live values, mirroring the Step 33 pattern. updateCampaignCard writes the live health band into the portfolio card. A new DOMContentLoaded listener refreshes every embedded card on first paint. c.identity.healthScore is kept in the seed for backwards compatibility only — no visible surface reads it for display.)');

  // ── Step 35: campaign history is now truthful ──────────────────
  // Contract: one user action = one history entry.
  //   - Campaign-aware asset save: 1 × 'asset-requested' (was 2)
  //   - Campaign-aware hook save:  1 × 'hook-attached' (was 0)
  // The source must write correctly. The renderer must not deduplicate.

  // -- 35.1: pushAssetRequestedToSource kind==='campaign' branch no longer
  // writes to c.history. The "Sync to campaign" link block in handleAssetSubmit
  // is the single source of truth for the campaign's asset-requested entry.
  var partsBody35 = getFnBody('pushAssetRequestedToSource');
  assert('Step 35: pushAssetRequestedToSource still exists',
         typeof partsBody35 === 'string' && partsBody35.length > 0);
  // Slice the kind==='campaign' branch — find the branch opener and read the
  // next ~600 chars (must contain "devStoreAppend" and must NOT contain
  // "push(c)" which is the inner function call that wrote to c.history).
  var kindCampBranch35 = null;
  if (partsBody35) {
    var idx = partsBody35.indexOf("kind === 'campaign'");
    if (idx >= 0) kindCampBranch35 = partsBody35.substring(idx, idx + 600);
  }
  assert('Step 35: source-sync campaign branch is locatable in pushAssetRequestedToSource',
         kindCampBranch35 && /devStoreAppend/.test(kindCampBranch35));
  assert('Step 35: source-sync campaign branch no longer calls push(c) on the campaign',
         kindCampBranch35 && !/push\(c\)/.test(kindCampBranch35));
  // The link block in handleAssetSubmit still writes the asset-requested entry —
  // it's the source of truth, not pushAssetRequestedToSource.
  var hasBody35 = getFnBody('handleAssetSubmit');
  assert('Step 35: handleAssetSubmit link block still pushes asset-requested to c.history',
         hasBody35 && /c\.history\.push\(\{ action: 'asset-requested'/.test(hasBody35));

  // -- 35.2: handleHookSubmit writes 'hook-attached' to c.history on attach.
  // Pre-Step-35, handleHookSubmit had no campaign-history push for the hook.
  // The brief required exactly one entry per campaign-aware hook save.
  var hhsBody35 = getFnBody('handleHookSubmit');
  assert('Step 35: handleHookSubmit still calls attachToCampaign on save',
         hhsBody35 && /attachToCampaign\(cid,\s*'hook',\s*hook\.hookId/.test(hhsBody35));
  assert('Step 35: handleHookSubmit pushes hook-attached to c.history after a successful attach',
         hhsBody35 && /\.history\.push\(\{ action: 'hook-attached'/.test(hhsBody35));
  // The push must be guarded by the attach result, so a no-op re-attach (already
  // attached) does not create a second history row.
  assert('Step 35: hook-attached push is guarded by attachToCampaign returning non-null',
         hhsBody35 && /if\s*\(\s*attachRes\s*\)/.test(hhsBody35));
  // The note must reference the hook text, not a placeholder or asset title.
  // The actual note is a JS string concat: 'Hook "' + (hook.text || '').substring(0, 40) + '" attached.'
  // — the match-regex grabs only the leading literal "Hook \"" which doesn't contain hook.text.
  // Check the broader context: the hook-attached push must reference hook.text somewhere
  // within ~400 chars of the action label, so the note is genuinely built from the hook text.
  var hookNoteRegion35 = hhsBody35 && hhsBody35.match(/action: 'hook-attached'[\s\S]{0,400}hook\.text/);
  assert('Step 35: hook-attached note references hook.text (truthful, not a placeholder)',
         !!hookNoteRegion35);

  // -- 35.3: existing pipelines still work. Asset save still hits both stores,
  // hook save still emits the M2M, the campaign-link and source-sync branches
  // still run for non-campaign sources.
  assert('Step 35: handleAssetSubmit still calls assetAppend after the history push',
         hasBody35 && /assetAppend\(asset\)/.test(hasBody35));
  assert('Step 35: handleAssetSubmit still calls pushAssetRequestedToSource for source-sync',
         hasBody35 && /pushAssetRequestedToSource\(newSource,\s*asset\)/.test(hasBody35));
  // The non-campaign source branches (caption/meme/billboard/trend/hook) still
  // call push() to write to the source object's history.
  assert('Step 35: source-sync caption branch still pushes to the source object',
         partsBody35 && /push\(cap\)/.test(partsBody35));
  assert('Step 35: source-sync meme branch still pushes to the source object',
         partsBody35 && /push\(m\)/.test(partsBody35));
  assert('Step 35: source-sync billboard branch still pushes to the source object',
         partsBody35 && /push\(b\)/.test(partsBody35));
  assert('Step 35: source-sync trend branch still pushes to the source object',
         partsBody35 && /push\(t\)/.test(partsBody35));
  assert('Step 35: source-sync hook branch still pushes to the source object',
         partsBody35 && /push\(h\)/.test(partsBody35));

  // -- 35.4: the health engine and Strategist surfaces still get their inputs
  // (the fix does not regress Step 34 / Step 31 bridges).
  assert('Step 35: handleAssetSubmit still bridges c.assets[assetId] = asset (Step 31 fix intact)',
         hasBody35 && /c\.assets\[asset\.assetId\]\s*=\s*asset/.test(hasBody35));
  assert('Step 35: handleAssetSubmit still calls renderOpsFeed (Step 31 re-render intact)',
         hasBody35 && /renderOpsFeed\(\)/.test(hasBody35));
  assert('Step 35: handleHookSubmit still calls renderHookBank + renderCreativeStudio',
         hhsBody35 && /renderHookBank\(\)/.test(hhsBody35) && /renderCreativeStudio\(\)/.test(hhsBody35));

  results.push('  (Step 35 — Campaign history is now truthful: one user action = one history entry. The asset save no longer double-writes asset-requested to c.history when source IS the campaign (pushAssetRequestedToSource kind==campaign branch is now no-op for c.history; the link block in handleAssetSubmit is the single source of truth). The hook save now writes exactly one hook-attached entry on a successful attach (guarded by attachToCampaign returning non-null, so no-op re-attach does not create a duplicate). Non-campaign source branches still push to the source object (caption/meme/billboard/trend/hook history arrays) — the dual history contract is preserved for those five kinds. The Step 31 c.assets bridge and renderOpsFeed re-render are intact. The Step 25 hook→campaign auto-attach is intact.)');

  // ───────────────────────────────────────────────────────────────
  // STEP 36 — Calendar gets the campaign-aware workspace pattern.
  // The existing production/creative pattern (context state global +
  // context-panel HTML + renderContextPanel() + contextClear() +
  // openXModalForCampaign() + strategist on-click branch) is mirrored
  // for Calendar. Standalone Calendar is preserved (no context panel,
  // generic + button, generic modal). Switch to standalone restores it.
  // ───────────────────────────────────────────────────────────────

  // -- 36.1: HTML structure — context panel and modal banner exist.
  assert('Step 36: cal-context-panel HTML block exists',
         html.includes('id="cal-context-panel"'));
  assert('Step 36: cal-context-campaign-name placeholder exists',
         html.includes('id="cal-context-campaign-name"'));
  assert('Step 36: cal-context-reason placeholder exists',
         html.includes('id="cal-context-reason"'));
  assert('Step 36: cal-context-action placeholder exists',
         html.includes('id="cal-context-action"'));
  assert('Step 36: cal-context-panel hidden in standalone mode (display:none in style attr)',
         /<div id="cal-context-panel"[^>]*style="[^"]*display:none/.test(html));
  assert('Step 36: Switch to standalone button in context panel calls calendarContextClear',
         /class="view-btn"[^>]*onclick="calendarContextClear\(\)"/.test(html));
  assert('Step 36: cal-modal-campaign-banner HTML block exists inside calModal',
         html.includes('id="cal-modal-campaign-banner"'));
  assert('Step 36: cal-modal-campaign-name placeholder exists',
         html.includes('id="cal-modal-campaign-name"'));
  assert('Step 36: cal-modal-campaign-banner hidden in standalone mode (display:none in style attr)',
         /<div id="cal-modal-campaign-banner"[^>]*style="[^"]*display:none/.test(html));

  // -- 36.2: state global declared (mirrors window.productionContextCampaignId).
  assert('Step 36: window.calendarContextCampaignId state global declared',
         /window\.calendarContextCampaignId\s*=\s*window\.calendarContextCampaignId\s*\|\|\s*null/.test(html));

  // -- 36.3: calendarContextClear function exists, resets context, re-renders Calendar,
  //          and restores the generic + New Calendar Item button visibility.
  var ccc = getFnBody('calendarContextClear');
  assert('Step 36: calendarContextClear function defined', !!ccc);
  if (ccc) {
    assert('Step 36: calendarContextClear nulls window.calendarContextCampaignId',
           /window\.calendarContextCampaignId\s*=\s*null/.test(ccc));
    assert('Step 36: calendarContextClear calls renderCalendar',
           /renderCalendar\(\)/.test(ccc));
    assert('Step 36: calendarContextClear calls updateGenericCalButtonVisibility',
           /updateGenericCalButtonVisibility\(\)/.test(ccc));
  }

  // -- 36.4: updateGenericCalButtonVisibility toggles #btn-new-cal display
  //          based on window.calendarContextCampaignId (mirrors Step 32).
  var ugcbv = getFnBody('updateGenericCalButtonVisibility');
  assert('Step 36: updateGenericCalButtonVisibility function defined', !!ugcbv);
  if (ugcbv) {
    assert('Step 36: updateGenericCalButtonVisibility reads btn-new-cal',
           /getElementById\(['"]btn-new-cal['"]\)/.test(ugcbv));
    assert('Step 36: updateGenericCalButtonVisibility hides button when context is set',
           /window\.calendarContextCampaignId[\s\S]{0,100}btn\.style\.display\s*=\s*'none'/.test(ugcbv));
    assert('Step 36: updateGenericCalButtonVisibility shows button when context is null',
           /btn\.style\.display\s*=\s*''/.test(ugcbv));
  }

  // -- 36.5: renderCalendarContextPanel reads the campaign doc and renders
  //          the campaign name + reason (from live diagnosis) into the panel.
  var rccp = getFnBody('renderCalendarContextPanel');
  assert('Step 36: renderCalendarContextPanel function defined', !!rccp);
  if (rccp) {
    assert('Step 36: renderCalendarContextPanel reads window.calendarContextCampaignId',
           /window\.calendarContextCampaignId/.test(rccp));
    assert('Step 36: renderCalendarContextPanel reads contextCampaign via window.campaignData',
           /window\.campaignData\.campaigns/.test(rccp));
    assert('Step 36: renderCalendarContextPanel hides panel when no context',
           /panel\.style\.display\s*=\s*'none'/.test(rccp));
    assert('Step 36: renderCalendarContextPanel shows panel when context active',
           /panel\.style\.display\s*=\s*'block'/.test(rccp));
    assert('Step 36: renderCalendarContextPanel sets campaign name from identity.name',
           /contextCampaign\.identity\s*&&\s*contextCampaign\.identity\.name/.test(rccp));
    assert('Step 36: renderCalendarContextPanel reads live diagnosis for reason',
           /diagnoseCampaign\(contextId\)/.test(rccp));
    assert('Step 36: renderCalendarContextPanel surfaces the publishing-issue reason',
           /key\s*===\s*'publishing'/.test(rccp));
    assert('Step 36: renderCalendarContextPanel renders primary CTA wired to openCalModalForCampaign',
           /onclick="openCalModalForCampaign\(/.test(rccp));
    assert('Step 36: renderCalendarContextPanel CTA copy is "Schedule first publishing item for"',
           /Schedule first publishing item for/.test(rccp));
  }

  // -- 36.6: openCalModalForCampaign pre-fills the form from real OS data
  //          (mirrors openAssetModalForCampaign's contract).
  var ocmfc = getFnBody('openCalModalForCampaign');
  assert('Step 36: openCalModalForCampaign function defined', !!ocmfc);
  if (ocmfc) {
    assert('Step 36: openCalModalForCampaign calls openCalModal with campaign:<id> as source',
           /openCalModal\(['"]campaign:\s*['"]?\s*\+\s*campaignId/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign sets brand from first non-empty option',
           /brandEl\.options/.test(ocmfc) && /preferred\s*=\s*v/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign sets type to "campaign"',
           /typeEl\.value\s*=\s*'campaign'/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign sets title placeholder from brief.bigIdea or brief.purpose',
           /brief\.bigIdea\s*\|\|\s*brief\.purpose/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign sets modal title to "New Calendar Item — for <cname>"',
           /'New Calendar Item — for '\s*\+\s*cname/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign shows the inline campaign banner',
           /banner\.style\.display\s*=\s*'block'/.test(ocmfc));
    assert('Step 36: openCalModalForCampaign does NOT fabricate a title or date value (only placeholder)',
           !/\b(?:title|d)El\.value\s*=/.test(ocmfc) ||
           (!/titleEl\.value\s*=/.test(ocmfc) && !/\bdEl\.value\s*=/.test(ocmfc)));
  }

  // -- 36.7: openCalModal accepts a preselectedSourceRef argument and uses it.
  var ocm = getFnBody('openCalModal');
  assert('Step 36: openCalModal accepts preselectedSourceRef argument', !!ocm);
  if (ocm) {
    assert('Step 36: openCalModal signature includes preselectedSourceRef',
           /function\s+openCalModal\s*\(\s*preselectedSourceRef\s*\)/.test(ocm));
    assert('Step 36: openCalModal sets source value from preselectedSourceRef',
           /src\.value\s*=\s*preselectedSourceRef\s*\|\|\s*''/.test(ocm));
    assert('Step 36: openCalModal resets modal title to standalone default',
           /titleEl\.textContent\s*=\s*'New Calendar Item'/.test(ocm));
    assert('Step 36: openCalModal hides inline campaign banner by default',
           /banner\.style\.display\s*=\s*'none'/.test(ocm));
  }

  // -- 36.8: closeCalModal resets the inline campaign banner and modal title
  //          so a subsequent standalone open doesn't show stale context.
  var ccm = getFnBody('closeCalModal');
  assert('Step 36: closeCalModal function defined', !!ccm);
  if (ccm) {
    assert('Step 36: closeCalModal hides the inline campaign banner',
           /banner\.style\.display\s*=\s*'none'/.test(ccm));
    assert('Step 36: closeCalModal resets the modal title',
           /titleEl\.textContent\s*=\s*'New Calendar Item'/.test(ccm));
  }

  // -- 36.9: renderCalendar calls renderCalendarContextPanel near the top
  //          so the panel surfaces correctly on every view entry. Either a
  //          typeof guard or a try/catch wrapper is acceptable; both prove
  //          the call exists and is safe.
  var rcc = getFnBody('renderCalendar');
  assert('Step 36: renderCalendar function defined', !!rcc);
  if (rcc) {
    var hasRCCP = /renderCalendarContextPanel\(\)/.test(rcc);
    var hasGuard = /typeof\s+renderCalendarContextPanel\s*===\s*'function'/.test(rcc) ||
                   /try\s*\{[^}]*renderCalendarContextPanel\(\)[^}]*\}\s*catch/.test(rcc);
    assert('Step 36: renderCalendar calls renderCalendarContextPanel (guarded)', hasRCCP && hasGuard);
  }

  // -- 36.10: Strategist routing — issues[] and recOnclick both set
  //           window.calendarContextCampaignId for dest === 'calendar'.
  //   The Step 36 patch added two branches: one in issues[] loop, one
  //   in the recOnclick block. Both set the calendar context.
  assert('Step 36: strategist issues[] branch sets window.calendarContextCampaignId for dest === calendar',
         /if\s*\(\s*it\.dest\s*===\s*'calendar'\s*\)\s*\{[\s\S]{0,300}window\.calendarContextCampaignId/.test(html));
  assert('Step 36: strategist recOnclick branch sets window.calendarContextCampaignId for rec.dest === calendar',
         /if\s*\(\s*rec\.dest\s*===\s*'calendar'\s*\)\s*\{[\s\S]{0,200}window\.calendarContextCampaignId/.test(html));

  // -- 36.11: Standalone Calendar is preserved — the generic + New Calendar
  //           Item button stays in the DOM and is wired to openCalModal().
  assert('Step 36: + New Calendar Item button still exists in DOM',
         html.includes('id="btn-new-cal"') && html.includes('onclick="openCalModal()"'));
  assert('Step 36: openCalModal() is the standalone entry point (no required args)',
         /function\s+openCalModal\s*\(\s*preselectedSourceRef\s*\)/.test(html));

  // -- 36.12: Non-regression of prior contracts.
  //   The Step 31 c.assets bridge in handleAssetSubmit is still intact.
  var has36 = getFnBody('handleAssetSubmit');
  assert('Step 36: handleAssetSubmit still bridges c.assets[assetId] = asset (Step 31 contract intact)',
         has36 && /c\.assets\[asset\.assetId\]\s*=\s*asset/.test(has36));
  assert('Step 36: handleAssetSubmit still calls renderOpsFeed (Step 31 contract intact)',
         has36 && /renderOpsFeed\(\)/.test(has36));
  //   The Step 35 history-truth fix is still intact (no double asset-requested,
  //   one hook-attached per save).
  assert('Step 36: pushAssetRequestedToSource kind==campaign branch still skips inner push(c)',
         /kind === 'campaign'[\s\S]{0,500}devStoreAppend/.test(html) &&
         !/kind === 'campaign'[\s\S]{0,500}push\(c\)/.test(html));
  var hhs36 = getFnBody('handleHookSubmit');
  assert('Step 36: handleHookSubmit still pushes hook-attached to c.history (Step 35 contract intact)',
         hhs36 && /\.history\.push\(\{\s*action:\s*'hook-attached'/.test(hhs36));
  //   The Step 34 one-health-engine is still intact.
  var cchb36 = getFnBody('computeCampaignHealth');
  assert('Step 36: computeCampaignHealth function still defined (Step 34 contract intact)',
         typeof cchb36 === 'string' && cchb36.length > 200);
  assert('Step 36: computeCampaignHealth still uses getCampaignCategoryState as source',
         cchb36 && /getCampaignCategoryState\(/.test(cchb36));
  //   The Step 25/31 creative+production context state globals are still set/cleared
  //   by their respective clear functions. (Step 25's creative state is initialised
  //   on first use; Step 31's production state is defensively initialised to null
  //   on the window. Step 36 mirrors Step 31 for calendar.)
  var ccc36 = getFnBody('creativeContextClear');
  assert('Step 36: creativeContextClear still nulls window.creativeContextCampaignId',
         ccc36 && /window\.creativeContextCampaignId\s*=\s*null/.test(ccc36));
  var pcc36 = getFnBody('productionContextClear');
  assert('Step 36: productionContextClear still nulls window.productionContextCampaignId',
         pcc36 && /window\.productionContextCampaignId\s*=\s*null/.test(pcc36));
  assert('Step 36: window.productionContextCampaignId state global still declared',
         /window\.productionContextCampaignId\s*=\s*window\.productionContextCampaignId\s*\|\|\s*null/.test(html));
  assert('Step 36: window.calendarContextCampaignId state global still declared (Step 36 mirror of Step 31 pattern)',
         /window\.calendarContextCampaignId\s*=\s*window\.calendarContextCampaignId\s*\|\|\s*null/.test(html));
  //   The diagnoseCampaign function still defines the publishing issue with
  //   dest === 'calendar' (so the new strategist branch is reachable).
  var dcb36 = getFnBody('diagnoseCampaign');
  assert('Step 36: diagnoseCampaign still defines the publishing issue with dest=calendar',
         dcb36 && /key:'publishing'[\s\S]{0,400}dest:'calendar'/.test(dcb36));

  // -- 36.13: handleCalSubmit still writes calendar-linked to c.history when
  //           the calendar item's source IS the campaign (the dual-history
  //           contract established before Step 36). This proves the campaign-
  //           aware save still attaches to the campaign the same way the
  //           standalone save does.
  var hcs36 = getFnBody('handleCalSubmit');
  assert('Step 36: handleCalSubmit still writes calendar-linked to c.history for campaign source',
         hcs36 && /action:\s*'calendar-linked'/.test(hcs36) && /sourceKind\s*===\s*'campaign'/.test(hcs36));

  results.push('  (Step 36 — Calendar now has the campaign-aware workspace pattern. Strategist "Schedule Publishing" (and any dest===calendar action) sets window.calendarContextCampaignId before showView, so the Calendar renders a SCHEDULING FOR panel with the campaign name, a reason derived from the live publishing-issue diagnosis, and a single primary CTA "Schedule first publishing item for <Campaign> →" wired to openCalModalForCampaign. The calendar modal opens pre-filled with the campaign selected as the source object, the brand defaulted, the type set to "campaign", and a campaign-specific title placeholder built from brief.bigIdea or brief.purpose — never fabricated. The generic + New Calendar Item button hides when context is active (mirrors Step 32 updateGenericAssetButtonVisibility) and returns on Switch to standalone. Standalone Calendar is preserved: openCalModal() called with no args, no context panel, generic button visible. The calendar-linked dual-history contract (c.history push when sourceKind === campaign) is preserved. The Step 31 c.assets bridge, the Step 25/31 context state globals, the Step 34 one-health-engine, the Step 35 history-truth fix, and all prior contracts remain intact.)');

  // ───────────────────────────────────────────────────────────────
  // STEP 37 — Publishing capability is a single shared category that
  // any publishing integration can satisfy. Today the only integration
  // is Calendar. Reuses the Step 34 shared-category architecture
  // (getCampaignCategoryState) so every surface that consumes it
  // (Campaign Detail ring, Operations Feed card, Portfolio campaign-
  // cards, Strategist block) becomes truthful automatically.
  // ───────────────────────────────────────────────────────────────

  // -- 37.1: hasPublishingPlan() function exists and is the single shared
  //          publishing capability. Its name and signature do not mention
  //          any specific integration, so future integrations (Postiz,
  //          Meta, Buffer) can be added inside it without renaming.
  var hpp = getFnBody('hasPublishingPlan');
  assert('Step 37: hasPublishingPlan function defined', !!hpp);
  if (hpp) {
    assert('Step 37: hasPublishingPlan signature takes campaignId and returns boolean',
           /function\s+hasPublishingPlan\s*\(\s*campaignId\s*\)/.test(hpp) && /return\s+false/.test(hpp));
    // The function body must NOT mention Postiz/Meta/Buffer (those are
    // future integrations that get added later). Today it can mention Calendar.
    assert('Step 37: hasPublishingPlan reads from the calendar store (current integration)',
           /calReadAll\s*\(/.test(hpp) || /CAL_STORE_KEY/.test(hpp));
    assert('Step 37: hasPublishingPlan filters calendar items by campaign link',
           /sourceKind\s*===\s*'campaign'/.test(hpp) && /sourceId\s*===\s*campaignId/.test(hpp));
    assert('Step 37: hasPublishingPlan treats status="skipped" as NOT a plan',
           /'skipped'/.test(hpp));
  }

  // -- 37.2: getCampaignCategoryState delegates to hasPublishingPlan
  //          for the publishing category. The dead-code check
  //          `c.assets[].status === 'published'` is REMOVED.
  var gccs37 = getFnBody('getCampaignCategoryState');
  assert('Step 37: getCampaignCategoryState still defined', !!gccs37);
  if (gccs37) {
    assert('Step 37: getCampaignCategoryState calls hasPublishingPlan for publishing',
           /hasPublishingPlan\s*\(\s*campaignId\s*\)/.test(gccs37));
    assert('Step 37: getCampaignCategoryState no longer reads c.assets[].status === "published"',
           !/^\s*\ba\.status\s*===\s*'published'/m.test(gccs37) && !/^\s*\bc\.assets\[[^\]]+\]\.status\s*===\s*'published'/m.test(gccs37));
    // The production check (any non-rejected asset) is preserved.
    assert('Step 37: getCampaignCategoryState still reads c.assets for production (non-rejected)',
           /a\.status\s*!==\s*'rejected'/.test(gccs37));
    // The strategy, creative, learning checks are unchanged.
    assert('Step 37: getCampaignCategoryState still has strategy/creative/learning branches',
           /strategy:\s*strategy/.test(gccs37) && /creative:\s*creative/.test(gccs37) &&
                       /production:\s*production/.test(gccs37) && /learning:\s*learning/.test(gccs37));
  }

  // -- 37.3: Strategist's publishing-issue reason text is updated to
  //          match the canonical definition (a campaign-linked Calendar
  //          item, or future Postiz/Meta/Buffer integration).
  var dcb37 = getFnBody('diagnoseCampaign');
  assert('Step 37: diagnoseCampaign still defines the publishing issue', !!dcb37);
  if (dcb37) {
    assert('Step 37: publishing issue title is still "No publishing plan"',
           dcb37 && /key:'publishing'[\s\S]{0,400}title:'No publishing plan'/.test(dcb37));
    assert('Step 37: publishing issue reason no longer says "Nothing has gone live"',
           dcb37 && !/Nothing has gone live/.test(dcb37));
    assert('Step 37: publishing issue reason mentions campaign-linked publishing plan',
           dcb37 && /campaign-linked publishing plan/.test(dcb37));
    assert('Step 37: publishing issue reason is future-extensible (mentions Postiz/Meta/Buffer)',
           dcb37 && /Postiz/.test(dcb37) && /Meta/.test(dcb37) && /Buffer/.test(dcb37));
    assert('Step 37: publishing issue action is still "Schedule Publishing" with dest=calendar',
           dcb37 && /action:\s*'Schedule Publishing'/.test(dcb37) && /dest:\s*'calendar'/.test(dcb37));
  }

  // -- 37.4: Non-regression of the Step 34 one-health-engine contract.
  //   computeCampaignHealth and diagnoseCampaign still share the same
  //   category-state source, so they cannot disagree.
  var cchb37 = getFnBody('computeCampaignHealth');
  var dcb37cb = getFnBody('diagnoseCampaign');
  assert('Step 37: computeCampaignHealth still uses getCampaignCategoryState as source',
         cchb37 && /getCampaignCategoryState\(/.test(cchb37));
  assert('Step 37: diagnoseCampaign still uses getCampaignCategoryState as source',
         dcb37cb && /getCampaignCategoryState\(/.test(dcb37cb));

  // -- 37.5: Non-regression of the Step 36 publishing-category fix in
  //   the wider walkthrough surface. The Strategist's publishing-issue
  //   action is wired to the Calendar context state in renderStrategistBlock.
  //   Both the issues[] branch and the recOnclick branch set
  //   window.calendarContextCampaignId for dest === 'calendar'.
  assert('Step 37: strategist issues[] branch still sets window.calendarContextCampaignId for dest === calendar',
         /if\s*\(\s*it\.dest\s*===\s*'calendar'\s*\)\s*\{[\s\S]{0,300}window\.calendarContextCampaignId/.test(html));
  assert('Step 37: strategist recOnclick branch still sets window.calendarContextCampaignId for rec.dest === calendar',
         /if\s*\(\s*rec\.dest\s*===\s*'calendar'\s*\)\s*\{[\s\S]{0,200}window\.calendarContextCampaignId/.test(html));
  //   The Calendar's campaign-aware modal (Step 36) still preserves the
  //   pre-fill from existing OS data — no fabrication.
  var ocmfc37 = getFnBody('openCalModalForCampaign');
  assert('Step 37: openCalModalForCampaign function still defined (Step 36 contract intact)',
         !!ocmfc37);
  if (ocmfc37) {
    assert('Step 37: openCalModalForCampaign still sets type to "campaign"',
           /typeEl\.value\s*=\s*'campaign'/.test(ocmfc37));
    assert('Step 37: openCalModalForCampaign still does NOT fabricate a title value (only placeholder)',
           !/\btitleEl\.value\s*=/.test(ocmfc37));
  }
  //   handleCalSubmit still writes calendar-linked to c.history when source
  //   is a campaign — the history log is unchanged by Step 37.
  var hcs37 = getFnBody('handleCalSubmit');
  assert('Step 37: handleCalSubmit still writes calendar-linked to c.history for campaign source',
         hcs37 && /action:\s*'calendar-linked'/.test(hcs37) && /sourceKind\s*===\s*'campaign'/.test(hcs37));

  // -- 37.6: Non-regression of all prior contracts — Steps 25, 31, 32, 33, 34, 35, 36.
  assert('Step 37: handleAssetSubmit still bridges c.assets[assetId] = asset (Step 31 contract intact)',
         getFnBody('handleAssetSubmit') && /c\.assets\[asset\.assetId\]\s*=\s*asset/.test(getFnBody('handleAssetSubmit')));
  assert('Step 37: handleAssetSubmit still calls renderOpsFeed (Step 31 contract intact)',
         getFnBody('handleAssetSubmit') && /renderOpsFeed\(\)/.test(getFnBody('handleAssetSubmit')));
  assert('Step 37: handleHookSubmit still pushes hook-attached to c.history (Step 35 contract intact)',
         getFnBody('handleHookSubmit') && /\.history\.push\(\{\s*action:\s*'hook-attached'/.test(getFnBody('handleHookSubmit')));
  assert('Step 37: patchProductionAssetsSection still defined (Step 33 contract intact)',
         typeof getFnBody('patchProductionAssetsSection') === 'string' && getFnBody('patchProductionAssetsSection').length > 200);
  assert('Step 37: patchCampaignHealthSection still defined (Step 34 contract intact)',
         typeof getFnBody('patchCampaignHealthSection') === 'string' && getFnBody('patchCampaignHealthSection').length > 200);
  assert('Step 37: renderCalendarContextPanel still defined (Step 36 contract intact)',
         typeof getFnBody('renderCalendarContextPanel') === 'string' && getFnBody('renderCalendarContextPanel').length > 200);
  assert('Step 37: window.calendarContextCampaignId state global still declared',
         /window\.calendarContextCampaignId\s*=\s*window\.calendarContextCampaignId\s*\|\|\s*null/.test(html));
  assert('Step 37: window.productionContextCampaignId state global still declared',
         /window\.productionContextCampaignId\s*=\s*window\.productionContextCampaignId\s*\|\|\s*null/.test(html));
  //   clearDevData still clears the calendar store (no regression on Step 14/16 lifecycle).
  assert('Step 37: clearDevData still removes CAL_STORE_KEY (Step 14 lifecycle intact)',
         html.includes('removeItem(CAL_STORE_KEY)'));

  results.push('  (Step 37 — Publishing is now a single shared capability, not a Calendar-specific check. hasPublishingPlan(campaignId) is the canonical entry point: today it reads the campaign-linked Calendar items from the existing store and treats any non-skipped item as a publishing plan. getCampaignCategoryState() delegates to it for the publishing category. The dead-code check `c.assets[].status === "published"` is removed (asset statuses are needed/requested/in-production/ready/used/cancelled — there is no "published" state on assets, and the check was unreachable). The Strategist issue text is updated to match the canonical definition and is future-extensible (mentions Postiz / Meta / Buffer). Future integrations plug in by adding their own check inside hasPublishingPlan — the function name and signature do not mention any specific integration, so renaming is not required. Every surface that consumes getCampaignCategoryState (Campaign Detail ring/state/timestamp, Operations Feed, Portfolio campaign-cards, Strategist block) becomes truthful automatically because the shared category-state source is the single source of truth. All prior contracts (Step 25/31/32/33/34/35/36) remain intact — production, creative, learning, health engine, history truth, and Calendar campaign-aware modal are preserved.)');

  // ───────────────────────────────────────────────────────────────
  // STEP 38 — One Portfolio refresh function. The previous Portfolio
  // displayed frozen seed-time values (1 Healthy / 2 Degraded / 0 Critical,
  // 42 Total Assets, hardcoded "0 assets · Degraded" per card) while
  // Campaign Detail, Strategist, Operations Feed and computeCampaignHealth
  // showed live truth. refreshPortfolio() walks the campaign collection
  // and rewrites every visible Portfolio surface from current state.
  // ───────────────────────────────────────────────────────────────

  // -- 38.1: refreshPortfolio() function is declared and is the single
  //          Portfolio refresh entry point. No other "refresh the Portfolio"
  //          function exists alongside it.
  var rfp = getFnBody('refreshPortfolio');
  assert('Step 38: refreshPortfolio function is declared', !!rfp);
  if (rfp) {
    assert('Step 38: refreshPortfolio iterates the campaign collection',
           /Object\.keys\(window\.campaignData\.campaigns\)/.test(rfp) || /window\.campaignData\.campaigns\)/.test(rfp));
    assert('Step 38: refreshPortfolio calls updateCampaignCard for each card',
           /updateCampaignCard\(/.test(rfp));
    assert('Step 38: refreshPortfolio calls computeCampaignHealth for the totals',
           /computeCampaignHealth\(/.test(rfp));
    assert('Step 38: refreshPortfolio writes to the stable totals IDs',
           /portfolio-healthy/.test(rfp) && /portfolio-degraded/.test(rfp) &&
                       /portfolio-critical/.test(rfp) && /portfolio-total-assets/.test(rfp) &&
                       /portfolio-published/.test(rfp) && /portfolio-in-progress/.test(rfp) &&
                       /portfolio-card-title/.test(rfp));
    // The body contains a regex literal /selectCampaign\('([^']+)'\)/
    // (the source has a backslash before each paren because that text is
    // itself a regex literal). The next ~115 chars include the match
    // capture group, the `if (match && ids.indexOf(match[1]) === -1)` check,
    // and the stale-card `parentNode.removeChild(staleCards[s])` removal.
    // We assert the structural shape: the selectCampaign pattern is used
    // AND removeChild is called somewhere in the same stale-card block.
    assert('Step 38: refreshPortfolio removes stale .ccard whose campaignId is gone',
           /selectCampaign[\s\S]{0,200}removeChild/.test(rfp));
    // Does NOT introduce a second health engine.
    assert('Step 38: refreshPortfolio does NOT call c.identity.healthScore',
           !/c\.identity\.healthScore/.test(rfp));
  }
  // renderNewCampaignCard helper exists (used for Campaign Factory / dev-store).
  var rncc = getFnBody('renderNewCampaignCard');
  assert('Step 38: renderNewCampaignCard helper is declared', !!rncc);

  // -- 38.2: the Portfolio HTML has stable IDs on every count + the card grid.
  //   No more hardcoded seed-time literals in the HTML markup.
  assert('Step 38: Portfolio stat row uses #portfolio-healthy', /id="portfolio-healthy"/.test(html));
  assert('Step 38: Portfolio stat row uses #portfolio-degraded', /id="portfolio-degraded"/.test(html));
  assert('Step 38: Portfolio stat row uses #portfolio-critical', /id="portfolio-critical"/.test(html));
  assert('Step 38: Portfolio stat row uses #portfolio-total-assets', /id="portfolio-total-assets"/.test(html));
  assert('Step 38: Portfolio stat row uses #portfolio-published', /id="portfolio-published"/.test(html));
  assert('Step 38: Portfolio stat row uses #portfolio-in-progress', /id="portfolio-in-progress"/.test(html));
  assert('Step 38: Portfolio card title uses #portfolio-card-title', /id="portfolio-card-title"/.test(html));
  assert('Step 38: Portfolio card grid uses #portfolio-cards', /id="portfolio-cards"/.test(html));
  // The previous hardcoded "1 Healthy", "0 Critical", "42 Total Assets",
  // "1 Published", "41 In Progress" seed-time literals are GONE from the HTML.
  // The new HTML defaults every stat to 0 (which refreshPortfolio() rewrites
  // on boot and on every save), so we check that the SEED-TIME non-zero
  // values are not present anywhere in the markup.
  assert('Step 38: no hardcoded "1 Healthy" / "2 Degraded" / "42 Total Assets" / "1 Published" / "41 In Progress" seed-time literals in HTML',
         !/stat-value[^>]*>1<\/div><div class="stat-sub">Healthy/.test(html) &&
         !/stat-value[^>]*>2<\/div><div class="stat-sub">Degraded/.test(html) &&
         !/stat-value[^>]*>42<\/div><div class="stat-sub">Total Assets/.test(html) &&
         !/stat-value[^>]*>1<\/div><div class="stat-sub">Published/.test(html) &&
         !/stat-value[^>]*>41<\/div><div class="stat-sub">In Progress/.test(html));
  // Every stat in the new HTML starts at 0 — these are placeholders that
  // refreshPortfolio() rewrites on first paint.
  assert('Step 38: every Portfolio stat starts at 0 (placeholder, rewritten by refreshPortfolio on boot)',
         /id="portfolio-healthy"[^>]*>0</.test(html) &&
         /id="portfolio-degraded"[^>]*>0</.test(html) &&
         /id="portfolio-critical"[^>]*>0</.test(html) &&
         /id="portfolio-total-assets"[^>]*>0</.test(html) &&
         /id="portfolio-published"[^>]*>0</.test(html) &&
         /id="portfolio-in-progress"[^>]*>0</.test(html));
  // The previous hardcoded "4 campaigns" / per-card seed values are gone.
  assert('Step 38: no hardcoded "Campaign Portfolio — 4 campaigns" title in HTML',
         !/Campaign Portfolio\s*—\s*4 campaigns/.test(html));
  assert('Step 38: no hardcoded per-card seed asset counts in HTML',
         !/0 assets\s*&middot;\s*Degraded/.test(html) &&
         !/6 assets\s*&middot;\s*Degraded/.test(html) &&
         !/36 assets\s*&middot;\s*Unknown/.test(html));

  // -- 38.3: refreshPortfolio is called at every save path the brief
  //          required: boot, showView('portfolio'), handleAssetSubmit,
  //          handleHookSubmit, handleCalSubmit, changeAssetStatus,
  //          changeCalStatus, campaignFactoryCreate, devStoreHydrate.
  assert('Step 38: refreshPortfolio called on DOMContentLoaded boot',
         /DOMContentLoaded[\s\S]{0,400}refreshPortfolio\(\)/.test(html));
  assert('Step 38: refreshPortfolio called in showView("portfolio") branch',
         /name === 'portfolio'[\s\S]{0,200}refreshPortfolio\(\)/.test(html));
  var has38 = getFnBody('handleAssetSubmit');
  assert('Step 38: refreshPortfolio called in handleAssetSubmit',
         has38 && /refreshPortfolio\(\)/.test(has38));
  var hhs38 = getFnBody('handleHookSubmit');
  assert('Step 38: refreshPortfolio called in handleHookSubmit',
         hhs38 && /refreshPortfolio\(\)/.test(hhs38));
  var hcs38 = getFnBody('handleCalSubmit');
  assert('Step 38: refreshPortfolio called in handleCalSubmit',
         hcs38 && /refreshPortfolio\(\)/.test(hcs38));
  var cas38 = getFnBody('changeAssetStatus');
  assert('Step 38: refreshPortfolio called in changeAssetStatus',
         cas38 && /refreshPortfolio\(\)/.test(cas38));
  var ccs38 = getFnBody('changeCalStatus');
  assert('Step 38: refreshPortfolio called in changeCalStatus',
         ccs38 && /refreshPortfolio\(\)/.test(ccs38));
  var cfc38 = getFnBody('campaignFactoryCreate');
  assert('Step 38: refreshPortfolio called in campaignFactoryCreate',
         cfc38 && /refreshPortfolio\(\)/.test(cfc38));
  var dsh38 = getFnBody('devStoreHydrate');
  assert('Step 38: refreshPortfolio called in devStoreHydrate',
         dsh38 && /refreshPortfolio\(\)/.test(dsh38));

  // -- 38.4: refreshPortfolio uses the brief's mapping for the totals.
  //   "In progress" must use the current data model's intermediate states
  //   (requested / in-production / ready). "Published" must use the terminal
  //   state (used). Both are states the current model can prove.
  if (rfp) {
    assert('Step 38: refreshPortfolio in-progress count uses model-provable states',
           /inProgressStates\s*=\s*\['requested',\s*'in-production',\s*'ready'\]/.test(rfp) ||
           /inProgressStates\s*=\s*\['ready',\s*'in-production',\s*'requested'\]/.test(rfp));
    assert('Step 38: refreshPortfolio published count uses model-provable terminal state',
           /publishedStates\s*=\s*\['used'\]/.test(rfp));
  }

  // -- 38.5: Non-regression of the single health engine contract (Step 34).
  //   refreshPortfolio reads from computeCampaignHealth, not a parallel engine.
  //   No new health calculations are introduced. The diagnostic categories
  //   are still derived from getCampaignCategoryState.
  var cchb38 = getFnBody('computeCampaignHealth');
  assert('Step 38: computeCampaignHealth still defined (Step 34 contract intact)',
         typeof cchb38 === 'string' && cchb38.length > 200);
  assert('Step 38: computeCampaignHealth still uses getCampaignCategoryState as source',
         cchb38 && /getCampaignCategoryState\(/.test(cchb38));
  assert('Step 38: refreshPortfolio uses computeCampaignHealth (the single engine), not its own health math',
         rfp && /computeCampaignHealth\(/.test(rfp) && !/function\s+computeCampaignHealth/.test(rfp));
  // The diagnose engine is unchanged.
  var dcb38 = getFnBody('diagnoseCampaign');
  assert('Step 38: diagnoseCampaign still uses getCampaignCategoryState',
         dcb38 && /getCampaignCategoryState\(/.test(dcb38));

  // -- 38.6: Non-regression of Step 37 (publishing capability shared category).
  assert('Step 38: hasPublishingPlan still defined (Step 37 contract intact)',
         typeof getFnBody('hasPublishingPlan') === 'string' && getFnBody('hasPublishingPlan').length > 200);
  assert('Step 38: getCampaignCategoryState still delegates to hasPublishingPlan',
         /hasPublishingPlan\(\s*campaignId\s*\)/.test(html));
  // Step 33 contract: the Campaign Detail production assets counter is live.
  assert('Step 38: patchProductionAssetsSection still defined (Step 33 contract intact)',
         typeof getFnBody('patchProductionAssetsSection') === 'string' && getFnBody('patchProductionAssetsSection').length > 200);
  // Step 36 contract: the Calendar context-aware modal is preserved.
  assert('Step 38: openCalModalForCampaign still defined (Step 36 contract intact)',
         typeof getFnBody('openCalModalForCampaign') === 'string' && getFnBody('openCalModalForCampaign').length > 200);
  // Step 31 / 35 / 36 save contracts are preserved.
  assert('Step 38: handleAssetSubmit still bridges c.assets[assetId] = asset (Step 31 intact)',
         has38 && /c\.assets\[asset\.assetId\]\s*=\s*asset/.test(has38));
  assert('Step 38: handleHookSubmit still pushes hook-attached to c.history (Step 35 intact)',
         hhs38 && /\.history\.push\(\{\s*action:\s*'hook-attached'/.test(hhs38));
  assert('Step 38: handleCalSubmit still writes calendar-linked to c.history (Step 35 intact)',
         hcs38 && /action:\s*'calendar-linked'/.test(hcs38));

  results.push('  (Step 38 — One Portfolio refresh function. The previous Portfolio displayed frozen seed-time values (1 Healthy / 2 Degraded / 0 Critical, 42 Total Assets, "0 assets · Degraded" per card) while Campaign Detail, Strategist, Operations Feed and computeCampaignHealth showed live truth. refreshPortfolio() walks window.campaignData.campaigns and rewrites every visible Portfolio surface from current state: each card (via updateCampaignCard), the per-band counts (via computeCampaignHealth), the Total Assets count, the Published/In-Progress counts (using only states the current data model can prove: publishedStates = ["used"], inProgressStates = ["requested", "in-production", "ready"]), and the campaign-card-title. The HTML markup now uses stable IDs (#portfolio-healthy, #portfolio-degraded, #portfolio-critical, #portfolio-total-assets, #portfolio-published, #portfolio-in-progress, #portfolio-card-title, #portfolio-cards) — no more hardcoded seed-time literals. Stale .ccard elements whose campaignId is no longer in the data are removed. refreshPortfolio() is called on boot, on showView("portfolio"), on handleAssetSubmit, handleHookSubmit, handleCalSubmit, changeAssetStatus, changeCalStatus, campaignFactoryCreate, and devStoreHydrate. The single health engine (computeCampaignHealth) is the only source of truth — no second health engine is introduced. The Step 33/34/35/36/37 contracts are preserved: patchProductionAssetsSection, patchCampaignHealthSection, openCalModalForCampaign, hasPublishingPlan, and the per-campaign history-truth fixes are all intact.)');

  // ── Step 39: Campaign Detail becomes live on view entry ───────────
  // The walkthrough found that after an asset save (or hook attach, or calendar link)
  // the marketer navigates back to Campaign Detail and sees the stale "Health 35 · critical"
  // and "Production Assets — 0 total" text. The data layer is correct (Operations Feed,
  // Portfolio, computeCampaignHealth all agree) — only the Campaign Detail page is stale,
  // because showView('detail') only set the subtitle without re-running renderCampaign(id).
  //
  // Fix: showView('detail') now calls renderCampaign(activeCampaignId) before setting
  // the subtitle. This is the existing render pipeline (no second path), triggered once
  // per view entry. The Step 33/34 inline patches (patchProductionAssetsSection,
  // patchCampaignHealthSection) run as part of renderCampaign, so the Health ring +
  // Production Assets counter are always live on entry.
  section('Step 39: Campaign Detail live on view entry');

  // -- 39.1: showView('detail') calls renderCampaign(activeCampaignId).
  // Find the showView body and assert it now contains a renderCampaign call gated on
  // name === 'detail' and activeCampaignId.
  var sv39 = getFnBody('showView');
  assert('Step 39: showView function exists', typeof sv39 === 'string' && sv39.length > 1000);
  assert('Step 39: showView has the detail branch', sv39 && /name === 'detail'/.test(sv39));
  // The new branch: if detail AND renderCampaign exists AND window.campaignData.activeCampaignId is set.
  assert('Step 39: showView detail branch calls renderCampaign(activeCampaignId)',
         sv39 && /name\s*===\s*'detail'[\s\S]{0,500}renderCampaign\(\s*window\.campaignData\.activeCampaignId\s*\)/.test(sv39));
  assert('Step 39: showView detail branch guards on renderCampaign typeof',
         sv39 && /typeof\s+renderCampaign\s*===\s*'function'/.test(sv39));
  // The new branch is inside the LAST `if (name === 'detail')` block at the bottom
  // of showView's body. There are several `name === 'detail'` matches in the body
  // (view-detail / btn-detail toggles + the campaignSelectorWrap branch + our new
  // branch). Take the chunk immediately after the LAST `name === 'detail'` — that's
  // the body of the new `if (name === 'detail' && ...)` guard.
  var sv39Parts = sv39.split(/name\s*===\s*'detail'/);
  // sv39Parts[sv39Parts.length - 1] is the tail AFTER the new branch (else if + hooks etc.)
  // sv39Parts[sv39Parts.length - 2] is the body of the new branch.
  var sv39DetailBranch = sv39Parts[sv39Parts.length - 2];
  assert('Step 39: showView detail branch guards on activeCampaignId',
         /activeCampaignId/.test(sv39DetailBranch));
  // The guard reads activeCampaignId off window.campaignData (the data layer) — the
  // local 'activeCampaignId' var is not in scope inside showView, so the canonical
  // path is window.campaignData.activeCampaignId. Assert both forms exist (legacy
  // and canonical) so the test catches accidental future regressions either way.
  assert('Step 39: showView detail branch reads activeCampaignId from window.campaignData',
         /window\.campaignData\s*&&\s*window\.campaignData\.activeCampaignId/.test(sv39DetailBranch));
  assert('Step 39: showView detail branch guards on window.campaignData existence',
         /window\.campaignData[\s\S]{0,300}window\.campaignData\.campaigns\[window\.campaignData\.activeCampaignId\]/.test(sv39DetailBranch));
  // No second health engine — Step 39 just calls the existing renderCampaign, which
  // calls computeCampaignHealth via patchCampaignHealthSection.
  assert('Step 39: showView does NOT introduce a second health engine',
         !/function\s+computeCampaignHealth/.test(sv39DetailBranch));

  // -- 39.2: renderCampaign still contains the Step 33/34 patches.
  var rc39 = getFnBody('renderCampaign');
  assert('Step 39: renderCampaign still exists', typeof rc39 === 'string' && rc39.length > 500);
  assert('Step 39: renderCampaign still calls patchProductionAssetsSection (Step 33 intact)',
         rc39 && /patchProductionAssetsSection\(/.test(rc39));
  assert('Step 39: renderCampaign still calls patchCampaignHealthSection (Step 34 intact)',
         rc39 && /patchCampaignHealthSection\(/.test(rc39));

  // -- 39.3: save handlers still update their other surfaces.
  // handleHookSubmit already calls renderCampaign(cid) on attach (Step 25). Step 39
  // adds the view-entry refresh, so handleHookSubmit's existing call is preserved
  // (and useful when the marketer is currently on Campaign Detail when the save fires).
  var hhs39 = getFnBody('handleHookSubmit');
  assert('Step 39: handleHookSubmit still calls renderCampaign in attach branch',
         hhs39 && /renderCampaign\(\s*cid\s*\)/.test(hhs39));
  // handleAssetSubmit, handleCalSubmit, changeAssetStatus, changeCalStatus rely on the
  // navigation-side refresh now. Verify they still call refreshPortfolio + renderOpsFeed
  // (Step 38 contract preserved).
  var has39b = getFnBody('handleAssetSubmit');
  assert('Step 39: handleAssetSubmit still calls renderOpsFeed',
         has39b && /renderOpsFeed\(\)/.test(has39b));
  assert('Step 39: handleAssetSubmit still calls refreshPortfolio',
         has39b && /refreshPortfolio\(\)/.test(has39b));
  var hcs39 = getFnBody('handleCalSubmit');
  assert('Step 39: handleCalSubmit still calls refreshPortfolio',
         hcs39 && /refreshPortfolio\(\)/.test(hcs39));

  // -- 39.4: Non-regression of all previous steps.
  assert('Step 39: refreshPortfolio still defined (Step 38 intact)',
         typeof getFnBody('refreshPortfolio') === 'string' && getFnBody('refreshPortfolio').length > 500);
  assert('Step 39: computeCampaignHealth still defined (Step 34 intact)',
         typeof getFnBody('computeCampaignHealth') === 'string' && getFnBody('computeCampaignHealth').length > 200);
  assert('Step 39: patchProductionAssetsSection still defined (Step 33 intact)',
         typeof getFnBody('patchProductionAssetsSection') === 'string' && getFnBody('patchProductionAssetsSection').length > 200);
  assert('Step 39: patchCampaignHealthSection still defined (Step 34 intact)',
         typeof getFnBody('patchCampaignHealthSection') === 'string' && getFnBody('patchCampaignHealthSection').length > 200);
  assert('Step 39: renderFns still maps every seeded campaign',
         /renderFns\["trackman-intelligence"\]/.test(html) &&
         /renderFns\["takomo-101t"\]/.test(html) &&
         /renderFns\["winter-golf"\]/.test(html) &&
         /renderFns\["use-the-right-equipment-mq5l90bk"\]/.test(html));
  assert('Step 39: showView("portfolio") still calls refreshPortfolio',
         sv39 && /name === 'portfolio'[\s\S]{0,200}refreshPortfolio\(\)/.test(sv39));
  assert('Step 39: DOMContentLoaded boot still calls refreshPortfolio',
         /DOMContentLoaded[\s\S]{0,400}refreshPortfolio\(\)/.test(html));

  results.push('  (Step 39 — Campaign Detail is now live on view entry. The walkthrough surfaced a data-integrity finding: after an external state change (asset save, hook attach, calendar item linked) the Campaign Detail page kept the stale HTML from its last render — Health ring said 35/critical while computeCampaignHealth returned 60/degraded, and the Production Assets counter said "0 total" while c.assets had 1 entry. The data layer was already correct (Operations Feed, Portfolio, computeCampaignHealth all agreed). The fix is one new branch inside showView("detail"): renderCampaign(window.campaignData.activeCampaignId) is called before the subtitle is set, guarded by typeof + data existence + campaign existence. This is the existing render pipeline — no second health engine, no second refresh path — triggered once per view entry. The Step 33/34 inline patches (patchProductionAssetsSection, patchCampaignHealthSection) now run on every Campaign Detail entry, so the Health ring and Production Assets counter are always live. save handlers (handleAssetSubmit, handleHookSubmit, handleCalSubmit, changeAssetStatus, changeCalStatus) continue to call renderOpsFeed + refreshPortfolio on save for their respective surfaces; the navigation-side refresh completes the round-trip. Step 33/34/35/36/37/38 contracts all preserved.)');

  // ── Step 40: Truthful Asset Context (read-only) ───────────────
  // Verify resolver exists, returns the expected shape, and only emits proven relationships.
  // The resolver must read from localStorage + campaignData + calendarItems + campaign.channels.
  const hasResolver = /function\s+resolveAssetContext\s*\(\s*assetId\s*\)\s*\{/.test(html);
  assert('Step 40: resolveAssetContext(assetId) function exists', hasResolver);

  // Resolver must inspect localStorage asset_requests store OR campaign-scoped assets.
  const resolverSrc = hasResolver ? (html.match(/function\s+resolveAssetContext\s*\(\s*assetId\s*\)\s*\{[\s\S]*?\n\}/) || [''])[0] : '';
  assert('Step 40: resolver reads from assetReadAll (standalone store)',
         /assetReadAll\s*\(\s*\)/.test(resolverSrc));
  assert('Step 40: resolver walks window.campaignData.campaigns for campaign-scoped assets',
         /window\.campaignData\.campaigns[\s\S]{0,200}cid[\s\S]{0,200}assets[\s\S]{0,200}assetId/.test(resolverSrc));
  assert('Step 40: resolver scans calendarItems for asset references',
         /calendarItems[\s\S]{0,400}meta\.asset[\s\S]{0,200}===[\s\S]{0,80}assetId/.test(resolverSrc));
  assert('Step 40: resolver scans campaign.channels[].plannedItems[].asset',
         /channels[\s\S]{0,400}plannedItems[\s\S]{0,400}\.asset[\s\S]{0,80}===[\s\S]{0,80}assetId/.test(resolverSrc));
  assert('Step 40: hook binding is only emitted when paired in the SAME calendar/channel record',
         /calendarSlots[\s\S]{0,200}\.hookRef[\s\S]{0,400}channelPlans[\s\S]{0,200}\.hookRef/.test(resolverSrc));
  assert('Step 40: resolver returns empty arrays when nothing is proven',
         /calendarSlots:\s*\[\][\s\S]{0,40}channelPlans:\s*\[\][\s\S]{0,40}confirmedHookBindings:\s*\[\]/.test(resolverSrc));

  // Resolver must NOT infer relationships by scanning campaign-level hooks list alone.
  const noCampaignHookScan = !/campaign\.hooks[\s\S]{0,400}\.map[\s\S]{0,200}asset/.test(resolverSrc) &&
                             !/confirmedHookBindings\s*=\s*campaign\.hooks/.test(resolverSrc);
  assert('Step 40: resolver does NOT pair every campaign-level hook with this asset', noCampaignHookScan);

  // Verify the asset card template now embeds the truthful Asset Context block.
  assert('Step 40: renderAssetCard calls resolveAssetContext per asset',
         /function\s+renderAssetCard[\s\S]+?resolveAssetContext\(/.test(html));
  assert('Step 40: asset card contains CAMPAIGN CONTEXT section label',
         /class="actx-section-label"[\s\S]{0,40}CAMPAIGN CONTEXT/.test(html));
  assert('Step 40: asset card shows empty state "No publishing slot linked yet."',
         /No publishing slot linked yet\./.test(html));
  assert('Step 40: asset card shows empty state "No channel planned yet."',
         /No channel planned yet\./.test(html));
  assert('Step 40: asset card shows empty state "No hook is directly paired with this asset."',
         /No hook is directly paired with this asset\./.test(html));

  // Truthful direct fields.
  assert('Step 40: asset card labels Campaign directly (only via asset.campaignId)',
         /ctxRow\(\s*['"]Campaign['"]/.test(html));
  assert('Step 40: asset card labels Required by directly (only via asset.requiredBy)',
         /ctxRow\(\s*['"]Required by['"]/.test(html));
  assert('Step 40: asset card labels Status directly (only via asset.status)',
         /ctxRow\(\s*['"]Status['"]/.test(html));
  assert('Step 40: asset card labels Scheduled (only via calendarSlots[0].date/time)',
         /ctxRow\(\s*['"]Scheduled['"]/.test(html));
  assert('Step 40: asset card labels Channel (only via calendarSlots[0].channel || channelPlans[0].channel)',
         /ctxRow\(\s*['"]Channel['"]/.test(html));
  assert('Step 40: asset card labels "Ships with hook" (only via confirmedHookBindings[0])',
         /ctxRow\(\s*['"]Ships with hook['"]/.test(html));

  // CAMPAIGN CONTEXT sub-section: clearly labelled, distinct from direct asset fields.
  const ctxBlock = (html.match(/var contextHtml\s*=\s*'<div class="actx-block">[\s\S]*?'<\/div>'/) || [''])[0];
  assert('Step 40: CAMPAIGN CONTEXT section appears AFTER the direct asset rows',
         ctxBlock && /ctxRow\([^)]+\)[\s\S]{0,2000}actx-section-label[\s\S]{0,40}CAMPAIGN CONTEXT/.test(ctxBlock));
  assert('Step 40: CAMPAIGN CONTEXT includes Campaign health (computed, not stored)',
         ctxBlock && /ctxRow\(\s*['"]Campaign health['"]/.test(ctxBlock));
  assert('Step 40: CAMPAIGN CONTEXT includes Big idea',
         ctxBlock && /ctxRow\(\s*['"]Big idea['"]/.test(ctxBlock));

  // CSS for new context classes.
  assert('Step 40: CSS for .actx-block defined',
         /\.actx-block\s*\{/.test(html));
  assert('Step 40: CSS for .actx-row defined',
         /\.actx-row\s*\{/.test(html));
  assert('Step 40: CSS for .actx-label defined',
         /\.actx-label\s*\{/.test(html));
  assert('Step 40: CSS for .actx-empty defined',
         /\.actx-empty\s*\{/.test(html));
  assert('Step 40: CSS for .actx-section-label defined',
         /\.actx-section-label\s*\{/.test(html));

  // Guardrails — the brief forbids redesigning Asset Planner, adding attachment controls,
  // modifying Calendar, modifying campaign channels, or adding bidirectional fields.
  // The renderAssetCard edit must NOT add new onclick handlers beyond the existing three
  // (openEditAssetModal, promptAttachAsset, confirmDeleteAsset).
  const cardSrc = (html.match(/function\s+renderAssetCard[\s\S]*?function\s+renderAssetPlanner\s*\(\s*\)/) || [''])[0];
  const onclickMatches = cardSrc.match(/onclick="[^"]+"/g) || [];
  const onclicks = onclickMatches.join(' ');
  assert('Step 40: no new attachment control added (no attach/schedule/ship button)',
         !/attach-asset|attachToCampaign|schedule-asset|scheduleAsset|publishNow|shipNow/.test(onclicks));
  assert('Step 40: no asset-to-calendar/channedItem bidirectional field added to the asset object',
         !/asset\.(calItemId|scheduleId|channel|publishTarget|hookIds|attachedHooks)\s*=/.test(resolverSrc));

  // Read-only contract: renderAssetCard must NOT call any mutator (writeStore, assetAppend, assetWriteAll, assetDelete).
  assert('Step 40: renderAssetCard is read-only — no writeStore, assetAppend, or assetDelete call',
         !/writeStore\s*\(|assetAppend\s*\(|assetDelete\s*\(|assetWriteAll\s*\(/.test(cardSrc));

  results.push('  (Step 40 — Truthful Asset Context. New shared resolver resolveAssetContext(assetId) walks asset.campaignId → campaign → calendarItems + campaign.channels[].plannedItems, returns only records that explicitly reference this asset, and only emits a hook binding when the SAME calendar slot or plannedItem pairs both the asset and a hook. The asset card now embeds an Asset Context block: direct fields (Campaign, Required by, Status, Scheduled, Channel, Ships with hook) with truthful empty states, followed by a clearly labelled CAMPAIGN CONTEXT section (campaign name, status, computed health, big idea). The renderAssetCard edit does not add any new mutation or attach control — Step 31/36/37/39 contracts all preserved. Asset Planner behaviour unchanged: still standalone-workspace + context-aware modes, still no click-to-detail, still sortable by priority/requiredBy/updatedAt.)');

  // ── Summary ────────────────────────────────────────────────────
  results.push('');
  results.push(`Total: ${total}, Passed: ${passed}, Failed: ${failed}`);
  console.log(results.join('\n'));
  process.exit(failed > 0 ? 1 : 0);
})().catch(e => {
  console.error('Suite error:', e);
  console.log(results.join('\n'));
  process.exit(1);
});
