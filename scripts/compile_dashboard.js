#!/usr/bin/env node
/**
 * compile_dashboard.js
 * Reads all /data JSON files and builds dashboard.html
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT_HTML = path.join(__dirname, '..', 'dashboard.html');
const SUMMARY_OUT = path.join(DATA_DIR, 'dashboard-summary.json');
const META_OUT = path.join(DATA_DIR, 'build-meta.json');

function readJson(filename) {
  try {
    const raw = fs.readFileSync(path.join(DATA_DIR, filename), 'utf8');
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function timeAgo(isoString) {
  if (!isoString || isoString === 'never') return 'never';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function freshnessBadge(updated, maxAgeHours = 26) {
  if (!updated || updated === 'never') return '<span class="badge stale">⚠️ stale</span>';
  const age = (Date.now() - new Date(updated).getTime()) / 3600000;
  if (age > maxAgeHours) return '<span class="badge stale">⚠️ stale</span>';
  if (age > maxAgeHours * 0.7) return '<span class="badge warn">🕐 aging</span>';
  return '<span class="badge fresh">✅ fresh</span>';
}

function buildSection(title, badge, content) {
  return `<div class="section">
    <div class="section-header">
      <h2>${title}</h2>
      ${badge}
    </div>
    ${content}
  </div>`;
}

function truncate(str, len = 80) {
  if (!str) return '';
  return str.length > len ? str.substring(0, len) + '...' : str;
}

// ── LOAD ALL DATA ──────────────────────────────────────────────────
const ig = readJson('ig-analytics.json') || {};
const ga4 = readJson('ga4-metrics.json') || {};
const reddit = readJson('reddit-trends.json') || {};
const news = readJson('golf-news.json') || {};
const seoRank = readJson('seo-rankings.json') || {};
const seoAudit = readJson('seo-audit.json') || {};
const hooks = readJson('hook-bank.json') || {};
const ideas = readJson('content-ideas.json') || {};
const ab = readJson('ab-tests.json') || {};
const used = readJson('used-items.json') || { suppressed_ideas: [], suppressed_hooks: [] };
const published = readJson('published-posts.json') || { published: [] };
const buildMeta = readJson('build-meta.json') || {};
const postPlan   = readJson('post-plan.json') || null;
const salesPrio  = readJson('sales-priority.json') || null;
const missed     = readJson('missed-opportunities.json') || null;
const followUpQ  = readJson('follow-up-queue.json') || null;
const assetNeeds = readJson('asset-needs.json') || null;
const ownerWork  = readJson('owner-workload.json') || null;
const convAttr   = readJson('conversion-attribution.json') || null;
const funnelLeak = readJson('funnel-leaks.json')          || null;
const ctaPerf    = readJson('cta-performance.json')       || null;
const retarget   = readJson('retargeting-recommendations.json') || null;
const recScores = readJson('recommendation-scores.json') || null;

// ── SUMMARY BAR ──────────────────────────────────────────────────
const now = new Date().toISOString();
const sources = [
  { name: 'IG Analytics', updated: ig.updated },
  { name: 'GA4', updated: ga4.updated },
  { name: 'Reddit', updated: reddit.updated },
  { name: 'Golf News', updated: news.updated },
  { name: 'SEO Rankings', updated: seoRank.updated },
  { name: 'SEO Audit', updated: seoAudit.updated },
  { name: 'Hook Bank', updated: hooks.updated },
  { name: 'Ideas', updated: ideas.updated },
];
const stale = sources.filter(s => {
  if (!s.updated || s.updated === 'never') return true;
  return (Date.now() - new Date(s.updated).getTime()) > 26 * 3600000;
});

let topRecommendation = 'N/A';
if (ideas.ideas && ideas.ideas.length > 0) {
  const top = ideas.ideas.find(i => i.priority === 'today') || ideas.ideas[0];
  topRecommendation = truncate(top.title || top.hook || 'N/A', 60);
}

const summaryBar = `
<div class="summary-bar">
  <div class="summary-item">
    <span class="summary-label">Last Build</span>
    <span class="summary-value">${new Date(now).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg' })} SAST</span>
  </div>
  <div class="summary-item">
    <span class="summary-label">Stale Sources</span>
    <span class="summary-value ${stale.length > 0 ? 'warn' : 'ok'}">${stale.length > 0 ? stale.map(s => s.name).join(', ') : 'none'}</span>
  </div>
  <div class="summary-item">
    <span class="summary-label">Today's Top Idea</span>
    <span class="summary-value">${topRecommendation}</span>
  </div>
</div>`;

// ── IG PERFORMANCE ────────────────────────────────────────────────
let igContent = '<p class="empty">No IG data yet.</p>';
if (ig.posts && ig.posts.length > 0) {
  const posts = ig.posts.slice(0, 10);
  const best = posts.reduce((b, p) => (parseFloat(p.engagementRate) || 0) > (parseFloat(b.engagementRate) || 0) ? p : b, posts[0]);
  const avgEng = posts.reduce((s, p) => s + (parseFloat(p.engagementRate) || 0), 0) / posts.length;
  
  igContent = `
  <div class="ig-stats-row">
    <div class="ig-stat">
      <span class="ig-stat-num">${posts.length}</span>
      <span class="ig-stat-label">posts tracked</span>
    </div>
    <div class="ig-stat">
      <span class="ig-stat-num">${avgEng.toFixed(2)}%</span>
      <span class="ig-stat-label">avg engagement</span>
    </div>
    <div class="ig-stat">
      <span class="ig-stat-num">${best.engagementRate || '?'}%</span>
      <span class="ig-stat-label">best eng rate</span>
    </div>
  </div>
  <div class="post-list">
    ${posts.map(p => `
    <div class="post-row">
      <span class="post-date">${new Date(p.timestamp).toLocaleDateString('en-ZA', {timeZone:'Africa/Johannesburg'})}</span>
      <span class="post-caption">${truncate(p.captionPreview || p.caption || 'n/a', 45)}</span>
      <span class="post-reach">${p.reach || 0} reach</span>
      <span class="post-likes">❤️ ${p.likeCount || 0}</span>
      <span class="post-eng ${(parseFloat(p.engagementRate) || 0) > 3 ? 'good' : 'ok'}">${p.engagementRate || 0}% eng</span>
    </div>`).join('')}
  </div>`;
}
const igSection = buildSection('📱 Instagram Performance', freshnessBadge(ig.updated), igContent);

// ── THIS WEEK STRIP ───────────────────────────────────────────────
let thisWeekStrip = '';
let execSummarySection = '';
if (postPlan || salesPrio || missed || convAttr || funnelLeak) {
  const nextPost    = postPlan?.plan?.[0];
  const topSales    = salesPrio?.priorities?.[0];
  const runnerUp    = salesPrio?.priorities?.[1];
  const topMissed   = missed?.opportunities?.[0];
  const secondMissed = missed?.opportunities?.[1];
  const bestCTA     = topSales ? topSales.recommended_cta : null;
  const topLeak     = funnelLeak?.leaks?.[0];
  const topConvSvc   = convAttr?.summary?.top_converting_service || 'n/a';
  const topConvCTA   = convAttr?.summary?.top_converting_cta || 'n/a';
  const topHookTheme = convAttr?.summary?.top_hook_theme || 'n/a';
  const bookingSess  = convAttr?.summary?.booking_sessions || 0;
  const topBookingPg = convAttr?.summary?.top_booking_page || 'n/a';
  const sevColor     = { high: '#ff4757', medium: '#ffa500', low: '#00b4d8' };
  const missSev      = topMissed?.severity ? (sevColor[topMissed.severity] || 'var(--muted)') : 'var(--muted)';

  thisWeekStrip = `<div class="tw-strip">
    <div class="tw-item tw-item--post">
      <div class="tw-label">🎯 Post this first</div>
      <div class="tw-value">${nextPost?.hook ? truncate(nextPost.hook, 42) : 'No post planned'}</div>
      <div class="tw-meta">${(nextPost?.objective || '').toUpperCase()} · ${nextPost?.format || ''}</div>
    </div>
    <div class="tw-sep"></div>
    <div class="tw-item tw-item--sales">
      <div class="tw-label">💰 Push this week</div>
      <div class="tw-value">${topSales?.label || 'n/a'}</div>
      <div class="tw-meta">${topSales?.score ? topSales.score.toFixed(1) : '?'}/10 · ${topSales?.reasons?.[0] || ''}</div>
    </div>
    <div class="tw-sep"></div>
    <div class="tw-item tw-item--money">
      <div class="tw-label">💸 Making money</div>
      <div class="tw-value" style="font-size:0.82rem">${topConvSvc}</div>
      <div class="tw-meta">${bookingSess} booking sessions</div>
      <div class="tw-meta" style="color:#ffa500">${topHookTheme} converts</div>
    </div>
    <div class="tw-sep"></div>
    <div class="tw-item tw-item--missed">
      <div class="tw-label">⚠️ Biggest leak</div>
      <div class="tw-value" style="font-size:0.82rem;color:${topLeak?.severity === 'high' ? '#ff4757' : missSev}">${topLeak ? topLeak.easy_fix?.substring(0, 44) : (topMissed ? truncate(topMissed.suggestion, 44) : 'None detected')}</div>
      <div class="tw-meta">${topLeak ? topLeak.type?.replace(/_/g, ' ') : (topMissed?.type?.replace(/_/g, ' ') || '')}</div>
    </div>
    <div class="tw-sep"></div>
    <div class="tw-item tw-item--cta">
      <div class="tw-label">📲 Best CTA</div>
      <div class="tw-value">${bestCTA ? truncate(bestCTA.split('·')[0], 36) : 'Book your session'}</div>
      <div class="tw-meta">${topSales?.label || 'all posts'}</div>
    </div>
  </div>`;

  // Executive summary — inside same conditional as strip
  function execBadge(label, value, color) {
    return `<div class="es-item">
      <div class="es-label">${label}</div>
      <div class="es-value" style="${color ? 'color:' + color + ';font-weight:800' : ''}">${value}</div>
    </div>`;
  }
  const livePosts = ig.posts ? ig.posts.filter(p => {
    const age = (Date.now() - new Date(p.timestamp || p.created || 0).getTime()) / 86400000;
    return age <= 14;
  }).length : 0;
  const trustScore = postPlan?.plan ? Math.min(10, (postPlan.plan.filter(p => p.status === 'ready').length * 2 + 4)).toFixed(1) : 'n/a';
  const topAction  = nextPost ? truncate(nextPost.hook, 55) : 'None planned';
  const topSvc     = topSales?.label || 'n/a';
  const topLeakSvc = topLeak ? (topLeak.service || topLeak.type?.replace(/_/g, ' ')) : (topMissed ? (topMissed.topic || topMissed.type?.replace(/_/g, ' ')) : 'none');
  const loadedOwner = ownerWork?.most_loaded || 'n/a';
  const loadedCount = ownerWork?.most_loaded_count || 0;
  const sevColorEs = { high: '#ff4757', medium: '#ffa500', low: '#00b4d8' };
  const topLeakSeverity = topLeak?.severity || topMissed?.severity || 'low';
  const topLeakColor = sevColorEs[topLeakSeverity] || 'var(--text)';
  execSummarySection = `
  <div class="es-box">
    <div class="es-title">📋 THIS WEEK IN ONE LOOK</div>
    <div class="es-grid">
      ${execBadge('🎯 Top post', truncate(topAction, 40))}
      ${execBadge('💰 Service to push', topSvc, '#ffa500')}
      ${execBadge('⚠️ Missed / leak', topLeakSvc, topLeakColor)}
      ${execBadge('👥 Owner pressure', loadedOwner !== 'n/a' ? `${loadedOwner} (${loadedCount})` : 'Balanced', '#ff6b81')}
      ${execBadge('📊 Trust score', `${trustScore}/10`, livePosts >= 5 ? '#2ed573' : '#ffa500')}
    </div>
  </div>`;
}

// ── HOOK BANK ─────────────────────────────────────────────────────
let hookContent = '<p class="empty">No hook data yet. Run analyse_hooks.py.</p>';
if (hooks.hooks && hooks.hooks.length > 0) {
  const proven = hooks.hooks.filter(h => h.score >= 4).slice(0, 8);
  const fresh = hooks.hooks.filter(h => h.score >= 2 && h.score < 4).slice(0, 5);
  
  hookContent = `
  <div class="hook-group">
    <h3>🔥 Proven Hooks (score 4+)</h3>
    <div class="hook-list">
      ${proven.map(h => `
      <div class="hook-card">
        <div class="hook-text">${truncate(h.hook_text || h.text || h.headline || 'n/a', 60)}</div>
        <div class="hook-meta">
          <span class="hook-score">${h.score}/10</span>
          <span class="hook-topic">${h.topic_cluster || 'general'}</span>
          <span class="hook-formula">${h.formula_type || 'stat'}</span>
        </div>
      </div>`).join('')}
    </div>
  </div>
  <div class="hook-group">
    <h3>🧪 Fresh Hooks to Test</h3>
    <div class="hook-list">
      ${fresh.map(h => `
      <div class="hook-card fresh">
        <div class="hook-text">${truncate(h.hook_text || h.text || h.headline || 'n/a', 60)}</div>
        <div class="hook-meta">
          <span class="hook-score">${h.score}/10</span>
          <span class="hook-topic">${h.topic_cluster || 'general'}</span>
        </div>
      </div>`).join('')}
    </div>
  </div>`;
}
if (hooks.proven_hooks && hooks.proven_hooks.length > 0) {
  hookContent = `
  <div class="hook-group">
    <h3>🔥 Top Performing Hooks</h3>
    <div class="hook-list">
      ${hooks.proven_hooks.slice(0, 8).map(h => `
      <div class="hook-card">
        <div class="hook-text">${truncate(h.hook_text || h.text || h.headline || 'n/a', 60)}</div>
        <div class="hook-meta">
          <span class="hook-score">${h.engagementRate || h.score || '?'}%</span>
          <span class="hook-topic">${h.topic || h.topic_cluster || 'general'}</span>
        </div>
      </div>`).join('')}
    </div>
  </div>`;
}
const hookSection = buildSection('🪝 Hook Bank', freshnessBadge(hooks.updated), hookContent);

// ── WATCHED + WORKED ────────────────────────────────────────────
// Helper: truncate at word boundary, not mid-word
function wwTruncate(str, len) {
  if (!str) return '';
  if (str.length <= len) return str;
  const truncated = str.substring(0, len);
  const lastSpace = truncated.lastIndexOf(' ');
  return lastSpace > len * 0.7 ? truncated.substring(0, lastSpace) : truncated;
}

// Helper: determine content_type and override topics for non-hook cards
function wwClassify(h) {
  const text = (h.hook_text || '').toLowerCase();
  const rawTopics = h.youtube_topic_match || [];
  let contentType = 'hook';
  let topics = rawTopics;

  // CTA-led: starts with booking/session/schedule language
  if (/^(book|schedule|book your|book a|get your|claim|secure)/.test(text) ||
      (text.includes('book') && text.includes('session') && text.length < 70) ||
      (text.includes('@swingshack') && /book/i.test(text))) {
    contentType = 'cta';
    topics = ['booking', 'conversion'];
  }
  // Promo/competition-led
  else if (/\b(win|wins|competition|contest|prize|tournament|championship|leaderboard|lowest net|closest to|hole\-in\-one)\b/.test(text)) {
    contentType = 'promo';
    // Override: remove irrelevant carryover tags, keep competition/driver
    topics = rawTopics.filter(t => !['fitness', 'beginner', 'weather'].includes(t));
    if (!topics.includes('competition')) topics.unshift('competition');
    if (!topics.includes('driver') && text.includes('driver')) topics.push('driver');
    topics = topics.slice(0, 3);
  }
  // Product feature
  else if (/\b(new|now available|just dropped|lab golf|la golf|golf bar|putters? (now|available|dropped|in store)|custom fitted)\b/.test(text) &&
           /\b(driver|putter|iron|wedge|club|grip|shaft)\b/.test(text)) {
    contentType = 'product';
    topics = rawTopics.filter(t => !['fitness', 'beginner', 'weather', 'slice_fix'].includes(t));
    if (!topics.includes('product')) topics.unshift('product');
    topics = topics.slice(0, 3);
  }

  return { contentType, topics };
}

// Helper: action suggestion based on content_type + bucket
function wwAction(contentType, bucket) {
  if (contentType === 'cta')    return '<span class="ww-action ww-action--cta">📲 Use as CTA</span>';
  if (contentType === 'promo')  return '<span class="ww-action ww-action--boost">🚀 Promote as contest</span>';
  if (contentType === 'product') return '<span class="ww-action ww-action--product">🛒 Post as product feature</span>';
  if (bucket === 'proven_and_trending') return '<span class="ww-action ww-action--boost">🚀 Boost on IG</span>';
  return '<span class="ww-action ww-action--reel">🎬 Turn into Reel</span>';
}

let watchedContent = '<p class="empty">No watched + worked data yet.</p>';

if ((hooks.watched_and_worked && hooks.watched_and_worked.length > 0) ||
    (hooks.output_buckets && (hooks.output_buckets.proven_and_trending.length > 0 || hooks.output_buckets.trending_to_test.length > 0))) {

  // Build unified list from both sources
  const wwAll = [
    ...(hooks.watched_and_worked || []),
    ...((hooks.output_buckets && !hooks.watched_and_worked) ?
      [...(hooks.output_buckets.proven_and_trending || []).map(h => ({ ...h, signal_bucket: 'proven_and_trending' })),
       ...(hooks.output_buckets.trending_to_test || []).map(h => ({ ...h, signal_bucket: 'trending_to_test' }))] : [])
  ];

  // Deduplicate by hook_id
  const seen = new Set();
  const ww = wwAll.filter(h => {
    if (!h.hook_id) return true;
    if (seen.has(h.hook_id)) return false;
    seen.add(h.hook_id); return true;
  }).slice(0, 5);

  const cards = ww.map(h => {
    const bucket = h.signal_bucket || 'proven_only';
    const { contentType, topics } = wwClassify(h);

    let statusBadge = '';
    if (bucket === 'proven_and_trending') statusBadge = '<span class="ww-badge ww-badge--pt">🔥 PROVEN + TRENDING</span>';
    else if (bucket === 'trending_to_test') statusBadge = '<span class="ww-badge ww-badge--tt">🚀 PROMOTE NEXT</span>';
    else if (bucket === 'proven_only') statusBadge = '<span class="ww-badge ww-badge--po">✅ PROVEN ONLY</span>';

    let contentTypeBadge = '';
    if (contentType === 'cta') contentTypeBadge = '<span class="ww-ct-badge ww-ct-badge--cta">CTA</span>';
    else if (contentType === 'promo') contentTypeBadge = '<span class="ww-ct-badge ww-ct-badge--promo">PROMO</span>';
    else if (contentType === 'product') contentTypeBadge = '<span class="ww-ct-badge ww-ct-badge--product">PRODUCT</span>';

    const topicHtml = topics.slice(0, 3).map(t => `<span class="ww-topic">${t}</span>`).join('');

    // Evidence: show first title + note about additional matches
    let evidenceHtml = '';
    if (h.youtube_evidence_titles && h.youtube_evidence_titles.length > 0) {
      const first = h.youtube_evidence_titles[0];
      const rest = h.youtube_evidence_titles.length - 1;
      if (rest > 0) {
        evidenceHtml = `<div class="ww-evidence">📺 ${wwTruncate(first, 45)} <span class="ww-evidence-more">+ ${rest} more video${rest > 1 ? 's' : ''}</span></div>`;
      } else {
        evidenceHtml = `<div class="ww-evidence">📺 ${wwTruncate(first, 50)}</div>`;
      }
    }

    const action = wwAction(contentType, bucket);

    return {
      bucket,
      html: `
    <div class="ww-card ww-card--${bucket === 'proven_and_trending' ? 'pt' : bucket === 'trending_to_test' ? 'tt' : 'po'}" data-content-type="${contentType}">
      <div class="ww-card-top">
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          ${statusBadge}
          ${contentTypeBadge}
        </div>
        ${action}
      </div>
      <div class="ww-hook">${wwTruncate(h.hook_text || 'n/a', 68)}</div>
      <div class="ww-scores">
        <span class="ww-score ig">IG ${h.ig_proof_score || '?'}</span>
        <span class="ww-score yt">YT ${h.youtube_alignment_score || '?'}</span>
        <span class="ww-score cross" title="Cross = IG proof × 0.6 + YouTube alignment × 0.2 + Reddit × 0.2">Cross ${h.cross_signal_score || '?'}</span>
      </div>
      ${topicHtml ? `<div class="ww-topics">${topicHtml}</div>` : ''}
      ${evidenceHtml}
    </div>`
    };
  });

  // SUMMARY COUNTS: derived directly from rendered card badges — always accurate
  const ptCount = cards.filter(c => c.bucket === 'proven_and_trending').length;
  const ttCount = cards.filter(c => c.bucket === 'trending_to_test').length;
  const poCount = cards.filter(c => c.bucket === 'proven_only').length;
  const summaryLine = `<p class="ww-summary-line">${ptCount} 🔥 proven + trending · ${ttCount} 🚀 promote next · ${poCount} ✅ proven only</p>`;

  const badge = '<span class="badge ig-yt-badge">IG + YT</span>';
  const cardHtml = cards.map(c => c.html).join('');
  // Wrap in a filterable container with tab buttons
  watchedContent = `
  <div class="ww-filter-bar">
    <button class="ww-filter-btn active" data-filter="all">All</button>
    <button class="ww-filter-btn" data-filter="hook">Hooks</button>
    <button class="ww-filter-btn" data-filter="promo">Promo</button>
    <button class="ww-filter-btn" data-filter="cta">CTA</button>
    <button class="ww-filter-btn" data-filter="product">Product</button>
  </div>
  ${summaryLine}
  <div class="ww-grid" id="ww-grid">${cardHtml}</div>
  <script>
  document.querySelectorAll('.ww-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const f = btn.dataset.filter;
      document.querySelectorAll('.ww-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.ww-card').forEach(c => {
        const ct = c.dataset.contentType || 'hook';
        c.style.display = (f === 'all' || ct === f) ? '' : 'none';
      });
    });
  });
  </script>`;
}

const watchedSection = buildSection('👀 WATCHED + WORKED', freshnessBadge(hooks.updated), watchedContent);

// ── CONTENT IDEAS ────────────────────────────────────────────────
let ideaContent = '<p class="empty">No content ideas yet. Run generate_content_ideas.py.</p>';
if (ideas.ideas && ideas.ideas.length > 0) {
  const today = ideas.ideas.filter(i => i.priority === 'today' || i.freshness_score >= 8).slice(0, 5);
  const thisWeek = ideas.ideas.filter(i => i.freshness_score >= 6 && i.freshness_score < 8).slice(0, 6);
  
  ideaContent = `
  <div class="idea-group">
    <h3>🎯 Post Today</h3>
    <div class="idea-list">
      ${today.length > 0 ? today.map(i => `
      <div class="idea-card">
        <div class="idea-title">${truncate(i.title || i.hook || 'n/a', 55)}</div>
        <div class="idea-meta">
          <span class="idea-format">${i.format || 'static'}</span>
          <span class="idea-source">${i.source_reason || 'unknown'}</span>
          <span class="idea-score">📊 ${i.freshness_score || '?'}/10</span>
        </div>
        ${i.best_cta ? `<div class="idea-cta">CTA: ${i.best_cta}</div>` : ''}
      </div>`).join('') : '<p class="empty">No high-priority ideas today</p>'}
    </div>
  </div>
  <div class="idea-group">
    <h3>📅 This Week</h3>
    <div class="idea-list">
      ${thisWeek.map(i => `
      <div class="idea-card">
        <div class="idea-title">${truncate(i.title || i.hook || 'n/a', 55)}</div>
        <div class="idea-meta">
          <span class="idea-format">${i.format || 'static'}</span>
          <span class="idea-source">${i.source_reason || 'unknown'}</span>
        </div>
      </div>`).join('')}
    </div>
  </div>`;
}
if (ideas.post_today && ideas.post_today.length > 0) {
  ideaContent = `
  <div class="idea-group">
    <h3>🎯 Post Today</h3>
    <div class="idea-list">
      ${ideas.post_today.slice(0, 5).map(i => `
      <div class="idea-card today">
        <div class="idea-title">${truncate(i.title || i.headline || 'n/a', 60)}</div>
        <div class="idea-meta">
          <span class="idea-format">${i.format || 'static'}</span>
          <span class="idea-cta">CTA: ${i.cta || i.best_cta || 'link in bio'}</span>
        </div>
      </div>`).join('')}
    </div>
  </div>`;
}

// ── FOLLOW UP NEXT ───────────────────────────────────────────────
let followUpContent = '<p class="empty">No follow-up queue yet.</p>';
if (followUpQ && followUpQ.queue && followUpQ.queue.length > 0) {
  const items = followUpQ.queue.slice(0, 4);
  const cards = items.map(item => {
    const urgClass = item.urgency === 'high' ? 'fu-urgency--high' : item.urgency === 'medium' ? 'fu-urgency--med' : 'fu-urgency--low';
    const urgLabel = item.urgency === 'high' ? 'HIGH' : item.urgency === 'medium' ? 'MED' : 'low';
    const planned = item.already_planned ? '<span class="fu-planned">📅 in this week\'s plan</span>' : '';
    return `
    <div class="fu-card">
      <div class="fu-card-header">
        <span class="fu-topic">${item.topic}</span>
        <span class="fu-owner">👤 ${item.owner}</span>
        <span class="fu-urgency ${urgClass}">${urgLabel}</span>
        ${planned}
      </div>
      <div class="fu-hook">${truncate(item.suggested_hook || item.original_hook || '', 65)}</div>
      <div class="fu-why">→ ${truncate(item.why_now || '', 60)}</div>
      <div class="fu-footer">
        <span class="fu-asset">📦 ${truncate(item.asset_needed || '', 40)}</span>
        <span class="fu-cta">${truncate(item.suggested_cta || '', 35)}</span>
      </div>
    </div>`;
  }).join('');

  const summary = `<p class="fu-summary">
    ${followUpQ.queue.length} topics need follow-up ·
    <span class="fu-hi">${followUpQ.meta?.high_urgency || 0} high priority</span> ·
    Owners: ${(followUpQ.meta?.owners || []).join(', ')}
  </p>`;

  followUpContent = summary + '<div class="fu-grid">' + cards + '</div>';
}
const followUpSection = buildSection('🔄 FOLLOW UP NEXT', freshnessBadge(followUpQ?.updated), followUpContent);

// ── ASSET NEEDS THIS WEEK ───────────────────────────────────────
let assetContent = '<p class="empty">No asset needs detected.</p>';
if (assetNeeds && assetNeeds.needs && assetNeeds.needs.length > 0) {
  const cards = assetNeeds.needs.slice(0, 5).map(n => {
    const urg = n.urgency === 'today' ? 'today' : n.urgency === 'this_week' ? 'week' : 'flex';
    return `
    <div class="an-card">
      <div class="an-header">
        <span class="an-owner">👤 ${n.owner}</span>
        <span class="an-count">${n.count} post${n.count > 1 ? 's' : ''}</span>
        <span class="an-urg">${urg}</span>
      </div>
      <div class="an-label">${n.asset_label || n.asset_raw}</div>
      <div class="an-posts">${n.posts.slice(0,2).map(p => `<div class="an-post">· ${p.hook || ''}</div>`).join('')}</div>
    </div>`;
  }).join('');
  assetContent = `<div class="an-summary">${assetNeeds.needs.length} asset needs across ${Object.keys(assetNeeds.by_owner || {}).length} owners · ${assetNeeds.summary?.by_urgency?.today || 0} needed today</div><div class="an-grid">${cards}</div>`;
}
const assetSection = buildSection('📦 ASSET NEEDS THIS WEEK', freshnessBadge(assetNeeds?.updated), assetContent);

// ── OWNER WORKLOAD ───────────────────────────────────────────────
let workloadContent = '<p class="empty">No workload data yet.</p>';
if (ownerWork && ownerWork.owners && ownerWork.owners.length > 0) {
  const rows = ownerWork.owners.slice(0, 5).map(ow => {
    const hiToday = ow.by_urgency.today > 0;
    return `
    <div class="ow-row">
      <div class="ow-owner">
        <span class="ow-name">${ow.owner}</span>
        <span class="ow-total">${ow.total} items</span>
      </div>
      <div class="ow-bars">
        <span class="ow-bar ow-bar--today ${hiToday ? 'active' : ''}" title="Today">${ow.by_urgency.today > 0 ? ow.by_urgency.today + ' today' : ''}</span>
        <span class="ow-bar ow-bar--week">${ow.by_urgency.this_week > 0 ? ow.by_urgency.this_week + ' this week' : ''}</span>
        <span class="ow-bar ow-bar--flex">${ow.by_urgency.flexible > 0 ? ow.by_urgency.flexible + ' flexible' : ''}</span>
      </div>
      <div class="ow-top-item">${ow.items[0] ? ow.items[0].hook?.substring(0, 50) || ow.items[0].topic : '—'}</div>
    </div>`;
  }).join('');
  workloadContent = `
  <div class="ow-header-row">
    <span class="ow-col-owner">Owner</span>
    <span class="ow-col-items">Workload</span>
    <span class="ow-col-top">Top item</span>
  </div>
  ${rows}
  <p class="ow-note">Most loaded: <b>${ownerWork.most_loaded || 'n/a'}</b> (${ownerWork.most_loaded_count || 0} items)</p>`;
}
const workloadSection = buildSection('👥 OWNER WORKLOAD', freshnessBadge(ownerWork?.updated), workloadContent);

// ── RETARGETING RECOMMENDATIONS ──────────────────────────────────
let retargetContent = '<p class="empty">No retargeting recommendations yet.</p>';
if (retarget && retarget.recommendations && retarget.recommendations.length > 0) {
  const urgColors = { today: '#ff4757', this_week: '#ffa500', flexible: '#00b4d8' };
  const typeIcons = {
    retarget_existing:       '\ud83d\udd01',
    add_booking_cta:         '\ud83d\udcdd',
    new_service_reminder:   '\ud83c\udfaf',
    push_booking_cta:       '\ud83d\udcb8',
    rework_angle:            '\ud83d\udd04',
    promo_plus_booking:     '\ud83c\udf89',
  };
  const cards = retarget.recommendations.slice(0, 6).map(r => {
    const urg = r.urgency === 'today' ? 'TODAY' : r.urgency === 'this_week' ? 'THIS WEEK' : 'flex';
    const urgC = urgColors[r.urgency] || '#00b4d8';
    const icon = typeIcons[r.type] || '\ud83d\udccb';
    const planned = r.already_planned ? '<span class="rt-planned">\ud83d\udcc5 in plan</span>' : '';
    return '<div class="rt-card"><div class="rt-header"><span class="rt-icon">' + icon + '</span><span class="rt-action">' + r.action + '</span><span class="rt-owner">\ud83d\udc64 ' + r.owner + '</span><span class="rt-urg" style="background:' + urgC + '22;color:' + urgC + '">' + urg + '</span>' + planned + '</div><div class="rt-hook">' + truncate(r.suggested_hook || r.hook || '—', 70) + '</div><div class="rt-why">\u2192 ' + truncate(r.why || '', 65) + '</div><div class="rt-cta">CTA: ' + truncate(r.suggested_cta || '', 55) + '</div></div>';
  }).join('');
  const summary = '<p class="rt-summary">' + retarget.recommendations.length + ' retargeting actions \u00b7 <b>' + retarget.summary.today + ' today</b> \u00b7 <b>' + retarget.summary.this_week + ' this week</b></p>';
  retargetContent = summary + '<div class="rt-grid">' + cards + '</div>';
}
const retargetSection = buildSection('\ud83d\udd01 RETARGET THIS WEEK', freshnessBadge(retarget?.updated), retargetContent);

// DO THIS FIRST
let doFirstContent = '<p class="empty">No priority actions yet.</p>';
if (recScores && recScores.do_first && recScores.do_first.length > 0) {
  const cards = recScores.do_first.map(function(d) {
    var score = d.item && d.item.score ? d.item.score : '?';
    var scoreColor = score >= 8 ? '#2ed573' : score >= 5 ? '#ffa502' : '#ff4757';
    var title = truncate(d.item && (d.item.suggested_hook || d.item.hook || d.item.service || d.item.action) || '—', 55);
    var meta = truncate(d.item && d.item.suggested_cta || d.score_note || '', 50);
    return '<div class="dtf-card"><div class="dtf-emoji">' + d.emoji + '</div><div class="dtf-body"><div class="dtf-label">' + d.label + '</div><div class="dtf-title">' + title + '</div><div class="dtf-meta">' + meta + '</div></div><div class="dtf-score" style="color:' + scoreColor + '">' + score + '</div></div>';
  }).join('');
  var overall = recScores.summary && recScores.summary.overall_priority_score ? recScores.summary.overall_priority_score : '?';
  doFirstContent = '<div class="dtf-summary">Overall priority: <b style="color:#ffa502">' + overall + '/10</b> &middot; ' + recScores.do_first.length + ' actions queued</div><div class="dtf-grid">' + cards + '</div>';
}
var doFirstSection = buildSection('\ud83d\udcaa DO THIS FIRST', freshnessBadge(recScores && recScores.updated), doFirstContent);

const ideaSection = buildSection('\ud83d\udca1 Content Ideas', freshnessBadge(ideas.updated), ideaContent);

// ── GOLF NEWS ─────────────────────────────────────────────────────
let newsContent = '<p class="empty">No golf news yet.</p>';
if (news.news && news.news.length > 0) {
  newsContent = `
  <div class="news-list">
    ${news.news.slice(0, 8).map(n => `
    <div class="news-card">
      <div class="news-headline">${truncate(n.title || n.headline || 'n/a', 70)}</div>
      <div class="news-meta">
        <span class="news-source">${n.source || 'unknown'}</span>
        <span class="news-date">${n.published_date || n.date || ''}</span>
      </div>
      ${n.content_angle_score >= 7 ? `<span class="news-badge">🔥 use this</span>` : ''}
    </div>`).join('')}
  </div>`;
}
if (news.items && news.items.length > 0) {
  newsContent = `
  <div class="news-list">
    ${news.items.slice(0, 8).map(n => `
    <div class="news-card">
      <div class="news-headline">${truncate(n.title || 'n/a', 70)}</div>
      <div class="news-meta">
        <span class="news-source">${n.source || 'unknown'}</span>
        <span class="news-date">${n.date || ''}</span>
      </div>
    </div>`).join('')}
  </div>`;
}
const newsSection = buildSection('🏌️ Golf News', freshnessBadge(news.updated), newsContent);

// ── REDDIT TRENDS ─────────────────────────────────────────────────
let redditContent = '<p class="empty">No Reddit trends yet.</p>';
if (reddit.trends && reddit.trends.length > 0) {
  const hot = reddit.trends.filter(t => t.score >= 50).slice(0, 6);
  redditContent = `
  <div class="reddit-list">
    ${hot.map(t => `
    <div class="reddit-card">
      <div class="reddit-title">${truncate(t.title || 'n/a', 70)}</div>
      <div class="reddit-meta">
        <span class="reddit-sub">r/${t.subreddit || 'golf'}</span>
        <span class="reddit-score">⬆ ${t.score || 0}</span>
        <span class="reddit-comments">💬 ${t.comments_count || t.num_comments || 0}</span>
      </div>
      <div class="reddit-intent">${(t.intent || t.topic_cluster || 'general').replace(/_/g, ' ')}</div>
    </div>`).join('')}
  </div>`;
}
const redditSection = buildSection('🔴 Reddit Pain Points', freshnessBadge(reddit.updated), redditContent);

// ── SEO + WEBSITE ────────────────────────────────────────────────
let seoContent = '<p class="empty">No SEO data yet.</p>';
if (seoRank.keywords && seoRank.keywords.length > 0) {
  seoContent = `
  <div class="seo-keywords">
    <table class="seo-table">
      <tr><th>Keyword</th><th>Rank</th><th>Delta</th><th>Recommendation</th></tr>
      ${seoRank.keywords.slice(0, 10).map(k => `
      <tr>
        <td>${k.keyword || k.term || 'n/a'}</td>
        <td class="${(k.current_rank || 0) <= 10 ? 'good' : 'ok'}">${k.current_rank || '?'}</td>
        <td class="${(k.delta || 0) > 0 ? 'good' : (k.delta || 0) < 0 ? 'bad' : 'ok'}">${(k.delta || 0) > 0 ? '↑' : (k.delta || 0) < 0 ? '↓' : '→'} ${Math.abs(k.delta || 0)}</td>
        <td>${truncate(k.recommendation || k.note || '', 40)}</td>
      </tr>`).join('')}
    </table>
  </div>`;
}
if (seoRank.rising_keywords || seoRank.falling_keywords) {
  seoContent = `
  <div class="seo-summary">
    ${(seoRank.rising_keywords || []).length > 0 ? `<div class="seo-win"><b>📈 Rising:</b> ${seoRank.rising_keywords.join(', ')}</div>` : ''}
    ${(seoRank.falling_keywords || []).length > 0 ? `<div class="seo-lose"><b>📉 Falling:</b> ${seoRank.falling_keywords.join(', ')}</div>` : ''}
  </div>
  <div class="seo-keywords">
    <table class="seo-table">
      <tr><th>Keyword</th><th>Rank</th><th>7d Δ</th></tr>
      ${(seoRank.keywords || []).slice(0, 12).map(k => `
      <tr>
        <td>${k.keyword || k.term || 'n/a'}</td>
        <td class="${(k.current_rank || 0) <= 5 ? 'good' : ''}">${k.current_rank || '?'}</td>
        <td class="${(k.delta_7d || k.delta || 0) > 0 ? 'good' : (k.delta_7d || k.delta || 0) < 0 ? 'bad' : 'ok'}">${k.delta_7d || k.delta || 0}</td>
      </tr>`).join('')}
    </table>
  </div>`;
}
const seoSection = buildSection('🔍 SEO Rankings', freshnessBadge(seoRank.updated), seoContent);

// ── WEBSITE PERFORMANCE (GA4) ───────────────────────────────────
let ga4Content = '<p class="empty">No GA4 data yet.</p>';
if (ga4.metrics || ga4.data || ga4.pages) {
  const pages = ga4.pages || (ga4.data && ga4.data.rows ? ga4.data.rows.slice(0, 8) : []);
  if (pages.length > 0) {
    ga4Content = `
    <div class="ga4-pages">
      <table class="ga4-table">
        <tr><th>Landing Page</th><th>Sessions</th><th>Eng Rate</th></tr>
        ${pages.map(r => {
          const page = r.pagePath || r.path || r.url || Object.values(r)[0];
          const sessions = r.sessions || r.pageViews || Object.values(r)[1] || 0;
          const engRate = r.engagementRate || r.bounceRate ? (100 - (r.bounceRate || 0)).toFixed(1) + '%' : '?';
          return `<tr><td>${truncate(page, 45)}</td><td>${sessions}</td><td class="${engRate > 60 ? 'good' : ''}">${engRate}</td></tr>`;
        }).join('')}
      </table>
    </div>`;
  }
}
const ga4Section = buildSection('🌐 Website Performance', freshnessBadge(ga4.updated), ga4Content);

// ── A/B TESTS ─────────────────────────────────────────────────────
let abContent = '<p class="empty">No A/B test data yet.</p>';
if (ab.tests && ab.tests.length > 0) {
  abContent = `
  <div class="ab-list">
    ${ab.tests.map(t => `
    <div class="ab-card">
      <div class="ab-name">${t.name || t.hook || 'Test ' + t.id}</div>
      <div class="ab-meta">
        <span class="ab-winner ${t.winner ? 'good' : ''}">${t.winner ? '🏆 Winner: ' + t.winner : '⏳ Pending'}</span>
        <span class="ab-eng">${t.engagement || t.engagementRate || '?'}% eng</span>
      </div>
      ${t.next_action ? `<div class="ab-action">→ ${t.next_action}</div>` : ''}
    </div>`).join('')}
  </div>`;
}
const abSection = buildSection('🧪 A/B Test Lab', freshnessBadge(ab.updated), abContent);

// ── USED ITEMS / COOLDOWN ─────────────────────────────────────────
const suppressedIdeas = (used.suppressed_ideas || []).slice(0, 5);
const suppressedHooks = (used.suppressed_hooks || []).slice(0, 5);
let usedContent = '<p class="empty">Nothing on cooldown.</p>';
if (suppressedIdeas.length > 0 || suppressedHooks.length > 0) {
  usedContent = `
  <div class="cooldown-list">
    ${suppressedHooks.map(h => `<div class="cooldown-item">🪝 <b>${h.id}</b> — on cooldown until ${h.release_on || '?'}</div>`).join('')}
    ${suppressedIdeas.map(i => `<div class="cooldown-item">💡 <b>${i.id}</b> — on cooldown until ${i.release_on || '?'}</div>`).join('')}
  </div>
  <p class="small">Items auto-release after cooldown expires.</p>`;
}
const usedSection = buildSection('🔄 Used Items On Cooldown', freshnessBadge(used.updated || 'never'), usedContent);

// ── BUILD FULL HTML ────────────────────────────────────────────────
const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swing Shack — Marketing Intelligence Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #0f0f23;
  --card: #1a1a2e;
  --card-hover: #1f1f3a;
  --text: #e0e0ff;
  --muted: #7878a0;
  --success: #00d26a;
  --warning: #ffa500;
  --danger: #ff4757;
  --info: #00b4d8;
  --purple: #9b59b6;
}
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg); color: var(--text); padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }

.header { text-align: center; padding: 20px 0 30px; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 30px; }
.header h1 { font-size: 2rem; background: linear-gradient(90deg, #e1306c, #ff0050); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header p { color: var(--muted); font-size: 0.9rem; margin-top: 8px; }

.summary-bar { display: flex; gap: 20px; background: var(--card); border-radius: 12px; padding: 15px 20px; margin-bottom: 25px; flex-wrap: wrap; }
.summary-item { display: flex; flex-direction: column; gap: 4px; }
.summary-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.summary-value { font-weight: 600; font-size: 0.95rem; }
.summary-value.warn { color: var(--warning); }
.summary-value.ok { color: var(--success); }

.section { background: var(--card); border-radius: 16px; padding: 20px; margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 12px; }
.section-header h2 { font-size: 1.2rem; }
.badge { font-size: 0.75rem; padding: 3px 8px; border-radius: 8px; }
.badge.fresh { background: rgba(0,210,106,0.15); color: var(--success); }
.badge.stale { background: rgba(255,71,87,0.15); color: var(--danger); }
.badge.warn { background: rgba(255,165,0,0.15); color: var(--warning); }

.empty { color: var(--muted); font-style: italic; font-size: 0.9rem; }
.small { font-size: 0.8rem; color: var(--muted); margin-top: 8px; }

.ig-stats-row { display: flex; gap: 20px; margin-bottom: 15px; }
.ig-stat { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px 18px; text-align: center; }
.ig-stat-num { font-size: 1.8rem; font-weight: bold; color: var(--info); display: block; }
.ig-stat-label { font-size: 0.75rem; color: var(--muted); }

.post-list { display: flex; flex-direction: column; gap: 6px; }
.post-row { display: flex; gap: 10px; align-items: center; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 8px; font-size: 0.85rem; }
.post-date { color: var(--muted); min-width: 80px; }
.post-caption { flex: 1; color: var(--text); }
.post-reach { color: var(--muted); }
.post-likes { color: #e1306c; }
.post-eng { color: var(--muted); }
.post-eng.good { color: var(--success); }

.hook-list { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.hook-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px 15px; }
.hook-card.fresh { border-left: 3px solid var(--info); }
.hook-text { font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; }
.hook-meta { display: flex; gap: 8px; font-size: 0.75rem; color: var(--muted); }
.hook-score { color: var(--warning); }
.hook-group { margin-bottom: 15px; }
.hook-group h3 { font-size: 0.9rem; color: var(--muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }

.idea-list { display: flex; flex-direction: column; gap: 8px; }
.idea-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px 15px; }
.idea-card.today { border-left: 3px solid var(--success); }
.idea-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; }
.idea-meta { display: flex; gap: 8px; font-size: 0.75rem; color: var(--muted); }
.idea-format { background: rgba(0,180,216,0.2); color: var(--info); padding: 2px 6px; border-radius: 4px; }
.idea-cta { font-size: 0.8rem; color: var(--success); margin-top: 4px; }
.idea-group { margin-bottom: 12px; }
.idea-group h3 { font-size: 0.85rem; color: var(--muted); margin-bottom: 8px; text-transform: uppercase; }

.news-list { display: flex; flex-direction: column; gap: 8px; }
.news-card { background: rgba(255,255,255,0.03); border-radius: 8px; padding: 10px 12px; }
.news-headline { font-weight: 600; font-size: 0.9rem; margin-bottom: 5px; }
.news-meta { font-size: 0.75rem; color: var(--muted); }
.news-source { margin-right: 10px; }
.news-badge { display: inline-block; background: rgba(255,71,87,0.2); color: var(--danger); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; margin-top: 4px; }

.reddit-list { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.reddit-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px; border-left: 3px solid #ff4500; }
.reddit-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; }
.reddit-meta { display: flex; gap: 10px; font-size: 0.75rem; color: var(--muted); }
.reddit-sub { color: #ff4500; }
.reddit-intent { font-size: 0.75rem; color: var(--info); margin-top: 4px; }

.seo-keywords { overflow-x: auto; }
.seo-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.seo-table th { text-align: left; color: var(--muted); padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
.seo-table td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.seo-table .good { color: var(--success); }
.seo-table .bad { color: var(--danger); }
.seo-summary { margin-bottom: 12px; font-size: 0.85rem; }
.seo-win { color: var(--success); margin-bottom: 4px; }
.seo-lose { color: var(--danger); }

.ga4-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.ga4-table th { text-align: left; color: var(--muted); padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
.ga4-table td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.ga4-table .good { color: var(--success); }

.ab-list { display: flex; flex-direction: column; gap: 10px; }
.ab-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px; }
.ab-name { font-weight: 600; margin-bottom: 5px; }
.ab-meta { display: flex; gap: 12px; font-size: 0.8rem; }
.ab-winner.good { color: var(--success); }
.ab-action { font-size: 0.8rem; color: var(--info); margin-top: 4px; }

.cooldown-list { display: flex; flex-direction: column; gap: 6px; }
.cooldown-item { background: rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 8px; font-size: 0.85rem; }

/* WATCHED + WORKED */
.ww-summary { font-size: 0.82rem; color: var(--muted); margin-bottom: 12px; font-style: italic; }
.ww-summary-line { font-size: 0.8rem; color: var(--muted); margin-bottom: 12px; font-weight: 600; }
.ww-filter-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.ww-filter-btn { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: var(--muted); font-size: 0.75rem; padding: 4px 12px; border-radius: 20px; cursor: pointer; transition: all 0.15s; font-weight: 600; }
.ww-filter-btn:hover { background: rgba(255,255,255,0.1); color: var(--text); }
.ww-filter-btn.active { background: rgba(155,89,182,0.3); border-color: rgba(155,89,182,0.5); color: #c07fd4; }

/* THIS WEEK STRIP */
.tw-strip { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr auto 1fr; gap: 0; background: var(--card); border-radius: 12px; padding: 14px 0; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.08); }
.tw-item { padding: 0 16px; }
.tw-item--post { border-left: 3px solid #00d26a; }
.tw-item--sales { border-left: 3px solid #ffa500; }
.tw-item--missed { border-left: 3px solid #ff4757; }
.tw-item--cta { border-left: 3px solid #00b4d8; }
.tw-item--money { border-left: 3px solid #ff4757; }

/* EXECUTIVE SUMMARY */
.es-box { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.08); }
.es-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); font-weight: 800; margin-bottom: 10px; }
.es-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 14px; }
.es-item { display: flex; flex-direction: column; gap: 3px; }
.es-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); }
.es-value { font-size: 0.82rem; font-weight: 700; color: var(--text); line-height: 1.3; }
.tw-sep { width: 1px; background: rgba(255,255,255,0.08); margin: 4px 0; }
.tw-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); font-weight: 700; margin-bottom: 5px; }
.tw-value { font-size: 0.85rem; font-weight: 700; color: var(--text); margin-bottom: 3px; line-height: 1.3; }
.tw-meta { font-size: 0.7rem; color: var(--muted); }
.tw-meta--secondary { color: var(--muted); opacity: 0.7; margin-top: 2px; }
.tw-action { font-size: 0.7rem; color: var(--info); margin-top: 3px; font-style: italic; }
.tw-sales-main { color: #ffa500; }

/* FOLLOW UP NEXT */
.fu-summary { font-size: 0.8rem; color: var(--muted); margin-bottom: 12px; font-weight: 600; }
.fu-hi { color: #ff4757; }
.fu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.fu-card { background: rgba(255,255,255,0.04); border-radius: 10px; padding: 12px 14px; border-left: 3px solid #ff6b35; }
.fu-card-header { display: flex; gap: 8px; align-items: center; margin-bottom: 7px; flex-wrap: wrap; }
.fu-topic { font-size: 0.72rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #ff6b35; background: rgba(255,107,53,0.15); padding: 2px 7px; border-radius: 4px; }
.fu-owner { font-size: 0.72rem; color: var(--muted); font-weight: 600; }
.fu-urgency { font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; }
.fu-urgency--high { background: rgba(255,71,87,0.2); color: #ff4757; }
.fu-urgency--med  { background: rgba(255,165,0,0.2); color: #ffa500; }
.fu-urgency--low  { background: rgba(0,180,216,0.2); color: var(--info); }
.fu-planned { font-size: 0.65rem; color: var(--success); background: rgba(0,210,106,0.1); padding: 2px 6px; border-radius: 4px; }
.fu-hook { font-size: 0.87rem; font-weight: 700; color: var(--text); margin-bottom: 4px; line-height: 1.35; }
.fu-why { font-size: 0.73rem; color: var(--muted); font-style: italic; margin-bottom: 5px; }
.fu-footer { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.fu-asset { font-size: 0.7rem; color: var(--info); }
.fu-cta { font-size: 0.7rem; color: var(--success); }

/* ASSET NEEDS THIS WEEK */
.an-summary { font-size: 0.78rem; color: var(--muted); margin-bottom: 10px; font-weight: 600; }
.an-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.an-card { background: rgba(255,255,255,0.04); border-radius: 8px; padding: 10px 12px; border-left: 3px solid var(--warning); }
.an-header { display: flex; gap: 6px; align-items: center; margin-bottom: 5px; flex-wrap: wrap; }
.an-owner { font-size: 0.75rem; font-weight: 800; color: var(--text); }
.an-count { font-size: 0.7rem; color: var(--muted); }
.an-urg { font-size: 0.65rem; font-weight: 700; padding: 1px 6px; border-radius: 4px; background: rgba(255,71,87,0.2); color: #ff4757; margin-left: auto; }
.an-urg.week { background: rgba(255,165,0,0.2); color: var(--warning); }
.an-urg.flex { background: rgba(0,180,216,0.15); color: var(--info); }
.an-label { font-size: 0.78rem; font-weight: 700; color: var(--warning); margin-bottom: 4px; }
.an-posts { display: flex; flex-direction: column; gap: 2px; }
.an-post { font-size: 0.68rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* OWNER WORKLOAD */
.ow-header-row { display: grid; grid-template-columns: 140px 1fr 1fr; gap: 10px; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.ow-col-owner, .ow-col-items, .ow-col-top { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); font-weight: 700; }
.ow-row { display: grid; grid-template-columns: 140px 1fr 1fr; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.ow-owner { display: flex; flex-direction: column; gap: 2px; }
.ow-name { font-size: 0.82rem; font-weight: 800; color: var(--text); }
.ow-total { font-size: 0.7rem; color: var(--muted); }
.ow-bars { display: flex; gap: 5px; flex-wrap: wrap; }
.ow-bar { font-size: 0.7rem; padding: 2px 7px; border-radius: 5px; color: var(--muted); background: rgba(255,255,255,0.05); }
.ow-bar--today.active { background: rgba(255,71,87,0.2); color: #ff4757; font-weight: 700; }
.ow-bar--week { color: var(--muted); }
.ow-top-item { font-size: 0.75rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ow-note { font-size: 0.72rem; color: var(--muted); margin-top: 8px; font-style: italic; }

/* RETARGET THIS WEEK */
.rt-summary { font-size: 0.78rem; color: var(--muted); margin-bottom: 10px; font-weight: 600; }
.rt-summary b { color: #ff4757; }
.rt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.rt-card { background: rgba(255,255,255,0.04); border-radius: 10px; padding: 11px 13px; border-left: 3px solid #ff6b35; }
.rt-header { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.rt-icon { font-size: 0.9rem; }
.rt-action { font-size: 0.78rem; font-weight: 800; color: var(--text); flex: 1; }
.rt-owner { font-size: 0.7rem; color: var(--muted); font-weight: 600; }
.rt-urg { font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; }
.rt-planned { font-size: 0.65rem; color: var(--success); background: rgba(0,210,106,0.1); padding: 2px 6px; border-radius: 4px; }
.rt-hook { font-size: 0.82rem; font-weight: 700; color: var(--text); margin-bottom: 3px; line-height: 1.3; }
.rt-why { font-size: 0.72rem; color: var(--muted); font-style: italic; margin-bottom: 4px; }
.rt-cta { font-size: 0.7rem; color: var(--success); }

/* DO THIS FIRST */
.dtf-summary { font-size: 0.78rem; color: var(--muted); margin-bottom: 10px; font-weight: 600; }
.dtf-summary b { color: #ffa502; }
.dtf-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; }
.dtf-card { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 14px 14px 12px; border-left: 4px solid #ffa502; display: flex; gap: 10px; align-items: flex-start; }
.dtf-emoji { font-size: 1.4rem; flex-shrink: 0; }
.dtf-body { flex: 1; min-width: 0; }
.dtf-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); font-weight: 700; margin-bottom: 4px; }
.dtf-title { font-size: 0.82rem; font-weight: 800; color: var(--text); line-height: 1.3; margin-bottom: 3px; }
.dtf-meta { font-size: 0.7rem; color: var(--success); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dtf-score { font-size: 1.3rem; font-weight: 900; flex-shrink: 0; line-height: 1; }
.ig-yt-badge { background: linear-gradient(90deg, rgba(225,48,108,0.25), rgba(255,0,80,0.25)); color: #e1306c; font-size: 0.72rem; letter-spacing: 0.5px; }
.ww-grid { display: flex; flex-direction: column; gap: 10px; }
.ww-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 14px 16px; }
.ww-card--pt { border-left: 4px solid var(--success); }
.ww-card--tt { border-left: 4px solid #ff6b35; }
.ww-card--po { border-left: 4px solid var(--purple); }
.ww-card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.ww-badge { display: inline-block; font-size: 0.68rem; padding: 3px 9px; border-radius: 6px; font-weight: 700; letter-spacing: 0.3px; }
.ww-badge--pt { background: rgba(0,210,106,0.25); color: #00d26a; border: 1px solid rgba(0,210,106,0.4); }
.ww-badge--tt { background: rgba(255,107,53,0.25); color: #ff6b35; border: 1px solid rgba(255,107,53,0.4); }
.ww-badge--po { background: rgba(155,89,182,0.2); color: #b07cc6; border: 1px solid rgba(155,89,182,0.35); }
.ww-action { font-size: 0.72rem; padding: 3px 8px; border-radius: 5px; font-weight: 600; }
.ww-action--cta   { background: rgba(0,210,106,0.15); color: var(--success); }
.ww-action--reel  { background: rgba(225,48,108,0.15); color: #e1306c; }
.ww-action--lessons { background: rgba(0,180,216,0.15); color: var(--info); }
.ww-action--product { background: rgba(255,165,0,0.15); color: var(--warning); }
.ww-action--boost { background: rgba(255,107,53,0.15); color: #ff6b35; }
.ww-hook { font-weight: 600; font-size: 0.92rem; margin-bottom: 8px; line-height: 1.45; color: var(--text); }
.ww-scores { display: flex; gap: 10px; margin-bottom: 6px; }
.ww-score { font-size: 0.76rem; font-weight: 800; padding: 2px 8px; border-radius: 5px; letter-spacing: 0.2px; }
.ww-score.ig { background: rgba(225,48,108,0.2); color: #e1306c; }
.ww-score.yt { background: rgba(255,0,80,0.18); color: #ff4070; }
.ww-score.cross { background: rgba(155,89,182,0.2); color: #c07fd4; cursor: help; border-bottom: 1px dotted rgba(155,89,182,0.5); }
.ww-topics { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 4px; }
.ww-topic { background: rgba(255,255,255,0.08); color: var(--muted); font-size: 0.7rem; padding: 2px 7px; border-radius: 20px; }
.ww-evidence { font-size: 0.73rem; color: var(--muted); margin-top: 4px; }
.ww-evidence-more { color: var(--info); font-style: italic; }
.ww-ct-badge { display: inline-block; font-size: 0.62rem; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; }
.ww-ct-badge--cta    { background: rgba(0,210,106,0.15); color: #00d26a; }
.ww-ct-badge--promo { background: rgba(255,107,53,0.15); color: #ff6b35; }
.ww-ct-badge--product { background: rgba(255,165,0,0.15); color: var(--warning); }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⛳ Swing Shack — Marketing Intelligence</h1>
    <p>Auto-updated daily · Used items filtered · Ideas improve over time</p>
  </div>

  ${summaryBar}
  ${thisWeekStrip}
  ${execSummarySection}
  ${doFirstSection}
  ${igSection}
  ${hookSection}
  ${watchedSection}
  ${followUpSection}
  ${assetSection}
  ${ideaSection}
  ${workloadSection}
  ${retargetSection}
  ${abSection}
  ${newsSection}
  ${redditSection}
  ${seoSection}
  ${ga4Section}
  ${usedSection}
</div>
</body>
</html>`;

// Write outputs
fs.writeFileSync(OUTPUT_HTML, html);

// Build summary
const summary = {
  updated: now,
  sources,
  stale_count: stale.length,
  top_recommendation: topRecommendation,
  total_posts: (ig.posts || []).length,
  total_ideas: (ideas.ideas || ideas.post_today || []).length,
  hooks_tracked: (hooks.hooks || hooks.proven_hooks || []).length,
};
fs.writeFileSync(SUMMARY_OUT, JSON.stringify(summary, null, 2));

// Update build meta
const meta = {
  last_run: now,
  stale_sources: stale.map(s => s.name),
  errors: [],
  build_version: '2.0',
  sources_updated: sources.reduce((acc, s) => { acc[s.name] = s.updated; return acc; }, {}),
};
fs.writeFileSync(META_OUT, JSON.stringify(meta, null, 2));

console.log('✅ Dashboard compiled at', now);
console.log('   Stale sources:', stale.length > 0 ? stale.map(s => s.name).join(', ') : 'none');
console.log('   Posts:', summary.total_posts, '| Ideas:', summary.total_ideas, '| Hooks:', summary.hooks_tracked);