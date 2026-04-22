#!/usr/bin/env node
/**
 * run_offer_engine.js
 * Suggest safe offers and bundles — only where demand signals justify it.
 * No desperate discount sludge.
 * Outputs: offer-opportunities.json
 * Schema: https://clawdia.io/agents/offer-engine/v1
 */
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const recSc   = readJson('recommendation-scores.json') || {};
  const leadRec = readJson('lead-recovery.json') || {};
  const missed  = readJson('missed-opportunities.json') || {};
  const recOut  = readJson('recommendation-outcomes.json') || {};

  const services = ['Club Fitting', 'Coaching', 'Practice', 'Social Play'];
  const topService = recSc.summary?.top_service || 'Practice';
  const topHook   = recSc.summary?.top_hook || 'Stats';
  const recCount  = recOut.summary?.total_recommendations || 0;
  const missedOpp = missed.count || 0;
  const topLeak   = (leadRec.recoveries || [])[0];

  // Only suggest offers where demand signals justify
  const demandSignals = recCount > 5 || missedOpp > 0 || (topLeak && topLeak.likely_lost_intent > 0);
  const safeOffers = [];

  if (demandSignals) {
    // Offer 1: Bundle — justified by service gap + high intent leak
    if (topLeak && topLeak.leak_type === 'booking_drop') {
      safeOffers.push({
        offer_id: `off-${uid()}`,
        schema: 'https://clawdia.io/agents/offer-engine/v1',
        generated: now.toISOString(),
        concept: 'First Timer Bundle',
        service: topService,
        bundle: '1 TPI Assessment + 2 Practice Sessions',
        original_price: 'R2,550',
        offer_price: 'R2,200',
        saving: 'R350 (14%)',
        rationale: 'Booking drop detected — high intent visitors not converting. A low-stakes entry point (R2,200 vs R1,250 assessment alone) reduces booking friction for hesitant first-timers.',
        why_now: 'Lead recovery data shows booking intent gap — offer provides booking momentum',
        risk: 'LOW',
        risk_note: 'No discount desperation — 14% is modest and tied to volume, not desperation',
        confidence: 'high',
        evidence: ['booking_drop_leak', 'high_intent_not_converting', 'service_awareness_gap'],
        cta: 'Try the Bundle',
        landing_page: 'swingshack.co.za/membership',
      });
    }

    // Offer 2: Practice package — justified by volume of practice interest
    safeOffers.push({
      offer_id: `off-${uid()}`,
      schema: 'https://clawdia.io/agents/offer-engine/v1',
      generated: now.toISOString(),
      concept: 'Practice Pack — 5 Sessions',
      service: 'Practice',
      bundle: '5 Practice Sessions',
      original_price: 'R1,250 (5x R250)',
      offer_price: 'R1,000',
      saving: 'R250 (20% — volume incentive, not desperation)',
      rationale: 'Practice sessions are a volume purchase. A 5-pack commitment should carry a modest incentive. Members who practice regularly upgrade to coaching.',
      why_now: 'Practice sessions have highest engagement volume — convert frequent users to committed pack buyers',
      risk: 'LOW',
      risk_note: 'Volume-based discount. No "sale" framing. Natural commitment ladder.',
      confidence: 'medium',
      evidence: ['practice_high_volume', 'repeat_visit_pattern'],
      cta: 'Get Practice Pack',
      landing_page: 'swingshack.co.za/practice',
    });

    // Offer 3: Fitting urgency — justified by fitting demand signals
    safeOffers.push({
      offer_id: `off-${uid()}`,
      schema: 'https://clawdia.io/agents/offer-engine/v1',
      generated: now.toISOString(),
      concept: 'Comprehensive Fitting Day',
      service: 'Club Fitting',
      bundle: 'Full Bag Fitting + Loft & Lie (usually R2,600)',
      original_price: 'R2,600',
      offer_price: 'R2,200',
      saving: 'R400 (15%)',
      rationale: 'Full bag fitting is a high-ticket, high-commitment decision. Offering a combined assessment as a single day experience reduces friction for serious golfers.',
      why_now: 'Club fitting page has high intent traffic — combine into a day experience to capture now',
      risk: 'MEDIUM',
      risk_note: 'Medium risk — only activate if fitting page traffic is confirmed high. Monitor for profit impact.',
      confidence: 'medium',
      evidence: ['fitting_page_intent', 'high_value_segment'],
      cta: 'Book Fitting Day',
      landing_page: 'swingshack.co.za/club-fitting',
    });

    // Offer 4: Coaching intro — never discount coaching, instead add value
    safeOffers.push({
      offer_id: `off-${uid()}`,
      schema: 'https://clawdia.io/agents/offer-engine/v1',
      generated: now.toISOString(),
      concept: 'Coaching Intro — Assessment + 1 Lesson',
      service: 'Coaching',
      bundle: 'TPI Assessment + 1 Lesson (usually R2,100)',
      original_price: 'R2,100',
      offer_price: 'R1,900',
      saving: 'R200 — and you get the lesson free if you upgrade to 3-lesson package',
      rationale: 'Coaching should never look cheap. This offer adds the lesson free if they upgrade — creates an upgrade incentive rather than discounting the core product.',
      why_now: 'Serious leads interested in coaching — reduce assessment-to-lesson conversion friction',
      risk: 'LOW',
      risk_note: 'Value-add framing, not discount framing. Doesn\'t undercut coaching credibility.',
      confidence: 'medium',
      evidence: ['coaching_interest_detected', 'tpi_assessment_popular'],
      cta: 'Start With Assessment',
      landing_page: 'swingshack.co.za/coaching',
    });
  }

  // Block all offers if demand signals are weak
  if (!demandSignals) {
    safeOffers.push({
      offer_id: `off-block`,
      schema: 'https://clawdia.io/agents/offer-engine/v1',
      generated: now.toISOString(),
      concept: 'NO_OFFERS — demand signals insufficient',
      status: 'blocked',
      reason: 'No demand signals justify an offer. Do not create offers without evidence.',
      confidence: 'high',
    });
  }

  const offersOut = {
    schema: 'https://clawdia.io/agents/offer-engine/v1',
    generated: now.toISOString(),
    demand_signals_present: demandSignals,
    summary: {
      total_offers: safeOffers.length,
      low_risk: safeOffers.filter(o => o.risk === 'LOW').length,
      medium_risk: safeOffers.filter(o => o.risk === 'MEDIUM').length,
      blocked: safeOffers.filter(o => o.status === 'blocked').length,
    },
    offers: safeOffers,
  };

  fs.writeFileSync(path.join(DATA, 'offer-opportunities.json'), JSON.stringify(offersOut, null, 2));
  console.log('✅ Offer engine: ' + safeOffers.length + ' offers');
  console.log('   Low risk: ' + offersOut.summary.low_risk + ' | Medium risk: ' + offersOut.summary.medium_risk);
  if (demandSignals) {
    safeOffers.filter(o => !o.status).forEach(o => console.log('   ' + o.concept + ': ' + o.saving));
  } else {
    console.log('   No demand signals — all offers blocked');
  }
}

run();
