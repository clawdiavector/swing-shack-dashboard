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
const recScores  = readJson('recommendation-scores.json') || null;
const recOutcome  = readJson('recommendation-outcomes.json')  || null;
const expQueue    = readJson('experiment-queue.json')           || null;
const scaleRecs   = readJson('scaling-recommendations.json')   || null;
const killList    = readJson('kill-list.json')                 || null;
const anomalyAlert = readJson('anomaly-alerts.json')           || null;
const taskCards   = readJson('daily-task-cards.json')         || null;
const apprQueue   = readJson('approval-queue.json')          || null;
const deadlineRisk = readJson('deadline-risk.json')          || null;
const blockers    = readJson('blockers.json')                 || null;
const capShift   = readJson('capacity-shift.json')          || null;
const nudgeQ    = readJson('nudge-queue.json')            || null;
const fallbQ    = readJson('fallback-queue.json')           || null;
const nextDayQ  = readJson('next-day-queue.json')          || null;
const autoMsg   = readJson('auto-messages.json')           || null;
const supprRul  = readJson('suppression-rules.json')        || null;
const delAudit = readJson('delivery-audit.json')           || null;

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

// WHAT ACTUALLY WORKED
var wawsContent = '<p class="empty">No outcome data yet. Measurement loop is building history.</p>';
if (recOutcome && recOutcome.summary && recOutcome.summary.total_recommended > 0) {
  var wows = recOutcome.summary;
  var wrList = (recOutcome.type_win_rates || []).slice(0, 4).map(function(wr) {
    var wrColor = wr.win_rate >= 60 ? '#2ed573' : wr.win_rate >= 40 ? '#ffa502' : '#ff4757';
    return '<div class="waws-wr"><span class="waws-wr-name">' + (wr.type || '').replace(/_/g, ' ') + '</span><span class="waws-wr-rate" style="color:' + wrColor + '">' + wr.win_rate + '%</span><span class="waws-wr-count">(' + wr.won + 'W/' + wr.total + ')</span></div>';
  }).join('');

  var bestRec = recOutcome.best_recommendation;
  var worstRec = recOutcome.worst_recommendation;
  var ignoredItems = (recOutcome.ignored || []).slice(0, 3);
  var underItems = (recOutcome.underperformed || []).slice(0, 2);

  var bestRow = bestRec ? '<div class="waws-card wawc-won"><div class="waws-card-icon">\ud83c\udfc6</div><div class="waws-card-body"><div class="waws-card-type">Best performer</div><div class="waws-card-hook">' + truncate(bestRec.hook || '—', 65) + '</div><div class="waws-card-meta">+' + bestRec.delta + ' eng vs baseline | ' + bestRec.eng_rate + '% eng | ' + bestRec.reach + ' reach</div></div></div>' : '';

  var worstRow = worstRec && worstRec !== bestRec ? '<div class="waws-card wawc-lost"><div class="waws-card-icon">\u26d4\ufe0f</div><div class="waws-card-body"><div class="waws-card-type">Underperformed</div><div class="waws-card-hook">' + truncate(worstRec.hook || '—', 65) + '</div><div class="waws-card-meta">' + worstRec.delta + ' eng vs baseline | ' + worstRec.type + '</div></div></div>' : '';

  var ignoreList = ignoredItems.length > 0 ? '<div class="waws-sub"><div class="waws-sub-title">Ignored (no matching post found)</div>' + ignoredItems.map(function(r) { return '<div class="waws-ignored-row">\u21b3 ' + truncate(r.hook || r.type || '—', 55) + '</div>'; }).join('') + '</div>' : '';

  var underList = underItems.length > 0 ? '<div class="waws-sub"><div class="waws-sub-title">Underperformed</div>' + underItems.map(function(r) { return '<div class="waws-under-row">\u2193 ' + truncate(r.hook || r.type || '—', 55) + ' (delta: ' + r.delta + ')</div>'; }).join('') + '</div>' : '';

  wawsContent = '<div class="waws-stats">' +
    '<div class="waws-stat"><div class="waws-stat-val" style="color:#2ed573">' + wows.exec_rate + '%</div><div class="waws-stat-lbl">Exec rate</div></div>' +
    '<div class="waws-stat"><div class="waws-stat-val" style="color:' + (wows.overall_win_rate >= 50 ? '#2ed573' : '#ffa502') + '">' + wows.overall_win_rate + '%</div><div class="waws-stat-lbl">Win rate</div></div>' +
    '<div class="waws-stat"><div class="waws-stat-val">' + wows.total_recommended + '</div><div class="waws-stat-lbl">Recs tracked</div></div>' +
    '<div class="waws-stat"><div class="waws-stat-val">' + wows.executed + '</div><div class="waws-stat-lbl">Executed</div></div>' +
    '</div>' +
    '<div class="waws-wr-section"><div class="waws-wr-title">Win rate by type</div><div class="waws-wr-grid">' + wrList + '</div></div>' +
    bestRow + worstRow +
    ignoreList + underList;
}
var wawsSection = buildSection('\ud83d\udcca WHAT ACTUALLY WORKED', freshnessBadge(recOutcome && recOutcome.updated), wawsContent);

