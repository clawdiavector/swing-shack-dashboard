#!/usr/bin/env python3
"""
Campaign-Specific Blueprint Generator (M5) — with Blueprint Versioning

Every run creates a NEW version, preserving all previous versions in
campaign.memory.blueprintHistory. Active blueprint fields are kept in sync
with the latest version's data.

Schema:
  campaign.blueprint              — current active version
  campaign.memory.blueprintHistory — all previous versions (newest first)

Usage:
  python3 generate-blueprint.py <campaignId>           # create version 1 if none exists
  python3 generate-blueprint.py <campaignId> --new    # force new version
"""
import json, sys, os, re, urllib.request
from datetime import datetime, timezone

REPO_ROOT = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
DATA_FILE = os.path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json')
CONFIG    = '/Users/fivefriday/.openclaw-instance2/openclaw.json'

GENERIC_PILLAR_REJECT = [
    'value', 'proof', 'urgency', 'benefits', 'features',
    'awareness', 'consideration', 'conversion', 'social proof',
    'education', 'engagement', 'brand', 'visibility', 'reach'
]

MODEL = 'MiniMax-M2.7'

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
        'user': 'blueprint-generator'
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read())
    text_blocks = [c for c in result['content'] if c.get('type') == 'text']
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
            response_text = cleaned
    return None

def validate_blueprint(blueprint):
    errors = []
    for i, pillar in enumerate(blueprint.get('pillars', [])):
        name_lower = pillar.get('name', '').lower()
        for generic in GENERIC_PILLAR_REJECT:
            if name_lower == generic or name_lower.startswith(generic + ' '):
                errors.append(f'Pillar {i+1} generic name: "{pillar["name"]}"')
        if len(pillar.get('name', '')) < 10:
            errors.append(f'Pillar {i+1} name too short')
        if len(pillar.get('description', '')) < 30:
            errors.append(f'Pillar {i+1} description too short')
    tone = blueprint.get('dna', {}).get('tone', '').lower()
    for gt in ['authentic, informative, and persuasive', 'professional and friendly',
               'friendly and informative', 'educational and engaging']:
        if gt in tone:
            errors.append(f'Tone is generic: "{blueprint["dna"]["tone"]}"')
    palette = blueprint.get('visualDirection', {}).get('palette', {})
    placeholder_count = sum(1 for v in palette.values() if '#XXXXXX' in v)
    if placeholder_count > 0:
        errors.append(f'Palette has {placeholder_count} placeholder values')
    return errors

