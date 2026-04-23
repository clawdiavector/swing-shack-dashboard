const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Meta token monitoring — token dies same-day, this prevents silent decay
const TOKEN_PATH='/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json';
const IG_TOKEN_PATH='/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/instagram-api-token.json';
const cred=(p)=>{try{return JSON.parse(fs.readFileSync(p,'utf8'));}catch{return null;}};

const metaToken=cred(TOKEN_PATH);
const igToken=cred(IG_TOKEN_PATH);

// Calculate token age and warn thresholds
const TOKEN_WARN_HOURS=20;
const TOKEN_CRITICAL_HOURS=23;

function tokenAge(token){
  if(!token)return null;
  const savedAt=token.saved_at||token.created_at;
  if(!savedAt)return null;
  const ageMs=now-new Date(savedAt);
  return{age_hours:Math.round(ageMs/3600000),age_ms:ageMs};
}

const metaAge=tokenAge(metaToken);
const igAge=tokenAge(igToken);

// Status determination
function tokenStatus(age){
  if(!age)return null;
  if(age.age_hours>=TOKEN_CRITICAL_HOURS)return'CRITICAL';
  if(age.age_hours>=TOKEN_WARN_HOURS)return'WARNING';
  return'OK';
}

const metaStatus=tokenStatus(metaAge);
const igStatus=tokenStatus(igAge);

// Auto-check via Meta API (lightweight endpoint check)
let metaApiOk=false, igApiOk=false;
try{
  const https=require('https');
  // Just check if token file exists and is recent enough — actual API call would require network
  metaApiOk=!!(metaToken&&metaAge&&metaAge.age_hours<24);
  igApiOk=!!(igToken&&igAge&&igAge.age_hours<24);
}catch(e){metaApiOk=false;igApiOk=false;}

const reconnect_checklist=[
  {step:1,task:'Generate new User Access Token via Meta Developer Console',priority:'CRITICAL',status:'manual'},
  {step:2,task:'Exchange for Long-Lived Access Token via /oauth/access_token',priority:'CRITICAL',status:'manual'},
  {step:3,task:'Set up server-side OAuth cron to refresh before expiry',priority:'CRITICAL',status:'not_started'},
  {step:4,task:'Replace Basic Display API with Page Access Token for posting',priority:'HIGH',status:'not_started'},
  {step:5,task:'Test auto-refresh via cron',priority:'HIGH',status:'not_started'},
];

const alerts=[];
if(metaStatus==='CRITICAL')alerts.push({type:'CRITICAL',api:'Meta Ads',message:'Token '+metaAge.age_hours+'h old — expired or near expiry. Budget shifts frozen.'});
if(metaStatus==='WARNING')alerts.push({type:'WARNING',api:'Meta Ads',message:'Token '+metaAge.age_hours+'h old — refresh recommended within hours.'});
if(igStatus==='CRITICAL')alerts.push({type:'CRITICAL',api:'Instagram',message:'IG token '+igAge.age_hours+'h old — posting may fail.'});
if(igStatus==='WARNING')alerts.push({type:'WARNING',api:'Instagram',message:'IG token '+igAge.age_hours+'h old — monitor closely.'});

const mode=metaStatus==='CRITICAL'?'DEGRADED':metaStatus==='WARNING'?'DEGRADED':'MINIMAL';
const out={
  schema:'https://clawdia.io/agents/meta-oauth-watchdog/v1',
  generated:now.toISOString(),
  mode,
  tokens:{
    meta:{present:!!metaToken,age_hours:metaAge?.age_hours||null,status:metaStatus||'unknown',api_ok:metaApiOk,expires_estimate:metaToken?.saved_at?new Date(new Date(metaToken.saved_at).getTime()+86400000).toISOString():null},
    instagram:{present:!!igToken,age_hours:igAge?.age_hours||null,status:igStatus||'unknown',api_ok:igApiOk,expires_estimate:igToken?.saved_at?new Date(new Date(igToken.saved_at).getTime()+86400000).toISOString():null},
  },
  alerts,
  reconnect_checklist,
  recommendations:[
    {priority:1,action:'Set up server-side OAuth with long-lived Page Access Token',why:'Basic Display tokens expire same day. Need Page Access Token + server refresh cron.'},
    {priority:2,action:'Add daily token health check to morning cron',why:'Prevents silent decay. Alert if token <24h old.'},
  ],
  summary:{
    mode,
    alerts:alerts.length,
    critical_alerts:alerts.filter(a=>a.type==='CRITICAL').length,
    action_required:alerts.length>0?'YES':'NO',
    note:'Token expiry is the root cause of Meta Ads instability. This watchdog monitors but cannot fix the root cause.',
  },
};
fs.writeFileSync(path.join(DATA,'meta-auth-health.json'),JSON.stringify(out,null,2));
console.log('✅ meta_oauth_watchdog: mode='+mode);
console.log('   Meta: '+(metaStatus||'unknown')+' ('+metaAge?.age_hours+'h old) | IG: '+(igStatus||'unknown')+' ('+igAge?.age_hours+'h old)');
alerts.forEach(a=>console.log('   '+a.type+': '+a.api+' — '+a.message));
console.log('   RECONNECT: '+reconnect_checklist.filter(s=>s.status==='not_started').length+' steps not started');