// TEST / SCALE / KILL
var tskContent = '<p class="empty">No experiment data yet.</p>';
if ((expQueue || scaleRecs || killList || anomalyAlert) && (
  (expQueue && expQueue.experiments && expQueue.experiments.length > 0) ||
  (scaleRecs && scaleRecs.recommendations && scaleRecs.recommendations.length > 0) ||
  (killList && killList.items && killList.items.length > 0) ||
  (anomalyAlert && anomalyAlert.alerts && anomalyAlert.alerts.length > 0)
)) {
  var tskToday = (anomalyAlert && anomalyAlert.alerts || []).filter(function(a){ return a.severity === 'high' && a.urgency === 'today'; });
  var testItems = (expQueue && expQueue.experiments || []).slice(0, 3);
  var scaleItems = (scaleRecs && scaleRecs.recommendations || []).slice(0, 3);
  var killItems = (killList && killList.items || []).slice(0, 3);

  function tskCard(item, color, icon, type) {
    if (!item) return '';
    var title = item.hook || item.action || item.description || item.alert || item.cta_type || item.type || '—';
    var meta = item.success_metric || item.fix || item.likely_cause || item.reason || '';
    var owner = item.owner ? '<span class="tsk-owner">\ud83d\udc64 ' + item.owner + '</span>' : '';
    var badge = item.urgency ? '<span class="tsk-urg tsk-urg-' + item.urgency + '">' + item.urgency.toUpperCase() + '</span>' : '';
    return '<div class="tsk-card" style="border-left-color:' + color + '">' + icon + '<div class="tsk-body"><div class="tsk-title">' + title.substring(0,60) + '</div><div class="tsk-meta">' + meta.substring(0,65) + '</div>' + owner + badge + '</div></div>';
  }

  var testCol = testItems.length > 0
    ? '<div class="tsk-col"><div class="tsk-col-title tsk-test-title">\ud83d\udd2c TEST NEXT</div>' + testItems.map(function(t){ return tskCard(t, '#ffa502', '<div class="tsk-icon">\ud83d\udd2c</div>', 'test'); }).join('') + '</div>'
    : '<div class="tsk-col"><div class="tsk-col-title tsk-test-title">\ud83d\udd2c TEST NEXT</div><div class="tsk-empty">No experiments queued</div></div>';

  var scaleCol = scaleItems.length > 0
    ? '<div class="tsk-col"><div class="tsk-col-title tsk-scale-title">\u2b06\ufe0f SCALE NOW</div>' + scaleItems.map(function(s){ return tskCard(s, '#2ed573', '<div class="tsk-icon">\u2b06\ufe0f</div>', 'scale'); }).join('') + '</div>'
    : '<div class="tsk-col"><div class="tsk-col-title tsk-scale-title">\u2b06\ufe0f SCALE NOW</div><div class="tsk-empty">No scale candidates yet</div></div>';

  var killCol = killItems.length > 0
    ? '<div class="tsk-col"><div class="tsk-col-title tsk-kill-title">\ud83d\udd73\ufe0f KILL / PAUSE</div>' + killItems.map(function(k){ return tskCard(k, '#ff4757', '<div class="tsk-icon">\ud83d\udd73\ufe0f</div>', 'kill'); }).join('') + '</div>'
    : '<div class="tsk-col"><div class="tsk-col-title tsk-kill-title">\ud83d\udd73\ufe0f KILL / PAUSE</div><div class="tsk-empty">No kill candidates</div></div>';

  var alertBar = tskToday.length > 0
    ? '<div class="tsk-alert-bar">\u26a0\ufe0f ' + tskToday.length + ' high-urgency anomaly alert(s) need action today</div>'
    : '';

  tskContent = alertBar + '<div class="tsk-grid">' + testCol + scaleCol + killCol + '</div>';
}
var tskSection = buildSection('\ud83d\udd2c TEST / SCALE / KILL', freshnessBadge(expQueue && expQueue.updated), tskContent);

