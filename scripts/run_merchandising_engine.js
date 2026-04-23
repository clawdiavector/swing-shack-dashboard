const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const uid=()=>Math.random().toString(36).substring(2,10);
const now=new Date();
const recSc=r('recommendation-scores.json')||{};
const topSvc=recSc.summary?.top_service||'Practice';
const board={
  schema:'https://clawdia.io/agents/merchandising-engine/v1',
  generated:now.toISOString(),
  sections:[
    {
      zone:'hero_section',location:'Homepage / IG Bio link',
      product:'Full Bag Fitting',
      reason:'Highest margin + highest intent signal. Hero = most important. Fitting = Swing Shack differentiator.',
      creative:'TrackMan data image. "Your clubs. Decoded." headline. CTA: "Book Fitting — From R1,800"',
      priority:1,
    },
    {
      zone:'story_highlight',location:'Instagram Story Highlights',
      products:['TPI Assessment','Club Fitting Starter Pack','Loft & Lie'],
      reason:'Story highlights are permanent IG real estate. Fitting education content earns trust.',
      creative:'Before/after TrackMan numbers. "What 3 fittings taught this member." Weekly fitting tip.',
      priority:2,
    },
    {
      zone:'counter_display',location:'Swing Shack counter / physical space',
      products:['Practice Pack (5 sessions)','Bucket of Beer','Takomo balls'],
      reason:'Physical point of sale moment. People have time to look while waiting. Fast, tangible products.',
      creative:'A-frame: "Most popular: Practice Pack. 5 sessions, R1,000. Better than 5 x R250." Physical takeaway.',
      priority:1,
    },
    {
      zone:'staff_pick',location:'Bio / About page / Email signature',
      products:['Birdie Hunter Coaching with Dave'],
      reason:'Personal recommendation drives trust. Dave is the named instructor — personal brand = credibility.',
      creative:'"Staff pick: Dave\'s Birdie Hunter programme. Best for golfers serious about dropping shots."',
      priority:3,
    },
    {
      zone:'seasonal_push',location:'Homepage banner / IG grid',
      products:['Junior Golf Bundle','Social Play Group'],
      reason:'School holidays = junior demand. Weekend = group bookings. Match placement to timing.',
      creative:'Holiday: "Keep them off screens. Junior coaching from R850." Weekend: "Book your group — Friday night slots filling."',
      priority:2,
    },
    {
      zone:'footer_trust',location:'Website footer / About page',
      products:['TrackMan Technology','Certified Instructors'],
      reason:'Trust signals belong in footer. Not hero — they reinforce after intent is confirmed.',
      creative:'"TrackMan on every session. Certified TPI instructors. 4.8★ on Google."',
      priority:3,
    },
    {
      zone:'email_cta',location:'Booking confirmation emails / WhatsApp',
      products:['Practice Pack','3-Lesson Package'],
      reason:'Post-booking emails get 3x engagement. Add-on moment is right after confirmation.',
      creative:'"Great choice on [booking]. Most members who booked [this] also add [Practice Pack] — R200/session instead of R250. Add it here: [link]"',
      priority:1,
    },
  ],
  summary:{
    total_zones:7,
    hero_priority:'Full Bag Fitting',
    counter_priority:'Practice Pack',
    highest_impact:'Email post-booking upsell (3x engagement)',
  },
};
fs.writeFileSync(path.join(DATA,'merchandising-board.json'),JSON.stringify(board,null,2));
console.log('✅ Merchandising engine: '+board.sections.length+' zones');
board.sections.filter(s=>s.priority===1).forEach(s=>console.log('   P1: '+s.zone+': '+String(s.products||s.product||'').join ? (Array.isArray(s.products)?s.products.join(', '):s.products) : ''));
