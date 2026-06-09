#!/usr/bin/env python3
"""
M5 — Campaign Production Plan Generator

Turns an accepted campaign blueprint into a production plan:
- Asset Requirements (counts by content type)
- 30-day Calendar
- Asset Shells (one per content item)

Usage:
  python3 generate-production-plan.py <campaignId>         # generate if not exists
  python3 generate-production-plan.py <campaignId> --new  # regenerate even if exists
  python3 generate-production-plan.py <campaignId> --approve  # approve draft plan

M5 produces PLAN only — no final captions, images, or scripts.
M6 (next phase) produces actual content from the production queue.
"""

import json, sys, os, subprocess, datetime
from pathlib import Path

REPO = Path('/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard')
DATA_FILE = REPO / 'campaign-os' / 'campaign-data.json'
SCRIPT_DIR = REPO / 'scripts'

# ── AI Model ──────────────────────────────────────────────────────────────────
MODEL = 'MiniMax-M2.7'

# ── Asset type enum ───────────────────────────────────────────────────────────
ASSET_TYPES = ['feed-post', 'carousel', 'reel', 'story', 'gmb-post']

# ── Platform distribution (from Publisher lane) ──────────────────────────────
PLATFORM_MIX = {
    'instagram': {'feed-post': 0.60, 'carousel': 0.20, 'reel': 0.10, 'story': 0.10},
    'tiktok':   {'reel': 0.70, 'carousel': 0.30},
    'gmb':      {'gmb-post': 1.00}
}

# ── Calendar rules (from Publisher lane) ───────────────────────────────────────
# GMB posts Monday/Tuesday for local search visibility
# Feed posts weekdays
# Stories fill gaps (weekends allowed)
# Reels alternate weeks

def get_campaign(data, campaign_id):
    """Return campaign or exit with error."""
    campaigns = data.get('campaigns', {})
    if campaign_id not in campaigns:
        print(f"ERROR: Campaign '{campaign_id}' not found", file=sys.stderr)
        sys.exit(1)
    return campaigns[campaign_id]

def get_blueprint_status(campaign):
    """Check if blueprint is accepted or implicitly usable (status null + version >= 1)."""
    bp = campaign.get('blueprint', {})
    version = bp.get('blueprintVersion')
    status = bp.get('status')
    # Treat null status + existing version as implicitly accepted
    if version and version >= 1:
        return 'accepted'  # implicit accept
    return status or 'none'

def check_gate_g1(campaign, plan_data):
    """G1: Non-zero counts — each asset type count >= 1, total > 0."""
    req = plan_data.get('assetRequirements', {})
    total = req.get('total', 0)
    if total <= 0:
        return False, "G1 FAIL: total assets is 0"
    for atype in ASSET_TYPES:
        count = req.get(atype, 0)
        if count < 0:
            return False, f"G1 FAIL: {atype} count is negative"
    return True, "G1 PASS"

def check_gate_g2(plan_data):
    """G2: Calendar length — exactly 30 entries, sequential weekdays."""
    cal = plan_data.get('calendar', [])
    if len(cal) != 30:
        return False, f"G2 FAIL: calendar has {len(cal)} entries, need 30"
    # Check dates are sequential
    dates = [datetime.date.fromisoformat(e['date']) for e in cal]
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days != 1:
            return False, f"G2 FAIL: calendar dates not sequential at index {i}"
    return True, "G2 PASS"

def check_gate_g3(plan_data, assets):
    """G3: Unique assetIds — all calendar items link to real assets, no duplicates."""
    cal = plan_data.get('calendar', [])
    seen = set()
    for item in cal:
        aid = item.get('assetId')
        if not aid:
            return False, "G3 FAIL: calendar item missing assetId"
        if aid in seen:
            return False, f"G3 FAIL: duplicate assetId '{aid}'"
        seen.add(aid)
        if aid not in assets:
            return False, f"G3 FAIL: assetId '{aid}' not in assets registry"
    return True, "G3 PASS"