def build_prompt(campaign, is_retry=False, prior_errors=None):
    brief    = campaign.get('brief', {})
    ident    = campaign.get('identity', {})
    strat    = campaign.get('strategy', {})
    name          = ident.get('name', 'Untitled Campaign')
    goal_notes    = brief.get('goalNotes', '')
    context       = brief.get('context', '')
    audience      = brief.get('audience', '')
    primary_offer  = strat.get('primaryOffer', ident.get('primaryGoal', ''))
    platforms     = ident.get('platforms', [])
    platform_str  = ', '.join(platforms) if platforms else 'instagram'
    campaign_type = ident.get('campaignType', 'Awareness')

    type_palette_guidance = {
        'Awareness': 'Palette should feel thought-provoking with high contrast. Suggested anchor: bold primary (#FF6B35 warm orange for urgency), dark background (#0D0D0F), white text, gold accent (#D4AF37) for the solution moment.',
        'product-launch': 'Palette should feel premium and credible. Suggested anchor: chrome/silver tones with dark backgrounds, gold accent for price/quality signals.',
        'evergreen': 'Palette should feel trustworthy and consistent. Deep blue primary with warm accent.',
        'seasonal': 'Palette should feel timely and relevant, reflecting the season\'s mood while maintaining Swing Shack brand identity.',
        'promo': 'Palette should feel urgent and action-driving. High-contrast with dominant urgency colour, clear CTAs.',
        'event': 'Palette should feel event-worthy and social. Vibrant colours that stand out in feed.',
    }
    palette_guidance = type_palette_guidance.get(
        campaign_type,
        'Use the campaign type, goal notes, and context to determine appropriate colours.'
    )

    retry_note = ''
    if is_retry and prior_errors:
        retry_note = f'\n\nIMPORTANT: Your previous output was rejected. Errors: {"; ".join(prior_errors)}. Generate completely fresh, specific output. No generic labels.'

    return f"""You are a strategic campaign architect. Generate a complete campaign blueprint for:

Campaign: {name}
Platforms: {platform_str}
Campaign Type: {campaign_type}
Primary Offer: {primary_offer}

Goal Notes:
{goal_notes}

Campaign Theme & Context:
{context}

Target Audience:
{audience}

Palette Guidance:
{palette_guidance}{retry_note}

Think deeply about what makes THIS campaign unique. What is the specific argument it makes? What tension does it exploit? What does a golfer feel? What should they think after? What colours match this campaign's emotional register?

Generate a complete, campaign-specific blueprint in this exact JSON format — no markdown, no explanation, just the JSON:

{{
  "dna": {{
    "tone": "A specific, evocative tone description. 10-20 words. This is how the copy VOICES. Not generic.",
    "contentMix": "XX% [type] / XX% [type] / XX% [type] / XX% [type] — specific to this campaign's conversion path",
    "requiredContentTypes": ["type-a", "type-b", "type-c"],
    "preferredVisualStyles": ["style-a", "style-b", "style-c"],
    "forbiddenVisualStyles": ["style-to-avoid-a", "style-to-avoid-b"],
    "ctaPhilosophy": "How the CTA should feel and what it should say. 1-2 sentences. Campaign-specific.",
    "platformStrategy": {{
      "instagram": "Specific guidance for this campaign on Instagram. 1-2 sentences.",
      "tiktok": "Specific guidance for this campaign on TikTok. 1-2 sentences.",
      "gmb": "Specific guidance for this campaign on GMB. 1-2 sentences."
    }},
    "exampleHighPerforming": [],
    "exampleLowPerforming": []
  }},
  "visualDirection": {{
    "palette": {{
      "primary": "#XXXXXX",
      "secondary": "#XXXXXX",
      "accent": "#XXXXXX",
      "background": "#XXXXXX",
      "text": "#XXXXXX"
    }},
    "mood": "A vivid, campaign-specific mood. 5-12 words.",
    "creativeDirection": "A vivid description of exactly what the visuals should show, referencing the campaign theme. 3-5 sentences. Be specific.",
    "imageReferences": ["specific image reference a", "specific image reference b", "specific image reference c"],
    "colorUsage": "How to use the palette specifically for this campaign. 2-3 sentences. Why these colours for THIS campaign.",
    "typography": "Typeface guidance specific to this campaign. 1-2 sentences.",
    "layoutStyle": "Layout guidance specific to this campaign. 1-2 sentences.",
    "contentExamples": ["example post idea a", "example post idea b", "example post idea c"]
  }},
  "pillars": [
    {{"id": "p1", "name": "Pillar Name — specific to this campaign's argument", "description": "What this pillar owns strategically. 1-2 sentences. Be specific."}},
    {{"id": "p2", "name": "Pillar Name — specific to this campaign's argument", "description": "What this pillar owns strategically. 1-2 sentences. Be specific."}},
    {{"id": "p3", "name": "Pillar Name — specific to this campaign's argument", "description": "What this pillar owns strategically. 1-2 sentences. Be specific."}},
    {{"id": "p4", "name": "Pillar Name — specific to this campaign's argument", "description": "What this pillar owns strategically. 1-2 sentences. Be specific."}},
    {{"id": "p5", "name": "Pillar Name — specific to this campaign's argument", "description": "What this pillar owns strategically. 1-2 sentences. Be specific."}}
  ]
}}

Rules — these will be validated:
- Tone must be specific — NOT "authentic, informative, and persuasive"
- Pillars must emerge from the campaign theme — NOT "Value, Proof, Urgency" (rejected)
- Pillar names must be descriptive — NOT single generic words
- creativeDirection must reference the specific campaign theme
- imageReferences must be specific to this campaign's angle
- colorUsage must explain WHY these colours for THIS campaign
- Palette must use real hex values — not #XXXXXX placeholders
- Answer ONLY with valid JSON. No markdown fences. No preamble."""

def generate_blueprint(campaign, is_retry=False, prior_errors=None):
    prompt = build_prompt(campaign, is_retry, prior_errors)
    messages = [{"role": "user", "content": prompt}]
    print(f"  Calling {MODEL}...")
    response = call_model(messages)
    print(f"  Response: {len(response)} chars")
    blueprint = parse_json_with_retry(response)
    errors = validate_blueprint(blueprint)
    if errors:
        print(f"  Quality gate failed: {errors}")
        if not is_retry:
            return generate_blueprint(campaign, is_retry=True, prior_errors=errors)
        raise ValueError(f"Blueprint quality gate failed after retry: {errors}")
    return blueprint

def diff_summary(blueprint):
    """One-line summary of what makes this blueprint different."""
    tone = blueprint.get('dna', {}).get('tone', '')[:40]
    pillars = ' / '.join(p['name'].split(' — ')[0] for p in blueprint.get('pillars', [])[:3])
    return f"Tone: {tone} | Pillars: {pillars}"

