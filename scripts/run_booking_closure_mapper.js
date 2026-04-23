const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// GA4 has: sources=[{source:'google',sessions:638},{source:'(direct)',sessions:225}]
// Map GA4 source → service intent → booking proxy
const ga4=r('ga4-metrics.json')||{};
const ig=r('ig-analytics.json')||{};
const conv=r('conversion-attribution.json')||{};
const attr=r('post-attribution.json')||{};
const rec=r('recommendation-scores.json')||{};

// Source → service mapping based on UTM data from GA4
const sourceServiceMap={
  'instagram':{service:'Practice Session',intent:'MEDIUM',price:250,landing:'/book'},
  'facebook':{service:'Social Play',intent:'MEDIUM',price:450,landing:'/social-play'},
  'google':{service:'Coaching',intent:'HIGH',price:850,landing:'/coaching'},
  '(direct)':{service:'Practice Session',intent:'MEDIUM',price:250,landing:'/'},
  'meta':{service:'Social Play',intent:'MEDIUM',price:450,landing:'/social-play'},
};

const sources=(ga4.sources||[]).slice(0,15);
const closureMap=sources.map(function(s){
  var srcName=(s.source||'').toLowerCase();
  var svc=sourceServiceMap[srcName]||{service:'Practice Session',intent:'MEDIUM',price:250,landing:'/book'};
  var utmPosts=(attr.utm_map||[]).filter(function(u){return(srcName.includes(u.utm_source)||srcName.includes(u.utm_medium));}).slice(0,3);
  var hookIds=utmPosts.map(function(p){return p.hook_id;}).filter(Boolean);
  var recommendations=utmPosts.map(function(p){return p.recommendation_id;}).filter(Boolean);
  var hasAttribution=hookIds.length>0||recommendations.length>0;
  return{
    source:srcName,
    sessions:s.sessions||0,
    service:svc.service,
    service_intent:svc.intent,
    landing_page:svc.landing,
    price:svc.price,
    hook_ids:hookIds,
    recommendation_ids:recommendations,
    attribution_confidence:hasAttribution&&hookIds.length>0?'STRONG_PROXY':hasAttribution?'WEAK_PROXY':'UNMEASURABLE',
    estimated_booking_proxy:Math.round((s.sessions||0)*0.01*svc.price),
  };
});

// Summary
var strongProxy=closureMap.filter(function(c){return c.attribution_confidence==='STRONG_PROXY';});
var weakProxy=closureMap.filter(function(c){return c.attribution_confidence==='WEAK_PROXY';});
var unmeas=closureMap.filter(function(c){return c.attribution_confidence==='UNMEASURABLE';});
var totalSessions=closureMap.reduce(function(s,c){return s+(c.sessions||0);},0);
var estimatedRevenue=closureMap.reduce(function(s,c){return s+(c.estimated_booking_proxy||0);},0);

// Top posts from IG
var igPosts=(ig.posts||[]).filter(function(p){return(p.reach||0)>0;});
var topPosts=igPosts.sort(function(a,b){return(b.reach||0)-(a.reach||0);}).slice(0,3).map(function(p){
  return{reach:p.reach||0,engagement:p.engagementRate||0,hook:(p.hook||'').substring(0,40)};
});

var recommendations=[];
if(unmeas.length>closureMap.length*0.5){
  recommendations.push({priority:1,action:'Add UTM tracking to all Postiz posts — link to GA4 sessions',why:'Most sessions are unattributed. Need hook_id in UTM content param.'});
}
if(strongProxy.length===0){
  recommendations.push({priority:2,action:'Connect GA4 → Postiz attribution — link posts to sessions via UTM',why:'No STRONG_PROXY chain exists. All attribution is WEAK_PROXY or UNMEASURABLE.'});
}

var out={
  schema:'https://clawdia.io/agents/booking-closure-mapper/v1',
  generated:now.toISOString(),
  summary:{
    total_sources:closureMap.length,
    strong_proxy:strongProxy.length,
    weak_proxy:weakProxy.length,
    unmeasurable:unmeas.length,
    total_sessions:totalSessions,
    estimated_revenue_proxy:estimatedRevenue,
    honest_note:'Estimated revenue is SESSIONS × 1% conversion × service price. This is a guess. Real booking data requires GA4 → booking system integration.',
  },
  closure_map:closureMap,
  top_posts:topPosts,
  recommendations:recommendations,
};
fs.writeFileSync(path.join(DATA,'booking-closure.json'),JSON.stringify(out,null,2));
console.log('✅ booking_closure_mapper: '+closureMap.length+' sources mapped');
console.log('   STRONG_PROXY: '+strongProxy.length+' | WEAK_PROXY: '+weakProxy.length+' | UNMEASURABLE: '+unmeas.length);
console.log('   Total sessions: '+totalSessions+' | Estimated revenue proxy: R'+estimatedRevenue);
strongProxy.slice(0,2).forEach(function(c){console.log('   STRONG: '+c.source+' -> '+c.service+' ('+c.sessions+' sessions)');});
