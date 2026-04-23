const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Tracking implementation checklist — what must be built, what must be wired, what's blocked

const bookEvents=r('booking-events.json')||{events:[]};
const utmGov=r('utm-governance.json')||{};
const apiConn=r('api-connections.json')||{};

// What must be added ON SITE (requires Swing Shack dev)
const siteChanges=[
  {
    id:'SITE-001',
    priority:'P1',
    action:'Add booking_confirmation GA4 event on /book/confirmed page',
    params:['service','booking_value_proxy','utm_source','utm_medium','utm_campaign','hook_id','recommendation_id'],
    owner:'Swing Shack dev',
    effort:'low',
    blocks:['VERIFIED_REVENUE','VERIFIED_LEAD'],
    status:'NOT_STARTED',
    how:'gtag("event","booking_confirmation",{service,value,utm_source,utm_medium,utm_campaign,hook_id,recommendation_id})',
  },
  {
    id:'SITE-002',
    priority:'P1',
    action:'Pass service type through confirmation URL — add ?service=Full+Bag+Fitting to /book/confirmed',
    params:['service'],
    owner:'Swing Shack dev',
    effort:'low',
    blocks:['service_selected event','booking_value_proxy'],
    status:'NOT_STARTED',
    how:'Confirmation URL should include ?service=X from booking form selection',
  },
  {
    id:'SITE-003',
    priority:'P2',
    action:'Add GA4 event: service_selected — fire when user selects service type in booking form',
    params:['service','utm_source','utm_medium','utm_campaign'],
    owner:'Swing Shack dev',
    effort:'medium',
    blocks:['VERIFIED_LEAD'],
    status:'NOT_STARTED',
  },
  {
    id:'SITE-004',
    priority:'P2',
    action:'Add hook_id to UTM content param in Postiz — needs Postiz custom field support',
    params:['hook_id','recommendation_id'],
    owner:'Postiz config',
    effort:'medium',
    blocks:['attribution_chain'],
    status:'NOT_STARTED',
  },
];

// What must be added IN LINKS (can be done now via agent)
const linkChanges=[
  {id:'LINK-001',priority:'P1',action:'Retro-tag 20 existing IG posts with hook_id in utm_content',owner:'Agent',effort:'medium',status:'NOT_STARTED'},
  {id:'LINK-002',priority:'P1',action:'Enforce UTM on all new Postiz posts — source+medium+campaign+content mandatory',owner:'Agent',effort:'low',status:'NOT_STARTED'},
  {id:'LINK-003',priority:'P1',action:'Tag all Story links with UTM parameters',owner:'Agent',effort:'low',status:'NOT_STARTED'},
  {id:'LINK-004',priority:'P2',action:'Tag retargeting links with UTM',owner:'Agent',effort:'low',status:'NOT_STARTED'},
  {id:'LINK-005',priority:'P2',action:'Tag nurture/email links with UTM',owner:'Agent',effort:'medium',status:'NOT_STARTED'},
];

// What's blocked (waiting on external parties)
const blocked=[
  {id:'BLOCK-001',blocker:'WhatsApp Business API',action:'WhatsApp lead routing',waiting_since:'Phase 8B',days_waiting:0,priority:'P1'},
  {id:'BLOCK-002',blocker:'Meta OAuth server',action:'Meta Ads token refresh',waiting_since:'Phase 8B',days_waiting:0,priority:'P1'},
  {id:'BLOCK-003',blocker:'Swing Shack dev',action:'GA4 booking event implementation',waiting_since:'Phase 8D',days_waiting:0,priority:'P1'},
];

// Implementation roadmap
const roadmap=[
  {step:1,duration:'1 day',action:'Install GA4 tag on /book/confirmed page',owner:'Swing Shack dev',deliverable:'booking_confirmation event fires'},
  {step:2,duration:'2 hours',action:'Retro-tag 20 existing posts with hook_id',owner:'Agent',deliverable:'utm-governance compliance improves from 0%'},
  {step:3,duration:'1 day',action:'Pass service param through confirmation URL',owner:'Swing Shack dev',deliverable:'booking_value_proxy populated'},
  {step:4,duration:'1 week',action:'Postiz — add hook_id to UTM content field',owner:'Postiz config',deliverable:'All future posts carry hook_id'},
  {step:5,duration:'2 hours',action:'Validate full chain end-to-end',owner:'Agent',deliverable:'verification_promotion_engine upgrades sources'},
];

// Compliance status
var siteDone=siteChanges.filter(function(s){return s.status==='DONE';}).length;
var linkDone=linkChanges.filter(function(l){return l.status==='DONE';}).length;
var blockedCount=blocked.length;
var p1Site=siteChanges.filter(function(s){return s.priority==='P1';}).length;
var p1Link=linkChanges.filter(function(l){return l.priority==='P1';}).length;

var out={
  schema:'https://clawdia.io/agents/tracking-implementation-checklist/v1',
  generated:now.toISOString(),
  site_changes:siteChanges,
  link_changes:linkChanges,
  blocked:blocked,
  roadmap:roadmap,
  summary:{
    site_changes:siteChanges.length,
    link_changes:linkChanges.length,
    blocked:blocked.length,
    p1_critical:siteChanges.filter(function(s){return s.priority==='P1';}).length+linkChanges.filter(function(l){return l.priority==='P1';}).length,
    site_done:siteDone,
    link_done:linkDone,
    status:'WAITING ON SITE DEVELOPER',
    honest_note:'Agent can retro-tag posts and enforce future UTMs. GA4 event installation requires Swing Shack dev access.',
  },
  recommendations:[
    {priority:1,action:'Christelle: Get GA4 event installed on /book/confirmed page by Swing Shack dev — this is the single highest-value action',why:'Without this event, all revenue remains MODELLED. With it, STRONG_PROXY → VERIFIED_REVENUE.'},
    {priority:2,action:'Agent: Retro-tag 20 existing posts — begin immediately',why:'Starts building historical attribution while site changes are being built'},
    {priority:3,action:'Christelle: Ask Swing Shack to pass service param through confirmation URL',why:'Enables value modelling by service type'},
  ],
};
fs.writeFileSync(path.join(DATA,'tracking-implementation-checklist.json'),JSON.stringify(out,null,2));
console.log('✅ tracking_implementation_checklist: '+siteChanges.length+' site changes, '+linkChanges.length+' link changes');
console.log('   P1 critical: '+p1Site+' site + '+p1Link+' link = '+(p1Site+p1Link)+' total');
console.log('   Site: '+siteDone+'/'+siteChanges.length+' done | Link: '+linkDone+'/'+linkChanges.length+' done');
console.log('   BLOCKED: '+blockedCount+' (needs dev access)');
console.log('   First action: Retro-tag 20 posts (agent can do now)');
console.log('   Blocking action: booking_confirmation event (needs dev)');
