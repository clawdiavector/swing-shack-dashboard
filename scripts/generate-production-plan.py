#!/usr/bin/env python3
"""
M5: Campaign Production Plan Generator

Turns an accepted campaign blueprint into a structured production plan:
  - Asset Requirements summary
  - 30-day Publishing Calendar
  - Individual Asset Shells (campaigns[campaignId].assets[assetId])

Each asset shell is a PLANNED content item — not a finished asset.
No captions, images, or publish drafts generated here.

Schema:
  campaign.productionPlan    — the plan itself
  campaign.assets[assetId]   — individual asset shells

Trigger (M5 gate — all must be true):
  blueprint.blueprintVersion >= 1
  blueprint.active == true
  blueprint.dna exists
  blueprint.pillars.length >= 3
  not campaign.productionPlan  (unless --new flag)

Usage:
  python3 generate-production-plan.py <campaignId>
  python3 generate-production-plan.py <campaignId> --new   # regenerate even if plan exists
"""
import json, sys, os, re, urllib.request
from datetime import datetime, timezone, timedelta

REPO_ROOT = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
DATA_FILE = os.path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json')
CONFIG    = '/Users/fivefriday/.openclaw-instance2/openclaw.json'

MODEL = 'MiniMax-M2.7'

# ─── Validation Gates ─────────────────────────────────────────────────────────

def gate_check(name, condition, error_msg):
    """Log and accumulate gate failures."""
    if not condition:
        print(f"  GATE FAIL [{name}]: {error_msg}")
        return False
    print(f"  GATE PASS [{name}]")
    return True

def validate_production_plan(plan, campaign, errors):
    """Run G1–G8 against a generated production plan. Returns bool (pass/fail)."""
    bp     = campaign.get('blueprint', {})
    dna    = bp.get('dna', {})
    pillars = bp.get('pillars', [])
    platforms = campaign.get('identity', {}).get('platforms', [])

    ar = plan.get('assetRequirements', {})
    cal = plan.get('calendar', [])
    asset_map = {a['assetId']: a for a in plan.get('assetShells', [])}

    ok = True

    # G1 — Non-zero counts
    total = ar.get('total', 0)
    ok &= gate_check('G1', total > 0,
                     f'assetRequirements.total must be > 0, got {total}')
    for key in ['feedPosts', 'carousels', 'reels', 'stories', 'gmbPosts']:
        if key in ar:
            ok &= gate_check('G1', ar[key].get('count', 0) >= 0,
                             f'{key}.count must be >= 0')

    # G2 — Calendar length and structure
    ok &= gate_check('G2', len(cal) == 30,
                     f'calendar must have exactly 30 entries, got {len(cal)}')
    if cal:
        dates = [c['date'] for c in cal]
        ok &= gate_check('G2', len(set(dates)) == 30,
                         f'calendar dates must all be unique, found {30 - len(set(dates))} duplicates')

    # G3 — Unique, existing assetIds
    all_asset_ids = [c.get('assetId') for c in cal if c.get('assetId')]
    dupes = len(all_asset_ids) - len(set(all_asset_ids))
    ok &= gate_check('G3', dupes == 0,
                     f'assetIds must be unique in calendar, found {dupes} duplicates')
    for aid in set(all_asset_ids):
        ok &= gate_check('G3', aid in asset_map,
                         f'assetId "{aid}" in calendar but not in assetShells')

    # G4 — Pillar coverage
    pillar_ids = {p['id'] for p in pillars}
    cal_pillars = {c.get('pillar') for c in cal if c.get('pillar')}
    missing_pillars = pillar_ids - cal_pillars
    ok &= gate_check('G4', len(missing_pillars) == 0,
                     f'Pillars not covered in calendar: {missing_pillars}')

    # G5 — Real image rule
    requires_real = campaign.get('memory', {}).get('requiresRealProductImage', False)
    campaign_type = campaign.get('identity', {}).get('campaignType', '')
    if requires_real or campaign_type in ('equipment-fitting', 'product-launch'):
        for shell in plan.get('assetShells', []):
            img_type = shell.get('assetType', '')
            if img_type not in ('reel', 'story'):  # visual assets need real images
                ok &= gate_check('G5', shell.get('realImageNeeded') == True,
                                 f'{shell["assetId"]}: realImageNeeded must be true for equipment campaigns')
                ok &= gate_check('G5', shell.get('aiImageAllowed') == False
                                 or 'product' not in str(shell.get('aiForbiddenFor', [])).lower(),
                                 f'{shell["assetId"]}: aiImageAllowed must be false for product imagery')

    # G6 — Platform coverage
    platforms_in_cal = {c.get('platform') for c in cal if c.get('platform')}
    for plat in set(platforms):
        ok &= gate_check('G6', plat in platforms_in_cal,
                         f'Platform "{plat}" has no calendar entries')

    # G7 — No duplicate (date + platform + contentType)
    combos = [(c.get('date'), c.get('platform'), c.get('contentType'))
              for c in cal if c.get('date')]
    dupe_combos = len(combos) - len(set(combos))
    ok &= gate_check('G7', dupe_combos == 0,
                     f'Found {dupe_combos} duplicate (date+platform+contentType) entries')

    # G8 — Status consistency
    for shell in plan.get('assetShells', []):
        for field in ['captionStatus', 'visualStatus', 'approvalStatus', 'publishStatus']:
            ok &= gate_check('G8', field in shell and shell[field] is not None,
                             f'{shell["assetId"]}: missing or null field "{field}"')

    return ok


