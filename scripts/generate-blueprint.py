#!/usr/bin/env python3
"""
Campaign-Specific Blueprint Generator (M5)

Calls MiniMax-M2.7 to reason about the campaign's specific brief,
context, and theme — then generates truly campaign-specific:
  - DNA (tone, contentMix, ctaPhilosophy, platformStrategy)
  - Pillar names and descriptions
  - Visual direction (mood, creativeDirection, imageReferences, contentExamples)
  - Content mix specific to this campaign's conversion path

No generic templates. No campaign-type assumptions.
Every field should reflect this campaign and no other.
"""
import json, sys, os, urllib.request, urllib.parse

REPO_ROOT = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
DATA_FILE = os.path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json')
CONFIG    = '/Users/fivefriday/.openclaw-instance2/openclaw.json'

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
    # content is a list; find the text block
    text_blocks = [c for c in result['content'] if c.get('type') == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in response: {result["content"]}')
    return text_blocks[0]['text']

def generate_blueprint(campaign):
    brief   = campaign.get('brief', {})
    ident   = campaign.get('identity', {})
    strat   = campaign.get('strategy', {})

    # Campaign-specific inputs
    name         = ident.get('name', 'Untitled Campaign')
    goal_notes   = brief.get('goalNotes', '')
    context      = brief.get('context', '')
    audience     = brief.get('audience', '')
    primary_offer = strat.get('primaryOffer', ident.get('primaryGoal', ''))
    platforms    = ident.get('platforms', [])
    platform_str = ', '.join(platforms) if platforms else 'instagram'

    prompt = f"""You are a strategic campaign architect. Generate a complete campaign blueprint for:

Campaign: {name}
Platforms: {platform_str}
Primary Offer: {primary_offer}

Goal Notes (what the campaign must achieve):
{goal_notes}

Campaign Theme & Context (specific creative direction):
{context}

Target Audience:
{audience}

Your task: Think deeply about what makes THIS campaign unique. What is the specific argument it makes? What tension does it exploit? What does a golfer feel when they see this content? What should they think after?

Then generate a complete, campaign-specific blueprint in this exact JSON format — no markdown, no explanation, just the JSON:

{{
  "dna": {{
    "tone": "A specific, evocative tone description. 10-20 words. This is how the copy VOICES. Not generic.",
    "contentMix": "XX% [type] / XX% [type] / XX% [type] / XX% [type] — specific to this campaign's conversion path",
    "requiredContentTypes": ["type-a", "type-b", "type-c"],
    "preferredVisualStyles": ["style-a", "style-b", "style-c"],
    "forbiddenVisualStyles": ["style-to-avoid-a", "style-to-avoid-b"],
    "ctaPhilosophy": "How the CTA should feel and what it should say. 1-2 sentences. Campaign-specific.",
    "platformStrategy": {{
      "instagram": "Specific platform guidance for this campaign. 1-2 sentences. How does this campaign speak on Instagram specifically?",
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
    "colorUsage": "How to use the palette specifically for this campaign. 2-3 sentences. Not generic.",
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

Rules:
- Tone must be specific to this campaign — NOT "authentic, informative, and persuasive" (that's generic)
- Pillars must emerge from the campaign theme — NOT "Value, Proof, Urgency" (that's a template)
- creativeDirection must reference the specific campaign theme
- imageReferences must be specific to this campaign's angle
- colorUsage must explain WHY these colours for THIS campaign
- Answer ONLY with valid JSON. No markdown fences. No preamble."""

    messages = [
        {"role": "user", "content": prompt}
    ]

    print(f"  Calling MiniMax-M2.7 for campaign: {name}")
    response = call_model(messages)
    print(f"  Response length: {len(response)} chars")

    # Strip markdown fences if present
    response = response.strip()
    if response.startswith('```'):
        lines = response.split('\n')
        response = '\n'.join(lines[1:])  # drop first line (```json)
        response = response.strip()
        if response.endswith('```'):
            response = response[:-3].strip()

    blueprint = json.loads(response)
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

    print(f"Generating campaign-specific blueprint for: {campaign_id}")
    blueprint = generate_blueprint(campaign)

    # Apply blueprint to campaign
    brief = campaign.get('brief', {})
    ident = campaign.get('identity', {})

    campaign['dna']             = blueprint['dna']
    campaign['visualDirection'] = blueprint['visualDirection']
    campaign['strategy']['pillars'] = blueprint['pillars']

    # Memory note
    memory = campaign.get('memory', {'notes': []})
    memory.setdefault('notes', []).append({
        'type': 'blueprint-generated',
        'timestamp': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'detail': f'Campaign-specific blueprint generated via MiniMax-M2.7 reasoning. {len(blueprint["pillars"])} pillars, campaign-specific DNA and visualDirection.'
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

    data['updatedAt'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    print(f"Blueprint written for: {campaign_id}")
    print(f"  Pillars: {[p['name'] for p in blueprint['pillars']]}")
    print(f"  Tone: {blueprint['dna']['tone'][:60]}")