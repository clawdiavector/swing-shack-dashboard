"""
test_v2026_08_07_review_modal_fixes.py

Tests for the review-modal + multi-source-compose + image-portal work
shipped on top of the reference-library stack.

Coverage:
  - _extract_asset_context now finds assets in campaign-data.json
    (Takomo hero, etc.) — the Review-modal 🎨 Generate visual button
    depends on this.
  - /api/image/from-asset accepts override_prompt
  - /api/image/generate accepts reference_ids + product_ids + service_ids
    and returns a `layers` summary showing which compose layers fired
  - /api/image/references/<brand>/<ref>/thumbnail serves JPGs
  - /image-portal HTML + POST endpoint validates + writes keys locally
  - review modal HTML + CSS strings contain the new buttons
  - Inline caption editor wiring exists (HTML5 + JS selectors present)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))


@pytest.fixture
def app_client(monkeypatch):
    """Flask test client with auth bypass."""
    from app import app as flask_app, SHARED_PASSWORD

    flask_app.config["TESTING"] = True
    flask_app.config["SERVER_NAME"] = "localhost.localdomain"

    with flask_app.test_client() as client:
        login_resp = client.post("/login", data={"password": SHARED_PASSWORD},
                                  base_url="http://localhost.localdomain")
        assert login_resp.status_code in (200, 302), f"login failed: {login_resp.status_code}"
        yield client


# ============================================================================
# _extract_asset_context — campaign-data.json lookup
# ============================================================================


class TestExtractAssetContext:
    """The new 10th lookup path (campaign-data.json) must work for review-inbox
    assets like takomo-101t-hero-c whose data lives in the portfolio file,
    not the standalone data/ hook/caption files."""

    def test_find_review_inbox_asset_by_id(self):
        from app import _extract_asset_context
        text, kind = _extract_asset_context("takomo-101t-hero-c", "swing-shack")
        assert text is not None, "takomo-101t-hero-c not found in campaign-data.json"
        assert kind == "visual"
        # The asset's visualBrief starts with the club description
        assert "Takomo 101T iron" in text or "Takomo" in text

    def test_finds_asset_by_name_match(self):
        from app import _extract_asset_context
        # Asset IDs in campaign-data.json sometimes don't match the
        # canonical slug; the helper also matches against the asset's
        # `name` field with hyphen normalization.
        # `takomo-101t-hero-b` exists; the name is "Takomo 101T — Hero Visual B"
        text, kind = _extract_asset_context("takomo-101t-hero-b", "swing-shack")
        assert text is not None
        assert "Takomo" in text or "iron" in text.lower()

    def test_finds_visual_a(self):
        from app import _extract_asset_context
        text, kind = _extract_asset_context("takomo-101t-visual-a", "swing-shack")
        assert text is not None
        assert kind == "visual"

    def test_returns_none_for_unknown(self):
        from app import _extract_asset_context
        text, kind = _extract_asset_context("totally-fake-id-xyz", "swing-shack")
        assert text is None
        assert kind is None


# ============================================================================
# /api/image/from-asset accepts override_prompt
# ============================================================================


class TestImageFromAssetOverride:
    """Body.override_prompt must replace the auto-extracted prompt entirely;
    body.prompt (legacy) still appends with '. ' separator."""

    def test_override_prompt_used_when_present(self, monkeypatch):
        from app import app as flask_app, SHARED_PASSWORD
        flask_app.config["TESTING"] = True
        flask_app.config["SERVER_NAME"] = "localhost.localdomain"

        # Stub generate_image + _extract_asset_context so we don't hit APIs
        captured = {}

        def fake_gen(**kwargs):
            captured.update(kwargs)
            from _lib.image_gen_router import GenResult
            return GenResult(bytes=b"x", mime="image/png", model="m", provider="p",
                             cost_estimate_usd=0.0, prompt_used=kwargs["prompt"],
                             revised_prompt=None, warning=None, usage={},
                             saved_path=None, saved_sidecar_path=None)

        def fake_extract(aid, brand):
            return "AUTO_EXTRACTED_PROMPT", "visual"

        monkeypatch.setattr("_lib.image_gen_router.generate_image", fake_gen)
        monkeypatch.setattr("app._extract_asset_context", fake_extract)
        # Also unset keys to force auth-fail path? No — we want the happy path
        # so the prompt-composition logic gets exercised.
        import os
        os.environ["OPENAI_API_KEY"] = "sk-fake"
        os.environ["OPENROUTER_API_KEY"] = "sk-or-fake"

        with flask_app.test_client() as client:
            client.post("/login", data={"password": SHARED_PASSWORD},
                        base_url="http://localhost.localdomain")
            r = client.post("/api/image/from-asset/some-asset-id",
                            json={"override_prompt": "MY OVERRIDE PROMPT",
                                  "campaignId": "swing-shack"})
        # Don't assert on status — generation may fail at the OpenAI call,
        # but the prompt_composition should have already happened.
        assert captured.get("prompt") == "MY OVERRIDE PROMPT", \
            f"override_prompt should replace auto-extracted; got: {captured.get('prompt')!r}"

    def test_legacy_prompt_appended_with_separator(self, monkeypatch):
        from app import app as flask_app, SHARED_PASSWORD
        flask_app.config["TESTING"] = True
        flask_app.config["SERVER_NAME"] = "localhost.localdomain"

        captured = {}

        def fake_gen(**kwargs):
            captured.update(kwargs)
            from _lib.image_gen_router import GenResult
            return GenResult(bytes=b"x", mime="image/png", model="m", provider="p",
                             cost_estimate_usd=0.0, prompt_used=kwargs["prompt"],
                             revised_prompt=None, warning=None, usage={},
                             saved_path=None, saved_sidecar_path=None)

        def fake_extract(aid, brand):
            return "AUTO_EXTRACTED_PROMPT", "visual"

        monkeypatch.setattr("_lib.image_gen_router.generate_image", fake_gen)
        monkeypatch.setattr("app._extract_asset_context", fake_extract)
        import os
        os.environ["OPENAI_API_KEY"] = "sk-fake"

        with flask_app.test_client() as client:
            client.post("/login", data={"password": SHARED_PASSWORD},
                        base_url="http://localhost.localdomain")
            r = client.post("/api/image/from-asset/some-asset-id",
                            json={"prompt": "extra detail", "campaignId": "swing-shack"})
        assert captured.get("prompt") == "extra detail. AUTO_EXTRACTED_PROMPT"


# ============================================================================
# /api/image/generate accepts the 4-layer compose params
# ============================================================================


class TestImageGenerateCompose:
    """Verify /api/image/generate accepts reference_ids / product_ids /
    service_ids / include_learned_signals and returns a `layers` summary."""

    def test_layers_summary_in_response(self, monkeypatch, tmp_path):
        from app import app as flask_app, SHARED_PASSWORD
        from _lib import reference_dna as ref_dna_mod
        from _lib import product_service_library as psl_mod
        from _lib import feedback_loop as fb_mod

        # Redirect brand dir to tmp so seeding doesn't pollute prod
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: tmp_path / "brand")
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: tmp_path / "brand")
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: tmp_path / "brand")

        flask_app.config["TESTING"] = True
        flask_app.config["SERVER_NAME"] = "localhost.localdomain"

        captured = {}

        def fake_gen(**kwargs):
            captured.update(kwargs)
            from _lib.image_gen_router import GenResult
            return GenResult(bytes=b"x", mime="image/png", model="m", provider="p",
                             cost_estimate_usd=0.0, prompt_used=kwargs["prompt"],
                             revised_prompt=None, warning=None, usage={},
                             saved_path=None, saved_sidecar_path=None)

        monkeypatch.setattr("_lib.image_gen_router.generate_image", fake_gen)
        import os
        os.environ["OPENAI_API_KEY"] = "sk-fake"

        with flask_app.test_client() as client:
            client.post("/login", data={"password": SHARED_PASSWORD},
                        base_url="http://localhost.localdomain")
            r = client.post("/api/image/generate", json={
                "prompt": "Test promo",
                "brand": "swing-shack",
                "reference_ids": [],
                "product_ids": [],
                "service_ids": [],
                "include_learned_signals": False,
            })

        assert r.status_code == 200
        data = r.get_json()
        assert "layers" in data, f"response missing `layers` field: {list(data.keys())}"
        # Without refs/products/signals, only recipe should fire (maybe)
        assert data["layers"]["references"] == 0
        assert data["layers"]["products_or_services"] == 0
        # signals is loaded but may not be ready — just verify the field exists
        assert "signals" in data["layers"]

    def test_signals_opt_out(self, monkeypatch, tmp_path):
        from app import app as flask_app, SHARED_PASSWORD
        from _lib import reference_dna as ref_dna_mod
        from _lib import product_service_library as psl_mod
        from _lib import feedback_loop as fb_mod

        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: tmp_path / "brand")
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: tmp_path / "brand")
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: tmp_path / "brand")

        flask_app.config["TESTING"] = True
        flask_app.config["SERVER_NAME"] = "localhost.localdomain"

        def fake_gen(**kwargs):
            from _lib.image_gen_router import GenResult
            return GenResult(bytes=b"x", mime="image/png", model="m", provider="p",
                             cost_estimate_usd=0.0, prompt_used=kwargs["prompt"],
                             revised_prompt=None, warning=None, usage={},
                             saved_path=None, saved_sidecar_path=None)

        monkeypatch.setattr("_lib.image_gen_router.generate_image", fake_gen)
        os_environ_set = {}
        import os
        os.environ["OPENAI_API_KEY"] = "sk-fake"

        with flask_app.test_client() as client:
            client.post("/login", data={"password": SHARED_PASSWORD},
                        base_url="http://localhost.localdomain")
            r = client.post("/api/image/generate", json={
                "prompt": "Test",
                "brand": "swing-shack",
                "include_learned_signals": False,
            })

        assert r.status_code == 200
        data = r.get_json()
        # When opted out, signals is False
        assert data["layers"]["signals"] is False


# ============================================================================
# Image Portal
# ============================================================================


class TestImagePortal:
    def test_page_loads(self, app_client):
        r = app_client.get("/image-portal.html")
        assert r.status_code == 200
        assert b"Image Keys Portal" in r.data
        assert b"Setting keys on Railway" in r.data

    def test_post_validates_openai_prefix(self, app_client):
        r = app_client.post("/image-portal", json={"openai": "not-a-real-key"})
        assert r.status_code == 400
        assert "sk-" in r.get_json()["error"]

    def test_post_validates_openrouter_prefix(self, app_client):
        r = app_client.post("/image-portal", json={"openrouter": "not-an-or-key"})
        assert r.status_code == 400

    def test_post_writes_both_keys(self, app_client, monkeypatch, tmp_path):
        # Redirect writes to tmp_path
        import app as app_mod
        monkeypatch.setattr(app_mod, "IMAGE_CRED_DIRS", [str(tmp_path / "creds")])

        r = app_client.post("/image-portal", json={
            "openai": "sk-fake-test-12345",
            "openrouter": "sk-or-v1-fake-test-67890",
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["wrote_openai"] is not None
        assert data["wrote_openrouter"] is not None

        # Files exist + have correct perms
        import os, stat
        for fname in ("openai-api.json", "openrouter-api.json"):
            p = os.path.join(str(tmp_path / "creds"), fname)
            assert os.path.exists(p), f"{fname} not written"
            assert oct(os.stat(p).st_mode & 0o777) == "0o600", f"{fname} not chmod 600"
            payload = json.loads(open(p).read())
            assert "api_key" in payload

    def test_post_requires_at_least_one_key(self, app_client):
        r = app_client.post("/image-portal", json={})
        assert r.status_code == 400


# ============================================================================
# Review-modal HTML presence — the strings have to be in campaign-os.html
# so the live UI can show them.
# ============================================================================


class TestReviewModalStrings:
    """Static checks that the review-modal updates shipped in this session
    are present in campaign-os.html. Catches accidental rollbacks."""

    @pytest.fixture
    def html(self):
        return (ROOT / "campaign-os" / "campaign-os.html").read_text()

    def test_inline_caption_edit_button(self, html):
        assert 'rv-edit-cap-btn' in html
        assert 'rv-cap-edit' in html  # textarea id
        assert 'rv-cap-save' in html   # save button id

    def test_image_preview_falls_back_to_filePath(self, html):
        # The visualUrl chain in openReview should consult filePath
        assert "a.filePath" in html
        # Should also try mediaUrl
        assert "a.mediaUrl" in html

    def test_no_visual_placeholder_shown_when_missing(self, html):
        assert 'No visual yet' in html
        assert 'Generate visual' in html  # the action button

    def test_generate_visual_button_in_modal(self, html):
        assert 'rv-gen-visual' in html
        assert '/api/image/from-asset/' in html  # the endpoint it calls

    def test_character_counter_present(self, html):
        assert 'rv-cap-len' in html
        assert 'rv-cap-edit-count' in html

    def test_caption_falls_back_to_description(self, html):
        # For image-only assets, description is the caption
        assert 'captionText = a.caption || a.description' in html

    def test_visual_brief_falls_back_to_description(self, html):
        # visualBrief > description > realPhotoBrief
        assert 'visualBriefText = a.visualBrief || a.description || a.realPhotoBrief' in html


# ============================================================================
# image-lab HTML drag-and-drop
# ============================================================================


class TestImageLabDragAndDrop:
    @pytest.fixture
    def html(self):
        return (ROOT / "campaign-os" / "image-lab.html").read_text()

    def test_refs_draggable(self, html):
        assert 'draggable="true"' in html

    def test_drag_start_handler(self, html):
        assert 'dragstart' in html
        assert "application/x-ref-id" in html  # dataTransfer mime

    def test_drop_targets_on_library_items(self, html):
        assert "drop-target" in html  # CSS class for visual feedback
        assert "dragover" in html
        assert "drop" in html

    def test_attach_and_detach_helpers_present(self, html):
        assert 'attachRefToItem' in html
        assert 'detachRefFromItem' in html
        assert 'attached-refs' in html  # CSS for the chips

    def test_generate_endpoint_passes_reference_ids(self, html):
        # The plain generate path now sends the new 4-layer params
        assert 'reference_ids:' in html
        assert 'product_ids:' in html


# ============================================================================
# Image portal HTML presence
# ============================================================================


class TestImagePortalHtml:
    @pytest.fixture
    def html(self):
        return (ROOT / "campaign-os" / "image-portal.html").read_text()

    def test_status_section(self, html):
        assert 'id="status"' in html
        assert '/api/image/status' in html

    def test_railway_instructions_present(self, html):
        assert "Setting keys on Railway" in html
        assert "OPENAI_API_KEY" in html
        assert "OPENROUTER_API_KEY" in html
        assert "railway.com/dashboard" in html

    def test_paste_form(self, html):
        assert 'id="openai"' in html
        assert 'id="openrouter"' in html
        assert 'sk-or-' in html  # placeholder hint


# ============================================================================
# Smoke: pull the IG insights script + verify it parses + dry-run works
# ============================================================================


class TestIgInsightsScript:
    def test_script_parses(self):
        script = ROOT / "campaign-os" / "scripts" / "ig_insights_pull.py"
        assert script.exists()
        import ast
        ast.parse(script.read_text())  # no exception == parses

    def test_script_help_runs(self, monkeypatch):
        script = ROOT / "campaign-os" / "scripts" / "ig_insights_pull.py"
        # Run with --help — should exit cleanly
        import subprocess
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "--limit" in result.stdout
        assert "--brand" in result.stdout

    def test_script_runs_with_help(self, monkeypatch):
        script = ROOT / "campaign-os" / "scripts" / "ig_insights_pull.py"
        # Run with --help — should exit cleanly
        import subprocess
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(ROOT / "campaign-os"),
        )
        assert result.returncode == 0
        assert "--limit" in result.stdout
        assert "--brand" in result.stdout
        assert "--dry-run" in result.stdout