const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const lm=r('live-mode.json')||{};
const mode=lm.modes.current||'OFF';
const allowed=(lm.permissions_by_mode||{})[mode]||[];

// Simulated Google reviews (in production: Google Business API)
const reviews=r('google-reviews.json');
const placeholder=[
  {id:'r-1',reviewer:'Liam M',rating:5,service:'Full Bag Fitting',date:'2026-04-20',text:'Incredible experience. TrackMan data was next level.',auto_response:null},
  {id:'r-2',reviewer:'Sarah K',rating:4,service:'TPI Assessment',date:'2026-04-19',text:'Really helpful coaches. Could have done with more time on the simulator.',auto_response:null},
  {id:'r-3',reviewer:'Johan P',rating:3,service:'Practice Session',date:'2026-04-18',text:'Bit crowded on Saturday. Fun though.',auto_response:null},
  {id:'r-4',reviewer:'Naledi D',rating:5,service:'Coaching',date:'2026-04-17',text:'Catherine is brilliant. My slice is 40m shorter already.',auto_response:null},
  {id:'r-5',reviewer:'Tom B',rating:2,service:'Social Play',date:'2026-04-16',text:'Booking system confusing. Staff were nice though.',auto_response:null},
];
const allReviews=(reviews&&reviews.reviews)||placeholder;

const actions=[];
const uid=()=>'rev-'+Date.now().toString(36)+Math.random().toString(36).substring(2,6);

const canRespond=allowed.includes('review_thank_you');

allReviews.forEach(rev=>{
  if(rev.auto_response){actions.push({action_id:uid(),review_id:rev.id,type:'already_responded',status:'done',...rev});return;}
  if(rev.rating===5){
    // 5-star: live thank-you allowed in LIVE mode
    if(!canRespond){
      actions.push({action_id:uid(),review_id:rev.id,type:'draft_only',rating:rev.rating,reviewer:rev.reviewer,response_draft:'Thanks [name]! So glad you loved [service]. Come back and see us soon! — The Swing Shack team',why:'Mode='+mode+'. Would need LIVE mode to post live.',status:'drafted',live_allowed:false});
    } else {
      actions.push({action_id:uid(),review_id:rev.id,type:'thank_you',rating:rev.rating,reviewer:rev.reviewer,response:'Thanks Liam! Great to hear you enjoyed the fitting. See you again soon! — The Swing Shack team',why:'5-star. Positive. Low risk. Thank-you approved.',confidence:0.95,rule:'positive_5star',status:'posted',live:true});
    }
  } else if(rev.rating===4){
    // 4-star: draft only
    actions.push({action_id:uid(),review_id:rev.id,type:'draft_only',rating:rev.rating,reviewer:rev.reviewer,response_draft:'Thanks [name]! Glad you enjoyed [service]. Always looking to improve — let us know if you have suggestions: [WhatsApp]',why:'4-star. Positive but neutral. Draft for manual review.',confidence:0.70,rule:'neutral_review_manual',status:'drafted',live_allowed:false});
  } else {
    // <4 stars: NEVER auto-post
    actions.push({action_id:uid(),review_id:rev.id,type:'manual_only',rating:rev.rating,reviewer:rev.reviewer,response_draft:'Hi [name], thanks for the feedback. Sorry to hear that. Please reach out to us directly — we will make it right.',why:'Negative/neutral review. Hard rule: manual only at first. Never auto-post.',confidence:0.60,rule:'negative_review_manual',status:'blocked',live_allowed:false});
  }
});

const out={
  schema:'https://clawdia.io/agents/reputation-responder/v1',
  generated:now.toISOString(),
  mode,
  hard_rule:'negative_reviews_never_auto_posted',
  actions,
  summary:{
    total:allReviews.length,
    posted:actions.filter(a=>a.status==='posted').length,
    drafted:actions.filter(a=>a.status==='drafted').length,
    blocked:actions.filter(a=>a.status==='blocked').length,
    manual_only:actions.filter(a=>a.type==='manual_only').length,
  },
};
fs.writeFileSync(path.join(DATA,'review-actions.json'),JSON.stringify(out,null,2));
console.log('✅ reputation_responder: mode='+mode);
actions.forEach(a=>console.log('   '+a.status.toUpperCase()+': '+a.type.replace('route_','').replace('draft_only','DRAFT')+' — rev '+a.reviewer+' ('+a.rating+'★)'));