// RUN THE WEEK
var rtwContent = '<p class="empty">No operational data yet.</p>';
if (taskCards || apprQueue || deadlineRisk || blockers || capShift) {
  var rtwToday = (taskCards && taskCards.top_tasks || []).slice(0, 5);
  var rtwAppr = (apprQueue && apprQueue.pending_items || []).slice(0, 4);
  var rtwRisks = (deadlineRisk && deadlineRisk.risks || []).slice(0, 4);
  var rtwBlk = (blockers && blockers.blockers || []).slice(0, 4);
  var rtwShift = (capShift && capShift.shifts || []).slice(0, 3);

  function rtwCard(title, items, color, icon) {
    if (!items || items.length === 0) return '<div class="rtw-col"><div class="rtw-col-head" style="border-top-color:' + color + '">' + icon + ' ' + title + '</div><div class="rtw-empty">None</div></div>';
    var rows = items.slice(0, 4).map(function(i) {
      var itemTitle = (i.title || i.blocker || i.what_will_slip || i.task_title || i.action || '—').substring(0, 55);
      var meta = i.owner ? '<span class="rtw-owner">\ud83d\udc64 ' + i.owner + '</span>' : '';
      var badge = i.severity ? '<span class="rtw-sev rtw-sev-' + i.severity + '">' + i.severity.toUpperCase() + '</span>' : '';
      var fix = i.fix ? '<div class="rtw-fix">\u2192 ' + i.fix.substring(0, 55) + '</div>' : '';
      return '<div class="rtw-row"><div class="rtw-row-title">' + itemTitle + '</div>' + meta + badge + fix + '</div>';
    }).join('');
    return '<div class="rtw-col"><div class="rtw-col-head" style="border-top-color:' + color + '">' + icon + ' ' + title + '</div><div class="rtw-rows">' + rows + '</div></div>';
  }

  var todayTasksBlock = rtwCard('TODAY\'S TASKS', rtwToday, '#ff4757', '\ud83d\udcc5');
  var apprBlock = rtwCard('WAITING APPROVAL', rtwAppr, '#ffa502', '\u23f3');
  var riskBlock = rtwCard('AT RISK THIS WEEK', rtwRisks, '#ff6b35', '\u26a0\ufe0f');
  var blkBlock = rtwCard('BLOCKING EXECUTION', rtwBlk, '#ff4757', '\ud83d\udd28');
  var shiftBlock = rtwCard('REBALANCE WEEK', rtwShift, '#00b4d8', '\u21c4');

  var rtwSummary = '<div class="rtw-summary">' +
    '<span class="rtw-sum-item"><b>' + ((taskCards && taskCards.summary && taskCards.summary.total) || 0) + '</b> tasks</span>' +
    '<span class="rtw-sum-item"><b>' + ((taskCards && taskCards.summary && taskCards.summary.blocked_count) || 0) + '</b> blocked</span>' +
    '<span class="rtw-sum-item"><b>' + ((deadlineRisk && deadlineRisk.summary && deadlineRisk.summary.high_urgency) || 0) + '</b> risks high</span>' +
    '<span class="rtw-sum-item"><b>' + ((blockers && blockers.summary && blockers.summary.total_blockers) || 0) + '</b> blockers</span>' +
    '<span class="rtw-sum-item"><b>' + ((apprQueue && apprQueue.summary && apprQueue.summary.pending) || 0) + '</b> need approval</span>' +
    '</div>';

  rtwContent = rtwSummary + '<div class="rtw-grid">' + todayTasksBlock + apprBlock + riskBlock + blkBlock + shiftBlock + '</div>';
}
var rtwSection = buildSection('\ud83d\udd27 RUN THE WEEK', freshnessBadge(taskCards && taskCards.updated), rtwContent);

