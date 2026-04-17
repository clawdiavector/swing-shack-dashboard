#!/usr/bin/env node
/**
 * analyse_hooks.js
 * Reads IG analytics → generates hook bank with scores and formulas
 * Merges YouTube trend signals and Reddit pain points for cross-signal scoring
 *
 * Scoring model:
 * - IG proof: 60% (proven engagement)
 * - Reddit/search pain points: 20% (topic relevance)
 * - YouTube trend alignment: 20% (what's currently watched)
 *
 * Rules:
 * - YouTube is a multiplier, not the primary source of truth
 * - IG proof remains strongest signal
 * - Untested YouTube-aligned hooks must be labelled TEST NEXT, not PROVEN
 * - If YouTube and IG conflict, IG wins
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUT_FILE = path.join(DATA_DIR, 'hook-bank.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch(e) { return null; }
}

// ── IG performance score (0-10) ───────────────────────────────────────────────
function igScore(post) {
  const eng = parseFloat(post.engagementRate) || 0;
  const saves = parseFloat(post.saveRate) || 0;
  const shares = parseFloat(post.shareRate) || 0;
  const reach = parseInt(post.reach || 0);
  const raw = (eng * 2) + (saves * 3) + (shares * 5) + Math.min(reach / 100, 3);
  return Math.min(10, Math.max(0, raw));
}

// ── Formula classifier ─────────────────────────────────────────────────────────
function extractFormula(hookText) {
  if (!hookText) return 'unknown';
  if (hookText.match(/YOUR|THIS IS|THE\s+\w+:\s*\d/i)) return 'stat-demand';
  if (hookText.match(/\?|WHAT IF/i)) return 'question';
  if (hookText.match(/slice|hook|problem|fix|wrong|issue/i)) return 'pain-point';
  if (hookText.match(/pros average|trackman shows|benchmark/i)) return 'proof-led';
  if (hookText.match(/from r\d/i)) return 'price-led';
  if (hookText.match(/stop\s|don't\s/i)) return 'command';
  if (hookText.match(/secret|truth|mistake/i)) return 'reveal';
  return 'general';
}

// ── YouTube alignment scorer ────────────────────────────────────────────────────
function youtubeAlignmentScore(hookText, ytSignals) {
  if (!ytSignals || !ytSignals.signals) return { score: 0, matched_topics: [], matched_formats: [], evidence_titles: [] };

  const text = (hookText || '').toLowerCase();
  const { topic_clusters, format_patterns, recurring_phrases } = ytSignals.signals;

  // Topic match
  const topicKeywords = {
    driver: ['driver', 'drive', 'driving', 'tee', 'off the tee'],
    slice_fix: ['slice', 'hook', 'ball flight', 'aim', 'club path', 'straight'],
    senior: ['senior', 'older', '50+', 'aging'],
    beginner: ['beginner', 'new to', 'start', 'basics', 'first time', 'learn'],
    irons: ['iron', 'irons', 'fairway', 'approach shot'],
    short_game: ['chip', 'pitch', 'putt', 'putting', 'green', 'bunker'],
    simulator: ['simulator', 'indoor', 'launch monitor', 'trackman', 'rain'],
    lessons: ['lesson', 'pro', 'coach', 'professional', 'instruction', 'golf pro'],
    swing: ['swing', 'swinging', 'swing speed', 'club head'],
    fitness: ['fitness', 'flexibility', 'mobility', 'core', 'strength'],
    distance: ['distance', 'further', 'yards', 'meters', 'longer', 'gain'],
    consistency: ['consistent', 'consistently', 'repeat'],
  };

  const matchedTopics = [];
  let topicScore = 0;
  for (const [topic, keywords] of Object.entries(topicKeywords)) {
    if (keywords.some(kw => text.includes(kw))) {
      matchedTopics.push(topic);
      topicScore += 3;
    }
  }

  // Format match
  const formatLabels = format_patterns.map(f => f.label.toLowerCase());
  const matchedFormats = [];
  let formatScore = 0;
  const formatMap = {
    'how to...': ['how to'],
    '"best" superlative': ['best'],
    '"easy" simplicity': ['easy'],
    '"simple" promise': ['simple'],
    'question hook': ['?'],
    '"stop" command': ['stop'],
    'mistake framing': ['mistake'],
    'contrast hook': ['?'],
    '"honest" credibility': ['honest'],
    'experience claim': ['years'],
    'guarantee language': ['guarantee'],
  };
  for (const [label, triggers] of Object.entries(formatMap)) {
    if (formatLabels.includes(label) && triggers.some(t => text.includes(t))) {
      matchedFormats.push(label);
      formatScore += 2;
    }
  }

  // Phrase match (recurring YouTube phrases)
  let phraseScore = 0;
  const matchedPhrases = [];
  for (const { phrase } of (recurring_phrases || []).slice(0, 10)) {
    if (phrase.length > 4 && text.includes(phrase.slice(0, 15))) {
      matchedPhrases.push(phrase);
      phraseScore += 1;
    }
  }

  const raw = topicScore + formatScore + phraseScore;
  const score = Math.min(10, raw);

  return {
    score,
    matched_topics: matchedTopics,
    matched_formats: matchedFormats,
    phrase_matches: matchedPhrases,
    evidence_titles: [], // populated below with actual YouTube titles
  };
}

// ── Reddit pain-point relevance ─────────────────────────────────────────────────
function redditScore(hookText, reddit) {
  if (!reddit || !hookText) return 0;
  const trends = reddit.trends || reddit.hot_pain_points || [];
  if (!trends.length) return 0;

  const text = (hookText || '').toLowerCase();
  let hits = 0;
  for (const t of trends) {
    const ttext = ((t.title || '') + ' ' + (t.topic || '') + ' ' + (t.description || '')).toLowerCase();
    const words = ttext.split(/\s+/).filter(w => w.length > 3);
    const matchCount = words.filter(w => text.includes(w)).length;
    if (matchCount >= 2) hits++;
  }
  return Math.min(5, hits * 2);
}

// ── Cross-signal score ─────────────────────────────────────────────────────────
// Weights: IG 60% + Reddit 20% + YouTube 20%
// YouTube never outweighs IG proof
function crossSignalScore(ig, reddit, yt) {
  // If IG is proven (ig >= 4) and YouTube agrees — boost
  // If IG is proven but YouTube contradicts — leave IG score
  // If IG is untested but YouTube aligns — flag as TEST NEXT
  // If IG is weak but YouTube is strong — score stays low (IG wins)

  const igNorm = ig / 10;  // 0-1
  const ytNorm = yt / 10;  // 0-1
  const rdNorm = Math.min(reddit / 5, 1); // reddit score capped at 5, normalise to 0-1

  const raw = (igNorm * 0.6) + (rdNorm * 0.2) + (ytNorm * 0.2);
  return Math.min(10, Math.round(raw * 10 * 10) / 10);
}

// ── Bucket classifier ──────────────────────────────────────────────────────────
function classifyBucket(ig, ytScore, cross) {
  const provenIg = ig >= 4;
  const strongYt = ytScore >= 4;
  const testIg = ig >= 2 && ig < 4;

  if (provenIg && strongYt) return 'proven_and_trending';
  if (provenIg) return 'proven_only';
  if (testIg && strongYt) return 'trending_to_test';
  if (ig < 2 && ytScore >= 4) return 'trending_to_test';
  if (ig === 0 && ytScore > 0) return 'trending_to_test';
  if (provenIg && ytScore < 2) return 'proven_only';
  if (ig < 2 && ytScore < 2) return 'retire';
  return 'proven_only';
}

function run() {
  const ig = readJson('ig-analytics.json');
  const ab = readJson('ab-tests.json');
  const ytSignals = readJson('youtube-hook-signals.json');
  const reddit = readJson('reddit-trends.json');

  const posts = ig.posts || [];
  const ytVideos = (ytSignals ? ytSignals.videos_analyzed : 0) || 0;

  // ── Score each hook ──────────────────────────────────────────────────────
  const scored = posts.map(p => {
    const hookText = p.hook_text || p.captionPreview || '';
    const ig = igScore(p);
    const yt = youtubeAlignmentScore(hookText, ytSignals);
    const rd = redditScore(hookText, reddit);
    const cross = crossSignalScore(ig, rd, yt.score);
    const bucket = classifyBucket(ig, yt.score, cross);

    // Find matching YouTube titles as evidence
    const evidenceTitles = [];
    if (ytSignals && ytSignals.signals && yt.matched_topics.length > 0) {
      const ytTop = ytSignals.top_videos || [];
      for (const v of ytTop) {
        const vtext = ((v.title || '') + ' ' + (v.description || '')).toLowerCase();
        const hasTopic = yt.matched_topics.some(t => {
          const topicKw = {
            driver: ['driver', 'drive'], slice_fix: ['slice', 'hook'],
            senior: ['senior'], beginner: ['beginner', 'learn'],
            simulator: ['simulator', 'indoor'], lessons: ['lesson', 'pro', 'coach'],
          }[t] || [t];
          return topicKw.some(k => vtext.includes(k));
        });
        if (hasTopic && evidenceTitles.length < 2) {
          evidenceTitles.push(v.title);
        }
      }
    }

    return {
      hook_text: hookText,
      hook_id: p.hook_id || hookText.toLowerCase().replace(/[^a-z0-9]/g, '-').substring(0, 50),
      ig_proof_score: ig,
      youtube_alignment_score: yt.score,
      reddit_relevance_score: rd,
      cross_signal_score: cross,
      youtube_topic_match: yt.matched_topics,
      youtube_format_match: yt.matched_formats,
      youtube_evidence_titles: evidenceTitles,
      engagementRate: p.engagementRate || '0',
      saveRate: p.saveRate || '0',
      shareRate: p.shareRate || '0',
      reach: p.reach || 0,
      topic_cluster: p.topic_cluster || 'general',
      format_type: p.format_type || 'static',
      formula_type: extractFormula(hookText),
      signal_bucket: bucket,
      post_id: p.postId || p.id,
    };
  }).sort((a, b) => b.cross_signal_score - a.cross_signal_score);

  // ── Output buckets ───────────────────────────────────────────────────────
  const provenAndTrending = scored.filter(h => h.signal_bucket === 'proven_and_trending');
  const provenOnly = scored.filter(h => h.signal_bucket === 'proven_only');
  const trendingToTest = scored.filter(h => h.signal_bucket === 'trending_to_test');
  const retire = scored.filter(h => h.signal_bucket === 'retire');
  const weakHooks = scored.filter(h => h.ig_proof_score < 2 && h.youtube_alignment_score < 2);

  // ── Hook formulas ────────────────────────────────────────────────────────
  const formulaBuckets = {};
  scored.forEach(h => {
    const f = h.formula_type;
    if (!formulaBuckets[f]) formulaBuckets[f] = [];
    formulaBuckets[f].push(h);
  });

  // ── WATCHED + WORKED: hooks that are proven on IG AND aligned with YouTube ──
  const watchedAndWorked = provenAndTrending.slice(0, 5);

  const result = {
    updated: new Date().toISOString(),
    total_hooks: scored.length,
    cross_signal_sources: {
      ig_weight: '60%',
      youtube_weight: '20%',
      reddit_weight: '20%',
      youtube_videos_analyzed: ytVideos,
      reddit_trends_available: (reddit?.trends || reddit?.hot_pain_points || []).length,
    },
    output_buckets: {
      proven_and_trending: provenAndTrending.slice(0, 10),
      proven_only: provenOnly.slice(0, 10),
      trending_to_test: trendingToTest.slice(0, 10),
      retire: retire.slice(0, 5),
    },
    watched_and_worked: watchedAndWorked,
    hook_formulas: Object.entries(formulaBuckets).map(([formula, hooks]) => ({
      formula,
      count: hooks.length,
      best_example: hooks.sort((a, b) => b.cross_signal_score - a.cross_signal_score)[0]?.hook_text || '',
      avg_cross_score: (hooks.reduce((s, h) => s + h.cross_signal_score, 0) / hooks.length).toFixed(1),
    })),
    ab_winners: (ab?.tests || []).filter(t => t.winner).map(t => ({
      name: t.name,
      winner: t.winner,
      eng: t.engagement || t.engagementRate || '?',
      next_action: t.next_action || 'reuse formula',
    })),
    youtube_signals_summary: ytSignals ? {
      dominant_topics: ytSignals.summary?.dominant_topics || [],
      dominant_formats: ytSignals.summary?.dominant_formats || [],
      top_template: ytSignals.summary?.top_template || null,
    } : null,
  };

  fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2));

  console.log(`✅ Hook bank (with YouTube cross-signals)`);
  console.log(`   Total: ${scored.length} | P&T: ${provenAndTrending.length} | P: ${provenOnly.length} | T: ${trendingToTest.length} | Retire: ${retire.length}`);
  console.log(`   WATCHED + WORKED: ${watchedAndWorked.length} hooks`);
  console.log(`   YouTube topics: ${ytSignals?.summary?.dominant_topics?.join(', ') || 'none'}`);

  return result;
}

module.exports = { run };
if (require.main === module) run();