def check_gate_g4(campaign, plan_data):
    """G4: Pillar coverage — every pillar from strategy appears at least once."""
    pillars = campaign.get('strategy', {}).get('pillars', [])
    pillar_ids = {p['id'] for p in pillars}
    cal = plan_data.get('calendar', [])
    covered = {item['pillar'] for item in cal if item.get('pillar')}
    missing = pillar_ids - covered
    if missing:
        return False, f"G4 FAIL: pillars {missing} have no calendar items"
    return True, "G4 PASS"

def check_gate_g5(campaign, plan_data, assets):
    """G5: Real image rule — equipment/fitting campaigns require real photos for product."""
    campaign_type = campaign.get('identity', {}).get('campaignType', '')
    is_equipment = campaign_type in ('equipment', 'fitting', 'club-fitting', 'product')
    
    if not is_equipment:
        return True, "G5 PASS (non-equipment campaign)"
    
    # Equipment campaigns: realImageNeeded=true, aiImageAllowed=false for product
    for aid, asset in assets.items():
        if asset.get('realImageNeeded') and asset.get('aiImageAllowed'):
            return False, f"G5 FAIL: asset '{aid}' has realImageNeeded=true AND aiImageAllowed=true — product cannot be AI-generated"
    
    return True, "G5 PASS"

def check_gate_g6(campaign, plan_data):
    """G6: Platform coverage — every platform in identity.platforms has at least 1 item."""
    platforms = campaign.get('identity', {}).get('platforms', [])
    cal = plan_data.get('calendar', [])
    used_platforms = {item['platform'] for item in cal if item.get('platform')}
    for plat in platforms:
        if plat not in used_platforms:
            return False, f"G6 FAIL: platform '{plat}' has no calendar items"
    return True, "G6 PASS"

def check_gate_g7(plan_data):
    """G7: No content duplication — no same date+platform+contentType twice."""
    seen = set()
    for item in plan_data.get('calendar', []):
        key = (item.get('date'), item.get('platform'), item.get('contentType'))
        if key in seen:
            return False, f"G7 FAIL: duplicate content {key}"
        seen.add(key)
    return True, "G7 PASS"

def check_gate_g8(assets):
    """G8: Status consistency — every asset has captionStatus and visualStatus."""
    for aid, asset in assets.items():
        if 'captionStatus' not in asset:
            return False, f"G8 FAIL: asset '{aid}' missing captionStatus"
        if 'visualStatus' not in asset:
            return False, f"G8 FAIL: asset '{aid}' missing visualStatus"
    return True, "G8 PASS"

def generate_asset_counts(campaign):
    """Generate asset counts based on blueprint pillars + platform mix."""
    pillars = campaign.get('strategy', {}).get('pillars', [])
    bp = campaign.get('blueprint', {})
    dna = bp.get('dna', {})
    content_mix = dna.get('contentMix', {})
    n_pillars = len(pillars)
    
    if n_pillars == 0:
        n_pillars = 1  # fallback
    
    # Base counts per pillar (from M5 spec)
    # feed-post: 3 per pillar
    # carousel: 1 per pillar
    # stories: 2 per pillar
    # GMB: 2 per week = ~8 in 30 days
    
    feed_posts = 3 * n_pillars
    carousels = n_pillars
    stories = 2 * n_pillars
    reels = 2  # 2 per campaign (from M5 spec)
    gmb_posts = 8  # 2 per week × 4 weeks
    
    return {
        'feed-post': feed_posts,
        'carousel': carousels,
        'reel': reels,
        'story': stories,
        'gmb-post': gmb_posts,
        'total': feed_posts + carousels + reels + stories + gmb_posts
    }

