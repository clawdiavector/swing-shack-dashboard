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
const ideaSection = buildSection('💡 Content Ideas', freshnessBadge(ideas.updated), ideaContent);

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
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⛳ Swing Shack — Marketing Intelligence</h1>
    <p>Auto-updated daily · Used items filtered · Ideas improve over time</p>
  </div>

  ${summaryBar}
  ${igSection}
  ${hookSection}
  ${ideaSection}
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