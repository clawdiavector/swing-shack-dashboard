const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function hashCode(s){var h=0;for(var i=0;i<s.length;i++){h=Math.imul(31,h)+s.charCodeAt(i)|0;}return h;}
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// UTM backfill builder — creates retro-tagging map for existing posts
// Not perfect attribution, but cleaner history

const ig=r('ig-analytics.json')||{};
const utmGov=r('utm-governance.json')||{};
const rec=r('recommendation-scores.json')||{};
const bookEvents=r('booking-events.json')||{events:[]};

const posts=(ig.posts||[]).slice(0,30);

// For each post — determine what backfill is needed and possible
var backfillMap=posts.map(function(p){
  var hook=(p.hook||'');
  var hookId=(p.hook_id||('h'+Math.abs(hashCode(hook.substring(0,20)))%100000).toString()).substring(0,10);
  var recId=p.recommendation_id||'unknown';
  var hasUtm=!!(p.utm_source||p.campaign);
  var hasHookId=!!(p.utm_content&&p.utm_content.length>5);
  var hasRecId=!!(p.recommendation_id);
  
  // Determine service from hook text
  var svc='Practice Session';
  if(hook.toLowerCase().includes('fitting')||hook.toLowerCase().includes('club'))svc='Full Bag Fitting';
  else if(hook.toLowerCase().includes('tpi')||hook.toLowerCase().includes('assessment'))svc='TPI Assessment';
  else if(hook.toLowerCase().includes('coaching')||hook.toLowerCase().includes('lesson'))svc='Coaching';
  else if(hook.toLowerCase().includes('membership')||hook.toLowerCase().includes('member'))svc='Membership';
  else if(hook.toLowerCase().includes('birdie')||hook.toLowerCase().includes('pro'))svc='Birdie Hunter';
  
  // Campaign name from service
  var campaignMap={
    'Full Bag Fitting':'fitting-full-bag',
    'TPI Assessment':'coaching-tpi',
    'Coaching':'coaching-lessons',
    'Birdie Hunter':'coaching-birdie-hunter',
    'Practice Session':'practice-session',
    'Membership':'membership',
  };
  var campaign=campaignMap[svc]||'general';
  
  // Build corrected UTM URL
  var base='https://swingshack.co.za/';
  var svcParam='?service='+encodeURIComponent(svc);
  var utmStr='utm_source=instagram&utm_medium=social&utm_campaign='+campaign+'&utm_content='+hookId;
  var correctedUrl=base+svcParam+'&'+utmStr;
  
  // Quality of backfill
  var quality='PARTIAL';
  if(!hasUtm){
    quality='RECOVERABLE'; // was never tagged — can tag now with good guess
  } else if(hasHookId){
    quality='GOOD'; // has UTM with hook_id
  } else {
    quality='PARTIAL'; // has UTM but no hook_id — can improve
  }
  
  // What needs fixing
  var fixes=[];
  if(!hasUtm)fixes.push('ADD_UTMS');
  if(!hasHookId)fixes.push('ADD_HOOK_ID');
  if(!hasRecId)fixes.push('ADD_RECOMMENDATION_ID');
  if(p.utm_medium&&p.utm_medium.includes('postiz_auto'))fixes.push('REMOVE_POSTIZ_AUTO');
  
  return{
    post_id:p.id||'unknown',
    hook:hook.substring(0,40),
    hook_id:hookId,
    recommendation_id:recId,
    service:svc,
    current_utm:{
      source:p.utm_source||'missing',
      medium:p.utm_medium||'missing',
      campaign:p.utm_campaign||'missing',
      content:p.utm_content||'missing',
    },
    corrected_utm:{
      source:'instagram',
      medium:'social',
      campaign:campaign,
      content:hookId,
    },
    corrected_url:correctedUrl,
    backfill_quality:quality,
    fixes_needed:fixes,
    effort:fixes.length<=1?'LOW':fixes.length<=2?'MEDIUM':'HIGH',
    timestamp:p.timestamp||null,
    reach:p.reach||0,
    engagement:p.engagementRate||0,
  };
});

// Summary
var total=backfillMap.length;
var good=backfillMap.filter(function(p){return p.backfill_quality==='GOOD';}).length;
var partial=backfillMap.filter(function(p){return p.backfill_quality==='PARTIAL';}).length;
var recoverable=backfillMap.filter(function(p){return p.backfill_quality==='RECOVERABLE';}).length;
var needsTagging=backfillMap.filter(function(p){return p.fixes_needed.includes('ADD_UTMS');}).length;
var withHookId=backfillMap.filter(function(p){return!p.fixes_needed.includes('ADD_HOOK_ID');}).length;
var totalReach=backfillMap.reduce(function(s,p){return s+(p.reach||0);},0);

var out={
  schema:'https://clawdia.io/agents/utm-backfill-builder/v1',
  generated:now.toISOString(),
  backfill_map:backfillMap,
  summary:{
    total_posts:total,
    good_quality:good,
    partial_quality:partial,
    recoverable:recoverable,
    needs_tagging:needsTagging,
    with_hook_id:withHookId,
    without_hook_id:total-withHookId,
    total_reach_affected:totalReach,
    honest_note:'Backfill quality is PARTIAL or RECOVERABLE for most posts — hook_id and recommendation_id are best-guessed from post metadata, not from actual tracking.',
  },
  recommendations:[
    {priority:1,action:'Tag '+(needsTagging)+' posts with corrected UTMs — add hook_id to utm_content',why:'Starts building attribution history now while GA4 event is being built'},
    {priority:2,action:'Add recommendation_id where identifiable from post content',why:'Closes the chain further — recommendation links posts to specific marketing decision'},
    {priority:3,action:'Prioritise high-reach posts for backfill — '+(backfillMap.sort(function(a,b){return b.reach-a.reach;}).slice(0,5).reduce(function(s,p){return s+p.reach;},0))+' reach in top 5 posts',why:'Most impact on overall attribution quality'},
  ],
};
fs.writeFileSync(path.join(DATA,'utm-backfill.json'),JSON.stringify(out,null,2));
console.log('✅ utm_backfill_builder: '+total+' posts mapped for backfill');
console.log('   GOOD: '+good+' | PARTIAL: '+partial+' | RECOVERABLE: '+recoverable+' | Needs tagging: '+needsTagging);
console.log('   With hook_id: '+withHookId+' | Without: '+(total-withHookId)+' | Total reach affected: '+totalReach);
console.log('   Honest: Most backfill is PARTIAL — best-guessed service + hook_id, not real tracking');
EOF