#!/usr/bin/env node
/**
 * run_brand_guard.js — brand_guard agent core script
 * Tone compliance, forbidden phrases, AI-sounding language, off-brand wording
 * Reads: captions.json, caption-variants.json, blog-drafts.json, reddit-replies.json
 * Produces: brand-guard-report.json, tone-violations.json
 *
 * Schema: https://clawdia.io/agents/brand-guard/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const caps     = readJson('captions.json') || {};
  const capVars  = readJson('caption-variants.json') || {};
  const blogs    = readJson('blog-drafts.json') || {};
  const reddit   = readJson('reddit-replies.json') || {};

  // ── Brand rule sets ────────────────────────────────────────────────
  const FORBIDDEN_GENERIC = [
    'we are', 'our team is', 'here at', 'passionate about', 'cutting edge',
    'world class', 'best in class', 'revolutionary', 'game changer', 'game-changing',
    'best-in-class', 'next level', 'transform your', 'unlock your', 'discover the',
    'experience the', 'embrace the', 'join us as we', 'dedicated to',
    'passionate team', 'friendly staff', 'world-class facility',
  ];

  const SALESY_SLAGHTER = [
    'amazing', 'incredible', 'mind-blowing', 'insane', 'epic', 'fire',
    'best ever', 'guaranteed', 'proven to', 'will change your', 'totally',
    'literally', 'basically', 'obviously', 'clearly', 'definitely',
  ];

  const AMERICANISMS = [
    'anyway', 'fancy', 'mad', 'sick', 'hype', 'whip', 'dope', 'lit',
    'the best', 'awesome', 'bro', 'buddy', 'y\'all', 'dude',
  ];

  const WEAK_CTAS = [
    'click the link', 'click here', 'check out our', 'visit us at',
    'come and see', 'stop by', 'get in touch', 'reach out to us',
    'sign up today', 'sign up now', 'get started today',
  ];

  const SWING_SHACK_VOICE = {
    tone: 'direct, South African, data-driven, no fluff',
    examples: {
      good: [
        'Your swing speed is 83 mph. PGA Tour avg: 112. Here\'s how to close the gap.',
        'TrackMan found it in 3 swings. No guessing.',
        'From R850 — certified TPI coaches. Book online.',
      ],
      bad: [
        'World-class golfing experience awaits at our stunning facility!',
        'Our passionate team of experts is here to help you unlock your true potential!',
        'Amazing incredible results guaranteed!',
      ],
    },
  };

  // ── Check functions ────────────────────────────────────────────────
  function checkText(text, itemId, itemType, sourceHook) {
    const lower = (text || '').toLowerCase();
    const violations = [];

    // Generic AI tone
    const genericHits = FORBIDDEN_GENERIC.filter(p => lower.includes(p));
    if (genericHits.length > 0) {
      violations.push({
        type: 'generic_ai',
        severity: 'high',
        phrase: genericHits[0],
        msg: `"${genericHits[0]}" — generic marketing language, not Swing Shack voice`,
        replacement_suggestion: 'Use specific data or benefit instead',
      });
    }

    // Salesy language
    const salesyHits = SALESY_SLAGHTER.filter(p => lower.includes(p));
    if (salesyHits.length > 0) {
      violations.push({
        type: 'salesy_sludge',
        severity: 'medium',
        phrase: salesyHits[0],
        msg: `"${salesyHits[0]}" — too salesy, tone down`,
        replacement_suggestion: 'Use factual language instead',
      });
    }

    // Americanisms
    const amHits = AMERICANISMS.filter(p => lower.includes(p));
    if (amHits.length > 0) {
      violations.push({
        type: 'too_american',
        severity: 'low',
        phrase: amHits[0],
        msg: `"${amHits[0]}" — American slang, use SA alternatives`,
        replacement_suggestion: 'SA-friendly: "really", "very good", "great"',
      });
    }

    // Weak CTA
    const weakHits = WEAK_CTAS.filter(p => lower.includes(p));
    if (weakHits.length > 0) {
      violations.push({
        type: 'weak_cta',
        severity: 'low',
        phrase: weakHits[0],
        msg: `"${weakHits[0]}" — weak CTA, be more specific`,
        replacement_suggestion: '"Book your session" or "DM us to get started"',
      });
    }

    // Overclaim check — golf performance claims without data
    const overclaimPatterns = [
      /will (?:dramatically|significantly|completely)/i,
      /guarantee/i,
      /proven to (?:double|cut|eliminate)/i,
    ];
    overclaimPatterns.forEach(p => {
      if (p.test(text)) {
        violations.push({
          type: 'overclaim',
          severity: 'high',
          msg: 'Unsubstantiated performance claim — needs TrackMan data to back it up',
          replacement_suggestion: 'Add specific metric: "TrackMan found 12m improvement in 3 sessions"',
        });
      }
    });

    // No proof check — mentions golf improvement without data
    const hasImprovement = lower.match(/improv|better|faster|longer|stronger/);
    const hasProof = lower.match(/trackman|number|data|stat|meters|mph|speed/);
    if (hasImprovement && !hasProof && itemType === 'caption') {
      violations.push({
        type: 'no_proof',
        severity: 'medium',
        msg: 'Performance claim without data — add TrackMan stat for credibility',
        replacement_suggestion: '"Your carry distance is 187m. Here\'s how to add 20m."',
      });
    }

    return violations;
  }

  function checkCaption(c) {
    const text = (c.short_caption || '') + ' ' + (c.medium_caption || '');
    const violations = checkText(text, c.caption_id, 'caption', c.hook_text);

    // Emoji check — too many emoji is off-brand
    const emojiCount = (text.match(/[\u{1F300}-\u{1F9FF}]/gu) || []).length;
    if (emojiCount > 5) {
      violations.push({
        type: 'too_many_emoji',
        severity: 'low',
        count: emojiCount,
        msg: `${emojiCount} emoji — too many, tone down`,
        replacement_suggestion: 'Max 2-3 emoji per caption',
      });
    }

    const severity = violations.some(v => v.severity === 'high') ? 'fail'
      : violations.some(v => v.severity === 'medium') ? 'warn' : 'pass';

    return {
      item_id: c.caption_id,
      item_type: 'caption',
      hook_text: c.hook_text,
      text_preview: text.substring(0, 100),
      brand_score: Math.max(0, 100 - violations.length * 20),
      verdict: severity,
      violations,
      voice_example: severity !== 'pass' ? SWING_SHACK_VOICE.examples.good[0] : null,
    };
  }

  function checkBlogDraft(d) {
    const text = (d.headline || '') + ' ' + (d.sections || '');
    const violations = checkText(text, d.draft_id, 'blog_draft', null);

    // Check for proper SA context
    if (!text.includes('South Africa') && !text.includes('Johannesburg') && !text.includes('SA') && text.length > 500) {
      violations.push({
        type: 'missing_local_context',
        severity: 'low',
        msg: 'Long blog post without local (SA/Johannesburg) context — add location specificity',
        replacement_suggestion: 'Add "Indoor golf in Johannesburg" or "South African golfers"',
      });
    }

    // Check TrackMan mention
    if (!text.match(/trackman/i)) {
      violations.push({
        type: 'missing_proof_element',
        severity: 'medium',
        msg: 'No TrackMan mention in blog — key differentiator missing for SEO and authority',
        replacement_suggestion: 'Add section on what TrackMan measures and why it matters',
      });
    }

    const severity = violations.some(v => v.severity === 'high') ? 'fail'
      : violations.some(v => v.severity === 'medium') ? 'warn' : 'pass';

    return {
      item_id: d.draft_id,
      item_type: 'blog_draft',
      headline: d.headline,
      brand_score: Math.max(0, 100 - violations.length * 15),
      verdict: severity,
      violations,
    };
  }

  function checkRedditReply(r) {
    const text = (r.reply_draft || '') + ' ' + (r.soft_brand_mention || '');
    const violations = checkText(text, r.reply_id, 'reddit_reply', null);

    // Reddit-specific: must feel native, no brand voice
    if ((r.reply_draft || '').length > 200 && violations.length === 0) {
      // Good native reply
    } else if ((r.reply_draft || '').length <= 50) {
      violations.push({
        type: 'too_short_for_native',
        severity: 'medium',
        msg: 'Reply too short to feel native on Reddit',
        replacement_suggestion: 'Expand with a genuine helpful explanation, not just a quick mention',
      });
    }

    const severity = violations.some(v => v.severity === 'high') ? 'fail'
      : violations.some(v => v.severity === 'medium') ? 'warn' : 'pass';

    return {
      item_id: r.reply_id,
      item_type: 'reddit_reply',
      subreddit: r.subreddit,
      text_preview: (r.reply_draft || '').substring(0, 100),
      brand_score: Math.max(0, 100 - violations.length * 20),
      verdict: severity,
      violations,
      soft_brand_present: !!r.soft_brand_mention,
    };
  }

  // ── Run checks ─────────────────────────────────────────────────────
  const allReports = [];

  (caps.captions || []).forEach(c => allReports.push(checkCaption(c)));
  (blogs.drafts || []).forEach(d => allReports.push(checkBlogDraft(d)));
  (reddit.replies || []).forEach(r => allReports.push(checkRedditReply(r)));

  const passList = allReports.filter(r => r.verdict === 'pass');
  const warnList = allReports.filter(r => r.verdict === 'warn');
  const failList = allReports.filter(r => r.verdict === 'fail');

  const brandReport = {
    schema: 'https://clawdia.io/agents/brand-guard/v1',
    generated: new Date().toISOString(),
    total_items: allReports.length,
    pass: passList.length,
    warn: warnList.length,
    fail: failList.length,
    brand_score: allReports.length > 0
      ? Math.round(allReports.reduce((s, r) => s + (r.brand_score || 0), 0) / allReports.length)
      : 100,
    voice_standard: SWING_SHACK_VOICE.tone,
    violations_found: allReports.flatMap(r => r.violations),
    reports: allReports,
  };

  const toneViolations = {
    schema: 'https://clawdia.io/agents/brand-guard/v1',
    generated: new Date().toISOString(),
    total_violations: allReports.flatMap(r => r.violations).length,
    by_type: {
      generic_ai: allReports.flatMap(r => r.violations).filter(v => v.type === 'generic_ai').length,
      salesy_sludge: allReports.flatMap(r => r.violations).filter(v => v.type === 'salesy_sludge').length,
      too_american: allReports.flatMap(r => r.violations).filter(v => v.type === 'too_american').length,
      weak_cta: allReports.flatMap(r => r.violations).filter(v => v.type === 'weak_cta').length,
      overclaim: allReports.flatMap(r => r.violations).filter(v => v.type === 'overclaim').length,
      no_proof: allReports.flatMap(r => r.violations).filter(v => v.type === 'no_proof').length,
    },
    violations: allReports.flatMap(r => r.violations),
    worst_offenders: failList.slice(0, 3).map(r => ({
      item_id: r.item_id,
      item_type: r.item_type,
      violation_count: r.violations.length,
      worst_violation: r.violations[0]?.msg || null,
    })),
  };

  fs.writeFileSync(path.join(DATA, 'brand-guard-report.json'), JSON.stringify(brandReport, null, 2));
  fs.writeFileSync(path.join(DATA, 'tone-violations.json'), JSON.stringify(toneViolations, null, 2));

  console.log(`✅ Brand Guard: ${allReports.length} items checked`);
  console.log(`   PASS: ${passList.length} | WARN: ${warnList.length} | FAIL: ${failList.length}`);
  console.log(`   Brand score: ${brandReport.brand_score}/100`);
  console.log(`   Voice standard: ${SWING_SHACK_VOICE.tone}`);
  if (failList.length > 0) console.log(`   ⚠️  ${failList.length} items FAIL brand check — see brand-guard-report.json`);
  if (toneViolations.by_type.generic_ai > 0) console.log(`   🔤 Generic AI tone: ${toneViolations.by_type.generic_ai} items`);
  if (toneViolations.by_type.salesy_sludge > 0) console.log(`   📢 Salesy language: ${toneViolations.by_type.salesy_sludge} items`);
}

module.exports = { run };
if (require.main === module) run();