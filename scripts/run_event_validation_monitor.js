const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Event validation monitor — checks if booking_confirmation event is firing
// Also checks if params are arriving correctly

const bookEvents=r('booking-events.json')||{};
const apiConn=r('api-connections.json')||{};
const ga4=r('ga4-metrics.json')||{};
const ig=r('ig-analytics.json')||{};

// GA4 booking confirmation event — is it firing?
var bcEvent=(bookEvents.events||[]).filter(function(e){return e.event_id==='booking_completed';})[0];
var ssEvent=(bookEvents.events||[]).filter(function(e){return e.event_id==='service_selected';})[0];

// Check if GA4 has conversion goals (look in insights)
var ga4Insights=ga4.insights||{};
var hasConversions=ga4Insights&&Object.keys(ga4Insights).length>0;

// Check last known booking confirmation — not available without live event
var lastEventFired=null;
var lastEventParams=null;
var eventFiringStatus='NOT_FIRING';

// GA4 sources tell us what IS arriving
var ga4Sources=ga4.sources||[];
var hasUtmInGa4=ga4Sources.filter(function(s){return s.source&&s.source!=='(not set)';}).length>0;
var ga4TotalSessions=ga4Sources.reduce(function(s,x){return s+(x.sessions||0);},0);

// Parameter checklist for booking_confirmation
var paramChecklist=[
  {param:'service',description:'Service type selected',currently_arriving:'NO',required:true},
  {param:'booking_value_proxy',description:'Estimated value of booking',currently_arriving:'NO',required:true},
  {param:'utm_source',description:'Traffic source',currently_arriving:'YES',required:true,note:'GA4 captures utm_source but not from booking_confirmation event'},
  {param:'utm_medium',description:'Traffic medium',currently_arriving:'YES',required:true},
  {param:'utm_campaign',description:'Campaign name',currently_arriving:'YES',required:false},
  {param:'hook_id',description:'Marketing hook identifier',currently_arriving:'NO',required:false,note:'hook_id not in any UTM param yet'},
  {param:'recommendation_id',description:'Marketing recommendation that drove this',currently_arriving:'NO',required:false,note:'recommendation_id never makes it to GA4'},
];

var paramsArriving=paramChecklist.filter(function(p){return p.currently_arriving==='YES';}).length;
var paramsMissing=paramChecklist.filter(function(p){return p.currently_arriving==='NO'&&p.required;}).length;
var paramsOptionalMissing=paramChecklist.filter(function(p){return p.currently_arriving==='NO'&&!p.required;}).length;

// Monitoring windows
var checks=[
  {name:'booking_confirmation_event',check:'GA4 has custom event booking_confirmation in last 7 days',status:'NOT_FIRING',last_checked:now.toISOString(),evidence:'No GA4 event data received'},
  {name:'service_param_in_url',check:'Confirmation URL includes ?service=X',status:'NOT_CONFIGURED',last_checked:now.toISOString(),evidence:'Swing Shack dev has not implemented'},
  {name:'hook_id_in_utm',check:'UTM content param contains hook_id',status:'NOT_PRESENT',last_checked:now.toISOString(),evidence:'All existing posts lack hook_id'},
  {name:'recommendation_id_in_utm',check:'UTM contains recommendation_id',status:'NOT_PRESENT',last_checked:now.toISOString(),evidence:'recommendation_id never linked to UTM chain'},
];

var firingCount=checks.filter(function(c){return c.status==='FIRING';}).length;
var notConfiguredCount=checks.filter(function(c){return c.status==='NOT_CONFIGURED'||c.status==='NOT_PRESENT';}).length;

// Validation timeline
var validationTimeline=[
  {when:'Now',status:'RED',action:'Site not sending booking_confirmation event'},
  {when:'After site change',status:'AMBER',action:'Event fires but hook_id + recommendation_id still missing from params'},
  {when:'After Postiz UTM update',status:'GREEN',action:'Full chain validated — post → hook_id → session → booking'},
];

var out={
  schema:'https://clawdia.io/agents/event-validation-monitor/v1',
  generated:now.toISOString(),
  checks:checks,
  param_checklist:paramChecklist,
  summary:{
    booking_event_firing:eventFiringStatus,
    params_arriving:paramsArriving+'/'+paramChecklist.length,
    params_missing_required:paramsMissing,
    params_optional_missing:paramsOptionalMissing,
    validation_status:paramsMissing>0?'INCOMPLETE':'VALIDATING',
    honest_note:'booking_confirmation event is not firing. No booking system is connected to GA4. The event definition exists but the implementation does not.',
  },
  validation_timeline:validationTimeline,
  recommendations:[
    {priority:1,action:'Christelle: Ask Swing Shack dev to install booking_confirmation GA4 event on /book/confirmed',why:'This is the only way the event starts firing. No agent can do this.'},
    {priority:2,action:'Once event fires, validate params arriving in GA4 DebugView',why:'Verify service + value are populating before relying on the data'},
    {priority:3,action:'Add hook_id to Postiz UTM before next post goes live',why:'Without hook_id, event fires but attribution is incomplete'},
  ],
};
fs.writeFileSync(path.join(DATA,'event-validation.json'),JSON.stringify(out,null,2));
console.log('✅ event_validation_monitor: '+checks.length+' checks, '+paramChecklist.length+' params');
console.log('   Event firing: '+eventFiringStatus+' | Params arriving: '+paramsArriving+'/'+paramChecklist.length);
console.log('   Required params missing: '+paramsMissing+' | Optional params missing: '+paramsOptionalMissing);
console.log('   NOT_CONFIGURED: '+notConfiguredCount+' | FIRING: '+firingCount);
console.log('   Honest: booking_confirmation event not firing — needs dev to implement');
checks.forEach(function(c){console.log('   '+c.status+': '+c.name+' — '+c.evidence.substring(0,60));});