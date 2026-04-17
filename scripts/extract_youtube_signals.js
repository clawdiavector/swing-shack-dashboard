#!/usr/bin/env node
/**
 * extract_youtube_signals.js
 * Reads youtube-trends.json → extracts hook signals → writes youtube-hook-signals.json
 *
 * Signal types:
 * - recurring_phrases: word pairs / short phrases that appear across titles
 * - topic_clusters: recurring topics (driver, slice, senior, beginner, etc.)
 * - format_patterns: "How to...", "X Tips", "X Steps", "X Mistakes"
 * - urgency_language: action-driving words that create urgency
 * - before_after: problem→solution framing patterns
 * - mistake_fix: "mistake/fix" language patterns
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const YT_FILE = path.join(DATA_DIR, 'youtube-trends.json');
const OUT_FILE = path.join(DATA_DIR, 'youtube-hook-signals.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch(e) { return null; }
}

function tokenize(text) {
  if (!text) return [];
  return text.toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(w => w.length > 2);
}

function bigrams(words) {
  const result = [];
  for (let i = 0; i < words.length - 1; i++) {
    result.push(words[i] + ' ' + words[i + 1]);
  }
  return result;
}

function extractSignals(videos) {
  if (!videos || videos.length === 0) return null;

  const allText = videos.map(v => (v.title || '') + ' ' + (v.description || '')).join(' ');
  const words = tokenize(allText);
  const titles = videos.map(v => v.title || '');
  const titleText = titles.join(' ');

  // ── 1. Recurring phrases (bigrams appearing in 2+ titles) ──────────────
  const titleBigrams = titles.flatMap(t => bigrams(tokenize(t)));
  const bgCounts = {};
  titleBigrams.forEach(bg => { bgCounts[bg] = (bgCounts[bg] || 0) + 1; });
  const recurringPhrases = Object.entries(bgCounts)
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([phrase, count]) => ({ phrase, count, examples: titles.filter(t => t.toLowerCase().includes(phrase)).slice(0, 2) }));

  // ── 2. Topic clusters ───────────────────────────────────────────────────
  const topicPatterns = {
    'driver': ['driver', 'drive', 'driving', 'tee shot'],
    'slice_fix': ['slice', 'hook', 'ball flight', 'aim', 'club path'],
    'senior': ['senior', 'older', '50+'],
    'beginner': ['beginner', 'new to golf', 'start', 'basics', 'first time'],
    'irons': ['iron', 'irons', 'fairway', 'approach'],
    'short_game': ['chip', 'pitch', 'putt', 'putting', 'around the green', 'bunker'],
    'simulator': ['simulator', 'indoor', 'launch monitor', 'trackman'],
    'lessons': ['lesson', 'pro', 'coach', 'professional', 'instruction', 'tips from'],
    'swing': ['swing', 'swinging', 'swing speed'],
    'fitness': ['fitness', 'flexibility', 'mobility', 'core', 'strength'],
    'distance': ['distance', 'further', 'yards', 'meters', 'longer'],
    'consistency': ['consistent', 'consistently', 'repeatable', 'repeat'],
  };

  const topicMatches = {};
  for (const [topic, patterns] of Object.entries(topicPatterns)) {
    const matched = patterns.some(p => titleText.toLowerCase().includes(p));
    if (matched) topicMatches[topic] = videos.filter(v =>
      patterns.some(p => (v.title + v.description).toLowerCase().includes(p))
    ).length;
  }

  // ── 3. Format patterns ──────────────────────────────────────────────────
  const formatPatterns = [
    { pattern: /how to\s/i, label: 'How to...', example: 'How to hit driver' },
    { pattern: /\d+\s+(steps?|tips?|secrets?|mistakes?|signs?)/i, label: 'Numbered list', example: '5 Tips to fix your slice' },
    { pattern: /best\s/i, label: '"Best" superlative', example: 'Best driver tip ever' },
    { pattern: /easy\s/i, label: '"Easy" simplicity', example: 'Easy steps for better golf' },
    { pattern: /simple\s/i, label: '"Simple" promise', example: 'Simple golf swing' },
    { pattern: /(\?|how do|what if|should i)/i, label: 'Question hook', example: 'How do pro players...' },
    { pattern: /stop\s/i, label: '"Stop" command', example: 'Stop slicing' },
    { pattern: /mistake/i, label: 'Mistake framing', example: 'Biggest mistake amateur golfers make' },
    { pattern: /(\?|—|--)/, label: 'Contrast hook', example: 'Struggling with X? Here\'s the fix' },
    { pattern: /honest\s/i, label: '"Honest" credibility', example: 'My honest review after 5 years' },
    { pattern: /years?\s/i, label: 'Experience claim', example: 'After 5 years of practice' },
    { pattern: /guarantee/i, label: 'Guarantee language', example: 'We guarantee you\'ll improve' },
  ];

  const formatMatches = formatPatterns
    .map(f => ({ label: f.label, matched: f.pattern.test(titleText), example: titles.find(t => f.pattern.test(t)) || f.example }))
    .filter(f => f.matched)
    .map(f => ({ label: f.label, example: f.example }));

  // ── 4. Urgency language ─────────────────────────────────────────────────
  const urgencyPatterns = [
    { word: 'stop', strength: 3 },
    { word: 'how to', strength: 2 },
    { word: 'learn', strength: 2 },
    { word: 'fix', strength: 3 },
    { word: 'secret', strength: 2 },
    { word: 'mistake', strength: 3 },
    { word: 'right now', strength: 3 },
    { word: 'today', strength: 2 },
    { word: 'finally', strength: 2 },
    { word: 'prove', strength: 2 },
  ];

  const urgencyScore = urgencyPatterns.reduce((sum, p) => {
    const count = (titleText.toLowerCase().match(new RegExp(p.word, 'g')) || []).length;
    return sum + count * p.strength;
  }, 0);

  // ── 5. Before/after patterns ────────────────────────────────────────────
  const beforeAfterPattern = /struggling|want to|hitting|failing|can't|problem|issue|issue/i;
  const hasBeforeAfter = beforeAfterPattern.test(titleText);
  const beforeAfterExamples = hasBeforeAfter ? titles.filter(t => beforeAfterPattern.test(t)).slice(0, 3) : [];

  // ── 6. Mistake/fix patterns ─────────────────────────────────────────────
  const mistakeFixPattern = /mistake|fix|solution|wrong|error|instead|actually|here's what/i;
  const hasMistakeFix = mistakeFixPattern.test(titleText);
  const mistakeFixExamples = hasMistakeFix ? titles.filter(t => mistakeFixPattern.test(t)).slice(0, 3) : [];

  // ── 7. YouTube channel signals (who's making content) ──────────────────
  const channels = {};
  videos.forEach(v => { channels[v.channelTitle] = (channels[v.channelTitle] || 0) + 1; });
  const topChannels = Object.entries(channels).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // ── 8. Composite hook templates ─────────────────────────────────────────
  // These are synthesized from what performs on YouTube, for idea generation
  const topTitles = [...new Set(titles)].slice(0, 10);
  const templates = [
    { template: 'How to [skill] — [specific benefit]', source: 'how-to-format', count: titles.filter(t => /how to\s/i.test(t)).length },
    { template: '[Number] Tips for [outcome]', source: 'numbered-list', count: titles.filter(t => /\d+\s+(tips?|steps?)/i.test(t)).length },
    { template: 'The Truth About [common_mistake]', source: 'mistake-reveal', count: titles.filter(t => /mistake|truth|secret/i.test(t)).length },
    { template: '[Problem]? Here\'s the Fix', source: 'problem-fix', count: titles.filter(t => /\?|here's the/i.test(t)).length },
    { template: '[Player Type]: [advice]', source: 'player-specific', count: titles.filter(t => /senior|beginner|amateur/i.test(t)).length },
  ];

  return {
    fetched_at: new Date().toISOString(),
    source_file: 'youtube-trends.json',
    videos_analyzed: videos.length,
    top_videos: videos.slice(0, 10), // stored for evidence matching in hook analysis
    signals: {
      recurring_phrases: recurringPhrases,
      topic_clusters: topicMatches,
      format_patterns: formatMatches,
      urgency_score: urgencyScore,
      urgency_language: urgencyPatterns.filter(p => titleText.toLowerCase().includes(p.word)).map(p => p.word),
      has_before_after: hasBeforeAfter,
      before_after_examples: beforeAfterExamples,
      has_mistake_fix: hasMistakeFix,
      mistake_fix_examples: mistakeFixExamples,
      top_channels: topChannels,
      hook_templates: templates.filter(t => t.count > 0),
    },
    summary: {
      dominant_topics: Object.entries(topicMatches).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([t]) => t),
      dominant_formats: formatMatches.map(f => f.label),
      top_template: templates.filter(t => t.count > 0).sort((a, b) => b.count - a.count)[0]?.template || null,
    }
  };
}

function run() {
  const yt = readJson('youtube-trends.json');
  if (!yt) {
    console.error('youtube-trends.json not found');
    process.exit(1);
  }

  const videos = yt.top_videos || [];
  if (videos.length === 0) {
    console.error('No videos found in youtube-trends.json');
    process.exit(1);
  }

  const signals = extractSignals(videos);

  fs.writeFileSync(OUT_FILE, JSON.stringify(signals, null, 2));
  console.log(`✅ YouTube signals extracted from ${videos.length} videos`);
  console.log(`   Topics: ${signals.summary.dominant_topics.join(', ')}`);
  console.log(`   Formats: ${signals.summary.dominant_formats.join(', ')}`);
  console.log(`   Urgent phrases: ${signals.signals.urgency_language.join(', ')}`);
  console.log(`   Written to: ${OUT_FILE}`);

  return signals;
}

module.exports = { run, extractSignals };
if (require.main === module) run();