def current_blueprint_version(campaign):
    return campaign.get('blueprint', {}).get('blueprintVersion', 0)

def archive_blueprint(campaign):
    current = campaign.get('blueprint')
    if not current:
        return
    v = current.get('blueprintVersion', 0)
    history = campaign.setdefault('memory', {}).setdefault('blueprintHistory', [])
    archived = dict(current)
    archived['active'] = False
    history.insert(0, archived)
    print(f"  Archived v{v} to blueprintHistory")

def accept_blueprint(campaign):
    current = campaign.get('blueprint')
    if not current:
        print("No active blueprint to accept.")
        return
    v = current.get('blueprintVersion', 0)
    now = datetime.now(timezone.utc).isoformat()
    current['status'] = 'accepted'
    current['acceptedAt'] = now
    history = campaign.setdefault('memory', {}).setdefault('blueprintHistory', [])
    for h in history:
        if h.get('blueprintVersion') == v:
            h['status'] = 'accepted'
            h['acceptedAt'] = now
            break
    memory = campaign.setdefault('memory', {'notes': []})
    memory['notes'].append({
        'type': 'blueprint-accepted',
        'timestamp': now,
        'version': v,
        'detail': f'Blueprint v{v} accepted by operator.'
    })
    print(f"Blueprint v{v} accepted.")

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or len(args) < 1:
        print("Usage: python3 generate-blueprint.py <campaignId> [--new|--accept|--regenerate]")
        print("  --accept     : mark current blueprint version as accepted")
        print("  --regenerate : archive current, generate v+1 (new version)")
        print("  --new        : alias for --regenerate")
        print("  (no flag)    : first run — create v1 (overwrite if exists)")
        sys.exit(1)

    campaign_id = args[0]
    is_accept   = '--accept' in args
    is_regen    = '--regenerate' in args or '--new' in args

    with open(DATA_FILE) as f:
        data = json.load(f)
    campaign = data['campaigns'].get(campaign_id)
    if not campaign:
        print(f"Campaign not found: {campaign_id}")
        sys.exit(1)

    saved_primary_offer = campaign.get('strategy', {}).get('primaryOffer', '')

    if is_accept:
        accept_blueprint(campaign)
        if saved_primary_offer:
            campaign['strategy']['primaryOffer'] = saved_primary_offer
        data['updatedAt'] = datetime.now(timezone.utc).isoformat()
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
        sys.exit(0)

    current_v = current_blueprint_version(campaign)
    if is_regen and current_v > 0:
        next_v = current_v + 1
    elif current_v > 0:
        next_v = current_v
    else:
        next_v = 1

    print(f"Generating blueprint v{next_v} for: {campaign_id}"
          + (" (regenerate)" if is_regen and current_v > 0 else ""))

    if current_v > 0:
        archive_blueprint(campaign)

    blueprint = generate_blueprint(campaign)
    now = datetime.now(timezone.utc).isoformat()
    versioned = {
        'blueprintVersion': next_v,
        'generatedAt': now,
        'modelUsed': MODEL,
        'active': True,
        'dna': blueprint['dna'],
        'visualDirection': blueprint['visualDirection'],
        'pillars': blueprint['pillars'],
        'diffSummary': diff_summary(blueprint)
    }

    campaign['blueprint'] = versioned
    campaign['dna']                  = blueprint['dna']
    campaign['visualDirection']      = blueprint['visualDirection']
    campaign['strategy']['pillars']  = blueprint['pillars']
    campaign['blueprintVersion']      = next_v
    campaign['generatedAt']          = now
    campaign['modelUsed']            = MODEL

    if saved_primary_offer:
        campaign['strategy']['primaryOffer'] = saved_primary_offer
        print(f"  primaryOffer preserved: {saved_primary_offer}")

    memory = campaign.setdefault('memory', {'notes': [], 'blueprintHistory': []})
    memory['notes'].append({
        'type': 'blueprint-generated',
        'timestamp': now,
        'version': next_v,
        'detail': f'Blueprint v{next_v} generated via {MODEL}. {len(blueprint["pillars"])} pillars. {diff_summary(blueprint)}'
    })
    campaign['memory'] = memory

    campaign['pipeline'] = {
        'status': 'generatingBlueprint',
        'currentStep': 1,
        'totalSteps': 4,
        'currentAgent': 'Scout'
    }
    campaign['identity']['status'] = 'generatingBlueprint'

    data['updatedAt'] = now

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    print(f"Blueprint v{next_v} written for: {campaign_id}")
    print(f"  Pillars: {[p['name'] for p in blueprint['pillars']]}")
    print(f"  Tone: {blueprint['dna']['tone'][:60]}")
    print(f"  Palette: {blueprint['visualDirection']['palette']}")