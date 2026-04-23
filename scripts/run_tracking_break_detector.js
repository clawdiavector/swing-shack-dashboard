const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Tracking break detector — flags broken attribution chains

const ig=r('ig-analytics.json')||{};
const utmGov=r('utm-governance.json')||{};
const bookEvents=r('booking-events.json')||{};
const bookClosure=r('booking-closure.json')||{};
const apiConn=r('api-connections.json')||{};

var breaks=[];

// Check 1: Missing UTM on posts
var posts=(ig.posts||[]);
var postsWithoutUtm=posts.filter(function(p){return!(p.utm_source||p.campaign);});
if(postsWithoutUtm.length>0){
  breaks.push({
    type:'MISSING_UTM',
    severity:'HIGH',
    count:postsWithoutUtm.length,
    example:postsWithoutUtm[0]?(postsWithoutUtm[0].hook||'').substring(0,40):'unknown',
    impact:'Post-to-session chain is broken. Sessions from these posts are untrackable.',
    fix:'Add UTM parameters with hook_id to all posts. Retro-tag existing posts.',
    automated_fix_possible:true,
  });
}

// Check 2: Missing hook_id in UTM content
var postsWithoutHookId=posts.filter(function(p){return!p.utm_content||p.utm_content.length<3||p.utm_content==='missing';});
if(postsWithoutHookId.length>0){
  breaks.push({
    type:'MISSING_HOOK_ID',
    severity:'HIGH',
    count:postsWithoutHookId.length,
    example:postsWithoutHookId[0]?(postsWithoutHookId[0].hook||'').substring(0,40):'unknown',
    impact:'Cannot link post to session. A/B testing impossible without hook-level attribution.',
    fix:'Add hook_id to utm_content param in all post links.',
    automated_fix_possible:true,
  });
}

// Check 3: Missing recommendation_id
var postsWithoutRecId=posts.filter(function(p){return!p.recommendation_id||p.recommendation_id==='missing';});
if(postsWithoutRecId.length>0){
  breaks.push({
    type:'MISSING_RECOMMENDATION_ID',
    severity:'MEDIUM',
    count:postsWithoutRecId.length,
    example:postsWithoutRecId[0]?(postsWithoutRecId[0].hook||'').substring(0,40):'unknown',
    impact:'Cannot link post to marketing decision. Recommendation quality cannot be measured.',
    fix:'Add recommendation_id to post metadata in Postiz.',
    automated_fix_possible:true,
  });
}

// Check 4: Booking event not firing
var bcEvent=(bookEvents.events||[]).filter(function(e){return e.event_id==='booking_completed';})[0];
if(bcEvent&&!bcEvent.current_measurable){
  breaks.push({
    type:'BOOKING_EVENT_NOT_FIRING',
    severity:'CRITICAL',
    count:1,
    example:'/book/confirmed page has no GA4 event',
    impact:'All revenue is untrackable. STRONG_PROXY cannot become VERIFIED_REVENUE.',
    fix:'Install booking_confirmation event on /book/confirmed by Swing Shack dev.',
    automated_fix_possible:false,
    owner:'Swing Shack dev',
  });
}

// Check 5: Broken source chain (GA4 has sessions but no UTM source)
var ga4Sources=(r('ga4-metrics.json')||{}).sources||[];
var sessionsWithoutSource=ga4Sources.filter(function(s){return!s.source||s.source==='(not set)';});
if(sessionsWithoutSource.length>0){
  breaks.push({
    type:'BROKEN_SOURCE_CHAIN',
    severity:'MEDIUM',
    count:sessionsWithoutSource.length,
    example:sessionsWithoutSource[0]?sessionsWithoutSource[0].sessions+' sessions with no source':'(not set)',
    impact:'Sessions come from somewhere but cannot be attributed. Unknown traffic = wasted budget.',
    fix:'Ensure all traffic sources are properly tagged with UTM parameters.',
    automated_fix_possible:false,
  });
}

