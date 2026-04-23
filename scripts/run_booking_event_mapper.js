const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Booking event taxonomy — defines what a "booking" signal looks like
// Currently no live booking system connected — this maps the ideal state

const events=[
  {
    event_id:'booking_started',
    name:'Booking Started',
    trigger:'User lands on /book or /contact',
    signals:['page_view /book','page_view /contact','cta_click book_now'],
    utm_required:['utm_source','utm_medium','utm_campaign'],
    hook_id_required:false,
    priority:1,
    current_measurable:true,
    gap:'GA4 goal exists but not wired to booking system',
  },
  {
    event_id:'service_selected',
    name:'Service Selected',
    trigger:'User selects a service type',
    signals:['booking_form_service_field','url_param ?service='],
    utm_required:['utm_source','utm_medium','utm_campaign','utm_content'],
    hook_id_required:true,
    recommendation_id_required:false,
    priority:2,
    current_measurable:false,
    gap:'No service selection event in GA4 — form submission not tracked',
  },
  {
    event_id:'booking_completed',
    name:'Booking Confirmed',
    trigger:'Payment confirmed or booking slot reserved',
    signals:['page_view /book/confirmed','page_view /success','form_submit booking_success'],
    utm_required:['utm_source','utm_medium','utm_campaign','utm_content'],
    hook_id_required:true,
    recommendation_id_required:true,
    priority:1,
    current_measurable:false,
    gap:'No confirmation page in GA4 — booking system not connected to analytics',
  },
  {
    event_id:'booking_value_proxy',
    name:'Booking Value',
    trigger:'Service type determines value',
    signals:['price_param in confirmation URL','service_type from booking form'],
    utm_required:['utm_source','utm_medium'],
    hook_id_required:false,
    recommendation_id_required:false,
    priority:2,
    current_measurable:false,
    gap:'Price not passed through UTM — value must be modelled from service type',
  },
  {
    event_id:'source_utm',
    name:'Source Attribution',
    trigger:'Any utm_source present',
    signals:['utm_source parameter','referrer if no UTM'],
    utm_required:['utm_source'],
    hook_id_required:false,
    recommendation_id_required:false,
    priority:1,
    current_measurable:true,
    gap:'GA4 captures utm_source but hook_id is not in any UTM param',
  },
  {
    event_id:'recommendation_id',
    name:'Recommendation Linked',
    trigger:'recommendation_id in UTM content param',
    signals:['utm_content includes recommendation_id'],
    utm_required:['utm_source','utm_medium','utm_content'],
    hook_id_required:true,
    recommendation_id_required:true,
    priority:3,
    current_measurable:false,
    gap:'recommendation_id never makes it into UTM chain — needs Postiz + GA4 integration',
  },
];

// Current state summary
const measurable=events.filter(e=>e.current_measurable);
const not_measurable=events.filter(e=>!e.current_measurable);
const p1_events=events.filter(e=>e.priority===1);
const p2_events=events.filter(e=>e.priority===2);
const p3_events=events.filter(e=>e.priority===3);

// What needs to be built
const implementation_steps=[
  {step:1,action:'Add GA4 event: booking_confirmation — fire on /book/confirmed page view',priority:'P1',effort:'low',owner:'GA4 config',blocks:['booking_completed','booking_value_proxy']},
  {step:2,action:'Add service type to confirmation URL — pass ?service=Full+Bag+Fitting in confirmation',priority:'P1',effort:'low',owner:'Swing Shack dev',blocks:['service_selected','booking_value_proxy']},
  {step:3,action:'Wire Postiz hook_id into UTM content param — post → hook_id → GA4',priority:'P2',effort:'medium',owner:'Postiz + GA4',blocks:['recommendation_id','service_selected']},
  {step:4,action:'Set up GA4 → booking system event mapping — connect actual bookings to sessions',priority:'P1',effort:'high',owner:'Swing Shack dev',blocks:['booking_completed','booking_value_proxy']},
  {step:5,action:'Add recommendation_id to Postiz post metadata → UTM content param',priority:'P2',effort:'medium',owner:'Postiz config',blocks:['recommendation_id']},
];

const out={
  schema:'https://clawdia.io/agents/booking-event-mapper/v1',
  generated:now.toISOString(),
  events,
  summary:{
    total:events.length,
    currently_measurable:measurable.length,
    not_currently_measurable:not_measurable.length,
    p1_critical:p1_events.length,
    p2_important:p2_events.length,
    p3_nice:p3_events.length,
    honest_note:'Zero booking events are currently connected to GA4. The framework exists but the wiring does not.',
  },
  implementation_steps,
  recommendations:[
    {priority:1,action:'Add booking_confirmation GA4 event — single page view on /book/confirmed',why:'This alone upgrades STRONG_PROXY → VERIFIED_REVENUE for all channels'},{priority:2,action:'Wire service type through confirmation URL',why:'Enables value modelling by service — not just session counting'},{priority:3,action:'Add hook_id to UTM content in Postiz',why:'Closes the post → session → booking chain at the attribution level'},{priority:4,action:'Connect GA4 → booking system API',why:'Real booking data instead of modelled estimates'},
  ],
};
fs.writeFileSync(path.join(DATA,'booking-events.json'),JSON.stringify(out,null,2));
console.log('✅ booking_event_mapper: '+events.length+' events defined');
console.log('   Measurable now: '+measurable.length+' | Not yet: '+not_measurable.length);
console.log('   P1 critical: '+p1_events.length+' | P2: '+p2_events.length+' | P3: '+p3_events.length);
p1_events.forEach(e=>console.log('   P1: '+e.event_id+' — '+e.gap.substring(0,60)));
console.log('   Honest: '+out.summary.honest_note);