// AUTOMATE THE WEEK
var autContent = '<p class="empty">No automations ready.</p>';
if (nudgeQ || fallbQ || nextDayQ || autoMsg) {
  var nudgeReady = (nudgeQ && nudgeQ.nudges || []).filter(function(n){ return n.status === 'ready'; });
  var nudgeHigh = nudgeReady.filter(function(n){ return n.severity === 'high'; });
  var fallbacks = (fallbQ && fallbQ.fallbacks || []).slice(0, 4);
  var nextDay = nextDayQ;
  var autoMsgs = (autoMsg && autoMsg.messages || []).filter(function(m){ return m.status === 'draft'; }).slice(0, 3);
  var suppr = (supprRul && supprRul.suppressed_nudges || []).slice(0, 3);

  // NUDGE NOW column
  var nudgeCol = '';
  if (nudgeReady.length > 0) {
    var nudgeRows = nudgeReady.slice(0, 4).map(function(n) {
      var sev = n.severity === 'high' ? '#ff4757' : n.severity === 'medium' ? '#ffa502' : 'var(--muted)';
      return '<div class="aut-row"><div class="aut-row-title">' + (n.reason || n.type || '').substring(0, 55) + '</div><div class="aut-row-meta"><span class="aut-owner">\ud83d\udc64 ' + (n.owner || 'Unassigned') + '</span><span class="aut-sev" style="color:' + sev + '">' + (n.severity || '').toUpperCase() + '</span><span class="aut-win">' + (n.send_window || '') + '</span></div></div>';
    });
    nudgeCol = '<div class="aut-col"><div class="aut-col-head aut-head-nudge">\ud83d\udd27 NUDGE NOW <span class="aut-count">' + nudgeReady.length + '</span></div><div class="aut-rows">' + nudgeRows.join('') + '</div></div>';
  } else {
    nudgeCol = '<div class="aut-col"><div class="aut-col-head aut-head-nudge">\ud83d\udd27 NUDGE NOW</div><div class="aut-empty">All clear</div></div>';
  }

  // FALLBACK column
  var fallCol = '';
  if (fallbacks.length > 0) {
    var fallRows = fallbacks.map(function(f) {
      return '<div class="aut-row"><div class="aut-row-title">' + (f.fallback_hook || f.action || 'Fallback').substring(0, 55) + '</div><div class="aut-row-meta"><span class="aut-format">' + (f.fallback_format || f.swap_to_format || 'text') + '</span><span class="aut-owner">\ud83d\udc64 ' + (f.owner || '—') + '</span></div></div>';
    });
    fallCol = '<div class="aut-col"><div class="aut-col-head aut-head-fall">\u21a9\ufe0f USE THIS FALLBACK <span class="aut-count">' + fallbacks.length + '</span></div><div class="aut-rows">' + fallRows.join('') + '</div></div>';
  } else {
    fallCol = '<div class="aut-col"><div class="aut-col-head aut-head-fall">\u21a9\ufe0f USE THIS FALLBACK</div><div class="aut-empty">No fallbacks needed</div></div>';
  }

  // TOMORROW column
  var tomCol = '';
  if (nextDay && nextDay.post_queue && nextDay.post_queue.length > 0) {
    var tomRows = nextDay.post_queue.map(function(p) {
      var appr = p.approval_status === 'approved' ? '\u2705' : p.approval_status === 'needs_info' ? '\u23f3' : '\u2753';
      return '<div class="aut-row"><div class="aut-row-title">' + (p.hook || p.title || '').substring(0, 55) + '</div><div class="aut-row-meta"><span class="aut-owner">\ud83d\udc64 ' + (p.owner || '—') + '</span>' + appr + ' ' + (p.format || 'static') + '</div></div>';
    });
    tomCol = '<div class="aut-col"><div class="aut-col-head aut-head-tom">\ud83d\udcc5 READY FOR TOMORROW <span class="aut-count">' + nextDay.day_name + '</span></div><div class="aut-rows">' + tomRows.join('') + '</div></div>';
  } else {
    tomCol = '<div class="aut-col"><div class="aut-col-head aut-head-tom">\ud83d\udcc5 READY FOR TOMORROW</div><div class="aut-empty">Nothing scheduled</div></div>';
  }

  // SUPPRESSED column
  var supprCol = '';
  if (suppr.length > 0) {
    var supprRows = suppr.map(function(s) {
      return '<div class="aut-row aut-row-suppr"><div class="aut-row-title">' + (s.reason || s.type || '').substring(0, 55) + '</div><div class="aut-row-meta"><span class="aut-owner">\ud83d\udc64 ' + (s.owner || '—') + '</span><span class="aut-suppr-reason">' + (s.suppression_reason || 'suppressed') + '</span></div></div>';
    });
    supprCol = '<div class="aut-col"><div class="aut-col-head aut-head-suppr">\ud83d\udd0d SUPPRESSED <span class="aut-count">' + suppr.length + '</span></div><div class="aut-rows">' + supprRows.join('') + '</div></div>';
  } else {
    supprCol = '<div class="aut-col"><div class="aut-col-head aut-head-suppr">\ud83d\udd0d SUPPRESSED</div><div class="aut-empty">No spam blocked</div></div>';
  }

  autContent = '<div class="aut-summary">' + (nudgeHigh.length > 0 ? '<span class="aut-alert">\u26a0\ufe0f ' + nudgeHigh.length + ' high-severity nudge(s) ready to send</span>' : '<span>All automations quiet</span>') + '</div><div class="aut-grid">' + nudgeCol + fallCol + tomCol + supprCol + '</div>';
}
var autSection = buildSection('\ud83e\uddd7 AUTOMATE THE WEEK', freshnessBadge(nudgeQ && nudgeQ.updated), autContent);

