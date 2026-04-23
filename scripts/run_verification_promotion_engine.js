const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Verification promotion engine — upgrade sources as tracking improves
// UNKNOWN → WEAK_PROXY → STRONG_PROXY → VERIFIED_LEAD → VERIFIED_REVENUE

const convTruth=r('conversion-truth.json')||{};
const apiConn=r('api-connections.json')||{};
const bookEvents=r('booking-events.json')||{};
const utmGov=r('utm-governance.json')||{};
const eventVal=r('event-validation.json')||{};

// Current state of each tracking element
var bookingEventFiring=eventVal&&eventVal.summary?eventVal.summary.booking_event_firing==='FIRING':false;
var utmCompliance=(parseInt((utmGov.summary||{}).compliance_rate)||0);
var waConnected=(apiConn.connections||[]).some(function(c){return c.api==='whatsapp_business'&&c.status==='connected';});
var metaConnected=(apiConn.connections||[]).some(function(c){return c.api==='meta_ads'&&c.status==='connected';});
var hookIdInUtm=utmCompliance>50; // if >50% of posts have hook_id, we consider it "present"

// Current conversions from GA4
var ga4=(r('ga4-metrics.json')||{});
var totalSessions=(ga4.sources||[]).reduce(function(s,x){return s+(x.sessions||0);},0);

// What can be promoted based on what's actually implemented
var sources=convTruth.reclassified||convTruth.sources||[];

var promoted=sources.map(function(s){
  var oldBand=s.new_band||s.can_measure||'UNKNOWN';
  var newBand=oldBand;
  var promotionReason='';
  var promotionAction='';
  
  // Check what's actually been implemented
  if(oldBand==='UNKNOWN'&&s.source==='lead_routing'){
    if(waConnected){
      newBand='VERIFIED_LEAD';
      promotionReason='WhatsApp API now connected — can track message leads';
      promotionAction='WhatsApp routing now live — leads are trackable';
    } else {
      newBand='WEAK_PROXY';
      promotionReason='WhatsApp not connected but UTM chain exists';
      promotionAction='Connect WhatsApp API to upgrade to VERIFIED_LEAD';
    }
  } else if(oldBand==='UNKNOWN'&&s.source==='tiny_ad_shift'){
    if(metaConnected){
      newBand='STRONG_PROXY';
      promotionReason='Meta Ads API now connected';
      promotionAction='Meta Ads connected — budget shifts can execute with tracking';
    } else if(hookIdInUtm){
      newBand='WEAK_PROXY';
      promotionReason='UTM chain exists even without Meta API';
      promotionAction='Hook ID in UTM enables some attribution';
    }
  } else if(oldBand==='STRONG_PROXY'&&bookingEventFiring){
    newBand='VERIFIED_REVENUE';
    promotionReason='booking_confirmation event is now firing in GA4';
    promotionAction='VERIFIED_REVENUE achieved — revenue is now traceable';
  } else if(oldBand==='STRONG_PROXY'&&!bookingEventFiring&&hookIdInUtm){
    newBand='STRONG_PROXY';
    promotionReason='UTM with hook_id is present — but no booking event yet';
    promotionAction='Add booking_confirmation event to upgrade to VERIFIED_REVENUE';
  } else if(oldBand==='WEAK_PROXY'&&hookIdInUtm){
    newBand='STRONG_PROXY';
    promotionReason='hook_id in UTM strengthens attribution chain';
    promotionAction='Hook-level attribution now possible — upgrade to STRONG_PROXY';
  } else if(oldBand==='VERIFIED_LEAD'&&bookingEventFiring){
    newBand='VERIFIED_REVENUE';
    promotionReason='Booking confirmation event now firing — leads can be traced to revenue';
    promotionAction='VERIFIED_REVENUE achieved — booking event closes the loop';
  }
  
  var promoted=oldBand!==newBand;
  return{
    source:s.source,
    name:s.name,
    old_band:oldBand,
    new_band:newBand,
    promoted:promoted,
    promotion_reason:promotionReason||(promoted?'Upgraded':'No change'),
    promotion_action:promotionAction||'',
    confidence:s.confidence||50,
    automation_rights:newBand==='VERIFIED_REVENUE'||newBand==='VERIFIED_LEAD'?'ALLOWED':newBand==='STRONG_PROXY'?'CONDITIONAL':'MANUAL_ONLY',
  };
});

