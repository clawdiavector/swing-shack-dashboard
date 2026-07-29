"""
Caption Studio v2 — TDD tests
Tests voice-aware caption generation:
  - Backend: /api/intel/generate_captions/<asset_id> with voice/tone params
  - Intelligence: voice bible loading + generate_captions(voice=, tone=)
  - SPA: section renders with voice picker; generate respects voice
"""
import subprocess
import json
import sys
import os
import tempfile
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ─── Helpers ────────────────────────────────────────────────────────────────

def _run_py(caps_path, script, **env_overrides):
    """Run a Python snippet inside the campaign-os/ venv with DATA_DIR set."""
    env = {**os.environ, 'DATA_DIR': str(caps_path), **env_overrides}
    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env
    )
    return result

def _node(script, **env_overrides):
    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        ['node', '-e', script],
        capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env
    )
    return result

# ─── Voice bible fixture ─────────────────────────────────────────────────────

def _make_voice_bible(tmp):
    vb = {
        "schema": "https://clawdia.io/caption-studio/voice-bible/v1",
        "version": "1.0",
        "updated": "2026-07-28T00:00:00Z",
        "voices": {
            "swing-shack": {
                "id": "swing-shack",
                "label": "Swing Shack",
                "personality": "data-driven coach, confident, educational, no-nonsense",
                "template_prefix": "⛳ Here's the data-backed truth:",
                "template_suffix": "TrackMan doesn't lie.",
                "cta_default": "Book your session → swingshack.co.za",
                "allowed_tones": ["educational", "confident", "funny", "relatable", "provocative"],
                "example_caption": "Your slice isn't a mystery — TrackMan shows the exact cause in 30 minutes.",
            },
            "stick": {
                "id": "stick",
                "label": "Stick",
                "personality": "sarcastic, golf insider, calling out bad habits, meme-aware",
                "template_prefix": "🚩 Reality check:",
                "template_suffix": "Not sure why you'd do it any other way.",
                "cta_default": "Get fitted. Your game deserves better.",
                "allowed_tones": ["sarcastic", "funny", "confident", "relatable", "provocative"],
                "example_caption": "Off-rack clubs. The budget option that costs you strokes. Change my mind.",
            },
            "bag-drop": {
                "id": "bag-drop",
                "label": "Bag Drop",
                "personality": "community-first, fun, supportive, member energy",
                "template_prefix": "🫂 Fair warning:",
                "template_suffix": "You'll never go back.",
                "cta_default": "Drop your bag with us → swingshack.co.za",
                "allowed_tones": ["funny", "relatable", "educational", "confident"],
                "example_caption": "When your mate says 'I'll fix it myself' — we've all been there. Almost.",
            }
        }
    }
    p = tmp / 'voice_bible.json'
    with open(p, 'w') as f:
        json.dump(vb, f)
    return p

def _make_meme_knowledge(tmp):
    """Minimal meme knowledge fixture with voice_fit per meme."""
    memes = [
        {
            "id": "drake-preference",
            "name": "Drake Hotline Bling (Preference)",
            "voice_fit": ["swing-shack", "bag-drop"],
            "mechanism": "callout-contrast",
        },
        {
            "id": "disaster-girl",
            "name": "Disaster Girl",
            "voice_fit": ["stick"],
            "mechanism": "ironic-corporate",
        },
        {
            "id": "this-is-fine",
            "name": "This Is Fine",
            "voice_fit": ["swing-shack", "stick"],
            "mechanism": "self-deprecating",
        }
    ]
    p = tmp / 'meme_knowledge.json'
    with open(p, 'w') as f:
        json.dump({"memes": memes}, f)
    return p

# ─── Test 1: Voice bible loads correctly ─────────────────────────────────────

