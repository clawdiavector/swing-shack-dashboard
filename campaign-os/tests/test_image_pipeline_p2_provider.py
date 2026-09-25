"""P2 — provider reference-in, pick_model routing, cost ledger, daily cap."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)

_OR_RESPONSE = {
    "choices": [
        {
            "message": {
                "images": [
                    {
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + __import__("base64").b64encode(_TINY_PNG).decode("ascii")
                        }
                    }
                ]
            }
        }
    ],
    "usage": {"cost": 0.039},
}


def _purge() -> None:
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]


@pytest.fixture(autouse=True)
def _clean_modules(monkeypatch):
    monkeypatch.delenv("CAMPAIGN_OS_IMAGE_MODEL_FORCE", raising=False)
    _purge()
    yield
    _purge()


def test_openrouter_payload_includes_reference_image_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    captured: dict = {}

    def _fake_or(**kwargs):
        captured.update(kwargs)
        return _OR_RESPONSE

    from _lib import image_gen_router as router

    with patch.object(router, "_call_openrouter_multimodal", side_effect=_fake_or), patch.object(
        router, "_compose_full_prompt", return_value="brief prompt"
    ), patch.object(router, "openrouter_credentials_present", return_value=True):
        router.generate_image(
            "hello",
            provider="openrouter",
            model="google/gemini-2.5-flash-image",
            reference_bytes=[_TINY_PNG],
            brand_id=None,
            save=False,
        )

    messages = captured.get("messages") or []
    assert messages
    content = messages[0]["content"]
    assert isinstance(content, list)
    types = [c.get("type") for c in content]
    assert "image_url" in types
    text_chunks = [c for c in content if c.get("type") == "text"]
    assert text_chunks
    assert "Match the framing, lighting and palette" in text_chunks[0]["text"]


def test_krea_path_drops_reference_no_openrouter_call(monkeypatch):
    monkeypatch.setenv("KREA_MCP_TOKEN", "test-token")
    or_calls = {"n": 0}
    krea_calls: list[dict] = []

    from _lib import image_gen_router as router

    def _fake_or(**kwargs):
        or_calls["n"] += 1
        return _OR_RESPONSE

    def _fake_krea(**kwargs):
        krea_calls.append(kwargs)
        return {"job_id": "job-1", "structuredContent": {"job_id": "job-1"}}

    with patch.object(router, "_krea_credentials_present", return_value=True), patch.object(
        router, "_call_openrouter_multimodal", side_effect=_fake_or
    ), patch.object(router, "_call_krea_generate", side_effect=_fake_krea), patch.object(
        router, "_compose_full_prompt", return_value="brief"
    ):
        result = router.generate_image(
            "hello",
            provider="krea",
            model="bfl/flux-1.1-pro-ultra",
            reference_bytes=[_TINY_PNG],
            save=False,
        )

    assert or_calls["n"] == 0
    assert krea_calls
    assert result.reference_dropped is True


@pytest.mark.parametrize(
    "requirements, krea_on, expected_model, expected_provider",
    [
        (
            {"needs_reference": True, "photoreal": False, "typography": False, "edit": False},
            False,
            "google/gemini-2.5-flash-image",
            "openrouter",
        ),
        (
            {"needs_reference": False, "photoreal": False, "typography": False, "edit": True},
            False,
            "google/gemini-2.5-flash-image",
            "openrouter",
        ),
        (
            {"needs_reference": False, "photoreal": False, "typography": True, "edit": False},
            True,
            "ideogram/ideogram-3",
            "krea",
        ),
        (
            {"needs_reference": False, "photoreal": False, "typography": True, "edit": False},
            False,
            "google/gemini-2.5-flash-image",
            "openrouter",
        ),
        (
            {"needs_reference": False, "photoreal": True, "typography": False, "edit": False},
            True,
            "bfl/flux-1.1-pro-ultra",
            "krea",
        ),
        (
            {"needs_reference": False, "photoreal": True, "typography": False, "edit": False},
            False,
            "google/gemini-2.5-flash-image",
            "openrouter",
        ),
        (
            {"needs_reference": False, "photoreal": False, "typography": False, "edit": False},
            True,
            "google/gemini-2.5-flash-image",
            "krea",
        ),
    ],
)
def test_pick_model_table(requirements, krea_on, expected_model, expected_provider, monkeypatch):
    monkeypatch.delenv("KREA_MCP_TOKEN", raising=False)
    import _lib.creative_director as cd

    monkeypatch.setattr(cd, "_krea_connected", lambda: krea_on)
    out = cd.pick_model(requirements)
    assert out["model"] == expected_model
    assert out["provider"] == expected_provider
    assert "reason" in out


def test_pick_model_force_override(monkeypatch):
    from _lib.creative_director import pick_model

    monkeypatch.setenv(
        "CAMPAIGN_OS_IMAGE_MODEL_FORCE", "openrouter:google/gemini-2.5-flash-image"
    )
    out = pick_model({"needs_reference": False, "photoreal": True, "typography": False, "edit": False})
    assert out["model"] == "google/gemini-2.5-flash-image"
    assert out["provider"] == "openrouter"
    assert "CAMPAIGN_OS_IMAGE_MODEL_FORCE" in out["reason"]


def test_pick_model_never_returns_grok():
    from _lib.creative_director import pick_model

    for req in (
        {"needs_reference": True, "photoreal": True, "typography": True, "edit": True},
        {"needs_reference": False, "photoreal": False, "typography": False, "edit": False},
    ):
        out = pick_model(req)
        assert "grok-imagine" not in out["model"]


def test_cap_reached_skips_provider_http(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAMPAIGN_OS_MAX_IMAGES_PER_DAY", "1")
    _purge()

    from _lib import image_submit_quota

    image_submit_quota.record_brand_image_submit("stick")

    http_calls = {"n": 0}

    def _fake_urlopen(*args, **kwargs):
        http_calls["n"] += 1
        raise AssertionError("HTTP should not run when cap reached")

    from _lib.jobs.layer5 import draft_assets
    from _lib.jobs.layer5.image_draft_context import ImageDraftContext

    ctx = ImageDraftContext(job="test job", aspect="1024x1024", lineage={"calendar": {"type": "moment"}})
    row = {"id": "q-cap", "action": "draft_image", "status": "pending"}

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen), patch(
        "_lib.llm_spend.check", return_value=(True, "")
    ), patch("_lib.llm_spend.modelled_image_cost", return_value=0.04), patch(
        "_lib.llm_spend.write_approval_receipt"
    ), patch(
        "_lib.image_gen_router.generate_image_with_persistence"
    ) as gen_mock:
        asset_id, err = draft_assets._process_image_row(
            row, item_id="calendar_candidate:stick:cal-x", brand_id="stick", draft_ctx=ctx
        )

    assert asset_id is None
    assert err == "cap_reached"
    assert http_calls["n"] == 0
    gen_mock.assert_not_called()


def test_resolve_image_cost_openrouter_usage():
    from _lib.image_gen_router import _resolve_image_cost

    cost, source = _resolve_image_cost(
        provider="openrouter",
        usage={"cost": 0.051},
        size="1024x1024",
        n=1,
    )
    assert cost == pytest.approx(0.051)
    assert source == "openrouter"
