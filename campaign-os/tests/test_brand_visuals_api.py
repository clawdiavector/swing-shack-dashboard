"""Brand Visuals API — /api/brand/<id>/references and /visuals."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def visuals_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.brand_visuals"):
            del sys.modules[mod]
    import app as app_module

    monkeypatch.setattr(app_module, "_is_authed", lambda: True)
    return app_module.app.test_client(), tmp_path


def _seed_social(tmp_path: Path, brand: str = "stick"):
    plat_dir = tmp_path / "brand-directory" / brand / "social" / "instagram"
    (plat_dir / "media").mkdir(parents=True)
    (plat_dir / "media" / "post1.jpg").write_bytes(b"\xff\xd8\xffpost1")
    posts = {
        "posts": [
            {
                "source_id": "post1",
                "caption_preview": "Hello",
                "publish_date": "2026-01-01T00:00:00Z",
                "performance": {"reach": 10},
            }
        ]
    }
    (plat_dir / "posts.json").write_text(json.dumps(posts), encoding="utf-8")


def test_visuals_get_lists_social(visuals_client):
    client, tmp_path = visuals_client
    _seed_social(tmp_path)
    r = client.get("/api/brand/stick/visuals?platform=instagram")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert len(data["social"]) == 1
    assert data["social"][0]["id"] == "post1"
    assert "/api/visual-library/stick/image/" in data["social"][0]["thumb_url"]


def test_references_post_drive_roundtrip(visuals_client, monkeypatch):
    client, tmp_path = visuals_client
    brand = "stick"
    images = tmp_path / "brand-directory" / brand / "images"
    images.mkdir(parents=True)
    (images / "prod.jpg").write_bytes(b"\xff\xd8\xffprod")

    import _lib.reference_dna as ref_mod

    def fake_extract(image_path, brand, **kw):
        return {
            "ref_id": "ref-test123456",
            "brand": brand,
            "source_path": str(image_path),
            "source_filename": image_path.name,
            "palette": ["#111111"],
            "mood": ["test"],
            "orientation": "square",
            "luminance": {"bucket": "mid"},
            "product_tags": [],
            "tags": [],
            "label": "prod",
            "created": 1.0,
        }

    monkeypatch.setattr(ref_mod, "extract_reference_dna", fake_extract)
    monkeypatch.setattr(ref_mod, "_make_thumbnail", lambda *a, **k: True)

    r = client.post(
        "/api/brand/stick/references",
        json={"source": "drive", "id": "prod", "pillar": "demo", "note": "hero"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["dna"]["is_learnable"] is True

    r2 = client.get("/api/brand/stick/references")
    assert r2.status_code == 200
    assert r2.get_json()["references"]

    r3 = client.delete("/api/brand/stick/references/prod")
    assert r3.status_code == 200
    assert r3.get_json()["ok"] is True


def test_references_requires_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BUNDLED_DATA_DIR", raising=False)
    for mod in list(sys.modules):
        if mod == "app":
            del sys.modules[mod]
    import app as app_module

    monkeypatch.setattr(app_module, "_is_authed", lambda: False)
    client = app_module.app.test_client()
    r = client.get("/api/brand/stick/references")
    assert r.status_code == 401
    assert "auth" in (r.get_json() or {}).get("error", "").lower()
