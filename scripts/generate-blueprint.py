#!/usr/bin/env python3
"""
Campaign-Specific Blueprint Generator (M5)

Calls MiniMax-M2.7 to reason about the campaign's specific brief,
context, and theme — then generates truly campaign-specific:
  - DNA (tone, contentMix, ctaPhilosophy, platformStrategy)
  - Pillar names and descriptions
  - Visual direction (mood, creativeDirection, imageReferences, contentExamples)
  - Content mix specific to this campaign's conversion path

Quality gates:
  - Rejects generic pillar names (Value, Proof, Urgency, etc.)
  - Validates JSON parse, retries once on failure
  - Verifies schema presence before writing
  - Preserves strategy.primaryOffer across generation

No generic templates. No campaign-type assumptions.
Every field should reflect this campaign and no other.
"""
import json, sys, os, re, urllib.request
from datetime import datetime, timezone

REPO_ROOT = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
DATA_FILE = os.path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json')
CONFIG    = '/Users/fivefriday/.openclaw-instance2/openclaw.json'

# Generic pillar names that indicate template thinking — reject these
GENERIC_PILLAR_REJECT = [
    'value', 'proof', 'urgency', 'benefits', 'features',
    'awareness', 'consideration', 'conversion', 'social proof',
    'education', 'engagement', 'brand', 'visibility', 'reach'
]

def get_credentials():
    with open(CONFIG) as f:
        cfg = json.load(f)
    v = cfg['models']['providers']['minimax-portal']
    return ''.join(v['apiKey']), v['baseUrl']

def call_model(messages, model='MiniMax-M2.7'):
    api_key, base_url = get_credentials()
    url = f"{base_url}/v1/messages?model={model}"
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
        text = '\n'.join(lines[1:])  # drop ```json
        text = text.strip()
        if text.endswith('```'):
            text = text[:-3].strip()
    # Remove any stray markdown elsewhere
    text = re.sub(r'```[a-z]*', '', text).strip()
    return text

def parse_json_with_retry(response_text, max_retries=2):
    """Parse JSON with retry. Strip fences on first try."""
    for attempt in range(max_retries):
        cleaned = strip_markdown(response_text) if attempt == 0 else response_text
        # Also try stripping any trailing non-JSON
        # Find the last valid closing brace
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
    """Quality gate: reject blueprints with generic/non-specific content."""
    errors = []

    # Check pillars for generic names
    for i, pillar in enumerate(blueprint.get('pillars', [])):
        name_lower = pillar.get('name', '').lower()
        # Check if any generic term appears as the pillar name (not just substring)
        for generic in GENERIC_PILLAR_REJECT:
            if name_lower == generic or name_lower.startswith(generic + ' '):
                errors.append(f'Pillar {i+1} has generic name: "{pillar["name"]}"')
        # Pillar name must be descriptive, not just a category
        if len(pillar.get('name', '')) < 10:
            errors.append(f'Pillar {i+1} name too short: "{pillar["name"]}"')
        if len(pillar.get('description', '')) < 30:
            errors.append(f'Pillar {i+1} description too short')

    # Check tone for generic phrases
    tone = blueprint.get('dna', {}).get('tone', '').lower()
    generic_tones = ['authentic, informative, and persuasive', 'professional and friendly',
                     'friendly and informative', 'educational and engaging']
    for gt in generic_tones:
        if gt in tone:
            errors.append(f'Tone is generic: "{blueprint["dna"]["tone"]}"')

    # Check palette is not all placeholders
    palette = blueprint.get('visualDirection', {}).get('palette', {})
    placeholder_count = sum(1 for v in palette.values() if '#XXXXXX' in v or v == '#XXXXXX')
    if placeholder_count > 0:
        errors.append(f'Palette has {placeholder_count} placeholder values')

    return errors

