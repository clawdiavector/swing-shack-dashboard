const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

const pubLog=r('live-publish-log.json')||{};
const budgetAct=r('budget-actions.json')||{};
const leadLog=r('lead-routing-log.json')||{};
const lm=r('live-mode.json')||{};
const mode=(lm.modes&&lm.modes.current)||'OFF';

const capabilities=[
  {
    id:'discord_nudge',name:'Discord Nudges',
    sent:((pubLog.actions)||[]).filter(function(a){return a.type==='discord_nudge'&&a.status==='sent';}).length,
    acted_on:0,
    prevented_miss:0,
    value:'unknown',
    useful:null,
    notes:'Webhook feedback not connected - cannot measure acted_on rate yet',
  },
  {
    id:'fallback_swap',name:'Fallback Swaps',
    used:((pubLog.actions)||[]).filter(function(a){return a.type==='fallback_swap';}).length,
    prevented_miss:0,
    value:'unknown',
    useful:null,
    notes:'No A/B winner tracking yet - swap effectiveness unknown',
  },
  {
    id:'low_risk_publish',name:'Low-Risk Publishing',
    published:((pubLog.actions)||[]).filter(function(a){return a.type==='low_risk_publish'&&a.status==='posted';}).length,
    reach:0,engagement:0,
    value:'unknown',
    useful:null,
    notes:'Postiz integration not connected - cannot measure reach/engagement yet',
  },
  {
    id:'lead_routing',name:'Lead Routing',
    routed:((leadLog.actions)||[]).filter(function(a){return a.status==='sent'||a.status==='queued';}).length,
    hot:((leadLog.actions)||[]).filter(function(a){return a.type==='route_whatsapp';}).length,
    converted:0,
    sla_met:0,sla_missed:0,
    value:'unknown',
    useful:null,
    notes:'WhatsApp Business API not connected - routing is simulated, no real leads yet',
  },
  {
    id:'tiny_ad_shift',name:'Budget Shifts',
    shifts:((budgetAct.actions)||[]).filter(function(a){return a.status==='recommended'||a.status==='applied';}).length,
    amount_r:((budgetAct.actions)||[]).reduce(function(s,a){return s+(a.amount||0);},0),
    roas_change:0,
    value:'unknown',
    useful:null,
    notes:'Meta Ads API not connected - budget shifts are placeholder',
  },
  {
    id:'review_thank_you',name:'Review Thank-Yous',
    posted:0,
    drafted:0,
    value:'medium',
    useful:true,
    notes:'Google Business API not connected - posting is simulated. Safe to expand manually.',
  },
];

const verdict=capabilities.map(function(c){
  var hasData=c.value!=='unknown';
  var isActive=c.sent||c.used||c.published||c.routed||c.shifts||c.posted||c.drafted;
  return {id:c.id,name:c.name,has_data:hasData,is_active:isActive>0,verdict:!hasData?'NO_DATA':isActive===0?'NOT_ACTIVE':'REQUIRES_PROOF'};
});

var recommendations=[];
verdict.forEach(function(c){
  if(c.value==='unknown'&&c.is_active){
    recommendations.push({priority:1,capability:c.id,action:'Connect '+c.name+' to real data - cannot measure value without it',why:'Autonomy without measurement is just busywork'});
  }
  if(c.id==='review_thank_you'&&c.useful===true){
    recommendations.push({priority:3,capability:c.id,action:'Expand review thank-yous - high value, low risk',why:'5-star thank-yous are safe and build Google reputation'});
  }
});

var totalActive=verdict.filter(function(c){return c.is_active;}).length;
var provenUseful=verdict.filter(function(c){return c.useful===true;}).length;

var out={
  schema:'https://clawdia.io/agents/autonomy-performance-reporter/v1',
  generated:now.toISOString(),
  mode:mode,
  capabilities:capabilities,
  summary:{
    total:capabilities.length,
    with_data:verdict.filter(function(c){return c.has_data;}).length,
    active:totalActive,
    proven_useful:provenUseful,
    no_data:verdict.filter(function(c){return c.value==='unknown';}).length,
    verdict:'Autonomy is RUNNING but not MEASURED yet - connect real APIs to prove value',
  },
  recommendations:recommendations,
  honest_note:'All value metrics are unknown until Postiz, Meta Ads, WhatsApp Business, and Google Business APIs are connected.',
};
fs.writeFileSync(path.join(DATA,'autonomy-performance.json'),JSON.stringify(out,null,2));
console.log(' autonomy_performance_reporter: '+verdict.length+' capabilities');
verdict.forEach(function(c){console.log('   '+c.name+': '+c.verdict+(c.is_active?' (active)':''));});
console.log('   Verdict: '+out.summary.verdict);