# ─── Blueprint Generator ──────────────────────────────────────────────────────

def get_credentials():
    with open(CONFIG) as f:
        cfg = json.load(f)
    v = cfg['models']['providers']['minimax-portal']
    return ''.join(v['apiKey']), v['baseUrl']

def call_model(messages):
    api_key, base_url = get_credentials()
    url = f"{base_url}/v1/messages?model={MODEL}"
    body = json.dumps({
        "messages": messages,
        "max_tokens": 4000,
        "thinking": {"type": "enabled", "budget_tokens": 16000}
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'anthropic-version': '2023-06-01',
        'user': 'production-plan-generator'
    })
    with urllib.request.urlopen(req, timeout=150) as resp:
        result = json.loads(resp.read())
    text_blocks = [c for c in result['content'] if c.get('type') == 'text' and c.get('text')]
    if not text_blocks:
        raise ValueError(f'No text block in response: {result["content"]}')
    return text_blocks[0]['text']

def strip_markdown(text):
    text = text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:])
        text = text.strip()
        if text.endswith('```'):
            text = text[:-3].strip()
    text = re.sub(r'```[a-z]*', '', text).strip()
    return text

def parse_json_with_retry(response_text, max_retries=2):
    for attempt in range(max_retries):
        cleaned = strip_markdown(response_text) if attempt == 0 else response_text
        last_brace = cleaned.rfind('}')
        if last_brace > 0:
            cleaned = cleaned[:last_brace+1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  JSON parse attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                raise
    return None


def build_prompt(campaign, campaign_id, platform_rules, real_image_rule):
    bp        = campaign.get('blueprint', {})
    dna       = bp.get('dna', {})
    pillars   = bp.get('pillars', [])
    vis_dir   = bp.get('visualDirection', {})
    brief     = campaign.get('brief', {})
    identity  = campaign.get('identity', {})
    name      = identity.get('name', 'Untitled')
    platforms = identity.get('platforms', [])
    plan_start = identity.get('planStartDate') or datetime.now(timezone.utc).strftime('%Y-%m-%d')

    pillar_txt = '\n'.join(f'  - {p["id"]}: {p["name"]} — {p.get("description","")[:80]}' for p in pillars)

    return f"""You are a content production planner. Generate a 30-day production plan for campaign: {name}

## Campaign Blueprint

**Tone:** {dna.get('tone', '—')}
**Content Mix:** {dna.get('contentMix', '—')}
**CTA Philosophy:** {dna.get('ctaPhilosophy', '—')}

**Platforms:** {', '.join(platforms)}
**Primary Offer:** {(campaign.get('strategy') or {}).get('primaryOffer', '—')}

**Campaign Type:** {identity.get('campaignType', 'Awareness')}
**Success Target:** {brief.get('successTarget', '—')}

## Pillars

{pillar_txt}

## Visual Direction

**Mood:** {vis_dir.get('mood', '—')}
**Creative Direction:** {vis_dir.get('creativeDirection', '—')[:200]}
**Color Usage:** {vis_dir.get('colorUsage', '—')[:150]}
**Image References:** {' | '.join(vis_dir.get('imageReferences', [])[:3])}

## Real Image Rule

{real_image_rule}

## Platform Publishing Rules

{platform_rules}

---

Generate a complete production plan in this EXACT JSON format — no markdown, no explanation:

{{
  "productionPlan": {{
    "planVersion": 1,
    "generatedAt": "{datetime.now(timezone.utc).isoformat()}",
    "modelUsed": "{MODEL}",
    "planStatus": "draft",
    "assetRequirements": {{
      "feedPosts": {{ "count": N, "platforms": ["instagram"], "realImageNeeded": true/false, "aiImageAllowed": true/false }},
      "carousels": {{ "count": N, "slides": N, "platforms": ["instagram"], "realImageNeeded": true/false, "aiImageAllowed": true/false }},
      "reels": {{ "count": N, "durationSec": N, "platforms": ["instagram","tiktok"], "realImageNeeded": true/false, "aiImageAllowed": true/false }},
      "stories": {{ "count": N, "platforms": ["instagram"], "realImageNeeded": false, "aiImageAllowed": true }},
      "gmbPosts": {{ "count": N, "platforms": ["gmb"], "realImageNeeded": true, "aiImageAllowed": false }},
      "total": N
    }},
    "realImageRule": {{
      "enforced": true/false,
      "reason": "...",
      "aiAllowedFor": ["background", "layout", "concept-mood", "typography"],
      "aiForbiddenFor": ["club heads", "equipment on-face", "golfer likeness", "swing motion"]
    }},
    "calendar": [
      {{
        "date": "YYYY-MM-DD",
        "dayOfWeek": "Monday/Tuesday/etc",
        "platform": "instagram/tiktok/gmb",
        "contentType": "feed-post/carousel/reel/story/gmb-post",
        "pillar": "p1/p2/p3/p4/p5",
        "pillarName": "Pillar Name",
        "assetId": "campaign-slug-platform-nn",
        "assetRequirement": "1-line specific brief referencing pillar and creative direction",
        "captionStatus": "pending",
        "visualStatus": "pending",
        "approvalStatus": "pending",
        "publishStatus": "planned"
      }}
      // 29 more entries — spread across 30 days, weekdays heavier, weekends lighter
      // GMB posts on Monday/Tuesday for visibility
      // Rotate through all 5 pillars, weighted by contentMix percentages
    ],
    "assetShells": [
      // One shell per calendar entry, all fields populated:
      {{
        "assetId": "campaign-slug-platform-nn",
        "campaignId": {campaign_id},
        "name": "Platform ContentType — Pillar Hook",
        "assetType": "feed-post/carousel/reel/story/gmb-post",
        "pillar": "p1/p2/etc",
        "pillarName": "Full Pillar Name",
        "objective": "What this piece achieves strategically. 1 sentence.",
        "requiredVisual": "Specific 1-line brief referencing campaign creativeDirection and imageReferences. Be vivid and specific.",
        "realImageNeeded": true/false,
        "aiImageAllowed": true/false,
        "aiAllowedFor": ["background", "layout", "concept-mood", "typography"],
        "aiForbiddenFor": ["club heads", "equipment on-face", "golfer likeness", "swing motion"],
        "realPhotoBrief": "For assets requiring real photography: 1-2 sentence brief for photographer or image source. Be specific about what must be captured.",
        "captionStatus": "pending",
        "captionRequired": true,
        "copyRequirement": "What this caption needs to achieve. 1 sentence.",
        "captionLength": "e.g. 150-200 chars / 280 max / no limit",
        "captionTone": "e.g. witty revelation / direct CTA / educational",
        "visualStatus": "pending",
        "approvalStatus": "pending",
        "publishStatus": "planned",
        "owner": "copywriter/image-gen/christelle",
        "dueDate": "YYYY-MM-DD",
        "plannedDate": "YYYY-MM-DD",
        "platform": "instagram/tiktok/gmb",
        "status": "planned",
        "qualityGateState": "pending",
        "history": [
          {{ "action": "shell-created", "by": "M5-generator", "at": "{datetime.now(timezone.utc).isoformat()}" }}
        ]
      }}
    ]
  }}
}}

Rules:
- calendar.length must be exactly 30
- All assetIds in calendar must exist in assetShells
- Every pillar (p1-p5) must appear at least once
- Every platform in identity.platforms must have calendar entries
- No duplicate (date + platform + contentType) combinations
- realImageNeeded must be true for equipment/product campaigns
- Caption and visual status must both be "pending" for all shells
- Dates must be sequential weekdays from planStartDate
- Due dates must be 2-3 days before plannedDate
- Answer ONLY with valid JSON. No markdown fences."""


def compute_asset_requirements(n_pillars):
    """Compute asset requirements from 30-day calendar schedule (Python-owned)."""
    # 30-day calendar schedule (exactly 30 entries):
    # Mon: GMB, Tue: GMB → 4 Mon + 5 Tue = 9 GMB
    # Wed: feed, Thu: carousel, Fri: feed → 5 Wed + 4 Thu + 5 Fri = 9 feed + 4 carousel
    # Alternate Fri: reel → 2 reels
    # Sat: story, Sun: story → 4 Sat + 4 Sun = 8 stories
    # Extra: 4 feed-post for pillar diversity = 40 total
    return {
        'feed-post': 9 + 4,   # 9 from calendar + 4 extra for pillar rotation
        'carousel':  4,
        'reel':      2,
        'story':     8,
        'gmb-post':  9,
        'total':     36
    }


def build_calendar_python(assets, pillars, start_date):
    """Build 30-day calendar using Python (source of truth)."""
    by_type = {'feed-post': [], 'carousel': [], 'reel': [], 'story': [], 'gmb-post': []}
    for aid, a in assets.items():
        ct = a.get('contentType', 'feed-post')
        if ct in by_type:
            by_type[ct].append(a)
    for ct in by_type:
        by_type[ct].sort(key=lambda x: x['assetId'])

    idx = {ct: 0 for ct in by_type}

    def next_asset(ct):
        lst = by_type.get(ct, [])
        i = idx.get(ct, 0)
        if i < len(lst):
            idx[ct] = i + 1
            return lst[i]
        return None

    # Schedule: Mon=GMB, Tue=GMB, Wed=feed, Thu=carousel, Fri=feed+reel(weeks 1,3), Sat/Sun=story
    day_schedule = {
        0: [('gmb-post', 'gmb')],
        1: [('gmb-post', 'gmb')],
        2: [('feed-post', 'instagram')],
        3: [('carousel', 'instagram')],
        4: [('feed-post', 'instagram'), ('reel', 'instagram')],  # reel weeks 1,3 only
        5: [('story', 'instagram')],
        6: [('story', 'instagram')],
    }

    calendar = []
    for i in range(30):
        current = start_date + timedelta(days=i)
        dow = current.weekday()
        items = list(day_schedule.get(dow, [('feed-post', 'instagram')]))
        # Reels on Fridays of week 1 and week 3 only (i=4, i=18)
        if dow == 4 and i not in [4, 18]:
            items = [items[0]]

        for ct, platform in items:
            asset = next_asset(ct)
            if not asset:
                continue
            p_idx = len(calendar) % max(len(pillars), 1)
            pillar = pillars[p_idx] if pillars else {'id': 'p1', 'name': 'Pillar 1'}
            calendar.append({
                'date': current.isoformat(),
                'dayOfWeek': current.strftime('%A'),
                'platform': platform,
                'contentType': ct,
                'pillar': asset.get('pillar') or pillar.get('id', ''),
                'pillarName': asset.get('pillarName') or pillar.get('name', ''),
                'assetId': asset.get('assetId', ''),
                'assetRequirement': asset.get('objective', ''),
                'captionStatus': 'pending',
                'visualStatus': 'pending',
                'approvalStatus': 'pending',
                'publishStatus': 'planned'
            })
    return calendar


def build_asset_shells_python(campaign_id, requirements, pillars, campaign):
    """Generate asset shells in Python (source of truth for counts/ids)."""
    campaign_type = campaign.get('identity', {}).get('campaignType', '')
    # Primary signal: memory flag. Fallback: campaignType keyword match
    is_equipment = campaign.get('memory', {}).get('requiresRealProductImage', False) or \
                  campaign_type in ('equipment', 'fitting', 'club-fitting', 'product', 'equipment-fitting', 'product-launch')
    idx = {'feed-post': 1, 'carousel': 1, 'reel': 1, 'story': 1, 'gmb-post': 1}
    shells = []

    for ct, count in requirements.items():
        if ct == 'total' or count <= 0:
            continue
        for i in range(count):
            num = str(idx[ct]).zfill(2)
            aid = f'{campaign_id}-{ct}-{num}'
            idx[ct] += 1
            p_idx = (i % max(len(pillars), 1))
            pillar = pillars[p_idx] if pillars else {'id': 'p1', 'name': 'Pillar 1'}

            shells.append({
                'assetId': aid,
                'campaignId': campaign_id,
                'name': f'{ct.replace("-"," ").title()} — {pillar.get("name","Pillar")}',
                'assetType': ct,
                'pillar': pillar.get('id', ''),
                'pillarName': pillar.get('name', ''),
                'objective': f'Execute on {pillar.get("name","this pillar")} — specific brief TBD from AI creative guidance',
                'requiredVisual': f'Visual for {ct} — campaign creative direction applies',
                'realImageNeeded': is_equipment and ct != 'story',
                'aiImageAllowed': ct == 'story' or not is_equipment,
                'captionStatus': 'pending',
                'visualStatus': 'pending',
                'approvalStatus': 'pending',
                'publishStatus': 'planned',
                'owner': 'copywriter',
                'platform': 'gmb' if ct == 'gmb-post' else 'instagram',
                'contentType': ct,
                'qualityGateState': 'pending',
                'history': [{'action': 'shell-created', 'by': 'M5-generator', 'at': datetime.now(timezone.utc).isoformat()}]
            })
    return shells


def generate_production_plan(campaign):
    """Python owns structure; AI generates per-pillar creative guidance only."""
    campaign_id = campaign.get('identity', {}).get('campaignId', '')
    pillars = campaign.get('blueprint', {}).get('pillars', []) or campaign.get('strategy', {}).get('pillars', [])
    n_pillars = max(len(pillars), 3)

    # Step 1: Compute requirements in Python (not AI)
    requirements = compute_asset_requirements(n_pillars)
    print(f"  Python-computed requirements: {requirements}")

    # Step 2: Generate asset shells in Python
    shells = build_asset_shells_python(campaign_id, requirements, pillars, campaign)
    print(f"  Python-generated {len(shells)} asset shells")

    # Step 3: Build calendar in Python
    start_date = datetime.now(timezone.utc).date()
    calendar = build_calendar_python({s['assetId']: s for s in shells}, pillars, start_date)
    print(f"  Python-built calendar: {len(calendar)} entries")

    # Step 4: Call AI for per-pillar creative guidance only
    campaign_type = campaign.get('identity', {}).get('campaignType', '')
    # Primary signal: memory flag. Fallback: campaignType keyword match
    is_equipment = campaign.get('memory', {}).get('requiresRealProductImage', False) or \
                  campaign_type in ('equipment', 'fitting', 'club-fitting', 'product', 'equipment-fitting', 'product-launch')

    pillar_txt = '\n'.join(f'  - {p["id"]}: {p["name"]} — {p.get("description","")[:100]}' for p in pillars)
    tone = campaign.get('blueprint', {}).get('dna', {}).get('tone', '—')
    vis_dir = campaign.get('blueprint', {}).get('visualDirection', {})

    creative_prompt = f"""You are a content strategist. For campaign: {campaign_id}

PILLARS:
{pillar_txt}

TONE: {tone}
VISUAL MOOD: {vis_dir.get('mood', '—')}
CREATIVE DIRECTION: {str(vis_dir.get('creativeDirection',''))[:200]}

For EACH pillar, generate creative guidance in this EXACT JSON format:
{{
  "pillarCreative": [
    {{
      "pillar": "p1",
      "pillarName": "...",
      "hook": "1-line scroll-stopper for this pillar (under 10 words, provocative or surprising)",
      "visualBrief": "Specific visual description for image-gen — include mood, composition, color palette, reference style. 2-3 sentences.",
      "keyMessage": "The single most important thing this pillar communicates. 1 sentence.",
      "copyDirection": "Tone and approach for captions: educational / provocative / social-proof / etc. 1-2 sentences.",
      "captionAngles": ["angle 1", "angle 2", "angle 3"]
    }}
    // ... one per pillar
  ]
}}

Answer ONLY with valid JSON. No markdown fences, no explanation."""

    messages = [{"role": "user", "content": creative_prompt}]
    print(f"  Calling {MODEL} for per-pillar creative guidance...")
    response = call_model(messages)
    print(f"  Response: {len(response)} chars")
    creative_data = parse_json_with_retry(response)

    # Step 5: Inject AI creative guidance into asset shells
    pillar_creative = {}
    if creative_data:
        for item in creative_data.get('pillarCreative', []):
            pillar_creative[item.get('pillar', '')] = item

    for shell in shells:
        pc = pillar_creative.get(shell.get('pillar'), {})
        if pc:
            shell['objective'] = pc.get('keyMessage', shell['objective'])
            shell['requiredVisual'] = pc.get('visualBrief', shell['requiredVisual'])
            shell['copyDirection'] = pc.get('copyDirection', '')
            shell['captionAngles'] = pc.get('captionAngles', [])
            if not shell.get('name') and pc.get('hook'):
                shell['name'] = f"{shell.get('contentType','').replace('-',' ').title()} -- {pc['hook'][:30]}"

            # Copy briefing fields (deterministic, not AI)
            LENGTH_MAP = {'feed-post': '150-220 chars', 'carousel': '100-150 chars per slide',
                          'reel': '80-120 chars (hook-first)', 'story': '150-200 chars',
                          'gmb-post': '200-350 chars (local SEO optimized)'}
            TONE_MAP = {'feed-post': 'conversational, edge-of-fairway wit',
                         'carousel': 'provocative, pattern interrupts',
                         'reel': 'urgent hook, pattern interrupt',
                         'story': 'off-the-cuff, authentic',
                         'gmb-post': 'informative, trust-building'}
            ct = shell.get('contentType', 'feed-post')
            caption_angles = shell.get('captionAngles', [])
            angle_str = ' | '.join(caption_angles[:2]) if caption_angles else shell.get('pillarName', '')
            shell['copyRequirement'] = f"Address: {angle_str}. Goal: {shell.get('copyDirection','')[:100]}"
            shell['captionLength'] = LENGTH_MAP.get(ct, '150-200 chars')
            shell['captionTone'] = TONE_MAP.get(ct, 'conversational')

    # Step 6: Assemble final production plan
    pp = {
        'planVersion': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelUsed': MODEL,
        'planStatus': 'draft',
        'assetRequirements': {
            'feedPosts': {'count': requirements['feed-post'], 'platforms': ['instagram'], 'realImageNeeded': is_equipment, 'aiImageAllowed': not is_equipment},
            'carousels': {'count': requirements['carousel'], 'slides': requirements['carousel'], 'platforms': ['instagram'], 'realImageNeeded': is_equipment, 'aiImageAllowed': not is_equipment},
            'reels': {'count': requirements['reel'], 'durationSec': 30, 'platforms': ['instagram', 'tiktok'], 'realImageNeeded': is_equipment, 'aiImageAllowed': not is_equipment},
            'stories': {'count': requirements['story'], 'platforms': ['instagram'], 'realImageNeeded': False, 'aiImageAllowed': True},
            'gmbPosts': {'count': requirements['gmb-post'], 'platforms': ['gmb'], 'realImageNeeded': True, 'aiImageAllowed': False},
            'total': requirements['total']
        },
        'realImageRule': {
            'enforced': is_equipment,
            'reason': 'Equipment/fitting campaign — real photography required for all product visuals' if is_equipment else 'Awareness campaign — AI permitted',
            'aiAllowedFor': ['background', 'layout', 'concept-mood', 'typography'] if is_equipment else ['all elements'],
            'aiForbiddenFor': ['club heads', 'equipment on-face', 'golfer likeness', 'swing motion'] if is_equipment else []
        },
        'calendar': calendar,
        'assetShells': shells
    }

    return {'productionPlan': pp}


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 generate-production-plan.py <campaignId> [--new]")
        sys.exit(1)

    campaign_id = args[0]
    force_new   = '--new' in args

    with open(DATA_FILE) as f:
        data = json.load(f)

    campaign = data['campaigns'].get(campaign_id)
    if not campaign:
        print(f"Campaign not found: {campaign_id}")
        sys.exit(1)

    bp = campaign.get('blueprint', {})

    # M5 Trigger Gate
    trigger_ok = (
        bp.get('blueprintVersion', 0) >= 1
        and bp.get('active') == True
        and bool(bp.get('dna'))
        and len(bp.get('pillars', [])) >= 3
    )
    if not trigger_ok:
        print("M5 trigger gate FAILED:")
        print(f"  blueprintVersion >= 1: {bp.get('blueprintVersion', 0) >= 1}")
        print(f"  active == true: {bp.get('active') == True}")
        print(f"  dna exists: {bool(bp.get('dna'))}")
        print(f"  pillars >= 3: {len(bp.get('pillars', [])) >= 3}")
        sys.exit(1)
    print(f"M5 trigger gate PASSED for {campaign_id}")

    # Check existing plan
    if campaign.get('productionPlan') and not force_new:
        print(f"Production plan already exists. Use --new to regenerate.")
        sys.exit(0)

    print(f"Generating production plan for: {campaign_id}")
    plan_data = generate_production_plan(campaign)

    # Validate with G1–G8
    errors = []
    gates_passed = validate_production_plan(plan_data.get('productionPlan', {}), campaign, errors)

    if not gates_passed:
        print(f"\nGATE FAILURES — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        print("\nRetrying with stricter prompt...")
        # Retry with error context
        retry_prompt = build_prompt(campaign, campaign_id,
            "PLATFORM RULES: Retry — previous plan failed validation. Ensure all G1-G8 rules pass.",
            "REAL IMAGE RULE: Retry — previous plan violated image rules.") + f"\n\nPREVIOUS ERRORS: {'; '.join(errors)}"
        messages = [{"role": "user", "content": retry_prompt}]
        response = call_model(messages)
        plan_data = parse_json_with_retry(response)
        errors2 = []
        gates_passed = validate_production_plan(plan_data.get('productionPlan', {}), campaign, errors2)
        if not gates_passed:
            print(f"FATAL: Production plan failed G1-G8 after retry: {errors2}")
            sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    pp  = plan_data['productionPlan']

    # Write productionPlan to campaign
    campaign['productionPlan'] = pp

    # Write asset shells to campaign.assets
    assets = campaign.get('assets', {})
    for shell in pp.get('assetShells', []):
        assets[shell['assetId']] = shell
    campaign['assets'] = assets

    # Memory note
    memory = campaign.get('memory', {'notes': []})
    memory.setdefault('notes', []).append({
        'type': 'production-plan-generated',
        'timestamp': now,
        'detail': 'M5 production plan v' + str(pp.get('planVersion')) + ' generated. ' +
                  str((pp.get('assetRequirements') or {}).get('total', 0)) + ' assets, ' +
                  str(len(pp.get('calendar', []))) + ' calendar entries.'
    })
    campaign['memory'] = memory

    # Pipeline update
    campaign['pipeline'] = {
        'status': 'generatingM5',
        'currentStep': 2,
        'totalSteps': 4,
        'currentAgent': 'Clawfix'
    }

    data['updatedAt'] = now

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    ar = pp.get('assetRequirements', {})
    print(f"\nProduction plan v{pp.get('planVersion')} written for: {campaign_id}")
    print(f"  Total assets: {ar.get('total', '?')}")
    print(f"  Feed posts: {(ar.get('feedPosts') or {}).get('count','?')}")
    print(f"  Carousels: {(ar.get('carousels') or {}).get('count','?')}")
    print(f"  Reels: {(ar.get('reels') or {}).get('count','?')}")
    print(f"  Stories: {(ar.get('stories') or {}).get('count','?')}")
    print(f"  GMB posts: {(ar.get('gmbPosts') or {}).get('count','?')}")
    print(f"  Calendar entries: {len(pp.get('calendar',[]))}")
    print(f"  Asset shells: {len(pp.get('assetShells',[]))}")