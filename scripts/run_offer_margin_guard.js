const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const MIN_MARGIN=0.45;
const rec=r('recommendation-scores.json')||{};
// Block list — never allow these
const blockedOffers=[
  {offer:'30% off fittings','reason':'Desperation pricing. fittings are high-trust purchases. Discount signals low quality.',alternatives:['Free sleeve of fitting balls','Priority fitting slot','Loft & lie check free with booking']},
  {offer:'50% off coaching','reason':'Coaching margin supports instructors. Halving price devalues the product and staff.',alternatives:['Free TPI assessment with 3-lesson package','Add a friend free (2-for-1 study)']},
  {offer:'Buy 1 get 1 free','reason':'Two-for-one on simulator time is operationally loss-making. Not viable.',alternatives:['Practice Pack: 5 sessions for price of 4','Bring a friend — their session free, yours at normal price']},
  {offer:'First session free','reason':'Free sessions train bad behaviour. Members who pay full price show up and value the coaching more.',alternatives:['R250 first session — add a R250 Practice Pack credit','Intro offer: TPI assessment R1,000 instead of R1,250 — first-timer only']},
  {offer:'Seasonal sale / Black Friday','reason':'Golf services are not fashion. Discounting signals urgency desperation. SA market reads through it.',alternatives:['Mid-year membership drive — "Commit to the season"','End-of-year function packages for corporates']},
];
// Approved safe offers
const safeOffers=[
  {offer:'Practice Pack (5 for price of 4)','saving':'R250 (20%)','margin_remaining':0.60,'approved':true,'type':'volume_incentive','reason':'Members who practice more get better results. 5-pack builds habit without discounting the single session price.'},
  {offer:'Fitting + Lesson bundle','saving':'R350 (11%)','margin_remaining':0.70,'approved':true,'type':'value_add','reason':'Natural pairing. Fitting data makes lessons immediately actionable. Both margin-healthy.'},
  {offer:'Free fitting ball sleeve with first booking','saving':'R80 value','margin_remaining':0.75,'approved':true,'type':'value_add','reason':'Cost to Swing Shack ~R80 wholesale. Perceived value high. Converts hesitant first-timers.'},
  {offer:'Junior bundle (3 lessons + practice)','saving':'R250 (11%)','margin_remaining':0.58,'approved':true,'type':'volume_incentive','reason':'Parents respond to structured offers. Margin still healthy at 58%. Seasonal only.'},
];
// Margin check function
function checkMargin(originalPrice,salePrice,margin){
  if(margin<MIN_MARGIN)return{approved:false,reason:'Margin '+Math.round(margin*100)+'% below minimum '+Math.round(MIN_MARGIN*100)+'% floor.'};
  return{approved:true,reason:'Margin '+Math.round(margin*100)+'% — above floor. Approved.'};
}
const out={
  schema:'https://clawdia.io/agents/offer-margin-guard/v1',
  generated:now.toISOString(),
  rules:{min_margin_percent:Math.round(MIN_MARGIN*100),principle:'value_add_over_discounting'},
  blocked_offers:blockedOffers,
  safe_offers:safeOffers,
  margin_check:checkMargin(null,null,0.55),
  summary:{
    blocked:blockedOffers.length,
    safe_approved:safeOffers.length,
    principle:'Never discount margin below '+Math.round(MIN_MARGIN*100)+'%. Always prefer value-add over price cuts.',
  },
};
fs.writeFileSync(path.join(DATA,'offer-margin-checks.json'),JSON.stringify(out,null,2));
console.log('✅ Offer margin guard: '+blockedOffers.length+' blocked, '+safeOffers.length+' approved');
blockedOffers.forEach(o=>console.log('   BLOCKED: '+o.offer));
safeOffers.filter(s=>s.type==='value_add').forEach(o=>console.log('   SAFE: '+o.offer));