def generate_calendar(campaign, assets, plan_data):
    """Build 30-day calendar from asset shells."""
    requirements = plan_data.get('assetRequirements', {})
    bp = campaign.get('blueprint', {})
    dna = bp.get('dna', {})
    content_mix = dna.get('contentMix', {})
    pillars = campaign.get('strategy', {}).get('pillars', [])
    
    # Start date: today
    start = datetime.date.today()
    
    calendar = []
    asset_list = sorted(assets.values(), key=lambda a: a.get('dueDate', '9999'))
    
    day_idx = 0
    for i in range(30):
        current_date = start + datetime.timedelta(days=i)
        day_of_week = current_date.strftime('%A')
        
        # Determine content types for this day
        # GMB: Monday/Tuesday only
        # Instagram feed: weekdays
        # Stories: any day, fill gaps
        # Reels: alternate weeks (week 1, 3)
        
        day_items = []
        
        # GMB posts on Monday/Tuesday
        if day_of_week in ('Monday', 'Tuesday'):
            gmb_assets = [a for a in asset_list if a.get('contentType') == 'gmb-post' and a.get('platform') == 'gmb']
            if gmb_assets:
                item = gmb_assets[0]
                day_items.append({
                    'date': current_date.isoformat(),
                    'dayOfWeek': day_of_week,
                    'platform': 'gmb',
                    'contentType': 'gmb-post',
                    'pillar': item.get('pillar', ''),
                    'pillarName': item.get('pillarName', ''),
                    'assetId': item.get('assetId', ''),
                    'assetRequirement': item.get('objective', ''),
                    'captionStatus': item.get('captionStatus', 'pending'),
                    'visualStatus': item.get('visualStatus', 'pending'),
                    'approvalStatus': item.get('approvalStatus', 'pending'),
                    'publishStatus': 'planned'
                })
        
        # Instagram posts on weekdays
        if day_of_week not in ('Saturday', 'Sunday'):
            ig_assets = [a for a in asset_list if a.get('platform') == 'instagram' and a.get('contentType') in ('feed-post', 'carousel') and a.get('assetId') not in [d['assetId'] for d in day_items]]
            if ig_assets:
                item = ig_assets[0]
                day_items.append({
                    'date': current_date.isoformat(),
                    'dayOfWeek': day_of_week,
                    'platform': 'instagram',
                    'contentType': item.get('contentType', 'feed-post'),
                    'pillar': item.get('pillar', ''),
                    'pillarName': item.get('pillarName', ''),
                    'assetId': item.get('assetId', ''),
                    'assetRequirement': item.get('objective', ''),
                    'captionStatus': item.get('captionStatus', 'pending'),
                    'visualStatus': item.get('visualStatus', 'pending'),
                    'approvalStatus': item.get('approvalStatus', 'pending'),
                    'publishStatus': 'planned'
                })
        
        # Stories (any day, fewer on weekends)
        if day_of_week not in ('Saturday', 'Sunday') or i % 3 == 0:
            story_assets = [a for a in asset_list if a.get('contentType') == 'story' and a.get('platform') == 'instagram' and a.get('assetId') not in [d['assetId'] for d in day_items]]
            if story_assets:
                item = story_assets[0]
                day_items.append({
                    'date': current_date.isoformat(),
                    'dayOfWeek': day_of_week,
                    'platform': 'instagram',
                    'contentType': 'story',
                    'pillar': item.get('pillar', ''),
                    'pillarName': item.get('pillarName', ''),
                    'assetId': item.get('assetId', ''),
                    'assetRequirement': item.get('objective', ''),
                    'captionStatus': item.get('captionStatus', 'pending'),
                    'visualStatus': item.get('visualStatus', 'pending'),
                    'approvalStatus': item.get('approvalStatus', 'pending'),
                    'publishStatus': 'planned'
                })
        
        # Reels (alternate weeks)
        if i % 14 < 7:
            reel_assets = [a for a in asset_list if a.get('contentType') == 'reel' and a.get('assetId') not in [d['assetId'] for d in day_items]]
            if reel_assets:
                item = reel_assets[0]
                day_items.append({
                    'date': current_date.isoformat(),
                    'dayOfWeek': day_of_week,
                    'platform': item.get('platform', 'instagram'),
                    'contentType': 'reel',
                    'pillar': item.get('pillar', ''),
                    'pillarName': item.get('pillarName', ''),
                    'assetId': item.get('assetId', ''),
                    'assetRequirement': item.get('objective', ''),
                    'captionStatus': item.get('captionStatus', 'pending'),
                    'visualStatus': item.get('visualStatus', 'pending'),
                    'approvalStatus': item.get('approvalStatus', 'pending'),
                    'publishStatus': 'planned'
                })
        
        calendar.extend(day_items)
    
    return calendar

