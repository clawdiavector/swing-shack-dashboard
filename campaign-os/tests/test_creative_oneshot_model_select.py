"""Recraft / allow_unverified model selection."""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_recraft_unverified_not_auto_routed():
    from _lib.creative_director import _MODEL_CAPABILITIES, pick_model

    caps = _MODEL_CAPABILITIES["recraft/recraft-v3"]
    assert caps.get("verified") is False
    assert "fidelity" not in caps
    routed = pick_model({"typography": True})
    assert not str(routed.get("model") or "").startswith("recraft/")


def test_requested_recraft_operator_only():
    from _lib.creative_director import _model_allowed, pick_model

    assert _model_allowed("recraft/recraft-v3") is False
    assert _model_allowed("recraft/recraft-v3", allow_unverified=True) is True
    out = pick_model({"typography": True}, requested_model="recraft/recraft-v3")
    assert out["model"] == "recraft/recraft-v3"
    assert out.get("unverified") is True
