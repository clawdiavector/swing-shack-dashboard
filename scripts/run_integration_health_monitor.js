const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const conn=r('api-connections.json')||{apis:[]};
const apis=(conn.apis||[]);

// Check each API's health based on last success vs now
const health=apis.map(api=>{
  const lastSucc=api.last_success?new Date(api.last_success):null;
  const hoursAgo=lastSucc?Math.floor((now-lastSucc)/3600000):999;
  const daysAgo=lastSucc?Math.floor((now-lastSucc)/86400000):999;
  
  let status='offline';
  if(!api.connected)status='offline';
  else if(api.id==='meta_ads'&&api.auth_status==='active_but_unstable')status='degraded';
  else if(hoursAgo>24)status='stale';
  else if(hoursAgo<=1)status='connected';
  else status='connected'; // connected but hours old is fine
  
  // Auth expiry risk
  let authExpiryRisk=false;
  if(api.id==='meta_ads')authExpiryRisk=true; // Token expires same day by design
  if(api.id==='whatsapp_business')authExpiryRisk=true;
  
  // Missing permissions
  const missingPerms=[];
  if(api.id==='meta_ads'&&!api.live_safe)missingPerms.push('Server-side token refresh (OAuth server)');
  if(api.id==='whatsapp_business'&&api.connected&&api.scope_level!=='full')missingPerms.push('Premium tier for full WhatsApp API access');
  
  // Capabilities at risk
  const atRisk=api.capabilities_unlocked||[];
  
  return{...api,status,hours_ago:hoursAgo,days_ago:daysAgo,auth_expiry_risk:authExpiryRisk,missing_permissions:missingPerms,capabilities_at_risk:atRisk};
});

const offline=health.filter(a=>a.status==='offline');
const degraded=health.filter(a=>a.status==='degraded');
const stale=health.filter(a=>a.status==='stale');
const connected=health.filter(a=>a.status==='connected');

const recommendations=[];
if(degraded.find(a=>a.id==='meta_ads')){
  recommendations.push({priority:1,api:'meta_ads',action:'Fix Meta token refresh — set up server-side OAuth for long-lived tokens',why:'Token expires same-day. Current tokens die within hours of issuing. Needs permanent refresh mechanism.'});
}
if(offline.find(a=>a.id==='whatsapp_business')){
  recommendations.push({priority:2,api:'whatsapp_business',action:'Connect WhatsApp Business API — enables live lead routing',why:'lead_router_live is simulated. WhatsApp API is the only way to route real leads.'});
}
if(offline.find(a=>a.id==='search_console')){
  recommendations.push({priority:3,api:'search_console',action:'Connect Google Search Console — enables real SEO performance data',why:'SEO rankings are from third-party tools only. Search Console gives real click/impression data.'});
}
if(degraded.find(a=>a.id==='google_business')){
  recommendations.push({priority:3,api:'google_business',action:'Verify GMB credentials are fresh — API write access required for review responses',why:'reputation_responder can draft but cannot post without verified GMB API access.'});
}

const out={
  schema:'https://clawdia.io/agents/integration-health-monitor/v1',
  generated:now.toISOString(),
  summary:{total:health.length,connected:connected.length,degraded:degraded.length,stale:stale.length,offline:offline.length},
  health,
  recommendations,
};
fs.writeFileSync(path.join(DATA,'integration-health.json'),JSON.stringify(out,null,2));
console.log('✅ integration_health_monitor: '+health.length+' APIs');
health.forEach(a=>console.log('   '+a.status.toUpperCase().padEnd(10)+a.name+' (last:'+(a.hours_ago<1?'<1h ago':a.hours_ago<24?a.hours_ago+'h ago':a.days_ago+'d ago')+')'));
recommendations.slice(0,3).forEach(r=>console.log('   P'+r.priority+': '+r.api+' — '+r.action.substring(0,60)));
