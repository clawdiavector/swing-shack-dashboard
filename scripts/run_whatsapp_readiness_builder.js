const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// WhatsApp routing — prepared for when API connects
// Current state: WhatsApp Business API not connected
// This prepares all routing logic, templates, and SLA rules

const routing_rules=[
  {
    rule_id:'hot-lead-fitting',name:'Hot Lead — Club Fitting',
    trigger:{source:'instagram',service:'Full Bag Fitting',intent_score:80},
    action:'route_whatsapp',
    sla_minutes:60,
    message_template:'Hi {{name}}! Great to hear about your interest in our Full Bag Fitting. Can we call you in the next hour? — The Swing Shack team',
    escalation:'call_booking_team',
    status:'ready',
    missing:[],
  },
  {
    rule_id:'hot-lead-coaching',name:'Hot Lead — Coaching',
    trigger:{source:'instagram',service:'Coaching',intent_score:80},
    action:'route_whatsapp',
    sla_minutes:60,
    message_template:'Hi {{name}}! Awesome that you\'re interested in coaching. Our instructors Catherine and Dave have limited slots — want to book a call this week? — The Swing Shack team',
    escalation:'call_booking_team',
    status:'ready',
    missing:[],
  },
  {
    rule_id:'warm-lead-fitting',name:'Warm Lead — Any Service',
    trigger:{source:'website',intent_score:55},
    action:'route_callback',
    sla_minutes:240,
    message_template:'Hi {{name}}, thanks for reaching out to Swing Shack! We\'ll call you within 4 hours.',
    escalation:'email_followup_4h',
    status:'ready',
    missing:[],
  },
  {
    rule_id:'cold-lead-nurture',name:'Cold Lead — Practice/Social',
    trigger:{source:'organic',intent_score:15},
    action:'route_nurture',
    sla_minutes:1440,
    sequence:'cold_nurture_v1',
    message_template:'Hi {{name}}, thanks for your interest in Swing Shack! Here\'s what\'s popular right now:',
    escalation:'email_weekly',
    status:'ready',
    missing:[],
  },
  {
    rule_id:'membership-enquiry',name:'Membership Enquiry',
    trigger:{source:'any',service:'Membership',intent_score:60},
    action:'route_whatsapp_priority',
    sla_minutes:120,
    message_template:'Hi {{name}}, great question about Swing Shack membership! Here\'s what members get: 4 free practice sessions/month, 15% off coaching, 25% off fittings. Want to chat about which membership fits you?',
    escalation:'call_booking_team',
    status:'ready',
    missing:[],
  },
];

const message_templates={
  greeting:'Hi {{name}}, thanks for reaching out to Swing Shack! How can we help?',
  fitting_interest:'That\'s great — our Full Bag Fitting with TrackMan is a brilliant place to start. Want to book a session this week?',
  coaching_interest:'Awesome. Catherine and Dave are our certified instructors — what would you most like to work on?',
  membership_info:'Swing Shack membership gives you 4 free practice sessions/month, 15% off coaching and 25% off fittings. Want to know more?',
  booking_confirmed:'Perfect — you\'re booked in. See you at Swing Shack! ⛳',
  follow_up_24h:'Hi {{name}}, just checking in — did you want to book that session? We have availability this week.',
  closing:'Thanks for chatting with Swing Shack! Come see us soon. ⛳',
};

const escalation_flow={
  sla_tiers:[
    {tier:'hot',sla_minutes:60,action:'WhatsApp immediate',escalation:'call if no response in 60min'},
    {tier:'warm',sla_minutes:240,action:'Callback within 4h',escalation:'email if no response'},
    {tier:'cold',sla_minutes:1440,action:'Nurture sequence',escalation:'weekly email for 3 weeks'},
  ],
  manual_override:['booking_above_r2000','membership_inquiry','group_booking_4plus'],
};

const readiness={
  routing_rules_ready:routing_rules.filter(r=>r.status==='ready').length,
  total_routing_rules:routing_rules.length,
  templates_ready:Object.keys(message_templates).length,
  sla_tiers_configured:escalation_flow.sla_tiers.length,
  manual_override_count:escalation_flow.manual_override.length,
  api_connected:false,
  blocker:'WhatsApp Business API not connected',
  can_activate_when_api_lives:true,
};

const recommendations=[];
if(!readiness.api_connected)recommendations.push({priority:1,action:'Connect WhatsApp Business API to activate routing',why:'Routing rules and templates are ready. Only the API connection is missing.'});
if(readiness.templates_ready<5)recommendations.push({priority:3,action:'Add group booking and event-specific templates',why:'Missing templates for social play groups and corporate events.'});

const out={
  schema:'https://clawdia.io/agents/whatsapp-readiness-builder/v1',
  generated:now.toISOString(),
  readiness,
  routing_rules,
  message_templates,
  escalation_flow,
  recommendations,
  summary:{
    routes_ready:routing_rules.length,
    templates_ready:Object.keys(message_templates).length,
    status:'READY_TO_ACTIVATE',
    note:'All routing logic, templates, and SLA rules are prepared. Waiting for WhatsApp Business API connection.',
  },
};
fs.writeFileSync(path.join(DATA,'whatsapp-routing-ready.json'),JSON.stringify(out,null,2));
const out2={
  schema:'https://clawdia.io/agents/whatsapp-template-pack/v1',
  generated:now.toISOString(),
  templates:message_templates,
  routing_rules,
};
fs.writeFileSync(path.join(DATA,'whatsapp-template-pack.json'),JSON.stringify(out2,null,2));
console.log('✅ whatsapp_readiness_builder: '+routing_rules.length+' rules, '+Object.keys(message_templates).length+' templates ready');
routing_rules.forEach(r=>console.log('   '+r.status.toUpperCase()+': '+r.name+' (SLA:'+r.sla_minutes+'min)'));
console.log('   STATUS: READY TO ACTIVATE when WhatsApp API connects');