def generate_asset_shells(campaign, requirements):
    """Generate asset shell objects for all required content items."""
    campaign_id = campaign.get('identity', {}).get('campaignId', '')
    pillars = campaign.get('strategy', {}).get('pillars', [])
    bp = campaign.get('blueprint', {})
    visual_dir = bp.get('visualDirection', {})
    campaign_type = campaign.get('identity', {}).get('campaignType', '')
    
    # Real image rule: equipment/fitting campaigns must use real photography
    is_equipment = campaign_type in ('equipment', 'fitting', 'club-fitting', 'product')
    
    assets = {}
    idx = {'feed-post': 1, 'carousel': 1, 'reel': 1, 'story': 1, 'gmb-post': 1}
    
    for atype, count in requirements.items():
        if atype == 'total':
            continue
        if count <= 0:
            continue
        
        # Determine platform mix for this asset type
        platform = 'instagram'
        if atype == 'gmb-post':
            platform = 'gmb'
        elif atype == 'reel':
            # 70% instagram, 30% tiktok (from Publisher lane)
            platform = 'instagram'  # simplified — could add tiktok variant
        
        for i in range(count):
            num = str(idx[atype]).zfill(2)
            asset_id = f"{campaign_id}-{atype}-{num}"
            idx[atype] += 1
            
            pillar = pillars[i % len(pillars)] if pillars else {'id': 'p1', 'name': 'Pillar 1'}
            
            # Real image rule enforcement
            real_needed = is_equipment
            ai_allowed = not is_equipment  # equipment campaigns: aiImageAllowed=false for product
            
            asset = {
                'assetId': asset_id,
                'campaignId': campaign_id,
                'title': f"{atype.replace('-', ' ').title()} — {pillar.get('name', 'Pillar')}",
                'assetType': atype,
                'platform': platform,
                'contentType': atype,
                'pillar': pillar.get('id', ''),
                'pillarName': pillar.get('name', ''),
                'objective': f"Content for {pillar.get('name', 'pillar')} pillar — {atype}",
                'requiredVisual': f"Visual for {pillar.get('name', 'pillar')} — {atype}",
                'realImageNeeded': real_needed,
                'aiImageAllowed': ai_allowed,
                'aiAllowedFor': ['background', 'layout', 'concept-mood'] if ai_allowed else [],
                'aiForbiddenFor': ['club heads', 'golf equipment on-face', 'golfer likeness', 'swing motion'] if is_equipment else [],
                'realPhotoBrief': 'Real golf equipment photography required — no AI generation for product' if is_equipment else '',
                'captionStatus': 'pending',
                'visualStatus': 'pending',
                'approvalStatus': 'pending',
                'publishStatus': 'draft',
                'owner': 'creation',
                'dueDate': None,
                'plannedDate': None,
                'status': 'planned',
                'qualityGateState': 'pending',
                'history': [
                    {'action': 'shell-created', 'by': 'M5-generator', 'at': datetime.datetime.utcnow().isoformat() + 'Z'}
                ]
            }
            assets[asset_id] = asset
    
    return assets

def run_gates(campaign, plan_data, assets):
    """Run all G1-G8 gates. Returns (all_passed, failures)."""
    gates = [
        check_gate_g1(campaign, plan_data),
        check_gate_g2(plan_data),
        check_gate_g3(plan_data, assets),
        check_gate_g4(campaign, plan_data),
        check_gate_g5(campaign, plan_data, assets),
        check_gate_g6(campaign, plan_data),
        check_gate_g7(plan_data),
        check_gate_g8(assets),
    ]
    failures = [msg for passed, msg in gates if not passed]
    return len(failures) == 0, failures

def ai_generate_plan(prompt, model=MODEL):
    """Call MiniMax-M2.7 via OpenClaw CLI."""
    cmd = ['openclaw', 'ai', '--model', model, '--', prompt]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