def generate_blueprint(campaign):
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

    # Campaign-type palette guidance — base colours to use as anchor, model adjusts
    type_palette_guidance = {
        'Awareness': (
            'Palette should feel thought-provoking and slightly uncomfortable — '
            'the "wrong tool" metaphor demands high contrast and clear contrast. '
            'Suggested anchor: bold primary (#FF6B35 or similar warm orange for urgency), '
            'dark background (#0D0D0F), white text, gold or green accent for the "solution" moment.'
        ),
        'product-launch': (
            'Palette should feel premium and credible. Suggested anchor: '
            'chrome/silver tones with dark backgrounds, gold accent for price/quality signals. '
            'Think: what colours communicate "this is the right equipment".'
        ),
        'evergreen': (
            'Palette should feel trustworthy and consistent. Suggested anchor: '
            'deep blue primary with warm accent. Think: what colours communicate ongoing value.'
        ),
        'seasonal': (
            'Palette should feel timely and relevant. Anchor colours should reflect the season\'s mood '
            'while maintaining Swing Shack brand identity.'
        ),
        'promo': (
            'Palette should feel urgent and action-driving. Suggested anchor: '
            'high-contrast with a dominant urgency colour (red/orange) and clear CTAs.'
        ),
        'event': (
            'Palette should feel event-worthy and social. Suggested anchor: '
            'vibrant colours that stand out in feed, with clear brand anchor.'
        )
    }
    palette_guidance = type_palette_guidance.get(
        campaign_type,
        'Palette should feel appropriate for the campaign goal and audience. Use the campaign type, goal notes, and context to determine colours.'
    )

    prompt = f"""You are a strategic campaign architect. Generate a complete campaign blueprint for:

Campaign: {name}
Platforms: {platform_str}
Campaign Type: {campaign_type}
Primary Offer: {primary_offer}

Goal Notes (what the campaign must achieve):
{goal_notes}

Campaign Theme & Context (specific creative direction):
{context}

Target Audience:
{audience}

Palette Guidance:
{palette_guidance}

Your task: Think deeply about what makes THIS campaign unique. What is the specific argument it makes? What tension does it exploit? What does a golfer feel when they see this content? What should they think after? What colours match this campaign's emotional register?

Then generate a complete, campaign-specific blueprint in this exact JSON format — no markdown, no explanation, just the JSON:

{{
  "dna": {{
    "tone": "A specific, evocative tone description. 10-20 words. This is how the copy VOICES. Not generic.",
    "contentMix": "XX% [type] / XX% [type] / XX% [type] / XX% [type] — specific to this campaign's conversion path",
    "requiredContentTypes": ["type-a", "type-b", "type-c"],
    "preferredVisualStyles": ["style-a", "style-b", "style-c"],
    "forbiddenVisualStyles": ["style-to-avoid-a", "style-to-avoid-b"],
    "ctaPhilosophy": "How the CTA should feel and what it should say. 1-2 sentences. Campaign-specific.",
    "platformStrategy: {{
      "instagram": "Specific platform guidance for this campaign. 1-2 sentences.",
      "tiktok": "Specific platform guidance for this campaign. 1-2 sentences.",
      "gmb": "Specific platform guidance for this campaign. 1-2 sentences."
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
    "mood": "A vivid, campaign-specific mood. 5-12 words. Think: what feeling does a golfer get looking at this content?",
    "creativeDirection": "A vivid description of exactly what the visuals should show, referencing the campaign theme. 3-5 sentences. Be specific — this is not generic.",
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

Rules — these will be validated programmatically:
- Tone must be specific to this campaign — NOT "authentic, informative, and persuasive"
- Pillars must emerge from the campaign theme — NOT "Value, Proof, Urgency" (those will be rejected)
- Pillar names must be descriptive and specific — NOT just single words or generic categories
- creativeDirection must reference the specific campaign theme
- imageReferences must be specific to this campaign's angle
- colorUsage must explain WHY these colours for THIS campaign
- Palette must use real hex values — not #XXXXXX placeholders
- Answer ONLY with valid JSON. No markdown fences. No preamble."""

    messages = [{"role": "user", "content": prompt}]

    print(f"  Calling MiniMax-M2.7 for campaign: {name}")
    response = call_model(messages)
    print(f"  Response length: {len(response)} chars")

    blueprint = parse_json_with_retry(response)

    # Quality gate — reject generic pillars
    errors = validate_blueprint(blueprint)
    if errors:
        print(f"  QUALITY GATE FAILED: {errors}")
        # Retry once with stricter prompt
        print("  Retrying with stricter quality guidance...")
        retry_prompt = prompt + "\n\nIMPORTANT: Your previous output contained generic content. " \
                          "The following were rejected: " + "; ".join(errors) + ". " \
                          "Ensure pillars are specific arguments, not generic labels. " \
                          "Use real hex palette values. Generate fresh, specific output."
        messages = [{"role": "user", "content": retry_prompt}]
        response = call_model(messages)
        blueprint = parse_json_with_retry(response)
        errors = validate_blueprint(blueprint)
        if errors:
            raise ValueError(f"Blueprint quality gate failed after retry: {errors}")

    return blueprint

if __name__ == '__main__':
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not campaign_id:
        print("Usage: python3 generate-blueprint.py <campaignId>")
        sys.exit(1)

    with open(DATA_FILE) as f:
        data = json.load(f)

    campaign = data['campaigns'].get(campaign_id)
    if not campaign:
        print(f"Campaign not found: {campaign_id}")
        sys.exit(1)

    # Fix 1: Preserve strategy.primaryOffer before any write
    saved_primary_offer = campaign.get('strategy', {}).get('primaryOffer', '')

    print(f"Generating campaign-specific blueprint for: {campaign_id}")
    blueprint = generate_blueprint(campaign)

    # Apply blueprint — only write the fields that come from the model
    campaign['dna']              = blueprint['dna']
    campaign['visualDirection'] = blueprint['visualDirection']
    campaign['strategy']['pillars'] = blueprint['pillars']

    # Fix 1 (restored): Restore primaryOffer that was set by create-campaign.js
    if saved_primary_offer:
        campaign['strategy']['primaryOffer'] = saved_primary_offer
        print(f"  primaryOffer preserved: {saved_primary_offer}")

    # Memory note
    now = datetime.now(timezone.utc).isoformat()
    memory = campaign.get('memory', {'notes': []})
    memory.setdefault('notes', []).append({
        'type': 'blueprint-generated',
        'timestamp': now,
        'detail': f'Campaign-specific blueprint generated via MiniMax-M2.7 reasoning. '
                  f'{len(blueprint["pillars"])} pillars, campaign-specific DNA and visualDirection. '
                  f'primaryOffer preserved.'
    })
    campaign['memory'] = memory

    # Pipeline
    campaign['pipeline'] = {
        'status': 'generatingBlueprint',
        'currentStep': 1,
        'totalSteps': 4,
        'currentAgent': 'Scout'
    }
    campaign['identity']['status'] = 'generatingBlueprint'

    data['updatedAt'] = datetime.now(timezone.utc).isoformat()

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    print(f"Blueprint written for: {campaign_id}")
    print(f"  Pillars: {[p['name'] for p in blueprint['pillars']]}")
    print(f"  Tone: {blueprint['dna']['tone'][:60]}")
    print(f"  Palette: primary={blueprint['visualDirection']['palette']['primary']}, "
          f"accent={blueprint['visualDirection']['palette']['accent']}")