// Check 6: WhatsApp API not connected (lead routing blocked)
var waConnected=apiConn.connections&&apiConn.connections.some(function(c){return c.api==='whatsapp_business'&&c.status==='connected';});
if(!waConnected){
  breaks.push({
    type:'WHATSAPP_NOT_CONNECTED',
    severity:'HIGH',
    count:1,
    example:'WhatsApp Business API not connected',
    impact:'Lead routing is simulated, not live. Hot leads are not reaching WhatsApp.',
    fix:'Connect WhatsApp Business API — this unblocks lead routing automation.',
    automated_fix_possible:false,
    owner:'Christelle',
  });
}

// Check 7: Meta token expired
var metaToken=(r('meta-auth-health.json')||{}).tokens||{};
if(metaToken.meta&&metaToken.meta.status==='CRITICAL'){
  breaks.push({
    type:'META_TOKEN_EXPIRED',
    severity:'HIGH',
    count:1,
    example:'Meta token '+metaToken.meta.age_hours+'h old — likely invalid',
    impact:'Meta Ads API calls will fail. Budget shifts cannot execute.',
    fix:'Reconnect Meta OAuth — generate new token via Meta Developer Console.',
    automated_fix_possible:false,
    owner:'Christelle',
  });
}

// Check 8: No service param in GA4
var ga4HasService=false;
var ga4Data=r('ga4-metrics.json')||{};
if(ga4Data.insights&&ga4Data.insights.service){
  ga4HasService=true;
}
if(!ga4HasService){
  breaks.push({
    type:'NO_SERVICE_PARAM',
    severity:'MEDIUM',
    count:1,
    example:'GA4 has no service dimension — booking value cannot be modelled by service',
    impact:'Value modelling is crude (avg basket). Service-specific ROI is invisible.',
    fix:'Add service_selected GA4 event + pass ?service=X in confirmation URL.',
    automated_fix_possible:false,
    owner:'Swing Shack dev',
  });
}

// Severity summary
var criticalBreaks=breaks.filter(function(b){return b.severity==='CRITICAL';}).length;
var highBreaks=breaks.filter(function(b){return b.severity==='HIGH';}).length;
var mediumBreaks=breaks.filter(function(b){return b.severity==='MEDIUM';}).length;
var automatedFixable=breaks.filter(function(b){return b.automated_fix_possible;}).length;
var needsHuman=breaks.filter(function(b){return!b.automated_fix_possible;}).length;

var topBlocker=breaks.filter(function(b){return b.severity==='CRITICAL';})[0]||breaks.filter(function(b){return b.severity==='HIGH';})[0]||null;

var out={
  schema:'https://clawdia.io/agents/tracking-break-detector/v1',
  generated:now.toISOString(),
  breaks:breaks,
  summary:{
    total_breaks:breaks.length,
    critical:criticalBreaks,
    high:highBreaks,
    medium:mediumBreaks,
    automated_fixable:automatedFixable,
    needs_human_action:needsHuman,
    top_blocker:topBlocker?(topBlocker.type+' — '+topBlocker.impact.substring(0,60)):'NONE',
    honest_note:'Tracking chain has '+breaks.length+' breaks. '+automatedFixable+' can be fixed by agent. '+needsHuman+' require human action (dev access or API reconnection).',
  },
  recommendations:[
    {priority:1,action:topBlocker?'Fix: '+topBlocker.type:'No critical breaks',why:topBlocker?'This is the single biggest blocker to revenue truth':'All critical issues resolved'},
    {priority:2,action:'Agent: Fix '+automatedFixable+' automated-fixable breaks now',why:'Agent can fix UTM compliance without requiring dev access'},
    {priority:3,action:'Christelle: Escalate '+needsHuman+' human-required breaks to respective owners',why:'These require dev access, API reconnection, or admin action'},
  ],
};
fs.writeFileSync(path.join(DATA,'tracking-breaks.json'),JSON.stringify(out,null,2));
console.log('✅ tracking_break_detector: '+breaks.length+' breaks detected');
console.log('   CRITICAL: '+criticalBreaks+' | HIGH: '+highBreaks+' | MEDIUM: '+mediumBreaks);
console.log('   Auto-fixable: '+automatedFixable+' | Human required: '+needsHuman);
console.log('   Top blocker: '+(topBlocker?topBlocker.type:'NONE'));
breaks.filter(function(b){return b.severity==='CRITICAL';}).forEach(function(b){console.log('   CRITICAL: '+b.type+' — '+b.impact.substring(0,60));});