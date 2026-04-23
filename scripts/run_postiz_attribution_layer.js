const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Postiz attribution layer — wire UTMs to published posts
// GA4 UTM structure: swingshack.co.za/?utm_source=instagram&utm_medium=social&utm_campaign=round4-slice-fix&utm_content=hook-j
const ig=r('ig-analytics.json')||{};
const rec=r('recommendation-scores.json')||{};
const ab=r('ab-winners.json')||{};
const published=r('published-posts.json')||{published:[]};

// Build UTM map for all published posts
const posts=ig.posts||[];
const utmMap=[];

posts.slice(0,20).forEach(post=>{
  // Determine UTM campaign based on service/recommendation
  const rec_id=post.recommendation_id||null;
  const hook_id=post.hook_id||null;
  const service=post.service||rec?.recommendations?.find(r=>r.id===rec_id)?.service||'unknown';
  const hook_text=post.hook||'';
  
  // Map CTA type to GA4 UTM medium
  let utm_medium='social';
  let utm_campaign='organic';
  let cta_type='none';
  
  if(post.approved){
    utm_medium='postiz';
    cta_type=hook_text.includes('R')?'pricing':'awareness';
    utm_campaign='round4-'+(hook_text.includes('SLICE')?'slice-fix':hook_text.includes('DRIVE')?'drive':hook_text.includes('PRO')?'premium':'general');
  }
  
  const utm_source=post.source||'instagram';
  const landing_page=post.landing_page||'https://swingshack.co.za/'+(service!=='unknown'?'?service='+service:'');
  
  // Build full UTM URL
  const utm_params=[
    'utm_source='+utm_source,
    'utm_medium='+utm_medium,
    'utm_campaign='+utm_campaign,
    'utm_content='+encodeURIComponent((hook_id||post.id||'unknown').substring(0,20))
  ].join('&');
  
  const utm_url=landing_page.includes('?')?landing_page+'&'+utm_params:landing_page+'?'+utm_params;
  
  utmMap.push({
    post_id:post.id||null,
    hook_id:hook_id,
    recommendation_id:rec_id,
    service,
    cta_type,
    hook_text:hook_text.substring(0,50),
    utm_source,
    utm_medium,
    utm_campaign,
    utm_content:(hook_id||post.id||'unknown').substring(0,20),
    landing_page,
    utm_url,
    attribution_confidence:rec_id&&hook_id?'STRONG_PROXY':'WEAK_PROXY',
    published_at:post.timestamp||null,
    ig_reach:post.reach||0,
    ig_likes:post.likeCount||0,
    ig_engagement:post.engagementRate||0,
  });
});

// Summary
const strongProxy=utmMap.filter(u=>u.attribution_confidence==='STRONG_PROXY').length;
const weakProxy=utmMap.filter(u=>u.attribution_confidence==='WEAK_PROXY').length;
const byService={};
utmMap.forEach(u=>{
  if(!byService[u.service])byService[u.service]={count:0,reach:0};
  byService[u.service].count++;
  byService[u.service].reach+=u.ig_reach||0;
});

const out={
  schema:'https://clawdia.io/agents/postiz-attribution-layer/v1',
  generated:now.toISOString(),
  summary:{total:utmMap.length,strong_proxy:strongProxy,weak_proxy:weakProxy,total_ig_reach:utmMap.reduce((s,u)=>s+(u.ig_reach||0),0)},
  by_service:byService,
  attribution_confidence:{strong_proxy:strongProxy+' posts have full hook_id+recommendation_id chain',weak_proxy:weakProxy+' posts have partial attribution — no recommendation_id linked'},
  utm_map:utmMap,
};
fs.writeFileSync(path.join(DATA,'post-attribution.json'),JSON.stringify(out,null,2));

// UTM map summary
const utmSummary={schema:'https://clawdia.io/agents/utm-map/v1',generated:now.toISOString(),summary:{total_posts:utmMap.length,posts_with_full_attribution:strongProxy,posts_with_proxy_attribution:weakProxy},services:Object.entries(byService).map(([svc,d])=>({service:svc,...d}))};
fs.writeFileSync(path.join(DATA,'utm-map.json'),JSON.stringify(utmSummary,null,2));
console.log('✅ postiz_attribution_layer: '+utmMap.length+' posts mapped');
console.log('   STRONG_PROXY: '+strongProxy+' | WEAK_PROXY: '+weakProxy+' | Total reach: '+out.summary.total_ig_reach+' views');
Object.entries(byService).slice(0,3).forEach(([svc,d])=>console.log('   '+svc+': '+d.count+' posts, '+d.reach+' reach'));
