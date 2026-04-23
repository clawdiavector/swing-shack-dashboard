const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const uid=()=>Math.random().toString(36).substring(2,10);
const now=new Date();
// Scoring: margin × demand_signal × seasonality × trend
const products=[
  {id:'p-1',name:'Full Bag Fitting',type:'service',margin:0.75,demand:0.8,seasonality:0.9,trend:0.9,score:0,reason:'High-margin fitting season demand. Clubs changing for winter.',push:'now',confidence:'high'},
  {id:'p-2',name:'TPI Assessment',type:'service',margin:0.70,demand:0.85,seasonality:0.85,trend:0.8,score:0,reason:'Pre-lesson entry point. Every new golfer should start here.',push:'always',confidence:'high'},
  {id:'p-3',name:'Practice Pack (5 sessions)',type:'membership',margin:0.60,demand:0.7,seasonality:0.8,trend:0.9,score:0,reason:'Volume play — converts frequent users to committed. Strong repeat revenue.',push:'now',confidence:'high'},
  {id:'p-4',name:'Club Fitting Starter Pack',type:'service',margin:0.70,demand:0.6,seasonality:0.9,trend:0.7,score:0,reason:'Low-friction entry to fitting. Good for hesitant buyers.',push:'now',confidence:'medium'},
  {id:'p-5',name:'Junior Golf Bundle',type:'bundle',margin:0.55,demand:0.5,seasonality:0.7,trend:0.6,score:0,reason:'Seasonal — school holidays approaching. Parents buy during term start.',push:'next_week',confidence:'medium'},
  {id:'p-6',name:'Social Play (4 Players + Beer)',type:'service',margin:0.65,demand:0.9,seasonality:0.7,trend:0.8,score:0,reason:'Weekend groups — highest volume demand signal. Group bookings spike Fri/Sat.',push:'now',confidence:'high'},
  {id:'p-7',name:'Birdie Hunter Coaching',type:'coaching',margin:0.72,demand:0.55,seasonality:0.8,trend:0.7,score:0,reason:'High-intent coaching. Good for serious golfers ready to commit.',push:'now',confidence:'medium'},
  {id:'p-8',name:'Takomo Golf Gear',type:'product',margin:0.40,demand:0.4,seasonality:0.6,trend:0.5,score:0,reason:'Takomo clubs sell when fitting done. Post-fitting upsell. Not primary push.',push:'post_fitting',confidence:'low'},
];
products.forEach(p=>{p.score=Math.round(p.margin*p.demand*p.seasonality*p.trend*100)/100;});
products.sort((a,b)=>b.score-a.score);
const out={schema:'https://clawdia.io/agents/product-priority-engine/v1',generated:now.toISOString(),summary:{top_product:products[0].name,top_score:products[0].score,high_confidence:products.filter(p=>p.confidence==='high').length},products};
fs.writeFileSync(path.join(DATA,'product-priority.json'),JSON.stringify(out,null,2));
console.log('✅ Product priority engine: '+products.length+' products ranked');
products.slice(0,3).forEach(p=>console.log('   ['+p.score+'] '+p.name+' — '+p.reason.substring(0,50)));