// SENT TODAY
var sentContent = '<p class="empty">No nudges sent yet.</p>';
if (delAudit) {
  var s = delAudit.summary || {};
  var sentRows = (delAudit.sent || []).slice(0, 5).map(function(d) {
    return '<div class="sent-row"><div class="sent-type">' + (d.type || '').replace(/_/g, ' ') + '</div><div class="sent-owner">\ud83d\udc64 ' + (d.owner || '—') + '</div><div class="sent-status sent-ok">SENT</div></div>';
  });
  var supprRows = (delAudit.suppressed || []).slice(0, 3).map(function(d) {
    return '<div class="sent-row sent-row-suppr"><div class="sent-type">' + (d.type || '').replace(/_/g, ' ') + '</div><div class="sent-owner">\ud83d\udc64 ' + (d.owner || '—') + '</div><div class="sent-status sent-suppr">SUPPR</div><div class="sent-reason">' + (d.suppression_reason || '') + '</div></div>';
  });
  var failRows = (delAudit.failed || []).map(function(d) {
    return '<div class="sent-row sent-row-fail"><div class="sent-type">' + (d.type || '') + '</div><div class="sent-owner">\ud83d\udc64 ' + (d.owner || '—') + '</div><div class="sent-status sent-fail">FAILED</div><div class="sent-reason">' + (d.error || '') + '</div></div>';
  });

  var sentSummary = '<div class="sent-summary">' +
    '<span class="sent-count sent-ok-c">' + (s.sent || 0) + ' sent</span>' +
    '<span class="sent-count sent-dry-c">' + (s.dry_run || 0) + ' dry-run</span>' +
    '<span class="sent-count sent-suppr-c">' + (s.suppressed || 0) + ' suppressed</span>' +
    '<span class="sent-count sent-fail-c">' + (s.failed || 0) + ' failed</span>' +
    '</div>';

  var sentBlocks = '';
  if (sentRows.length > 0) sentBlocks += '<div class="sent-block-head">SENT</div>' + sentRows.join('');
  if (supprRows.length > 0) sentBlocks += '<div class="sent-block-head">SUPPRESSED</div>' + supprRows.join('');
  if (failRows.length > 0) sentBlocks += '<div class="sent-block-head">FAILED</div>' + failRows.join('');
  if (sentBlocks === '') sentBlocks = '<div class="aut-empty">All quiet — no sends yet today</div>';

  sentContent = sentSummary + '<div class="sent-list">' + sentBlocks + '</div>';
}
var sentSection = buildSection('\ud83d\udce4 SENT TODAY', freshnessBadge(delAudit && delAudit.updated), sentContent);

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