// Current implementation status
var implementationStatus={
  booking_event_firing:bookingEventFiring,
  utm_compliance_rate:utmCompliance+'%',
  hook_id_in_utm:hookIdInUtm,
  whatsapp_connected:waConnected,
  meta_connected:metaConnected,
};

// Summary
var verifiedRevenue=promoted.filter(function(p){return p.new_band==='VERIFIED_REVENUE';}).length;
var verifiedLead=promoted.filter(function(p){return p.new_band==='VERIFIED_LEAD';}).length;
var strongProxy=promoted.filter(function(p){return p.new_band==='STRONG_PROXY';}).length;
var weakProxy=promoted.filter(function(p){return p.new_band==='WEAK_PROXY';}).length;
var unknown=promoted.filter(function(p){return p.new_band==='UNKNOWN';}).length;
var newlyPromoted=promoted.filter(function(p){return p.promoted;}).length;

var nextPromotions=[];
if(!bookingEventFiring){
  nextPromotions.push({trigger:'booking_confirmation event fires',current:'STRONG_PROXY',upgrades_to:'VERIFIED_REVENUE',sources_affected:strongProxy});
}
if(!waConnected){
  nextPromotions.push({trigger:'WhatsApp API connects',current:'UNKNOWN (lead_routing)',upgrades_to:'VERIFIED_LEAD',sources_affected:1});
}
if(utmCompliance<80){
  nextPromotions.push({trigger:'UTM compliance reaches 80%+',current:'WEAK_PROXY',upgrades_to:'STRONG_PROXY',sources_affected:weakProxy});
}

var out={
  schema:'https://clawdia.io/agents/verification-promotion-engine/v1',
  generated:now.toISOString(),
  sources:promoted,
  implementation_status:implementationStatus,
  summary:{
    total:sources.length,
    verified_revenue:verifiedRevenue,
    verified_lead:verifiedLead,
    strong_proxy:strongProxy,
    weak_proxy:weakProxy,
    unknown:unknown,
    newly_promoted:newlyPromoted,
    honest_note:'Promotion requires actual tracking implementation — not just agent logic. booking_event_firing=false means no promotion to VERIFIED_REVENUE is possible yet.',
  },
  next_promotions:nextPromotions,
  recommendations:[
    {priority:1,action:'Get booking_confirmation event firing → upgrades STRONG_PROXY → VERIFIED_REVENUE',why:'This is the single promotion that changes the whole dashboard from MODELLED to VERIFIED'},
    {priority:2,action:'Connect WhatsApp API → upgrades lead_routing UNKNOWN → VERIFIED_LEAD',why:'Completes the social → booking loop for high-intent leads'},
    {priority:3,action:'Retrogate posts to 80%+ UTM compliance → upgrades WEAK_PROXY → STRONG_PROXY',why:'Hook-level attribution improves measurement quality for all channels'},
  ],
};
fs.writeFileSync(path.join(DATA,'verification-promotions.json'),JSON.stringify(out,null,2));
console.log('✅ verification_promotion_engine: '+sources.length+' sources checked');
console.log('   VERIFIED_REVENUE: '+verifiedRevenue+' | VERIFIED_LEAD: '+verifiedLead+' | STRONG: '+strongProxy+' | WEAK: '+weakProxy+' | UNKNOWN: '+unknown);
console.log('   Newly promoted: '+newlyPromoted+' | Implementation status: booking='+bookingEventFiring+' WA='+waConnected+' Meta='+metaConnected);
console.log('   Next: '+nextPromotions.length+' promotions available when tracking improves');
nextPromotions.forEach(function(p){console.log('   +: '+p.current+' → '+p.upgrades_to+' when '+p.trigger);});
console.log('   Honest: No VERIFIED_REVENUE possible until booking_confirmation event fires');