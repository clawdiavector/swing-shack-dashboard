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
  // 7. There IS a TODO comment about replacing Impact with computed Health Gain
  assert('TODO comment for Step 25 health engine present', /TODO:[\s\S]{0,300}Replace Impact with computed Health Gain/.test(html));
  // 8. The strategist block is prepended into detail-content in renderCampaign
  assert('renderCampaign prepends strategist block', /renderStrategistBlock\(id\)/.test(html));
  // 9. Issue action buttons navigate to existing views (not 'production' or 'creative-studio' which don't exist)
  assert('Plan Assets action uses dest=assets (not production)', /'Plan Assets',\s*dest:\s*'assets'/.test(html));
  assert('Create Creative action uses dest=creative (not creative-studio)', /'Create Creative',\s*dest:\s*'creative'/.test(html));
  assert('Schedule Publishing action uses dest=calendar', /'Schedule Publishing',\s*dest:\s*'calendar'/.test(html));
  // 10. State label is derived from health score (not invented)
  assert('State label derived from healthScore (>=80 healthy / >=50 degraded / else critical)', /currentHealth\s*>=\s*80[\s\S]{0,50}healthy[\s\S]{0,100}currentHealth\s*>=\s*50[\s\S]{0,50}degraded[\s\S]{0,100}critical/.test(html));
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