/* WHAT ACTUALLY WORKED */
.waws-stats { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 14px; }
.waws-stat { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 10px; text-align: center; }
.waws-stat-val { font-size: 1.5rem; font-weight: 900; color: var(--text); }
.waws-stat-lbl { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); margin-top: 2px; }
.waws-wr-section { margin-bottom: 12px; }
.waws-wr-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); font-weight: 700; margin-bottom: 6px; }
.waws-wr-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.waws-wr { display: flex; gap: 5px; align-items: center; background: rgba(255,255,255,0.05); border-radius: 6px; padding: 4px 8px; font-size: 0.75rem; }
.waws-wr-name { color: var(--muted); text-transform: capitalize; }
.waws-wr-rate { font-weight: 800; }
.waws-wr-count { color: var(--muted); font-size: 0.7rem; }
.waws-card { display: flex; gap: 10px; padding: 10px 12px; border-radius: 10px; margin-bottom: 8px; }
.wawc-won { background: rgba(46,213,115,0.1); border-left: 3px solid #2ed573; }
.wawc-lost { background: rgba(255,71,87,0.08); border-left: 3px solid #ff4757; }
.waws-card-icon { font-size: 1.3rem; flex-shrink: 0; }
.waws-card-body { flex: 1; }
.waws-card-type { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); font-weight: 700; margin-bottom: 3px; }
.waws-card-hook { font-size: 0.85rem; font-weight: 800; color: var(--text); margin-bottom: 2px; line-height: 1.3; }
.waws-card-meta { font-size: 0.72rem; color: var(--muted); }
.waws-sub { margin-top: 10px; }
.waws-sub-title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); font-weight: 700; margin-bottom: 4px; }
.waws-ignored-row { font-size: 0.78rem; color: var(--muted); padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.waws-under-row { font-size: 0.78rem; color: #ff4757; padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }

/* TEST / SCALE / KILL */
.tsk-alert-bar { background: rgba(255,71,87,0.15); border: 1px solid rgba(255,71,87,0.3); border-radius: 8px; padding: 8px 12px; font-size: 0.8rem; font-weight: 700; color: #ff4757; margin-bottom: 12px; }
.tsk-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.tsk-col { display: flex; flex-direction: column; gap: 8px; }
.tsk-col-title { font-size: 0.7rem; font-weight: 900; text-transform: uppercase; letter-spacing: 0.8px; padding: 6px 10px; border-radius: 6px; margin-bottom: 2px; }
.tsk-test-title { background: rgba(255,165,0,0.15); color: #ffa502; }
.tsk-scale-title { background: rgba(46,213,115,0.12); color: #2ed573; }
.tsk-kill-title { background: rgba(255,71,87,0.1); color: #ff4757; }
.tsk-empty { font-size: 0.75rem; color: var(--muted); padding: 8px; text-align: center; font-style: italic; }
.tsk-card { background: rgba(255,255,255,0.04); border-radius: 8px; padding: 10px 12px; border-left: 3px solid #888; display: flex; gap: 8px; align-items: flex-start; }
.tsk-icon { font-size: 1rem; flex-shrink: 0; margin-top: 1px; }
.tsk-body { flex: 1; min-width: 0; }
.tsk-title { font-size: 0.8rem; font-weight: 700; color: var(--text); line-height: 1.3; margin-bottom: 3px; }
.tsk-meta { font-size: 0.7rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; }
.tsk-owner { font-size: 0.68rem; color: var(--muted); font-weight: 600; display: inline-block; margin-right: 4px; }
.tsk-urg { font-size: 0.62rem; font-weight: 800; padding: 1px 5px; border-radius: 3px; display: inline-block; }
.tsk-urg-today { background: rgba(255,71,87,0.2); color: #ff4757; }
.tsk-urg-this_week { background: rgba(255,165,0,0.2); color: #ffa502; }
.tsk-urg-flexible { background: rgba(0,180,216,0.15); color: var(--info); }

/* RUN THE WEEK */
.rtw-summary { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 0.78rem; color: var(--muted); }
.rtw-summary b { color: var(--text); font-weight: 800; }
.rtw-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 10px; }
.rtw-col { background: rgba(255,255,255,0.03); border-radius: 10px; border-top: 3px solid #888; padding: 10px; }
.rtw-col-head { font-size: 0.68rem; font-weight: 900; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); margin-bottom: 8px; padding-top: 6px; }
.rtw-empty { font-size: 0.75rem; color: var(--muted); font-style: italic; text-align: center; padding: 8px; }
.rtw-rows { display: flex; flex-direction: column; gap: 6px; }
.rtw-row { padding: 7px 9px; background: rgba(255,255,255,0.04); border-radius: 7px; }
.rtw-row-title { font-size: 0.78rem; font-weight: 700; color: var(--text); line-height: 1.3; margin-bottom: 3px; }
.rtw-owner { font-size: 0.68rem; color: var(--muted); font-weight: 600; display: inline; margin-right: 4px; }
.rtw-sev { font-size: 0.6rem; font-weight: 800; padding: 1px 5px; border-radius: 3px; display: inline-block; }
.rtw-sev-high { background: rgba(255,71,87,0.2); color: #ff4757; }
.rtw-sev-medium { background: rgba(255,165,0,0.2); color: #ffa502; }
.rtw-sev-low { background: rgba(0,180,216,0.15); color: var(--info); }
/* SENT TODAY */
.sent-summary { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 0.78rem; }
.sent-count { font-weight: 800; padding: 2px 8px; border-radius: 5px; }
.sent-ok-c { background: rgba(0,200,83,0.15); color: #00c853; }
.sent-dry-c { background: rgba(100,100,255,0.15); color: #6464ff; }
.sent-suppr-c { background: rgba(255,165,0,0.15); color: #ffa502; }
.sent-fail-c { background: rgba(255,71,87,0.15); color: #ff4757; }
.sent-list { display: flex; flex-direction: column; gap: 6px; }
.sent-row { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; align-items: center; padding: 8px 10px; background: rgba(255,255,255,0.04); border-radius: 7px; font-size: 0.75rem; }
.sent-row-suppr { background: rgba(255,165,0,0.06); }
.sent-row-fail { background: rgba(255,71,87,0.06); }
.sent-type { text-transform: capitalize; color: var(--text); font-weight: 600; }
.sent-owner { color: var(--muted); }
.sent-status { font-size: 0.65rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; }
.sent-ok { background: rgba(0,200,83,0.2); color: #00c853; }
.sent-suppr { background: rgba(255,165,0,0.2); color: #ffa502; }
.sent-fail { background: rgba(255,71,87,0.2); color: #ff4757; }
.sent-reason { font-size: 0.68rem; color: var(--muted); }
.sent-block-head { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); padding: 4px 0 2px; border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 4px; }
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
  ${wawsSection}
  ${tskSection}
  ${rtwSection}
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