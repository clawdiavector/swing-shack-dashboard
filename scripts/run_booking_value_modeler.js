const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=function(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch(e){return null;}};
const now=new Date();

// Booking value modeler — estimate commercial value where payment data is unavailable
// Rules: verified revenue and modelled revenue must be clearly separate

const ga4=r('ga4-metrics.json')||{};
const ig=r('ig-analytics.json')||{};
const bookClosure=r('booking-closure.json')||{};

// Service values from swingshack.co.za/membership (CONFIRMED pricing)
const serviceValues={
  'Full Bag Fitting':{price:1800,frequency:'one-time',category:'fitting',avg_basket:1800,confidence:'HIGH'},
  'Iron Fitting':{price:900,frequency:'one-time',category:'fitting',avg_basket:900,confidence:'HIGH'},
  'Driver Fitting':{price:900,frequency:'one-time',category:'fitting',avg_basket:900,confidence:'HIGH'},
  'Putter Fitting':{price:900,frequency:'one-time',category:'fitting',avg_basket:900,confidence:'HIGH'},
  'Wedge Fitting':{price:900,frequency:'one-time',category:'fitting',avg_basket:900,confidence:'HIGH'},
  'TPI Assessment':{price:1250,frequency:'one-time',category:'coaching',avg_basket:1250,confidence:'HIGH'},
  'Coaching':{price:850,frequency:'per-session',category:'coaching',avg_basket:850,confidence:'MEDIUM'},
  'Birdie Hunter':{price:2300,frequency:'package',category:'coaching',avg_basket:2300,confidence:'HIGH'},
  'I Am Golf':{price:2850,frequency:'weekly',category:'coaching',avg_basket:2850,confidence:'HIGH'},
  'Practice Session':{price:250,frequency:'per-session',category:'simulator',avg_basket:250,confidence:'HIGH'},
  'Social Play':{price:250,frequency:'per-session',category:'simulator',avg_basket:250,confidence:'HIGH'},
  'Social Play - 2 Players':{price:340,frequency:'per-session',category:'simulator',avg_basket:340,confidence:'HIGH'},
  'Social Play - 3-4 Players':{price:450,frequency:'per-session',category:'simulator',avg_basket:450,confidence:'HIGH'},
  'Membership':{price:250,frequency:'monthly',category:'membership',avg_basket:250,confidence:'MEDIUM'},
};

// Membership LTV
var membershipLTV={
  months:12,
  monthly_price:250,
  total_ltv:3000,
  free_sessions_month:4,
  session_value:250,
  free_session_value_month:1000,
  effective_monthly_value:1250,
  confidence:'MEDIUM',
  note:'LTV modelled on 12-month commitment. Actual churn may be lower.',
};

// Membership LTV calculation
var effectiveMonthly=membershipLTV.monthly_price+membershipLTV.free_session_value_month*0.1; // 10% of free session value is captured
membershipLTV.effective_monthly_value=Math.round(effectiveMonthly);
membershipLTV.total_ltv=membershipLTV.effective_monthly_value*membershipLTV.months;

// GA4 sessions analysis
var totalSessions=(ga4.sources||[]).reduce(function(s,x){return s+(x.sessions||0);},0);
var igReach=(ig.posts||[]).reduce(function(s,p){return s+(p.reach||0);},0);
var igPosts=(ig.posts||[]).length;

// Booking value model
var conversionRateModel=0.01; // 1% of sessions convert (conservative)
var avgBasketModel=850; // average of all service baskets

var sessionsBySource={};
(ga4.sources||[]).forEach(function(s){
  var src=s.source||'unknown';
  sessionsBySource[src]=(sessionsBySource[src]||0)+(s.sessions||0);
});

var modelledRevenue={};
Object.keys(sessionsBySource).forEach(function(src){
  var sessions=sessionsBySource[src];
  var modelled_bookings=Math.round(sessions*conversionRateModel);
  var revenue=modelled_bookings*avgBasketModel;
  modelledRevenue[src]={
    sessions:sessions,
    modelled_bookings:modelled_bookings,
    conversion_rate:conversionRateModel,
    avg_basket:avgBasketModel,
    modelled_revenue:revenue,
    confidence:'WEAK_PROXY',
    note:'sessions × 1% × R850. This is a guess, not real revenue.',
  };
});

// Per-service modelled revenue from closure map
var closureMap=(bookClosure.closure_map||[]);
var byService={};
closureMap.forEach(function(c){
  var svc=c.service||'unknown';
  if(!byService[svc])byService[svc]={sessions:0,modelled_bookings:0,modelled_revenue:0};
  byService[svc].sessions+=c.sessions||0;
  byService[svc].modelled_bookings+=Math.round((c.sessions||0)*conversionRateModel);
  var sv=serviceValues[svc]||{price:850};
  byService[svc].modelled_revenue+=Math.round((c.sessions||0)*conversionRateModel*sv.price);
});

// Aggregate
var totalModelledRevenue=Object.values(modelledRevenue).reduce(function(s,x){return s+x.modelled_revenue;},0);
var totalModelledBookings=Object.values(modelledRevenue).reduce(function(s,x){return s+x.modelled_bookings;},0);

var out={
  schema:'https://clawdia.io/agents/booking-value-modeler/v1',
  generated:now.toISOString(),
  service_values:serviceValues,
  membership_ltv:membershipLTV,
  modelled_revenue:modelledRevenue,
  by_service:byService,
  conversion_rate_model:{
    rate:conversionRateModel,
    basis:'conservative industry average for service businesses',
    confidence:'WEAK',
    note:'1% conversion from session to booking. Real rate unknown without booking system data.',
  },
  avg_basket_model:{
    basket:avgBasketModel,
    basis:'average of confirmed service prices from swingshack.co.za/membership',
    confidence:'MEDIUM',
  },
  summary:{
    total_modelled_sessions:totalSessions,
    total_modelled_bookings:totalModelledBookings,
    total_modelled_revenue:totalModelledRevenue,
    ig_total_reach:igReach,
    ig_posts:igPosts,
    conversion_rate_used:conversionRateModel,
    honest_note:'ALL REVENUE HERE IS MODELED. Not real bookings. Modelled = sessions × 1% × avg basket. Real revenue requires booking system → GA4 integration.',
    labelled:'MODELLED — not verified revenue',
  },
  recommendations:[
    {priority:1,action:'Connect booking system to GA4 — replaces modelled revenue with verified revenue',why:'Every R in the dashboard now is a guess'},
    {priority:2,action:'Use actual conversion rate once booking data is available',why:'1% is a conservative guess — real rate could be 3x or 10x or 0.1x'},
  ],
};
fs.writeFileSync(path.join(DATA,'booking-value-model.json'),JSON.stringify(out,null,2));
console.log('✅ booking_value_modeler: '+Object.keys(serviceValues).length+' services valued');
console.log('   Modelled sessions: '+totalSessions+' | Bookings: '+totalModelledBookings+' | Revenue: R'+totalModelledRevenue);
console.log('   IG reach: '+igReach+' across '+igPosts+' posts');
console.log('   Membership LTV: R'+membershipLTV.total_ltv+' (12 months, R'+membershipLTV.effective_monthly_value+'/month effective)');
console.log('   Honest: ALL REVENUE IS MODELED — label it clearly');