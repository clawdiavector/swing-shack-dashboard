"""Weekly report showed reach 0 on every Instagram image and carousel post.

Meta removed the `impressions` metric for Instagram media (Graph v22, 2025).
Asking for it fails the whole /{media_id}/insights call, the report swallows
the error, and reach falls back to 0. Reels never asked for impressions, so
their reach kept working. Found 16 Nov 2026: Zernio showed the same Bag Drop
image posts reaching 3-57 people while the report said 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import meta_api  # noqa: E402


@pytest.mark.parametrize("media_type", ["IMAGE", "CAROUSEL_ALBUM", "VIDEO", "REELS", ""])
def test_no_media_type_asks_for_impressions(media_type):
    metrics = meta_api._metrics_for_media_type(media_type)
    assert "impressions" not in metrics
    assert "reach" in metrics


def test_image_insights_fall_back_to_core_metrics_when_meta_rejects_one(monkeypatch):
    """If Meta rejects any metric in the set, retry with the core set so reach still lands."""
    calls = []

    def fake_graph_get(path, params=None, **kw):
        metrics = params["metric"].split(",")
        calls.append(metrics)
        if len(calls) == 1:
            raise meta_api.MetaUpstreamError("(#100) metric not supported")
        return {"data": [{"name": m, "values": [{"value": 42 if m == "reach" else 1}]}
                         for m in metrics]}

    monkeypatch.setattr(meta_api, "_graph_get", fake_graph_get)
    monkeypatch.setattr(meta_api, "load_brand_integration", lambda b: {})
    monkeypatch.setattr(meta_api, "resolve_credentials_for_brand",
                        lambda b, c: {"token": "t", "mode": "test", "source": "test"})
    out = meta_api.get_post_insights_for_brand("stick", "123", media_type="IMAGE")
    assert out["_flat"]["reach"] == 42
    assert len(calls) == 2
    assert set(calls[1]) == {"reach", "likes", "comments", "saved", "shares"}