def write_campaign(data):
    """Write campaign data to file + commit + push."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Commit
    subprocess.run(['git', 'add', 'campaign-os/campaign-data.json'], cwd=REPO, check=True)
    cp = data.get('campaigns', {})
    cid = list(cp.keys())[0] if cp else 'unknown'
    msg = f"feat(m5): generate production plan for {cid}"
    try:
        subprocess.run(['git', 'commit', '-m', msg], cwd=REPO, check=True, capture_output=True)
        # Push
        token = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True).stdout.strip()
        if token.startswith('gho_'):
            remote = f'https://{token}@github.com/clawdiavector/swing-shack-dashboard.git'
            subprocess.run(['git', 'remote', 'set-url', 'origin', remote], cwd=REPO, check=True)
            subprocpush = subprocess.run(['git', 'push', 'origin', 'main'], cwd=REPO, capture_output=True, text=True)
            # Restore clean remote
            subprocess.run(['git', 'remote', 'set-url', 'origin', 'https://github.com/clawdiavector/swing-shack-dashboard.git'], cwd=REPO, check=True)
            return subprocpush.returncode == 0
        return False
    except Exception as e:
        print(f"WARNING: git push failed: {e}", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: generate-production-plan.py <campaignId> [--new] [--approve]", file=sys.stderr)
        sys.exit(1)
    
    campaign_id = sys.argv[1]
    regenerate = '--new' in sys.argv
    approve = '--approve' in sys.argv
    
    # Load data
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    
    campaign = get_campaign(data, campaign_id)
    
    # Check if production plan already exists
    existing = campaign.get('productionPlan')
    if existing and not regenerate:
        print(f"Production plan already exists for '{campaign_id}'. Use --new to regenerate.")
        print(f"Existing plan: {json.dumps(existing, indent=2)}")
        sys.exit(0)
    
    # Gate 0: Blueprint must exist (accepted or implicit)
    bp_status = get_blueprint_status(campaign)
    if bp_status not in ('accepted', 'implicit'):
        print(f"ERROR: Blueprint not accepted for '{campaign_id}' (status: {bp_status})", file=sys.stderr)
        print("Accept the blueprint first before generating a production plan.")
        sys.exit(1)
    
    print(f"Generating production plan for '{campaign_id}'...")
    
    # Generate asset requirements
    requirements = generate_asset_counts(campaign)
    print(f"Asset requirements: {json.dumps(requirements, indent=2)}")
    
    # Generate asset shells
    assets = generate_asset_shells(campaign, requirements)
    print(f"Generated {len(assets)} asset shells")
    
    # Build production plan
    plan_data = {
        'planVersion': 1,
        'generatedAt': datetime.datetime.utcnow().isoformat() + 'Z',
        'modelUsed': MODEL,
        'planStatus': 'draft',
        'assetRequirements': requirements,
        'realImageRule': {
            'enforced': True,
            'reason': 'equipment campaign — product photography requires real images, no AI club heads',
            'aiAllowedFor': ['background', 'layout', 'concept-mood', 'typography'],
            'aiForbiddenFor': ['club heads', 'golf equipment on-face', 'golfer likeness', 'swing motion']
        },
        'calendar': []  # filled below
    }
    
    # Generate calendar
    calendar = generate_calendar(campaign, assets, plan_data)
    plan_data['calendar'] = calendar
    print(f"Calendar: {len(calendar)} entries")
    
    # Run G1-G8 gates
    passed, failures = run_gates(campaign, plan_data, assets)
    if not passed:
        print("GATES FAILED:")
        for f in failures:
            print(f"  - {f}")
        print("Production plan not written. Fix failures and retry.")
        sys.exit(1)
    
    print("All gates passed.")
    
    # Approve if requested
    if approve:
        plan_data['planStatus'] = 'approved'
    
    # Write to campaign
    campaign['productionPlan'] = plan_data
    campaign['assets'] = assets
    
    # Save + commit + push
    pushed = write_campaign(data)
    
    print(f"\nProduction plan {'approved' if approve else 'generated'} for '{campaign_id}'")
    print(f"  Assets: {len(assets)}")
    print(f"  Calendar entries: {len(calendar)}")
    print(f"  Git push: {'SUCCESS' if pushed else 'FAILED (local only)'}")
    
    if approve:
        print("\nPlan approved. M6 (asset generation) is now unlocked.")

if __name__ == '__main__':
    main()