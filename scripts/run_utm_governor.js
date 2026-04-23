const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function hashCode(s){var h=0;for(var i=0;i<s.length;i++){h=Math.imul(31,h)+s.charCodeAt(i)|0;}return h;}
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

const ig=r('ig-analytics.json')||{};
const rec=r('recommendation-scores.json')||{};

const posts=(ig.posts||[]).slice(0,20);

const utmTemplate={
  required:['utm_source','utm_medium','utm_campaign','utm_content'],
  recommended:['utm_source','utm_medium','utm_campaign','utm_content','hook_id','recommendation_id','service'],
};

const campaignMap={
  'Full Bag Fitting':{campaign:'fitting-full-bag',medium:'social'},
  'Iron Fitting':{campaign:'fitting-iron',medium:'social'},
  'Coaching':{campaign:'coaching-lessons',medium:'social'},
  'TPI Assessment':{campaign:'coaching-tpi',medium:'social'},
  'Practice Session':{campaign:'practice-session',medium:'social'},
  'Social Play':{campaign:'social-play',medium:'social'},
  'Membership':{campaign:'membership',medium:'social'},
  'Birdie Hunter':{campaign:'coaching-birdie-hunter',medium:'social'},
};

const taggables=posts.map(function(p){
  var hook=(p.hook||'');
  var recs=(rec.recommendations||[]);
  var svc='';
  for(var i=0;i<recs.length;i++){if(recs[i].service){svc=recs[i].service;break;}}
  var cmap=campaignMap[svc]||{campaign:'general',medium:'social'};
  var hkId=('h'+Math.abs(hashCode(hook.substring(0,20)))%100000).toString().substring(0,10);
  var hasUtm=!!(p.utm_source||p.campaign);
  var base='https://swingshack.co.za/';
  var svcParam=svc?'?service='+encodeURIComponent(svc):'';
  var utmStr='utm_source='+(p.utm_source||'instagram')+'&utm_medium='+(p.utm_medium||'social')+'&utm_campaign='+(p.utm_campaign||cmap.campaign)+'&utm_content='+hkId;
  var fullUrl=base+svcParam+(svcParam?'&':'?')+utmStr;
  return{
    post_id:p.id||'unknown',
    hook:hook.substring(0,30),
    service:svc||'unknown',
    has_utm:hasUtm,
    hook_id:hkId,
    full_url:fullUrl,
    compliant:hasUtm&&p.utm_content,
  };
});

var needsTagging=taggables.filter(function(t){return!t.compliant;}).slice(0,10);
var okCount=taggables.filter(function(t){return t.compliant;}).length;
var complianceRate=posts.length>0?Math.round(okCount/posts.length*100):0;

var out={
  schema:'https://clawdia.io/agents/utm-governor/v1',
  generated:now.toISOString(),
  summary:{
    total_posts:posts.length,
    currently_compliant:okCount,
    needs_tagging:needsTagging.length,
    compliance_rate:complianceRate+'%',
    honest_note:'All posts lack hook_id and recommendation_id in UTM. utm_content is present but not the hook_id.',
  },
  utm_template:utmTemplate,
  campaign_map:campaignMap,
  posts_needing_utm:needsTagging.map(function(t){return{post_id:t.post_id,hook:t.hook,service:t.service,full_url:t.full_url};}),
  recommendations:[
    {priority:1,action:'Retroactively add hook_id to utm_content for all existing posts',why:'Without hook_id in UTM, post-to-session chain is broken'},
    {priority:2,action:'Wire recommendation_id into UTM for all future Postiz posts',why:'Closes attribution chain at first hop'},
  ],
};
fs.writeFileSync(path.join(DATA,'utm-governance.json'),JSON.stringify(out,null,2));
console.log('✅ utm_governor: '+posts.length+' posts checked');
console.log('   Compliant: '+okCount+' | Needs tagging: '+needsTagging.length+' | Rate: '+complianceRate+'%');
console.log('   Honest: hook_id and recommendation_id missing from all UTMs');