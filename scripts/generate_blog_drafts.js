#!/usr/bin/env node
/**
 * generate_blog_drafts.js — blog_beast agent core script
 * Reads: seo-audit.json, seo-rankings.json, website-insights.json, content-ideas.json
 * Produces: blog-briefs.json, blog-drafts.json, faq-opportunities.json
 *
 * Rule: Write for search + AI answerability + real conversion intent. Not fluff.
 * Schema: https://clawdia.io/agents/blog-beast/v1
 */
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const MEM  = path.join(BASE, 'memory', 'daily');
const DATA = path.join(BASE, 'data');

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const seoAudit = readJson('seo-audit.json') || {};
  const seoRank = readJson('seo-rankings.json') || {};
  const webIns = readJson('website-insights.json') || {};
  const ideas = readJson('content-ideas.json') || {};
  const hooks = readJson('hook-bank.json') || {};

  // ── Keyword sources ────────────────────────────────────────────────
  const kw = seoRank.keywords || [];
  const risingKws = seoRank.rising_keywords || [];
  const quickWins = seoRank.quick_wins || [];
  const topPages = webIns.top_pages || [];

  // ── Topic clusters for Swing Shack ────────────────────────────────
  const CLUSTERS = [
    {
      cluster: 'TrackMan Golf Technology',
      keywords: ['trackman golf', 'trackman indoor golf', 'golf launch monitor', 'trackman johannesburg', 'indoor golf tech'],
      angle: "TrackMan is the gold standard for golf improvement. Show what it measures, why it matters, who it's for.",
    },
    {
      cluster: 'Indoor Golf Johannesburg',
      keywords: ['indoor golf johannesburg', 'indoor golf sandton', 'golf simulator johannesburg', 'golf near me indoor'],
      angle: 'Location-first intent. Clear directions, what to expect, pricing context, booking ease.',
    },
    {
      cluster: 'Golf Coaching & Lessons',
      keywords: ['golf lessons johannesburg', 'golf coach sandton', 'tpi assessment', 'golf improvement'],
      angle: 'Transformation story. Before/after numbers, certified coaches, real feedback.',
    },
    {
      cluster: 'Golf Club Fitting',
      keywords: ['club fitting johannesburg', 'trackman fitting', 'driver fitting', 'iron fitting', 'custom golf clubs'],
      angle: 'Trust + data. How TrackMan fitting works, what it costs, what you get, why it beats guesswork.',
    },
    {
      cluster: 'Practice & Warm-up',
      keywords: ['golf practice indoor', 'golf warm up simulator', 'indoor range', 'golf bucket'],
      angle: 'Convenience + preparation. How indoor practice fits into a real golf improvement program.',
    },
  ];

  // ── Blog brief generator ───────────────────────────────────────────
  function buildBrief(cluster, kwItem, priority) {
    const targetKw = kwItem?.keyword || cluster.keywords[0];
    const intent = targetKw.includes('how') || targetKw.includes('what') ? 'informational'
      : targetKw.includes('book') || targetKw.includes('price') || targetKw.includes('cost') ? 'transactional'
      : 'informational';
    const wordCount = intent === 'transactional' ? 1200 : 1800;

    return {
      brief_id: `bb-${uid()}`,
      schema: 'https://clawdia.io/agents/blog-beast/v1',
      generated: new Date().toISOString(),
      cluster,
      target_keyword: targetKw,
      secondary_keywords: cluster.keywords.filter(k => k !== targetKw).slice(0, 3),
      search_intent: intent,
      word_count_target: wordCount,
      tone: 'knowledgeable, South African, data-driven, not salesy',
      structure: intent === 'informational'
        ? ['HOOK (stat or question)', 'PROBLEM (what golfers get wrong)', 'SOLUTION (TrackMan/data)', 'HOW IT WORKS (Swing Shack specifics)', 'FAQ (5 questions)', 'CTA (book session)']
        : ['HOOK (direct benefit)', 'WHAT YOU GET (pricing/packages)', 'PROCESS (booking + session)', 'PROOF (numbers/results)', 'CTA (book now)'],
      h1_suggestion: targetKw.includes('trackman') ? `What TrackMan Golf Technology Means for Your Game` :
        targetKw.includes('indoor golf johannesburg') ? `Indoor Golf in Johannesburg: The Complete Guide` :
        targetKw.includes('fitting') ? `Club Fitting in Johannesburg: What to Expect` :
        `${targetKw.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}: What You Need to Know`,
      seo_notes: `Target: ${targetKw}. Intent: ${intent}. Include ${cluster.angle.substring(0, 50)}.`,
      conversion_goal: intent === 'transactional' ? 'book_session' : 'email_signup',
      status: 'draft',
      confidence: priority === 'quick_win' ? 90 : priority === 'rising' ? 80 : 70,
      owner: 'blog_beast',
      ready_for_qa: true,
      next_action: 'Write draft, QA for SEO + brand, publish',
    };
  }

  // ── Blog draft generator ──────────────────────────────────────────
  function buildDraft(brief, hookBank) {
    const h1 = brief.h1_suggestion;
    const hook = hookBank?.output_buckets?.proven_and_trending?.[0]?.hook_text ||
                 hookBank?.output_buckets?.proven_only?.[0]?.hook_text ||
                 'Your golf numbers don\'t lie.';
    const serviceMap = {
      'TrackMan Golf Technology': { emoji: '🏌️', name: 'TrackMan', price: 'from R250/session' },
      'Indoor Golf Johannesburg': { emoji: '🎮', name: 'Swing Shack', price: 'from R250/session' },
      'Golf Coaching & Lessons': { emoji: '🎯', name: 'Swing Shack Coaching', price: 'from R850/lesson' },
      'Golf Club Fitting': { emoji: '🏆', name: 'TrackMan Fitting', price: 'from R900/session' },
      'Practice & Warm-up': { emoji: '🥂', name: 'Practice', price: 'from R250/session' },
    };
    const svc = serviceMap[brief.cluster?.cluster] || serviceMap['Indoor Golf Johannesburg'];

    const faqs = [
      `How much does ${svc.name} cost at Swing Shack?`,
      `Is indoor golf worth it for real improvement?`,
      `How accurate is TrackMan compared to outdoor?`,
      `What should I bring to my first session?`,
      `Do I need to be a good golfer to use TrackMan?`,
    ];

    const faqAnswers = {
      [`How much does ${svc.name} cost at Swing Shack?`]: `${svc.price}. Check swingshack.co.za/membership for full pricing and packages.`,
      'Is indoor golf worth it for real improvement?': 'Yes — TrackMan data shows exactly where your swing breaks down. PGA Tour pros use the same tech. Indoor means zero weather risk and consistent conditions.',
      'How accurate is TrackMan compared to outdoor?': 'TrackMan is accurate to ±1 yard for carry distance. Better than most outdoor range cameras. Used by tour pros worldwide.',
      'What should I bring to my first session?': 'Just yourself and your clubs. We provide everything else — launch monitor, screen, ball data.',
      'Do I need to be a good golfer to use TrackMan?': 'No. TrackMan is for everyone — beginners through tour pros. Data helps beginners understand what they\'re doing, and helps pros fine-tune.',
    };

    const sections = brief.search_intent === 'informational'
      ? `## ${h1}\n\n*Your golf numbers don't lie.*\n\nIf you've ever wondered whether indoor golf actually helps your game, the answer is in the data. TrackMan launch monitors give you measurements that outdoor practice simply can't — club head speed, attack angle, smash factor, carry distance. Every number tells you something true about your swing.\n\n## The Problem With Traditional Golf Practice\n\nMost golfers practice by feel. They hit balls on the range, make adjustments based on gut instinct, and hope something changes. The problem: feel isn't real. Tour pros spend thousands on launch monitor data because numbers don't lie.\n\n## How TrackMan Changes Everything\n\nTrackMan gives you:\n- **Club head speed** — how fast you're actually swinging\n- **Attack angle** — whether you're hitting up or down\n- **Smash factor** — how efficiently you're striking the ball\n- **Carry distance** — how far the ball actually travels\n\nAt Swing Shack, every session is tracked. Every session builds your data profile.\n\n## What to Expect at Swing Shack\n\nBook a TrackMan session from ${svc.price}. No appointment needed for practice bays. Fitting sessions require booking.\n\n## Frequently Asked Questions\n\n${faqs.map((q, i) => `**${q}**\n${Object.values(faqAnswers)[i] || 'Contact Swing Shack for details.'}`).join('\n\n')}\n\n## Ready to Know Your Numbers?\n\n[Book your TrackMan session at Swing Shack](https://swingshack.co.za)\n\n#IndoorGolfJohannesburg #TrackManGolf #GolfSouthAfrica`
      : `## ${h1}\n\n*${svc.price} · TrackMan Technology · Johannesburg*\n\n[Intro paragraph — 150 words on why ${svc.name} matters and who it's for]\n\n## What You Get\n\n[Pricing table from swingshack.co.za/membership]\n\n## The Process\n\n1. Book online or via DM\n2. Arrive 10 minutes early\n3. 60-minute session with full TrackMan data\n4. Results explained by certified instructor\n\n## Book Now\n\n[swingshack.co.za]\n\n#IndoorGolfJohannesburg #TrackManGolf #SwingShack`;

    return {
      draft_id: `bd-${uid()}`,
      schema: 'https://clawdia.io/agents/blog-beast/v1',
      generated: new Date().toISOString(),
      linked_brief_id: brief.brief_id,
      target_keyword: brief.target_keyword,
      headline: h1,
      search_intent: brief.search_intent,
      sections,
      faqs: faqs.map((q, i) => ({ q, a: Object.values(faqAnswers)[i] || '' })),
      word_count_estimate: brief.word_count_target,
      cta: 'Book your session at swingshack.co.za',
      status: 'draft',
      confidence: brief.confidence,
      owner: 'blog_beast',
      ready_for_qa: true,
      next_action: 'QA: check SEO score, brand voice, links, CTA',
    };
  }

  // ── Build briefs ──────────────────────────────────────────────────
  const briefs = [];

  // Quick-win keywords → top priority
  quickWins.slice(0, 3).forEach(kw => {
    const cluster = CLUSTERS.find(c => c.keywords.includes(kw.keyword)) || CLUSTERS[0];
    briefs.push(buildBrief(cluster, kw, 'quick_win'));
  });

  // Rising keywords → second priority
  risingKws.slice(0, 3).forEach(kw => {
    const cluster = CLUSTERS.find(c => c.keywords.some(k => kw.keyword?.includes(k.split(' ')[0]))) || CLUSTERS[0];
    briefs.push(buildBrief(cluster, kw, 'rising'));
  });

  // Top pages from GA4 → third priority
  topPages.slice(0, 3).forEach(p => {
    const cluster = CLUSTERS[Math.floor(Math.random() * CLUSTERS.length)];
    briefs.push(buildBrief(cluster, { keyword: p.path || p.page || 'indoor golf' }, 'top_page'));
  });

  // One brief per cluster as baseline
  CLUSTERS.slice(0, 2).forEach(c => {
    briefs.push(buildBrief(c, { keyword: c.keywords[0] }, 'baseline'));
  });

  // ── Build drafts from first 3 briefs ──────────────────────────────
  const drafts = briefs.slice(0, 3).map(b => buildDraft(b, hooks));

  // ── FAQ opportunities ─────────────────────────────────────────────
  const faqs = briefs.map(b => ({
    faq_id: `faq-${uid()}`,
    schema: 'https://clawdia.io/agents/blog-beast/v1',
    generated: new Date().toISOString(),
    cluster: b.cluster?.cluster,
    target_keyword: b.target_keyword,
    questions: [
      `What is ${b.target_keyword}?`,
      `How much does ${b.target_keyword} cost in Johannesburg?`,
      `Is ${b.target_keyword} worth it?`,
      `What's the best ${b.target_keyword} in Johannesburg?`,
    ],
    source: b.search_intent === 'transactional' ? 'pricing_intent' : 'informational_intent',
    status: 'draft',
    owner: 'blog_beast',
    ready_for_qa: true,
  }));

  const briefsResult = {
    schema: 'https://clawdia.io/agents/blog-beast/v1',
    generated: new Date().toISOString(),
    total: briefs.length,
    by_intent: {
      informational: briefs.filter(b => b.search_intent === 'informational').length,
      transactional: briefs.filter(b => b.search_intent === 'transactional').length,
    },
    by_priority: {
      quick_win: briefs.filter(b => b.confidence >= 90).length,
      rising: briefs.filter(b => b.confidence >= 80 && b.confidence < 90).length,
      baseline: briefs.filter(b => b.confidence < 80).length,
    },
    ready_for_qa: briefs.filter(b => b.ready_for_qa).length,
    briefs,
  };

  const draftsResult = {
    schema: 'https://clawdia.io/agents/blog-beast/v1',
    generated: new Date().toISOString(),
    total: drafts.length,
    ready_for_qa: drafts.filter(d => d.ready_for_qa).length,
    drafts,
  };

  const faqsResult = {
    schema: 'https://clawdia.io/agents/blog-beast/v1',
    generated: new Date().toISOString(),
    total: faqs.length,
    ready_for_qa: faqs.filter(f => f.ready_for_qa).length,
    faqs,
  };

  fs.writeFileSync(path.join(DATA, 'blog-briefs.json'), JSON.stringify(briefsResult, null, 2));
  fs.writeFileSync(path.join(DATA, 'blog-drafts.json'), JSON.stringify(draftsResult, null, 2));
  fs.writeFileSync(path.join(DATA, 'faq-opportunities.json'), JSON.stringify(faqsResult, null, 2));

  console.log(`✅ Blog briefs: ${briefsResult.total} | ${briefsResult.ready_for_qa} ready for QA`);
  console.log(`   Blog drafts: ${draftsResult.total} | ${draftsResult.ready_for_qa} ready for QA`);
  console.log(`   FAQ clusters: ${faqsResult.total}`);
  console.log(`   Quick-win briefs: ${briefsResult.by_priority.quick_win} | Rising: ${briefsResult.by_priority.rising}`);
}

module.exports = { run };
if (require.main === module) run();