def test_voice_bible_loads():
    """Intelligence module can load voice_bible.json and return voice definitions."""
    script = f"""
import sys; sys.path.insert(0, '_lib')
from intelligence import _load_voice_bible, _now_iso
vb = _load_voice_bible()
assert vb is not None, 'voice_bible returned None'
assert 'swing-shack' in vb.get('voices', {{}}), 'swing-shack voice missing'
assert 'stick' in vb.get('voices', {{}}), 'stick voice missing'
assert 'bag-drop' in vb.get('voices', {{}}), 'bag-drop voice missing'
ss = vb['voices']['swing-shack']
assert ss['template_prefix'].startswith('⛳'), f'bad prefix: {{ss[\"template_prefix\"]}}'
assert 'educational' in ss['allowed_tones'], 'educational tone missing for swing-shack'
print('ok')
"""
    result = _node(f"""
const {{execSync}} = require('child_process');
const sys = require('sys');
// use python
const out = execSync('python3 -c {json.dumps(script)}', {{cwd: '{REPO}/campaign-os'}});
console.log(out.toString());
""".replace('sys', 'util'))
    # Actually run via subprocess in test context
    import subprocess
    env = {**os.environ}
    env['DATA_DIR'] = str(REPO / 'data')
    r = subprocess.run(
        [sys.executable, '-c', f"""
import sys; sys.path.insert(0, '{REPO}/campaign-os/_lib')
from intelligence import _load_voice_bible
vb = _load_voice_bible()
assert vb is not None, 'voice_bible returned None'
voices = vb.get('voices', {{}})
assert 'swing-shack' in voices, f'swing-shack missing: {{list(voices.keys())}}'
assert 'stick' in voices, f'stick missing'
assert 'bag-drop' in voices, f'bag-drop missing'
ss = voices['swing-shack']
assert '⛳' in ss.get('template_prefix', ''), f'bad prefix: {{ss.get(\"template_prefix\")}}'
assert 'educational' in ss.get('allowed_tones', []), 'educational tone missing'
print('PASS: test_voice_bible_loads')
"""],
        capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env
    )
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout, f"Test did not pass: {r.stdout}"


# ─── Test 2: generate_captions respects voice parameter ───────────────────────

def test_generate_captions_voice_param():
    """generate_captions(voice='stick') returns captions with stick voice applied."""
    script = f"""
import sys; sys.path.insert(0, '{REPO}/campaign-os/_lib')
from intelligence import generate_captions

# Without voice: fall back to default behaviour
r1 = generate_captions(n=3)
assert r1.get('ok') == True, 'generate_captions failed'

# With voice='stick': each variant must carry voice annotation
r2 = generate_captions(n=2, voice='stick')
assert r2.get('ok') == True, f'voice=stick failed: {{r2}}'
variants = r2.get('variants', [])
assert len(variants) >= 1, f'no variants returned: {{r2}}'
for v in variants:
    assert v.get('voice') == 'stick', f'variant missing voice annotation: {{v}}'

print('PASS: test_generate_captions_voice_param')
"""
    env = {**os.environ}
    env['DATA_DIR'] = str(REPO / 'data')
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout


# ─── Test 3: Different voices produce different captions ──────────────────────

def test_voices_produce_different_captions():
    """Same asset, different voices → different output."""
    script = f"""
import sys; sys.path.insert(0, '{REPO}/campaign-os/_lib')
from intelligence import generate_captions

r_swing = generate_captions(n=3, voice='swing-shack')
r_stick = generate_captions(n=3, voice='stick')
r_bag   = generate_captions(n=3, voice='bag-drop')

# Voice prefix is applied to body, not hook. Check body for the voice signal.
bodies_swing = [v.get('body','') for v in r_swing.get('variants',[])]
bodies_stick  = [v.get('body','') for v in r_stick.get('variants',[])]
bodies_bag    = [v.get('body','') for v in r_bag.get('variants',[])]

assert any('⛳' in b or 'TrackMan' in b for b in bodies_swing), f'swing-shack body missing voice signal: {{bodies_swing[0][:80] if bodies_swing else "NONE"}}'
assert any('🚩' in b or 'Reality check' in b for b in bodies_stick), f'stick body missing voice signal: {{bodies_stick[0][:80] if bodies_stick else "NONE"}}'
assert any('🫂' in b or 'Fair warning' in b for b in bodies_bag), f'bag-drop body missing voice signal: {{bodies_bag[0][:80] if bodies_bag else "NONE"}}'

# Verify variants are annotated with voice
for v in r_swing.get('variants',[]):
    assert v.get('voice') == 'swing-shack', f'swing-shack variant missing voice: {{v}}'
for v in r_stick.get('variants',[]):
    assert v.get('voice') == 'stick', f'stick variant missing voice: {{v}}'
for v in r_bag.get('variants',[]):
    assert v.get('voice') == 'bag-drop', f'bag-drop variant missing voice: {{v}}'

print('PASS: test_voices_produce_different_captions')
"""
    env = {**os.environ}
    env['DATA_DIR'] = str(REPO / 'data')
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout


