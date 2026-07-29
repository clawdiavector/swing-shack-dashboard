/**
 * tests/test_generate_publish_queue.js
 *
 * Step 89 — test suite for the canonical publish queue generator.
 *
 * Run: node tests/test_generate_publish_queue.js
 *
 * Coverage:
 *   1. Generator exits 0 on valid canonical
 *   2. Generator output has the legacy qa-inspector/v1 schema
 *   3. Generator is deterministic (same input -> byte-identical output)
 *   4. Generator is idempotent (re-run produces same output)
 *   5. dry-run does not write the output file
 *   6. Only scheduled assets from active campaigns are emitted
 *   7. Non-active campaign's scheduled assets are filtered out
 *   8. Non-scheduled assets in active campaigns are filtered out
 *   9. Campaign OS item_ids use canonical assetId (no synthetic IDs)
 *  10. linked_blueprint_id equals assetId (publisher's lookup key)
 *  11. platform resolved to first platform from comma-separated string
 *  12. linked_hook_id is deterministic (slug from asset name)
 *  13. hook_text comes from asset.caption (truncated to 220 chars)
 *  14. Existing legacy items preserved when not superseded
 *  15. Legacy item with same item_id as Campaign OS asset gets superseded
 *      (Campaign OS wins)
 *  16. Output items sorted by item_id (deterministic order)
 *  17. No duplicate item_ids in output
 *  18. No mutation of campaign-data.json (read-only)
 *  19. Already-published item_ids filtered out
 *  20. Publishing[] reference in canonical filters out asset
 *  21. Asset with missing platform field is filtered out
 *  22. Output JSON is parseable
 *  23. Each Campaign OS item has source='campaign-os'
 *  24. Each Campaign OS item has verdict='pass' and passed_checks=4
 *  25. Integration ID resolved correctly per platform
 *  26. Cross-campaign publishing[] lookup works (any campaign)
 *  27. Generated timestamp matches canonical updatedAt
 *  28. Output schema field is 'https://clawdia.io/agents/qa-inspector/v1'
 *  29. Empty scheduled set produces output with 0 campaignOsCount
 *  30. Empty scheduled set + empty legacy file = 0 items
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

const TMP_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'gen-queue-test-'));
const SCRIPT = path.join(__dirname, '..', 'scripts', 'generate_publish_queue.js');
const DEFAULT_CANONICAL = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
const DEFAULT_READY = path.join(__dirname, '..', 'data', 'ready-for-approval.json');

// Snapshot the original file ONCE at suite start. Every test runs the
// generator (which writes to DEFAULT_READY) and then this snapshot is
// restored in the suite-level cleanup. This guarantees test isolation
// regardless of test order.
const ORIGINAL_READY = fs.readFileSync(DEFAULT_READY);
process.on('exit', () => {
  try { fs.writeFileSync(DEFAULT_READY, ORIGINAL_READY); } catch (_) {}
});

let passed = 0, failed = 0, total = 0;
const results = [];

function assert(name, cond, info) {
  total++;
  if (cond) {
    passed++;
    results.push(`  PASS  ${name}`);
  } else {
    failed++;
    results.push(`  FAIL  ${name}${info ? ' — ' + JSON.stringify(info).substring(0, 200) : ''}`);
  }
}

function section(title) {
  results.push(`\n[${title}]`);
}

function buildTestCanonical(overrides = {}) {
  const canonical = JSON.parse(fs.readFileSync(DEFAULT_CANONICAL, 'utf8'));
  const baseCampId = overrides.campaignId || 'test-campaign';
  const baseAssetId = overrides.assetId || 'test-campaign-asset-1';
  const baseAsset = overrides.asset || {
    assetId: baseAssetId,
    campaignId: baseCampId,
    name: 'Test Asset For Publishing',
    assetType: 'feed-post',
    platform: 'instagram',
    caption: 'x'.repeat(250), // > 220 so we can verify truncation
    visualBrief: 'Test visual brief concept — should be long enough to count',
    filePath: 'assets/test.jpg',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01T00:00:00Z' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02T00:00:00Z' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-03T00:00:00Z', filePath: 'assets/test.jpg' },
      { action: 'visual-approved', by: 'retina', at: '2026-01-04T00:00:00Z' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-05T00:00:00Z' },
    ],
    owner: 'copywriter',
    qualityGateState: 'gate1-passed',
    captionStatus: 'approved',
    visualStatus: 'approved',
    approvalStatus: 'approved',
    publishStatus: 'scheduled',
  };
  canonical.campaigns[baseCampId] = {
    identity: { campaignId: baseCampId, status: overrides.campaignStatus || 'active' },
    assets: { [baseAssetId]: baseAsset },
    publishing: overrides.publishing || [],
  };
  canonical.updatedAt = '2026-07-23T11:00:00Z';
  return canonical;
}

function writeJson(p, data) {
  fs.writeFileSync(p, JSON.stringify(data, null, 2));
}

function runGenerator(canonicalPath, opts = {}) {
  const args = [SCRIPT];
  if (canonicalPath) args.push('--canonical-path', canonicalPath);
  if (opts.json) args.push('--json');
  if (!opts.dryRun) {
    // Default: LIVE mode (writes the file). Tests that want to verify
    // dry-run behavior pass dryRun: true explicitly.
  } else {
    args.push('--dry-run');
  }
  const stdout = execSync(args.join(' '), { encoding: 'utf8' });
  return stdout;
}

// ─── Tests ────────────────────────────────────────────────────────────────

section('1. Generator runs cleanly on valid canonical');
{
  const cp = path.join(TMP_ROOT, 'canonical1.json');
  writeJson(cp, buildTestCanonical());
  let exitOk = true;
  try { runGenerator(cp); } catch (e) { exitOk = false; }
  assert('exits 0 on valid canonical', exitOk);
}

section('2. Output preserves legacy qa-inspector/v1 schema');
{
  const cp = path.join(TMP_ROOT, 'canonical2.json');
  writeJson(cp, buildTestCanonical());
  // Run live and inspect data/ready-for-approval.json
  const out = path.join(TMP_ROOT, 'ready.json');
  // Backup current ready
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp, { dryRun: false });
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('schema field = qa-inspector/v1', written.schema === 'https://clawdia.io/agents/qa-inspector/v1');
    assert('items is an array', Array.isArray(written.items));
    assert('has campaignOsCount', typeof written.campaignOsCount === 'number');
    assert('has legacyCount', typeof written.legacyCount === 'number');
    assert('has source field', typeof written.source === 'string');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('3. Determinism — same input -> byte-identical output');
{
  const cp = path.join(TMP_ROOT, 'canonical3.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    const r1 = runGenerator(cp, { json: true });
    const r2 = runGenerator(cp, { json: true });
    assert('two runs produce identical JSON output', r1 === r2);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('4. Idempotence — re-run produces same output');
{
  const cp = path.join(TMP_ROOT, 'canonical4.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const after1 = fs.readFileSync(DEFAULT_READY);
    // Wait briefly so generated timestamp would differ if non-deterministic
    runGenerator(cp);
    const after2 = fs.readFileSync(DEFAULT_READY);
    assert('live re-run is byte-identical', after1.equals(after2));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('5. dry-run does not write the output file');
{
  const cp = path.join(TMP_ROOT, 'canonical5.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  const before = fs.statSync(DEFAULT_READY).mtimeMs;
  try {
    // Wait 50ms to ensure mtime would change if written
    execSync('sleep 0.05');
    runGenerator(cp, { dryRun: true });
    const after = fs.statSync(DEFAULT_READY).mtimeMs;
    assert('dry-run did not modify ready-for-approval.json', after === before);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('6. Only scheduled assets from active campaigns are emitted');
{
  const cp = path.join(TMP_ROOT, 'canonical6.json');
  writeJson(cp, buildTestCanonical({ asset: {
    assetId: 'sched-active', campaignId: 'active-camp', name: 'Scheduled',
    assetType: 'feed-post', platform: 'instagram', caption: 'x'.repeat(150),
    visualBrief: 'Test visual brief concept — should be long enough to count',
    filePath: 'assets/test.jpg',
    owner: 'copywriter', qualityGateState: 'gate1-passed',
    captionStatus: 'approved', visualStatus: 'approved',
    approvalStatus: 'approved', publishStatus: 'scheduled',
    history: [
      { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
      { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
      { action: 'visual-generated', by: 'image-gen', at: '2026-01-03', filePath: 'assets/test.jpg' },
      { action: 'visual-approved', by: 'retina', at: '2026-01-04' },
      { action: 'approval-approved', by: 'christelle', at: '2026-01-05' },
    ],
  }}));
  const out = path.join(TMP_ROOT, 'ready6.json');
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp, { json: true });
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('scheduled active asset IS emitted', ids.includes('sched-active'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('7. Non-active campaign scheduled assets are filtered out');
{
  const cp = path.join(TMP_ROOT, 'canonical7.json');
  writeJson(cp, buildTestCanonical({
    campaignId: 'inactive-camp', campaignStatus: 'generatingBlueprint',
    assetId: 'sched-inactive',
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('scheduled asset in non-active campaign is NOT emitted', !ids.includes('sched-inactive'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('8. Non-scheduled assets in active campaigns are filtered out');
{
  const cp = path.join(TMP_ROOT, 'canonical8.json');
  writeJson(cp, buildTestCanonical({
    campaignId: 'active-camp',
    assetId: 'planned-only', asset: {
      assetId: 'planned-only', campaignId: 'active-camp', name: 'Planned',
      assetType: 'feed-post', platform: 'instagram', caption: 'x'.repeat(150),
      visualBrief: 'Test visual brief concept — should be long enough to count',
      filePath: 'assets/test.jpg',
      owner: 'copywriter', qualityGateState: 'gate1-passed',
      captionStatus: 'approved', visualStatus: 'brief-written',
      approvalStatus: 'review', publishStatus: 'planned',
      history: [
        { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
        { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
      ],
    },
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('planned asset is NOT emitted', !ids.includes('planned-only'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('9. Campaign OS item_ids use canonical assetId (no synthetic IDs)');
{
  const cp = path.join(TMP_ROOT, 'canonical9.json');
  writeJson(cp, buildTestCanonical({ assetId: 'real-canonical-asset-id-xyz' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'real-canonical-asset-id-xyz');
    assert('emitted item has exact assetId, no synthetic prefix', item !== undefined);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('10. linked_blueprint_id equals assetId (publisher lookup key)');
{
  const cp = path.join(TMP_ROOT, 'canonical10.json');
  writeJson(cp, buildTestCanonical({ assetId: 'lookup-test-id' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'lookup-test-id');
    assert('linked_blueprint_id = assetId', item && item.linked_blueprint_id === 'lookup-test-id');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('11. Platform resolved to first from comma-separated string');
{
  const cp = path.join(TMP_ROOT, 'canonical11.json');
  writeJson(cp, buildTestCanonical({
    assetId: 'multi-platform',
    asset: {
      assetId: 'multi-platform', campaignId: 'active-camp', name: 'Multi',
      assetType: 'feed-post', platform: 'tiktok,instagram,gmb', caption: 'x'.repeat(150),
      visualBrief: 'Test visual brief concept — should be long enough to count',
      filePath: 'assets/test.jpg',
      owner: 'copywriter', qualityGateState: 'gate1-passed',
      captionStatus: 'approved', visualStatus: 'approved',
      approvalStatus: 'approved', publishStatus: 'scheduled',
      history: [
        { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
        { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
        { action: 'visual-generated', by: 'image-gen', at: '2026-01-03', filePath: 'assets/test.jpg' },
        { action: 'visual-approved', by: 'retina', at: '2026-01-04' },
        { action: 'approval-approved', by: 'christelle', at: '2026-01-05' },
      ],
    },
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'multi-platform');
    assert('platform = first platform in comma list', item && item.platform === 'tiktok');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('12. linked_hook_id is deterministic slug from asset.name');
{
  const cp = path.join(TMP_ROOT, 'canonical12.json');
  writeJson(cp, buildTestCanonical({
    assetId: 'slug-test',
    asset: {
      assetId: 'slug-test', campaignId: 'active-camp', name: 'Fit Solution — Visual Test 1',
      assetType: 'feed-post', platform: 'instagram', caption: 'x'.repeat(150),
      visualBrief: 'Test visual brief concept — should be long enough to count',
      filePath: 'assets/test.jpg',
      owner: 'copywriter', qualityGateState: 'gate1-passed',
      captionStatus: 'approved', visualStatus: 'approved',
      approvalStatus: 'approved', publishStatus: 'scheduled',
      history: [
        { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
        { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
        { action: 'visual-generated', by: 'image-gen', at: '2026-01-03', filePath: 'assets/test.jpg' },
        { action: 'visual-approved', by: 'retina', at: '2026-01-04' },
        { action: 'approval-approved', by: 'christelle', at: '2026-01-05' },
      ],
    },
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'slug-test');
    assert('linked_hook_id is deterministic slug', item && item.linked_hook_id === 'fit-solution-visual-test-1');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('13. hook_text from asset.caption (truncated to 220 chars)');
{
  const cp = path.join(TMP_ROOT, 'canonical13.json');
  writeJson(cp, buildTestCanonical({
    assetId: 'trunc-test',
    asset: {
      assetId: 'trunc-test', campaignId: 'active-camp', name: 'Trunc',
      assetType: 'feed-post', platform: 'instagram',
      caption: 'A'.repeat(300),
      visualBrief: 'Test visual brief concept — should be long enough to count',
      filePath: 'assets/test.jpg',
      owner: 'copywriter', qualityGateState: 'gate1-passed',
      captionStatus: 'approved', visualStatus: 'approved',
      approvalStatus: 'approved', publishStatus: 'scheduled',
      history: [
        { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
        { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
        { action: 'visual-generated', by: 'image-gen', at: '2026-01-03', filePath: 'assets/test.jpg' },
        { action: 'visual-approved', by: 'retina', at: '2026-01-04' },
        { action: 'approval-approved', by: 'christelle', at: '2026-01-05' },
      ],
    },
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'trunc-test');
    assert('hook_text length <= 220', item && item.hook_text.length === 220);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('14. Existing legacy items preserved when not superseded');
{
  const cp = path.join(TMP_ROOT, 'canonical14.json');
  writeJson(cp, buildTestCanonical());
  // Backup existing ready-for-approval
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    // Preserve current legacy items
    const originalReady = JSON.parse(backup);
    const beforeCount = originalReady.items.length;
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('legacyCount > 0 when legacy file has items', written.legacyCount > 0);
    assert('legacy items preserved', written.items.length > beforeCount - 1);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('15. Legacy item with same item_id as Campaign OS asset is superseded');
{
  const cp = path.join(TMP_ROOT, 'canonical15.json');
  writeJson(cp, buildTestCanonical({ assetId: 'duplicate-id-test' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    // Inject a fake legacy item with the same id
    const originalReady = JSON.parse(backup);
    originalReady.items.push({
      item_id: 'duplicate-id-test',
      item_type: 'caption',
      linked_blueprint_id: 'old-bp',
      verdict: 'pass',
      issues: ['legacy'],
      passed_checks: 4,
      total_checks: 4,
      source: 'legacy',
    });
    fs.writeFileSync(DEFAULT_READY, JSON.stringify(originalReady, null, 2));
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const matching = written.items.filter(i => i.item_id === 'duplicate-id-test');
    assert('only one entry per item_id', matching.length === 1);
    assert('Campaign OS wins (source=campaign-os)', matching[0].source === 'campaign-os');
    assert('legacy issues field is gone', !matching[0].issues || matching[0].issues.length === 0);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('16. Output items sorted by item_id');
{
  const cp = path.join(TMP_ROOT, 'canonical16.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    const sorted = [...ids].sort();
    assert('items sorted by item_id', JSON.stringify(ids) === JSON.stringify(sorted));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('17. No duplicate item_ids in output');
{
  const cp = path.join(TMP_ROOT, 'canonical17.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    const unique = new Set(ids);
    assert('no duplicate item_ids', unique.size === ids.length);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('18. No mutation of campaign-data.json');
{
  const cp = path.join(TMP_ROOT, 'canonical18.json');
  writeJson(cp, buildTestCanonical());
  const before = fs.readFileSync(cp, 'utf8');
  runGenerator(cp);
  const after = fs.readFileSync(cp, 'utf8');
  assert('canonical is byte-identical before/after', before === after);
}

section('19. Already-published item_ids filtered out');
{
  const cp = path.join(TMP_ROOT, 'canonical19.json');
  writeJson(cp, buildTestCanonical({ assetId: 'already-published-id' }));
  const backupReady = fs.readFileSync(DEFAULT_READY);
  const backupPub = fs.readFileSync(path.join(__dirname, '..', 'data', 'published-items.json'));
  try {
    // Inject fake published-item entry
    const pub = JSON.parse(backupPub);
    pub.published.push({
      publish_id: 'pub-fake',
      item_id: 'already-published-id',
      status: 'published_dry',
      platform: 'instagram',
    });
    fs.writeFileSync(path.join(__dirname, '..', 'data', 'published-items.json'), JSON.stringify(pub, null, 2));
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('already-published item_id is NOT emitted', !ids.includes('already-published-id'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backupReady);
    fs.writeFileSync(path.join(__dirname, '..', 'data', 'published-items.json'), backupPub);
  }
}

section('20. Publishing[] reference in canonical filters out asset');
{
  const cp = path.join(TMP_ROOT, 'canonical20.json');
  const canonical = buildTestCanonical({ assetId: 'has-publishing-ref' });
  canonical.campaigns['test-campaign'].publishing = [{
    publishingId: 'pub-fake-ref',
    assetId: 'has-publishing-ref',
    campaignId: 'test-campaign',
    postizPostId: 'cm-fake',
    currentStatus: 'published',
  }];
  writeJson(cp, canonical);
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('asset with publishing[] ref is NOT emitted', !ids.includes('has-publishing-ref'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('21. Asset with missing platform field is filtered out');
{
  const cp = path.join(TMP_ROOT, 'canonical21.json');
  writeJson(cp, buildTestCanonical({
    assetId: 'no-platform',
    asset: {
      assetId: 'no-platform', campaignId: 'active-camp', name: 'No Platform',
      assetType: 'feed-post', caption: 'x'.repeat(150),
      visualBrief: 'Test visual brief concept — should be long enough to count',
      filePath: 'assets/test.jpg',
      owner: 'copywriter', qualityGateState: 'gate1-passed',
      captionStatus: 'approved', visualStatus: 'approved',
      approvalStatus: 'approved', publishStatus: 'scheduled',
      history: [
        { action: 'caption-created', by: 'copywriter', at: '2026-01-01' },
        { action: 'visual-revised', by: 'image-gen', at: '2026-01-02' },
        { action: 'visual-generated', by: 'image-gen', at: '2026-01-03', filePath: 'assets/test.jpg' },
        { action: 'visual-approved', by: 'retina', at: '2026-01-04' },
        { action: 'approval-approved', by: 'christelle', at: '2026-01-05' },
      ],
      // platform is intentionally omitted
    },
  }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('asset with no platform field is NOT emitted', !ids.includes('no-platform'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('22. Output JSON is parseable');
{
  const cp = path.join(TMP_ROOT, 'canonical22.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const content = fs.readFileSync(DEFAULT_READY, 'utf8');
    let parseable = true;
    try { JSON.parse(content); } catch (_) { parseable = false; }
    assert('output is valid JSON', parseable);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('23. Each Campaign OS item has source=campaign-os');
{
  const cp = path.join(TMP_ROOT, 'canonical23.json');
  writeJson(cp, buildTestCanonical({ assetId: 'source-test' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'source-test');
    assert('source = campaign-os', item && item.source === 'campaign-os');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('24. Campaign OS items have verdict=pass and passed_checks=4');
{
  const cp = path.join(TMP_ROOT, 'canonical24.json');
  writeJson(cp, buildTestCanonical({ assetId: 'verdict-test' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'verdict-test');
    assert('verdict = pass', item && item.verdict === 'pass');
    assert('passed_checks = 4', item && item.passed_checks === 4);
    assert('total_checks = 4', item && item.total_checks === 4);
    assert('issues is empty array', Array.isArray(item && item.issues) && item.issues.length === 0);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('25. Integration ID resolved correctly per platform');
{
  const cp = path.join(TMP_ROOT, 'canonical25.json');
  // (Generator itself doesn't emit integration_id — that's the publisher's
  // job — but the legacy items may have it. Verify that the Campaign OS
  // item itself doesn't carry an integration_id (publisher adds it).)
  writeJson(cp, buildTestCanonical({ assetId: 'platform-resolution' }));
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp, { dryRun: false });  // live mode — file must be written
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const item = written.items.find(i => i.item_id === 'platform-resolution');
    assert('item exists in written file', item !== undefined);
    assert('platform is set', item && typeof item.platform === 'string' && item.platform.length > 0);
    // Generator intentionally does NOT set integration_id — publisher adds it
    assert('integration_id is not pre-set by generator (publisher responsibility)', !item.integration_id);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('26. Cross-campaign publishing[] lookup works');
{
  const cp = path.join(TMP_ROOT, 'canonical26.json');
  const canonical = buildTestCanonical({ assetId: 'cross-camp-published' });
  // Put the publishing[] ref in a DIFFERENT campaign
  canonical.campaigns['other-camp'] = {
    identity: { status: 'active' },
    assets: {},
    publishing: [{
      publishingId: 'pub-cross',
      assetId: 'cross-camp-published',
      campaignId: 'other-camp',
      postizPostId: 'cm-cross',
      currentStatus: 'published',
    }],
  };
  writeJson(cp, canonical);
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    const ids = written.items.map(i => i.item_id);
    assert('asset with cross-campaign publishing[] ref is NOT emitted', !ids.includes('cross-camp-published'));
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('27. Generated timestamp matches canonical updatedAt');
{
  const cp = path.join(TMP_ROOT, 'canonical27.json');
  writeJson(cp, buildTestCanonical());
  // Canonical has updatedAt = '2026-07-23T11:00:00Z'
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('generated = canonical.updatedAt', written.generated === '2026-07-23T11:00:00Z');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('28. Output schema field is qa-inspector/v1');
{
  const cp = path.join(TMP_ROOT, 'canonical28.json');
  writeJson(cp, buildTestCanonical());
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('schema = qa-inspector/v1', written.schema === 'https://clawdia.io/agents/qa-inspector/v1');
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('29. Empty scheduled set produces 0 campaignOsCount');
{
  const cp = path.join(TMP_ROOT, 'canonical29.json');
  const canonical = JSON.parse(fs.readFileSync(DEFAULT_CANONICAL, 'utf8'));
  canonical.updatedAt = '2026-07-23T11:00:00Z';
  writeJson(cp, canonical);
  const backup = fs.readFileSync(DEFAULT_READY);
  try {
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('campaignOsCount = 0', written.campaignOsCount === 0);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backup);
  }
}

section('30. Empty scheduled set + empty legacy file = 0 items');
{
  const cp = path.join(TMP_ROOT, 'canonical30.json');
  writeJson(cp, buildTestCanonical({ campaignId: 'inactive-camp', campaignStatus: 'draft', assetId: 'never' }));
  const backupReady = fs.readFileSync(DEFAULT_READY);
  try {
    // Set legacy file to empty
    fs.writeFileSync(DEFAULT_READY, JSON.stringify({ schema: 'https://clawdia.io/agents/qa-inspector/v1', items: [] }));
    runGenerator(cp);
    const written = JSON.parse(fs.readFileSync(DEFAULT_READY, 'utf8'));
    assert('count = 0', written.count === 0);
    assert('items.length = 0', written.items.length === 0);
  } finally {
    fs.writeFileSync(DEFAULT_READY, backupReady);
  }
}

// ─── Output ───────────────────────────────────────────────────────────────

results.push('');
results.push(`Total: ${total}, Passed: ${passed}, Failed: ${failed}`);
console.log(results.join('\n'));

// Cleanup
  try {
    fs.rmSync(TMP_ROOT, { recursive: true, force: true });
  } catch (_) {}

process.exit(failed > 0 ? 1 : 0);