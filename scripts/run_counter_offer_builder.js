#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const tracker=r('competitor-tracker.json')||{};
  const sov=r('share-of-voice.json')||{};
  // Counter-moves based on observed competitor behaviour
  const moves=[
    {move_id:'cm-1',competitor_move:'Golf Bar increases posting to 3x/week',our_counter:'Flip to DAILY. Publish every day including weekends. Golf Bar is strong on events — we own educational daily content they can\'t match.',our_content:'TrackMan educational Reels, stats hooks, fitting explainers',priority:'high',thrust:'quantity_plus_quality'},
    {move_id:'cm-2',competitor_move:'Rival runs discount campaign',our_counter:'Don\'t discount. Push TRUST + VALUE. "Cheapest isn\'t the best — your game data is worth the investment." Lean into TrackMan proof.',our_content:'Post testimonials with actual numbers. "Here\'s what 15 extra yards looks like."',priority:'high',thrust:'value_over_price'},
    {move_id:'cm-3',competitor_move:'Rival silent on social (Golden Tee pattern)',our_counter:'Flood their silence. Accelerate content. Publish what they\'re not. Gap their weakness: fitting education, blog, YouTube.',our_content:'TrackMan Tuesday series, fitting explainer blog, Google review push',priority:'medium',thrust:'flood_the_zone'},
    {move_id:'cm-4',competitor_move:'New entrant appears',our_counter:'Don\'t panic. First 90 days: watch only. Map their positioning. Do NOT react emotionally. If they\'re entertainment-focused: differentiate on performance. If fitting-focused: double down on coaching quality.',our_content:'Monitor, don\'t react. Respond after 90 days with data-backed positioning.',priority:'low',thrust:'observe_then_counter'},
    {move_id:'cm-5',competitor_move:'Rival does fitting campaign',our_counter:'Go deeper. Publish fitting results with real numbers. Before/after TrackMan data. "Pros average 264m drive. Here\'s what 3 fitting sessions did for this member."',our_content:'Member fitting case studies with actual TrackMan numbers',priority:'medium',thrust:'proof_over_promise'},
    {move_id:'cm-6',competitor_move:'Rival gets great Google reviews spike',our_counter:'Push review generation harder. Send post-visit WhatsApp: "We\'d love your feedback — takes 30 seconds." Target 50 new reviews in 30 days.',our_content:'Review QR at counter, WhatsApp review request, review incentive (small free drink)',priority:'high',thrust:'review_momentum'},
  ];
  const out={schema:'https://clawdia.io/agents/counter-offer-builder/v1',generated:now.toISOString(),summary:{total_moves:moves.length,high_priority:moves.filter(m=>m.priority==='high').length,immediate_action:moves.filter(m=>m.priority==='high')[0]?.competitor_move||null},moves};
  fs.writeFileSync(path.join(DATA,'counter-moves.json'),JSON.stringify(out,null,2));
  console.log('✅ Counter offer builder: '+moves.length+' moves');moves.filter(m=>m.priority==='high').forEach(m=>console.log('   HIGH: '+m.competitor_move.substring(0,60)));}
run();
