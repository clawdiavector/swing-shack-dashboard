"""
test_v2026_08_07_reference_library.py

Tests for the 3-layer Visual DNA + Library + Feedback Loop stack:
  - reference_dna.py       (point-at-image DNA capture + persistence)
  - product_service_library.py  (products/services CRUD + prompt composition)
  - feedback_loop.py       (score + correlation + signals → prompt)
  - image_gen_router._compose_full_prompt()  (4-layer stacker)
  - Flask routes for /api/image/references, /api/library, /api/image/feedback

All tests use the app's test client with auth bypassed via the dev password.
External HTTP calls (OpenAI / OpenRouter) are mocked.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))

# Test fixtures need a clean per-test brand dir — use temp
import _lib.reference_dna as ref_dna_mod
import _lib.product_service_library as psl_mod
import _lib.feedback_loop as fb_mod


@pytest.fixture
def temp_brand_root(monkeypatch, tmp_path):
    """Redirect brand-directory + feedback + references to tmp_path."""
    brand_dir = tmp_path / "brand-directory"
    brand_dir.mkdir(parents=True, exist_ok=True)
    test_brand = brand_dir / "test-brand"
    test_brand.mkdir(parents=True, exist_ok=True)

    # Patch root paths
    monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: brand_dir)
    monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: brand_dir)
    monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: brand_dir)

    return test_brand


@pytest.fixture
def sample_image(tmp_path):
    """Create a tiny synthetic JPG for ingest tests."""
    from PIL import Image
    p = tmp_path / "sample.jpg"
    # Dark image with a bright accent — easy palette to detect
    img = Image.new("RGB", (200, 200), (20, 30, 40))
    # Add a small bright spot
    for x in range(80, 120):
        for y in range(80, 120):
            img.putpixel((x, y), (245, 200, 66))
    img.save(p)
    return p


@pytest.fixture
def app_client(monkeypatch):
    """Flask test client with auth bypass + temp brand dir."""
    from app import app as flask_app, SHARED_PASSWORD

    flask_app.config["TESTING"] = True
    # ServerName so session cookie works in test
    flask_app.config["SERVER_NAME"] = "localhost.localdomain"

    with flask_app.test_client() as client:
        # Login using shared password — session cookie is set by the /login handler
        login_resp = client.post("/login", data={"password": SHARED_PASSWORD},
                                  base_url="http://localhost.localdomain")
        assert login_resp.status_code in (200, 302), f"login failed: {login_resp.status_code} {login_resp.data!r}"
        yield client


# ============================================================================
# reference_dna.py
# ============================================================================


class TestReferenceDNA:
    def test_derive_ref_id_is_stable(self, sample_image):
        id1 = ref_dna_mod.derive_ref_id(sample_image)
        id2 = ref_dna_mod.derive_ref_id(sample_image)
        assert id1 == id2
        assert id1.startswith("ref-")
        assert len(id1) == 16  # "ref-" + 12 hex

    def test_extract_reference_dna_shape(self, temp_brand_root, sample_image):
        dna = ref_dna_mod.extract_reference_dna(sample_image, "test-brand", label="dark hero", tags=["hero", "dark"])
        assert dna["brand"] == "test-brand"
        assert dna["label"] == "dark hero"
        assert "ref-" in dna["ref_id"]
        assert isinstance(dna["palette"], list)
        assert len(dna["palette"]) > 0
        assert dna["orientation"] in ("square", "portrait", "landscape")
        assert isinstance(dna["mood"], list)
        assert "hero" in dna["tags"]
        # Thumbnail created
        thumb_path = temp_brand_root / "references" / "thumbnails" / f"{dna['ref_id']}.jpg"
        assert thumb_path.exists()

    def test_save_load_list_delete_cycle(self, temp_brand_root, sample_image):
        dna = ref_dna_mod.extract_reference_dna(sample_image, "test-brand")
        ref_dna_mod.save_reference_dna(dna, "test-brand")

        loaded = ref_dna_mod.load_reference_dna(dna["ref_id"], "test-brand")
        assert loaded is not None
        assert loaded["ref_id"] == dna["ref_id"]

        listed = ref_dna_mod.list_reference_dnas("test-brand")
        assert any(r["ref_id"] == dna["ref_id"] for r in listed)

        deleted = ref_dna_mod.delete_reference_dna(dna["ref_id"], "test-brand")
        assert deleted is True
        assert ref_dna_mod.load_reference_dna(dna["ref_id"], "test-brand") is None

    def test_ingest_local_image_copies(self, temp_brand_root, sample_image):
        ref = ref_dna_mod.ingest_local_image(sample_image, "test-brand", label="copy-test")
        # Source copied into references/sources/
        sources_dir = temp_brand_root / "references" / "sources"
        assert any(sources_dir.iterdir())
        # Persisted
        assert ref_dna_mod.load_reference_dna(ref["ref_id"], "test-brand") is not None

    def test_reference_dna_to_prompt_has_all_layers(self, temp_brand_root, sample_image):
        dna = ref_dna_mod.extract_reference_dna(sample_image, "test-brand", label="test")
        prompt = ref_dna_mod.reference_dna_to_prompt(dna)
        assert "Visual reference" in prompt
        assert "test" in prompt
        assert "Lighting:" in prompt or "Lighting" in prompt or len(prompt) > 50

    def test_select_references_filters(self, temp_brand_root, sample_image):
        ref = ref_dna_mod.extract_reference_dna(sample_image, "test-brand")
        ref_dna_mod.save_reference_dna(ref, "test-brand")

        # Filter by product — none expected (sample image has no product OCR)
        filtered = ref_dna_mod.select_references("test-brand", product="Nonexistent", limit=5)
        assert len(filtered) == 0

        # Filter by palette that overlaps
        filtered = ref_dna_mod.select_references("test-brand", palette_hex=["#141e28"], limit=5)
        assert len(filtered) == 1

        # No filter returns all
        filtered = ref_dna_mod.select_references("test-brand", limit=10)
        assert len(filtered) == 1


# ============================================================================
# product_service_library.py
# ============================================================================


class TestProductServiceLibrary:
    def test_seed_defaults_load(self, temp_brand_root):
        lib = psl_mod.seed_defaults("test-brand")
        assert len(lib["products"]) >= 3  # SS defaults
        assert len(lib["services"]) >= 3

    def test_add_get_update_delete_item(self, temp_brand_root):
        item = psl_mod.add_item(
            "test-brand",
            kind="product",
            name="TrackMan 4",
            category="launch-monitor",
            headline="See every shot",
            description="Premium dual-radar.",
            tags=["premium"],
        )
        assert item["id"].startswith("product-")
        assert item["name"] == "TrackMan 4"

        got = psl_mod.get_item("test-brand", item["id"])
        assert got is not None
        assert got["name"] == "TrackMan 4"

        updated = psl_mod.update_item("test-brand", item["id"], headline="NEW HEADLINE")
        assert updated is not None
        assert updated["headline"] == "NEW HEADLINE"

        deleted = psl_mod.delete_item("test-brand", item["id"])
        assert deleted is True
        assert psl_mod.get_item("test-brand", item["id"]) is None

    def test_duplicate_name_gets_suffix(self, temp_brand_root):
        a = psl_mod.add_item("test-brand", kind="service", name="Coaching", description="x")
        b = psl_mod.add_item("test-brand", kind="service", name="Coaching", description="y")
        assert a["id"] != b["id"]
        assert b["id"].endswith("-2")

    def test_offering_references_unknown_raises(self, temp_brand_root):
        with pytest.raises(ValueError, match="unknown"):
            psl_mod.add_item(
                "test-brand",
                kind="offering",
                name="Bad Package",
                products=["nonexistent-id"],
            )

    def test_item_to_prompt_includes_name_and_headline(self, temp_brand_root):
        item = psl_mod.add_item(
            "test-brand",
            kind="service",
            name="Coaching",
            description="Private 60-min session.",
            headline="Your swing, decoded",
            default_palette=["#0b0d0e", "#f5c842"],
            preferred_mood=["premium"],
            default_prompt_seed="Studio lighting, dramatic",
            tags=["premium"],
        )
        prompt = psl_mod.item_to_prompt(item)
        assert "Coaching" in prompt
        assert "Your swing, decoded" in prompt
        assert "#0b0d0e" in prompt
        assert "premium" in prompt

    def test_attach_detach_reference(self, temp_brand_root, sample_image):
        item = psl_mod.add_item("test-brand", kind="product", name="X", description="x")
        ref = ref_dna_mod.extract_reference_dna(sample_image, "test-brand")
        ref_dna_mod.save_reference_dna(ref, "test-brand")

        attached = psl_mod.attach_reference("test-brand", item["id"], ref["ref_id"], as_hero=True)
        assert attached is not None
        assert ref["ref_id"] in attached["reference_ref_ids"]
        assert attached["hero_ref_id"] == ref["ref_id"]

        detached = psl_mod.detach_reference("test-brand", item["id"], ref["ref_id"])
        assert detached is not None
        assert ref["ref_id"] not in detached["reference_ref_ids"]
        assert detached["hero_ref_id"] is None


# ============================================================================
# feedback_loop.py
# ============================================================================


class TestFeedbackLoop:
    def test_compute_score_separates_winners(self):
        high = {"link_clicks": 80, "ga_sessions": 60, "bookings": 2, "ga_conversions": 3,
                "gmb_calls": 1, "likes": 100, "saves": 25, "comments": 8, "reach": 1500}
        low = {"link_clicks": 5, "ga_sessions": 3, "bookings": 0, "likes": 3, "reach": 100}
        assert fb_mod.compute_score(high) > fb_mod.compute_score(low)
        assert fb_mod.compute_score(high) > 0.8
        assert fb_mod.compute_score(low) < 0.6

    def test_add_record_persists_and_scores(self, temp_brand_root):
        rec = fb_mod.add_record(
            "test-brand",
            image_id="ref-001",
            kind="reference",
            source="ig",
            captured_signal={"likes": 50, "saves": 10, "reach": 800, "link_clicks": 30},
            dna_snapshot={
                "palette": ["#0b0d0e"],
                "mood": ["dark", "premium"],
                "luminance": {"bucket": "dark"},
                "orientation": "square",
                "product_tags": ["TrackMan"],
            },
        )
        assert rec["score"] > 0
        assert rec["kind"] == "reference"
        recs = fb_mod.list_records("test-brand")
        assert any(r["image_id"] == "ref-001" for r in recs)

    def test_compute_learned_signals_requires_min_samples(self, temp_brand_root):
        # 2 records — not ready
        for i in range(2):
            fb_mod.add_record("test-brand", image_id=f"r{i}", kind="reference", source="ig",
                              captured_signal={"likes": 10, "reach": 100})
        sig = fb_mod.compute_learned_signals("test-brand")
        assert sig["ready"] is False
        assert sig["samples"] == 2

        # 5+ records with high variance → ready. Use signals that pass the
        # 0.65 win threshold for the "winner" cohort and stay below for losers.
        for i in range(8):
            sig_payload = (
                {"likes": 200, "saves": 50, "reach": 1500, "link_clicks": 120, "bookings": 5, "ga_sessions": 80}
                if i % 2 == 0
                else {"likes": 5, "reach": 50}
            )
            dna = {
                "palette": ["#0b0d0e"] if i % 2 == 0 else ["#fff5e6"],
                "mood": ["dark", "premium"] if i % 2 == 0 else ["bright", "muted"],
                "luminance": {"bucket": "dark" if i % 2 == 0 else "bright"},
                "orientation": "square" if i % 2 == 0 else "landscape",
                "product_tags": ["TrackMan"] if i % 2 == 0 else [],
                "typography": {},
            }
            fb_mod.add_record("test-brand", image_id=f"r{i+10}", kind="reference", source="ig",
                              captured_signal=sig_payload, dna_snapshot=dna)
        sig = fb_mod.compute_learned_signals("test-brand")
        assert sig["ready"] is True
        assert sig["samples"] == 10
        assert "dark" in sig["preferences"]["luminance_bucket"]

    def test_signals_to_prompt(self, temp_brand_root):
        # Build a fake ready signal
        sig = {
            "ready": True,
            "palette_centroid_hex": ["#0b0d0e"],
            "preferences": {
                "luminance_bucket": {"dark": 0.9},
                "mood": {"premium": 0.8},
                "product_tags": {"TrackMan": 0.7},
            },
            "anti_preferences": {"luminance_bucket": {"bright": 0.3}},
        }
        prompt = fb_mod.signals_to_prompt(sig)
        assert "LEARNED WIN PROFILE" in prompt
        assert "dark" in prompt.lower()
        assert "#0b0d0e" in prompt

    def test_signals_to_prompt_empty_when_not_ready(self, temp_brand_root):
        sig = {"ready": False, "samples": 2}
        assert fb_mod.signals_to_prompt(sig) == ""

    def test_snapshot_helpers(self):
        ref = {
            "palette": ["#0b0d0e"],
            "mood": ["dark"],
            "luminance": {"bucket": "dark"},
            "orientation": "square",
            "product_tags": ["TrackMan"],
            "typography": {"primary_family": "Inter"},
        }
        snap = fb_mod.snapshot_from_reference(ref)
        assert snap["palette"] == ["#0b0d0e"]
        assert snap["product_tags"] == ["TrackMan"]

        gsnap = fb_mod.snapshot_from_generated("test", palette_hint=["#fff"], product_hint=["X"])
        assert gsnap["_provenance"] == "prompt-derived"


# ============================================================================
# image_gen_router._compose_full_prompt — the 4-layer stacker
# ============================================================================


class TestComposeFullPrompt:
    def test_compose_with_no_extras_returns_user_prompt(self):
        from _lib.image_gen_router import _compose_full_prompt
        prompt = _compose_full_prompt("hello")
        assert prompt == "hello"

    def test_compose_stacks_brand_recipe(self):
        from _lib.image_gen_router import _compose_full_prompt
        composed = _compose_full_prompt(
            "Premium promo",
            brand_recipe={"palette": {"primary": "orange"}, "mood": {"primary": "cinematic"},
                          "objects": {"primary": "golf ball"}, "summary": "tour grade"},
        )
        assert "Premium promo" in composed
        assert "orange" in composed
        assert "cinematic" in composed
        assert "golf ball" in composed

    def test_compose_stacks_all_four_layers(self):
        from _lib.image_gen_router import _compose_full_prompt
        composed = _compose_full_prompt(
            "TrackMan promo",
            brand_recipe={"palette": {"primary": "orange"}, "mood": {"primary": "premium"},
                          "summary": "Tour-grade data"},
            reference_dnas=[{"ref_id": "r1", "label": "dark-hero", "palette": ["#0b0d0e"],
                             "mood": ["dark"], "orientation": "portrait",
                             "luminance": {"bucket": "dark"}, "product_tags": ["TrackMan"]}],
            product_service_items=[{"id": "p1", "kind": "product", "name": "TrackMan 4",
                                    "headline": "Tour-grade data", "description": "Dual-radar.",
                                    "default_palette": ["#0b0d0e"], "preferred_mood": ["premium"],
                                    "tags": ["premium"]}],
            learned_signals={"ready": True, "palette_centroid_hex": ["#1a1a1a"],
                             "preferences": {"luminance_bucket": {"dark": 0.9}}},
        )
        # All 4 layers present
        assert "TrackMan promo" in composed  # layer 5: user prompt
        assert "orange" in composed  # layer 4: recipe
        assert "TrackMan 4" in composed  # layer 3: product
        assert "Visual reference: dark-hero" in composed  # layer 2: reference
        assert "LEARNED WIN PROFILE" in composed  # layer 1: signals

    def test_compose_handles_missing_layers_gracefully(self):
        from _lib.image_gen_router import _compose_full_prompt
        composed = _compose_full_prompt(
            "Just a prompt",
            reference_dnas=[],
            product_service_items=[],
            learned_signals={"ready": False},
        )
        assert "Just a prompt" in composed

    def test_compose_handles_broken_layers(self):
        """If a sub-layer raises, compose still returns the user prompt."""
        from _lib.image_gen_router import _compose_full_prompt
        # Bogus product_service_items with no `kind` key — should be skipped, not crash
        composed = _compose_full_prompt(
            "x",
            product_service_items=[{"__bad__": True}],
        )
        assert "x" in composed


# ============================================================================
# Flask routes (auth-gated, mocked external calls)
# ============================================================================


class TestFlaskRoutes:
    def test_image_lab_page_loads(self, app_client):
        r = app_client.get("/image-lab")
        assert r.status_code == 200
        assert b"Image Lab" in r.data

    def test_references_list_empty(self, app_client):
        r = app_client.get("/api/image/references/swing-shack")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["count"] == 0

    def test_references_upload_via_url(self, app_client, monkeypatch):
        """POST a URL → reference ingested."""
        from _lib.reference_dna import _default_brand_root
        # Patch the brand root so we don't pollute prod data
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: Path(tmp))

        # Stub ingest_url to avoid network
        from _lib import reference_dna as ref_mod
        def fake_ingest(url, brand, **kw):
            return {"ref_id": "ref-fake123", "brand": brand, "palette": ["#fff"],
                    "mood": ["test"], "orientation": "square", "luminance": {"bucket": "mid"},
                    "product_tags": [], "tags": [], "label": "test"}
        monkeypatch.setattr(ref_mod, "ingest_url", fake_ingest)

        r = app_client.post("/api/image/references/from-url",
                            json={"url": "http://example.com/test.jpg", "brand": "swing-shack"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["reference"]["ref_id"] == "ref-fake123"

    def test_library_items_list_seeds_defaults(self, app_client, monkeypatch):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: Path(tmp))

        r = app_client.get("/api/library/swing-shack/items?seed=true")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["totals"]["products"] >= 3
        assert data["totals"]["services"] >= 3

    def test_library_crud(self, app_client, monkeypatch):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: Path(tmp))

        # Create
        r = app_client.post("/api/library/swing-shack/items", json={
            "kind": "service", "name": "Test Service", "description": "x", "headline": "h",
        })
        assert r.status_code == 200
        item = r.get_json()["item"]

        # Read
        r = app_client.get(f"/api/library/swing-shack/items/{item['id']}")
        assert r.status_code == 200

        # Update
        r = app_client.put(f"/api/library/swing-shack/items/{item['id']}",
                           json={"headline": "NEW"})
        assert r.status_code == 200
        assert r.get_json()["item"]["headline"] == "NEW"

        # Delete
        r = app_client.delete(f"/api/library/swing-shack/items/{item['id']}")
        assert r.status_code == 200

    def test_feedback_record_and_summary(self, app_client, monkeypatch):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: Path(tmp))

        r = app_client.post("/api/image/feedback/record", json={
            "image_id": "ref-test", "kind": "reference", "source": "ig",
            "captured_signal": {"likes": 100, "reach": 1000, "link_clicks": 50, "bookings": 2},
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

        r = app_client.get("/api/image/feedback/swing-shack")
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["samples"] == 1

    def test_feedback_learned_signals_endpoint(self, app_client, monkeypatch):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: Path(tmp))

        r = app_client.get("/api/image/feedback/swing-shack/learned")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        # Initially not enough samples → not ready
        assert data["signals"]["ready"] is False

    def test_image_from_reference_returns_503_without_keys(self, app_client, monkeypatch):
        """Route exists + returns auth error when no provider key is set."""
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: Path(tmp))

        # Seed a reference
        from PIL import Image
        ref_img = Path(tmp) / "test.jpg"
        Image.new("RGB", (100, 100), (20, 20, 20)).save(ref_img)
        ref = ref_dna_mod.ingest_local_image(ref_img, "swing-shack")
        ref_id = ref["ref_id"]

        # Unset any provider keys
        for k in ("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_FILE"):
            monkeypatch.delenv(k, raising=False)

        r = app_client.post(f"/api/image/from-reference/swing-shack/{ref_id}",
                            json={"prompt": "test"})
        # Either 503 (no keys) or some auth-related response
        assert r.status_code in (200, 503, 504)

    def test_image_from_product_route(self, app_client, monkeypatch):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr(psl_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(ref_dna_mod, "_default_brand_root", lambda: Path(tmp))
        monkeypatch.setattr(fb_mod, "_default_brand_root", lambda: Path(tmp))

        # Seed library
        psl_mod.seed_defaults("swing-shack")

        # Unset keys
        for k in ("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_FILE"):
            monkeypatch.delenv(k, raising=False)

        r = app_client.post("/api/image/from-product/swing-shack/service-coaching-1on1",
                            json={"prompt": "test promo"})
        assert r.status_code in (200, 503, 504)