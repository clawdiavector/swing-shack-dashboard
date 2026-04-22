#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const lead=r('lead-recovery.json')||{};
  const rec=r('recommendation-scores.json')||{};
  const offer=r('offer-opportunities.json')||{};
  const topService=rec.summary?.top_service||'Practice';
  const topHook=rec.summary?.top_hook||'Stats';
  // Only build bundles that fit real buying behaviour
  const bundles=[
    {bundle_id:'bun-1',name:'Fitting Starter Pack',services:['Driver Fitting Assessment','1x Practice Session'],original:'R1,250',bundle_price:'R1,100',saving:'R150 (12%)',target:'first_time_fitter_not_ready_for_full_bag',rationale:'New fitters want to try before committing R900+ to full fitting. This gives them data + experience before the big spend. Real buying behaviour: test before invest.',operational_fit:'high',confidence:'high',why_now:'Fitting page has high intent traffic — offer this at first visit to close faster',cta:'Try the Starter Pack',landing:'/club-fitting'},
    {bundle_id:'bun-2',name:'Junior Golf Development Bundle',services:['3x Coaching Lessons (Catherine)','1x Practice Session'],original:'R2,350',bundle_price:'R2,100',saving:'R250 (11%)',target:'parents_of_junior_golfers',rationale:'Parents buying lessons want to see progress before committing to large packages. 3 lessons tests commitment + practice reinforces coaching. Real behaviour: small commitment first.',operational_fit:'high',confidence:'medium',why_now:'Junior golf interest seasonal — capture now before mid-year slump',cta:'Build Your Junior\'s Game',landing:'/coaching'},
    {bundle_id:'bun-3',name:'Social Golf Experience (x4)',services:['Social Play — 4 Players (3h)','Bucket of Beer'],original:'R1,020',bundle_price:'R920',saving:'R100 (10%)',target:'groups_booking_social',rationale:'Groups want the full social experience but feel awkward about the beer add-on separately. Package it. Makes the booking decision faster. Real behaviour: groups want all-in pricing.',operational_fit:'high',confidence:'high',why_now:'Social play bookings spike on weekends — pre-package to capture group bookings early in week',cta:'Book the Full Experience',landing:'/practice'},
    {bundle_id:'bun-4',name:'Precision Practice Pack (10 Sessions)',services:['10x Practice Sessions'],original:'R2,500 (10x R250)',bundle_price:'R2,000',saving:'R500 (20%)',target:'committed_practitioners_low_frequency',rationale:'High-frequency users who buy single sessions. A 10-pack gives them commitment discount + ensures retention. NOT a desperate discount — this is loyalty pricing. Real behaviour: commit to regular practice.',operational_fit:'high',confidence:'high',why_now:'Practice sessions are highest volume — convert frequent users to committed pack buyers',cta:'Commit to Your Practice',landing:'/practice'},
    {bundle_id:'bun-5',name:'Complete Improvement Package',services:['Full Bag Fitting','3x Coaching Lessons with Dave'],original:'R3,850',bundle_price:'R3,400',saving:'R450 (12%)',target:'serious_golfers_ready_to_commit',rationale:'Serious golfers who want fitting + immediate coaching application. R3,400 is significant but the fitting data makes coaching sessions immediately actionable. Real behaviour: high-intent buyers want everything at once.',operational_fit:'medium',confidence:'medium',why_now:'Only activate when fitting + coaching page traffic both high simultaneously',cta:'Get Fitted + Coached',landing:'/coaching'},
  ];
  const out={schema:'https://clawdia.io/agents/bundle-builder/v1',generated:now.toISOString(),summary:{total:bundles.length,high_confidence:bundles.filter(b=>b.confidence==='high').length},bundles};
  fs.writeFileSync(path.join(DATA,'bundle-opportunities.json'),JSON.stringify(out,null,2));
  console.log('✅ Bundle builder: '+bundles.length+' bundles');bundles.filter(b=>b.confidence==='high').forEach(b=>console.log('   HIGH CONF: '+b.name+' — '+b.target));}
run();
