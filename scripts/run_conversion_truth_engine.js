const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Conversion truth engine — reclassify ROI with bands:
// VERIFIED_REVENUE, VERIFIED_LEAD, STRONG_PROXY, WEAK_PROXY, UNKNOWN

const roiTruth=r('roi-truth.json')||{};
const bookingEvents=r('booking-events.json')||{};
const apiConn=r('api-connections.json')||{};

var sources=roiTruth.sources||[];

// Reclassify each source based on booking event availability
var reclassified=sources.map(function(s){
  var band=s.can_measure||'UNKNOWN';
  var events=bookingEvents.events||[];
  
  // Check if booking_completed event is measurable
  var bcEvent=events.filter(function(e){return e.event_id==='booking_completed';})[0];
  var serviceEvent=events.filter(function(e){return e.event_id==='service_selected';})[0];
  
  var bookingEventLive=bcEvent&&bcEvent.current_measurable;
  var serviceEventLive=serviceEvent&&serviceEvent.current_measurable;
  
  // Reclassify
  var newBand=band;
  var confidence=50;
  var reason='';
  
  if(band==='DIRECT'){
    newBand='VERIFIED_REVENUE';
    confidence=95;
    reason='Booking confirmation connected to GA4';
  } else if(band==='STRONG_PROXY'){
    if(bookingEventLive){
      newBand='VERIFIED_REVENUE';
      confidence=80;
      reason='Booking event now trackable — STRONG_PROXY upgrades to VERIFIED_REVENUE';
    } else if(serviceEventLive){
      newBand='VERIFIED_LEAD';
      confidence=70;
      reason='Service selection trackable but not booking confirmation';
    } else {
      newBand='STRONG_PROXY';
      confidence=55;
      reason='UTM chain exists but no booking confirmation event';
    }
  } else if(band==='WEAK_PROXY'){
    if(bookingEventLive){
      newBand='VERIFIED_LEAD';
      confidence=60;
      reason='Can track sessions but not final booking';
    } else {
      newBand='WEAK_PROXY';
      confidence=30;
      reason='Indirect correlation only — no booking event';
    }
  } else if(band==='UNMEASURABLE'){
    if(s.source==='lead_routing'){
      var waConnected=apiConn.connections&&apiConn.connections.some(function(c){return c.api==='whatsapp_business'&&c.status==='connected';});
      newBand=waConnected?'VERIFIED_LEAD':'UNKNOWN';
      confidence=waConnected?65:10;
      reason=waConnected?'WhatsApp API connected — can track message leads':'WhatsApp API not connected';
    } else if(s.source==='tiny_ad_shift'){
      var metaConnected=apiConn.connections&&apiConn.connections.some(function(c){return c.api==='meta_ads'&&c.status==='connected';});
      newBand=metaConnected?'STRONG_PROXY':'UNKNOWN';
      confidence=metaConnected?50:10;
      reason=metaConnected?'Meta Ads connected but no booking event':'Meta Ads not connected';
    } else {
      newBand='UNKNOWN';
      confidence=5;
      reason='No data path exists';
    }
  }
  
  return{
    source:s.source,
    name:s.name,
    old_band:band,
    new_band:newBand,
    confidence:confidence,
    reason:reason,
    automation_rights:confidence>=70?'ALLOWED':confidence>=50?'REVIEW_NEEDED':'BLOCKED',
  };
});

// Summary
var verifiedRevenue=reclassified.filter(function(r){return r.new_band==='VERIFIED_REVENUE';});
var verifiedLead=reclassified.filter(function(r){return r.new_band==='VERIFIED_LEAD';});
var strongProxy=reclassified.filter(function(r){return r.new_band==='STRONG_PROXY';});
var weakProxy=reclassified.filter(function(r){return r.new_band==='WEAK_PROXY';});
var unknown=reclassified.filter(function(r){return r.new_band==='UNKNOWN';});
var blocked=reclassified.filter(function(r){return r.automation_rights==='BLOCKED';});
var allowed=reclassified.filter(function(r){return r.automation_rights==='ALLOWED';});

var out={
  schema:'https://clawdia.io/agents/conversion-truth-engine/v1',
  generated:now.toISOString(),
  summary:{
    total:sources.length,
    verified_revenue:verifiedRevenue.length,
    verified_lead:verifiedLead.length,
    strong_proxy:strongProxy.length,
    weak_proxy:weakProxy.length,
    unknown:unknown.length,
    allowed_automation:allowed.length,
    blocked_automation:blocked.length,
    honest_note:'VERIFIED_REVENUE requires booking_completed event in GA4. VERIFIED_LEAD requires service_selected. Currently zero of either.',
  },
  reclassified:reclassified,
  recommendations:[
    {priority:1,action:'Add booking_completed GA4 event — upgrades all STRONG_PROXY to VERIFIED_REVENUE',why:'One event change upgrades multiple channels from guess to fact'},
    {priority:2,action:'Add service_selected event — upgrades WEAK_PROXY to VERIFIED_LEAD',why:'Trackable service intent is better than nothing'},
    {priority:3,action:'Connect WhatsApp API — upgrades lead_routing from UNKNOWN to VERIFIED_LEAD',why:'Currently 0% automation rights on lead routing'},
  ],
};
fs.writeFileSync(path.join(DATA,'conversion-truth.json'),JSON.stringify(out,null,2));
console.log('✅ conversion_truth_engine: '+sources.length+' sources reclassified');
console.log('   VERIFIED_REVENUE: '+verifiedRevenue.length+' | VERIFIED_LEAD: '+verifiedLead.length);
console.log('   STRONG_PROXY: '+strongProxy.length+' | WEAK_PROXY: '+weakProxy.length+' | UNKNOWN: '+unknown.length);
console.log('   Allowed: '+allowed.length+' | Blocked: '+blocked.length);
console.log('   Honest: Zero VERIFIED_REVENUE or VERIFIED_LEAD — no booking events connected');
blocked.forEach(function(r){console.log('   BLOCKED: '+r.name+' ('+r.new_band+')');});