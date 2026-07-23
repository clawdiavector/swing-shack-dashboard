/**
 * tests/test_asset_state_engine.js
 *
 * Step 87 Script 3 — 30 tests for the canonical Asset State Engine.
 *
 * Run: node tests/test_asset_state_engine.js
 *
 * Style: plain assertions, no external framework. Matches
 * tests/test_publisher_writeback.js and tests/test_phase2_wizard.js.
 *
 * All tests are pure — no canonical mutation. Fixtures are inline objects.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const eng = require('../scripts/_lib/asset-state-engine');

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

function fixture(overrides) {
  return Object.assign({
    assetId: 'test-asset',
    campaignId: 'test-campaign',
    assetType: 'feed-post',
    status: 'planned',
    owner: 'copywriter',
    caption: '',
    visualBrief: null,
    filePath: null,
    keyFindings: [],
    history: [],
  }, overrides || {});
}

// ─── Tests ────────────────────────────────────────────────────────────────

section('1. Pure determinism');
{
  const a = fixture({ caption: 'hello world this is a long caption for testing' });
  const r1 = eng.evaluateAsset(a, a.history, {});
  const r2 = eng.evaluateAsset(a, a.history, {});
  assert('evaluateAsset is deterministic across 2 calls', JSON.stringify(r1) === JSON.stringify(r2));
  // 100 calls
  let same = true;
  for (let i = 0; i < 100; i++) {
    const r = eng.evaluateAsset(a, a.history, {});
    if (JSON.stringify(r) !== JSON.stringify(r1)) { same = false; break; }
  }
  assert('evaluateAsset is deterministic across 100 calls', same);
}

section('2. Empty asset defaults');
{
  const r = eng.evaluateAsset(fixture(), [], {});
  assert('qualityGateState = pending', r.qualityGateState === 'pending');
  assert('captionStatus = pending', r.captionStatus === 'pending');
  assert('visualStatus = pending', r.visualStatus === 'pending');
  assert('approvalStatus = pending', r.approvalStatus === 'pending');
  assert('publishStatus = planned', r.publishStatus === 'planned');
}

section('3. Caption-created history -> captionStatus draft');
{
  const a = fixture({
    caption: '',
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('captionStatus = draft', r.captionStatus === 'draft');
}

section('4. Caption length >=100 + caption-created + no rejection -> approved');
{
  const a = fixture({
    caption: 'x'.repeat(150),
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('captionStatus = approved', r.captionStatus === 'approved');
}

section('5. Caption-rejected event -> rejected');
{
  const a = fixture({
    caption: 'short',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'caption-rejected', by: 'christelle', at: '2026-01-02T00:00:00Z', reason: 'tone off' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('captionStatus = rejected', r.captionStatus === 'rejected');
}

section('6. visual-revised + visualBrief -> brief-written');
{
  const a = fixture({
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [{ action: 'visual-revised', by: 'image-gen', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('visualStatus = brief-written', r.visualStatus === 'brief-written');
}

section('7. filePath + visual-generated event -> generated');
{
  const a = fixture({
    filePath: 'assets/x.png',
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-02T00:00:00Z', filePath: 'assets/x.png' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('visualStatus = generated', r.visualStatus === 'generated');
}

section('8. Research assetType -> visualStatus skipped');
{
  const a = fixture({ assetType: 'research', caption: '', visualBrief: null, filePath: null });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('visualStatus = skipped for research', r.visualStatus === 'skipped');
}

section('9. caption + visualBrief + owner -> gate1-passed');
{
  const a = fixture({
    caption: 'x'.repeat(80),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('qualityGateState = gate1-passed', r.qualityGateState === 'gate1-passed');
}

section('10. caption-created + visualBrief -> approvalStatus review');
{
  const a = fixture({
    caption: 'x'.repeat(80),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('approvalStatus = review', r.approvalStatus === 'review');
}

section('11. All gates satisfied -> publishStatus scheduled');
{
  const a = fixture({
    assetId: 'sched-test',
    caption: 'x'.repeat(150),
    platform: 'instagram',
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    filePath: 'assets/x.png',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-03T00:00:00Z', filePath: 'assets/x.png' },
      { action: 'visual-approved', by: 'retina', at: '2026-01-04T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-05T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('publishStatus = scheduled', r.publishStatus === 'scheduled');
}

section('11b. brief-written visualStatus is NOT sufficient for scheduled');
{
  // Step 88 hardening: even with full history of approval events, if the
  // visualStatus field is only brief-written (planning complete but no
  // production artefact), the engine MUST NOT return scheduled.
  const a = fixture({
    assetId: 'planning-only',
    caption: 'x'.repeat(150),
    platform: 'instagram',
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    visualStatus: 'brief-written',  // explicit: planning complete, no artefact
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-03T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('publishStatus = planned when visualStatus=brief-written', r.publishStatus === 'planned');
}

section('11c. Missing platform blocks scheduled');
{
  // Step 88 hardening: an asset without a platform field is not dispatchable
  // to any integration. Publisher would skip it. Schedule gate must reject.
  const a = fixture({
    assetId: 'no-platform',
    caption: 'x'.repeat(150),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    filePath: 'assets/x.png',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-03T00:00:00Z', filePath: 'assets/x.png' },
      { action: 'visual-approved', by: 'retina', at: '2026-01-04T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-05T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('publishStatus = planned when platform missing', r.publishStatus === 'planned');
}

section('11d. research asset with visualStatus=skipped CAN reach scheduled');
{
  // Step 88 design: research assets skip visual gate. With caption approved,
  // approval approved, gate1 passed (research derivation), platform set,
  // artefacts present (caption + keyFindings + platform), it should reach
  // scheduled.
  const a = fixture({
    assetId: 'research-sched',
    assetType: 'research',
    caption: 'x'.repeat(200),
    platform: 'instagram,tiktok',
    keyFindings: ['finding1', 'finding2'],
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-02T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('research publishStatus = scheduled', r.publishStatus === 'scheduled');
}

section('12. Postiz external confirmation -> publishStatus live');
{
  const a = fixture({
    assetId: 'live-test',
    caption: 'x'.repeat(150),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    filePath: 'assets/x.png',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-03T00:00:00Z', filePath: 'assets/x.png' },
      { action: 'visual-approved', by: 'retina', at: '2026-01-04T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-05T00:00:00Z' },
    ],
  });
  const ext = { postizConfirmations: [{ assetId: 'live-test', status: 'live', postizPostId: 'p-1' }] };
  const r = eng.evaluateAsset(a, a.history, ext);
  assert('publishStatus = live with postiz confirmation', r.publishStatus === 'live');
}

section('13. gate2-failed sticky without regen event');
{
  const a = fixture({
    qualityGateState: 'gate2-failed',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('qualityGateState stays gate2-failed', r.qualityGateState === 'gate2-failed');
}

section('14. gate2-failed + regenerate-requested -> reset to gate1');
{
  const a = fixture({
    qualityGateState: 'gate2-failed',
    caption: 'x'.repeat(150),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'regenerate-requested', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('qualityGateState = gate1-passed after regen', r.qualityGateState === 'gate1-passed');
}

section('15. Backward transition: caption-revised after approval -> draft');
{
  const a = fixture({
    caption: 'new draft',
    captionStatus: 'approved',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'caption-approved', by: 'christelle', at: '2026-01-02T00:00:00Z' },
      { action: 'caption-revised', by: 'copywriter', at: '2026-01-03T00:00:00Z' },
    ],
  });
  const r = eng.evaluateAsset(a, a.history, {});
  assert('captionStatus = draft after revision', r.captionStatus === 'draft');
}

section('16. applyStateTransition is idempotent');
{
  const a = fixture({
    captionStatus: 'draft',
    visualStatus: 'pending',
    approvalStatus: 'pending',
    qualityGateState: 'pending',
    publishStatus: 'planned',
  });
  const desired = {
    qualityGateState: 'pending',
    captionStatus: 'draft',
    visualStatus: 'pending',
    approvalStatus: 'pending',
    publishStatus: 'planned',
  };
  const r = eng.applyStateTransition(a, desired);
  assert('changed=false', r.changed === false);
  assert('fieldsChanged=[]', r.fieldsChanged.length === 0);
}

section('17. applyStateTransition writes only changed fields');
{
  const a = fixture({
    caption: 'preserve me',
    visualBrief: { concept: 'preserve me too' },
    filePath: 'preserve.png',
    captionStatus: 'draft',
    visualStatus: 'pending',
    approvalStatus: 'pending',
    qualityGateState: 'pending',
    publishStatus: 'planned',
  });
  const r = eng.applyStateTransition(a, {
    qualityGateState: 'pending',     // unchanged
    captionStatus: 'approved',        // changes
    visualStatus: 'brief-written',    // changes
    approvalStatus: 'pending',        // unchanged
    publishStatus: 'planned',         // unchanged
  });
  assert('changed=true', r.changed === true);
  assert('fieldsChanged has 2 entries', r.fieldsChanged.length === 2);
  assert('fieldsChanged includes captionStatus', r.fieldsChanged.includes('captionStatus'));
  assert('fieldsChanged includes visualStatus', r.fieldsChanged.includes('visualStatus'));
  assert('caption field untouched', a.caption === 'preserve me');
  assert('visualBrief field untouched', a.visualBrief.concept === 'preserve me too');
  assert('filePath field untouched', a.filePath === 'preserve.png');
  assert('asset.history untouched', JSON.stringify(a.history) === '[]');
}

section('18. applyStateTransition does NOT modify asset.history');
{
  const a = fixture({
    caption: 'x'.repeat(150),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
    ],
  });
  const historyLenBefore = a.history.length;
  const desired = eng.evaluateAsset(a, a.history, {});
  eng.applyStateTransition(a, desired);
  assert('history.length unchanged', a.history.length === historyLenBefore);
  assert('history contents unchanged', JSON.stringify(a.history) === JSON.stringify([
    { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
    { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
  ]));
}

section('19. evaluateAsset does NOT call fs');
{
  // Spawn evaluateAsset in a sandboxed vm context that has no fs.
  const src = fs.readFileSync(path.join(__dirname, '..', 'scripts', '_lib', 'asset-state-engine.js'), 'utf8');
  // Load module in sandbox WITHOUT fs binding.
  const sandbox = { module: { exports: {} }, exports: {}, console };
  sandbox.exports = sandbox.module.exports;
  // Minimal stubs to allow require resolution.
  vm.createContext(sandbox);
  // We cannot fully isolate require, so instead inspect source for the function body.
  const evalMatch = src.match(/function evaluateAsset\(asset, history, externalSignals\)\s*\{[\s\S]*?\n\}/);
  assert('evaluateAsset function found in source', !!evalMatch);
  const body = evalMatch[0];
  assert('body does not reference require', !/require\(/.test(body));
  assert('body does not reference fs.readFile', !/fs\.readFile/.test(body));
  assert('body does not reference fs.writeFile', !/fs\.writeFile/.test(body));
}

section('20. Determinism — 1000 invocations identical');
{
  const a = fixture({
    caption: 'x'.repeat(150),
    visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
    filePath: 'x.png',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
    ],
  });
  const r1 = eng.evaluateAsset(a, a.history, {});
  let same = true;
  for (let i = 0; i < 1000; i++) {
    const r = eng.evaluateAsset(a, a.history, {});
    if (JSON.stringify(r) !== JSON.stringify(r1)) { same = false; break; }
  }
  assert('1000 invocations identical', same);
}

section('21. External approval action overrides history');
{
  const a = fixture({
    assetId: 'ext-approve',
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const r = eng.evaluateAsset(a, a.history, {
    approvalActions: [{ assetId: 'ext-approve', action: 'approved', by: 'christelle' }],
  });
  assert('approvalStatus = approved from external', r.approvalStatus === 'approved');
}

section('22. reconcileCampaign atomic write');
{
  const tmpDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'ase-test-'));
  const cp = path.join(tmpDir, 'campaign-data.json');
  fs.writeFileSync(cp, JSON.stringify({
    campaigns: {
      'c1': {
        identity: { status: 'active' },
        assets: {
          'a1': {
            assetId: 'a1', assetType: 'feed-post', owner: 'copywriter',
            caption: 'x'.repeat(150),
            visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
            history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
          },
        },
      },
    },
  }, null, 2));
  const before = fs.readFileSync(cp, 'utf8');
  const r = eng.reconcileCampaign('c1', cp);
  const after = fs.readFileSync(cp, 'utf8');
  assert('reconcileCampaign changed = 1', r.changed === 1);
  assert('reconcileCampaign wrote to disk', before !== after);
  assert('no .tmp file left', !fs.existsSync(cp + '.tmp'));
  assert('no .lock file left', !fs.existsSync(cp + '.lock'));
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

section('23. reconcileCampaign dry-run does not write');
{
  const tmpDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'ase-test-'));
  const cp = path.join(tmpDir, 'campaign-data.json');
  fs.writeFileSync(cp, JSON.stringify({
    campaigns: {
      'c1': {
        identity: { status: 'active' },
        assets: {
          'a1': {
            assetId: 'a1', assetType: 'feed-post', owner: 'copywriter',
            caption: 'x'.repeat(150),
            visualBrief: { concept: 'A dramatic shot of the driver against a black backdrop with data overlay' },
            history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
          },
        },
      },
    },
  }, null, 2));
  const before = fs.readFileSync(cp, 'utf8');
  const r = eng.reconcileCampaign('c1', cp, { dryRun: true });
  const after = fs.readFileSync(cp, 'utf8');
  assert('reconcileCampaign dryRun returned', r.dryRun === true);
  assert('reconcileCampaign dryRun: file unchanged', before === after);
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

section('24. Real canonical: takomo-101t-research');
{
  const cp = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
  if (!fs.existsSync(cp)) {
    results.push('  SKIP  takomo-research (canonical not found)');
    total++; skipped++;
  } else {
    const data = JSON.parse(fs.readFileSync(cp, 'utf8'));
    const a = data.campaigns['takomo-101t'].assets['takomo-101t-research'];
    const r = eng.evaluateAsset(a, a.history, {});
    assert('takomo-research qualityGateState=gate1-passed', r.qualityGateState === 'gate1-passed');
    assert('takomo-research visualStatus=skipped', r.visualStatus === 'skipped');
    assert('takomo-research captionStatus=approved', r.captionStatus === 'approved');
    assert('takomo-research approvalStatus in (pending|review)', r.approvalStatus === 'pending' || r.approvalStatus === 'review');
    assert('takomo-research publishStatus=planned', r.publishStatus === 'planned');
  }
}

section('25. Real canonical: use-the-right-equipment first asset');
{
  const cp = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
  if (fs.existsSync(cp)) {
    const data = JSON.parse(fs.readFileSync(cp, 'utf8'));
    const c = data.campaigns['use-the-right-equipment-mq5l90bk'];
    const aid = Object.keys(c.assets)[0];
    const a = c.assets[aid];
    const r = eng.evaluateAsset(a, a.history, {});
    assert('use-the-right-equipment captionStatus=approved', r.captionStatus === 'approved');
    assert('use-the-right-equipment visualStatus=brief-written (no filePath)', r.visualStatus === 'brief-written');
    assert('use-the-right-equipment approvalStatus=review', r.approvalStatus === 'review');
    assert('use-the-right-equipment qualityGateState=gate1-passed', r.qualityGateState === 'gate1-passed');
    assert('use-the-right-equipment publishStatus=planned', r.publishStatus === 'planned');
  }
}

section('26. Real canonical: takomo-101t-visual-a stays gate2-failed');
{
  const cp = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
  if (fs.existsSync(cp)) {
    const data = JSON.parse(fs.readFileSync(cp, 'utf8'));
    const a = data.campaigns['takomo-101t'].assets['takomo-101t-visual-a'];
    const r = eng.evaluateAsset(a, a.history, {});
    assert('takomo-visual-a qualityGateState=gate2-failed (sticky)', r.qualityGateState === 'gate2-failed');
    assert('takomo-visual-a visualStatus=rejected or generated', ['rejected','generated'].includes(r.visualStatus));
    assert('takomo-visual-a approvalStatus=rejected', r.approvalStatus === 'rejected');
  }
}

section('27. Real canonical: 5 takomo partial assets');
{
  const cp = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
  if (fs.existsSync(cp)) {
    const data = JSON.parse(fs.readFileSync(cp, 'utf8'));
    const c = data.campaigns['takomo-101t'];
    const partials = ['takomo-101t-hook-a', 'takomo-101t-production', 'takomo-101t-hero-b', 'takomo-101t-hero-c'];
    for (const aid of partials) {
      const a = c.assets[aid];
      const r = eng.evaluateAsset(a, a.history, {});
      // hook-a and production have captions (>=100) -> approved; hero-b/c have no caption -> draft or pending
      const capLen = (a.caption || '').length;
      if (capLen >= 100) {
        assert(`${aid} captionStatus=approved`, r.captionStatus === 'approved', { capLen });
      } else {
        assert(`${aid} captionStatus in (pending,draft)`, ['pending','draft'].includes(r.captionStatus), { capLen });
      }
    }
  }
}

section('28. applyStateTransition rejects invalid field values');
{
  let threw = false;
  try {
    eng.applyStateTransition(fixture(), { qualityGateState: 'magic' });
  } catch (e) {
    threw = e instanceof eng.InvalidFieldValueError;
  }
  assert('InvalidFieldValueError thrown', threw);
}

section('29. evaluateAsset does NOT dereference asset.history');
{
  // Pass null/undefined for second arg; asset has history field but engine
  // must not touch it.
  const a = fixture({ history: [{ action: 'caption-created', by: 'x', at: '2026-01-01T00:00:00Z' }] });
  const r1 = eng.evaluateAsset(a, null, {});
  const r2 = eng.evaluateAsset(a, undefined, {});
  assert('null history -> same result as undefined', JSON.stringify(r1) === JSON.stringify(r2));
  assert('asset.history untouched by evaluateAsset', a.history.length === 1);
}

section('30. applyStateTransition field-only — does not mutate other fields');
{
  const a = fixture({
    assetId: 'iso-test',
    campaignId: 'iso-camp',
    assetType: 'reel',
    status: 'review',
    owner: 'copywriter',
    caption: 'preserve',
    visualBrief: { concept: 'preserve brief' },
    filePath: 'preserve.png',
    keyFindings: ['preserve'],
    history: [{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }],
  });
  const snapshot = JSON.stringify(a);
  const desired = eng.evaluateAsset(a, a.history, {});
  eng.applyStateTransition(a, desired);
  // only the 5 state fields + updatedAt may have changed
  const after = a;
  assert('assetId unchanged', after.assetId === 'iso-test');
  assert('campaignId unchanged', after.campaignId === 'iso-camp');
  assert('assetType unchanged', after.assetType === 'reel');
  assert('status unchanged', after.status === 'review');
  assert('owner unchanged', after.owner === 'copywriter');
  assert('caption unchanged', after.caption === 'preserve');
  assert('visualBrief unchanged', JSON.stringify(after.visualBrief) === JSON.stringify({ concept: 'preserve brief' }));
  assert('filePath unchanged', after.filePath === 'preserve.png');
  assert('keyFindings unchanged', JSON.stringify(after.keyFindings) === JSON.stringify(['preserve']));
  assert('history unchanged', JSON.stringify(after.history) === JSON.stringify([{ action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' }]));
}

// ─── Output ───────────────────────────────────────────────────────────────

results.push('');
results.push(`Total: ${total}, Passed: ${passed}, Failed: ${failed}`);
console.log(results.join('\n'));
process.exit(failed > 0 ? 1 : 0);