# ─── Test 4: generate_captions accepts tone parameter ─────────────────────────

def test_generate_captions_tone_param():
    """generate_captions(voice='swing-shack', tone='funny') returns tone annotation."""
    script = f"""
import sys; sys.path.insert(0, '{REPO}/campaign-os/_lib')
from intelligence import generate_captions

r = generate_captions(n=2, voice='swing-shack', tone='funny')
assert r.get('ok') == True, f'tone=funny failed: {{r}}'
variants = r.get('variants', [])
assert len(variants) >= 1, f'no variants: {{r}}'
for v in variants:
    assert v.get('tone') == 'funny', f'tone annotation missing/wrong: {{v}}'
    assert v.get('voice') == 'swing-shack', f'voice annotation wrong: {{v}}'

# Unknown tone should not crash — should still return captions
r2 = generate_captions(n=2, voice='stick', tone='unknown-tone')
assert r2.get('ok') == True, f'unknown tone crashed: {{r2}}'

print('PASS: test_generate_captions_tone_param')
"""
    env = {**os.environ}
    env['DATA_DIR'] = str(REPO / 'data')
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout


# ─── Test 5: SPA section HTML has voice picker elements ─────────────────────

def test_spa_has_voice_picker():
    """campaign-os.html contains voice picker UI in #sec-captions."""
    html_path = REPO / 'campaign-os' / 'campaign-os.html'
    content = html_path.read_text()

    assert 'id="cap-voice-select"' in content, 'Voice picker select not found in SPA'
    assert 'id="cap-tone-select"' in content, 'Tone picker select not found in SPA'
    assert 'swing-shack' in content, '"swing-shack" option not in voice picker'
    assert 'stick' in content, '"stick" option not in voice picker'
    assert 'bag-drop' in content, '"bag-drop" option not in voice picker'
    assert 'cap-gen' in content, 'Generate button not found'

    print("PASS: test_spa_has_voice_picker")


# ─── Test 6: API route responds with {ok, ...} envelope ─────────────────────

def test_api_captions_route_returns_ok_envelope():
    """GET /api/intel/generate/captions/<id>?voice=&tone= returns {ok, variants, ...}."""
    script = f"""
import sys, os, json
sys.path.insert(0, '{REPO}/campaign-os')
sys.path.insert(0, '{REPO}/campaign-os/_lib')
os.environ['DATA_DIR'] = '{REPO}/data'
os.environ['FLASK_ENV'] = 'testing'

from app import app

client = app.test_client()

# GET with voice/tone query params — correct route is /api/intel/generate/captions/<id>
rv = client.get('/api/intel/generate/captions/test-asset-404?voice=swing-shack&tone=funny&n=3')
assert rv.status_code == 200, f'Expected 200, got {{rv.status_code}}: {{rv.data[:100]}}'
body = json.loads(rv.data)
assert 'ok' in body, 'Response missing ok field'
assert body.get('ok') == True, 'Expected ok=True'
assert 'variants' in body, 'Missing variants field'
assert body.get('_voice') == 'swing-shack', f"Wrong voice: {{body.get('_voice')}}"
assert body.get('_tone') == 'funny', f"Wrong tone: {{body.get('_tone')}}"

# Health check must be ok
rv2 = client.get('/api/health')
body2 = json.loads(rv2.data)
assert body2.get('ok') == True or body2.get('status') == 'ok', 'Health check failed'

print('PASS: test_api_captions_route_returns_ok_envelope')
"""
    env = {**os.environ}
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout


