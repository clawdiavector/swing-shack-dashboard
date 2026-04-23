const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const lm=r('live-mode.json')||{};
const mode=lm.modes.current||'OFF';
const allowed=(lm.permissions_by_mode||{})[mode]||[];

// Lead scoring thresholds
const HOT_THRESHOLD=80;   // immediate WhatsApp
const WARM_THRESHOLD=55;  // callback queue
const COLD_THRESHOLD=15;  // nurture

// In production: reads from CRM/booking system/WhatsApp
// Placeholder leads for demonstration
const leads=r('leads.json')||{leads:[]};
const placeholderLeads=[
  {id:'l-1',source:'instagram',service:'Full Bag Fitting',intent_score:88,status:'new',created:new Date(Date.now()-3600000).toISOString()},
  {id:'l-2',source:'website',service:'TPI Assessment',intent_score:62,status:'new',created:new Date(Date.now()-7200000).toISOString()},
  {id:'l-3',source:'google',service:'Practice Pack',intent_score:38,status:'new',created:new Date(Date.now()-86400000).toISOString()},
];
const allLeads=leads.leads.length>0?leads.leads:placeholderLeads;

const actions=[];
const uid=()=>'rte-'+Date.now().toString(36)+Math.random().toString(36).substring(2,6);

const canRoute=allowed.includes('lead_routing');

allLeads.forEach(lead=>{
  if(!canRoute){
    actions.push({action_id:uid(),lead_id:lead.id,type:'blocked',why:'Mode='+mode+'. Need LIVE mode for lead routing.',status:'blocked'});
    return;
  }
  if(lead.intent_score>=HOT_THRESHOLD){
    actions.push({
      action_id:uid(),lead_id:lead.id,type:'route_whatsapp',
      service:lead.service,score:lead.intent_score,
      message:'Hi! Great to hear about your interest in '+lead.service+'. Can we call you in the next hour? — Swing Shack',
      why:'Hot lead (score:'+lead.intent_score+'). SLA: 1 hour.',
      confidence:0.90,rule:'hot_lead_sla',reversible:false,status:'sent',
    });
  } else if(lead.intent_score>=WARM_THRESHOLD){
    actions.push({
      action_id:uid(),lead_id:lead.id,type:'route_callback',
      service:lead.service,score:lead.intent_score,
      window:'4 hours',why:'Warm lead (score:'+lead.intent_score+'). Callback within 4h.',
      confidence:0.75,rule:'warm_lead_sla',reversible:false,status:'queued',
    });
  } else {
    actions.push({
      action_id:uid(),lead_id:lead.id,type:'route_nurture',
      service:lead.service,score:lead.intent_score,
      sequence:'cold_nurture_v1',why:'Cold lead (score:'+lead.intent_score+'). Nurture sequence.',
      confidence:0.60,rule:'cold_nurture',reversible:false,status:'queued',
    });
  }
});

const out={
  schema:'https://clawdia.io/agents/lead-router-live/v1',
  generated:now.toISOString(),
  mode,
  thresholds:{hot:HOT_THRESHOLD,warm:WARM_THRESHOLD,cold:COLD_THRESHOLD},
  routing:{hot:'WhatsApp immediate',warm:'Callback 4h',cold:'Nurture sequence'},
  actions,
  summary:{
    total:allLeads.length,
    hot:actions.filter(a=>a.type==='route_whatsapp').length,
    warm:actions.filter(a=>a.type==='route_callback').length,
    cold:actions.filter(a=>a.type==='route_nurture').length,
    blocked:actions.filter(a=>a.status==='blocked').length,
    note:'No live CRM/WhatsApp Business API connected. Placeholder routing — connects when Christelle enables WhatsAppflows.',
  },
};
fs.writeFileSync(path.join(DATA,'lead-routing-log.json'),JSON.stringify(out,null,2));
console.log('✅ lead_router_live: mode='+mode+', '+allLeads.length+' leads');
actions.filter(a=>a.status!=='blocked').slice(0,3).forEach(a=>console.log('   '+a.type.replace('route_','')+': lead '+a.lead_id+' (score:'+a.score+')'));