# ─── Test 7: Voice bible path resolves per-call via _data_paths ─────────────

def test_voice_bible_resolves_via_data_paths():
    """_load_voice_bible uses _data_paths resolution (runtime DATA_DIR > bundled)."""
    # Test 1: with runtime DATA_DIR containing voice_bible.json
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy voice_bible to tmp
        vb = {"voices": {"test-voice": {"id": "test-voice", "label": "Test Voice", "template_prefix": "TEST:"}}}
        p = Path(tmpdir) / 'voice_bible.json'
        with open(p, 'w') as f:
            json.dump(vb, f)

        script = f"""
import sys, os
sys.path.insert(0, '{REPO}/campaign-os/_lib')
os.environ['DATA_DIR'] = '{tmpdir}'
from intelligence import _load_voice_bible
vb = _load_voice_bible()
assert vb is not None, 'voice_bible returned None'
assert 'test-voice' in vb.get('voices', {{}}), 'test-voice not found'
paths_out = {{'data_dir': os.environ.get('DATA_DIR')}}
assert paths_out['data_dir'] == '{tmpdir}', 'wrong data_dir'
print('PASS: test_voice_bible_resolves_via_data_paths')
"""
        env = {**os.environ}
        env['DATA_DIR'] = tmpdir
        r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
        print(f"STDOUT: {r.stdout}")
        print(f"STDERR: {r.stderr}")
        assert r.returncode == 0, f"FAILED: {r.stderr}"
        assert 'PASS' in r.stdout


# ─── Test 8: generate_captions POST route with voice body ─────────────────────

def test_api_generate_captions_post_with_voice():
    """POST /api/captions/generate with {voice, tone} body returns {ok,...}."""
    script = f"""
import sys, os, json
sys.path.insert(0, '{REPO}/campaign-os')
sys.path.insert(0, '{REPO}/campaign-os/_lib')
os.environ['DATA_DIR'] = '{REPO}/data'
os.environ['FLASK_ENV'] = 'testing'

from app import app

client = app.test_client()

# POST to new /api/captions/generate route with voice/tone
rv = client.post('/api/captions/generate',
    json={{'voice': 'stick', 'tone': 'sarcastic', 'n': 3}},
    content_type='application/json'
)
assert rv.status_code == 200, f'Expected 200, got {{rv.status_code}}: {{rv.data[:100]}}'
body = json.loads(rv.data)
assert 'ok' in body, 'Response missing ok field'
assert body.get('ok') == True, f'Expected ok=True: {{body}}'
assert 'variants' in body, 'Missing variants field'
assert body.get('_voice') == 'stick', f"Wrong voice: {{body.get('_voice')}}"
assert body.get('_tone') == 'sarcastic', f"Wrong tone: {{body.get('_tone')}}"

print('PASS: test_api_generate_captions_post_with_voice')
"""
    env = {**os.environ}
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=str(REPO / 'campaign-os'), env=env)
    print(f"STDOUT: {r.stdout}")
    print(f"STDERR: {r.stderr}")
    assert r.returncode == 0, f"FAILED: {r.stderr}"
    assert 'PASS' in r.stdout


# ─── Run all ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_voice_bible_loads,
        test_generate_captions_voice_param,
        test_voices_produce_different_captions,
        test_generate_captions_tone_param,
        test_spa_has_voice_picker,
        test_api_captions_route_returns_ok_envelope,
        test_voice_bible_resolves_via_data_paths,
        test_api_generate_captions_post_with_voice,
    ]
    failed = 0
    for t in tests:
        print(f"\n>>> RUNNING {t.__name__}")
        try:
            t()
        except AssertionError as e:
            print(f"  ASSERTION FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
    print(f"\n{'='*60}")
    print(f"Results: {len(tests) - failed}/{len(tests)} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)
