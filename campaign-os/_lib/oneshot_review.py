"""Review projection helpers for draft_oneshot sidecars."""

from __future__ import annotations

import json
import os
from typing import Any


def read_router_sidecar(path: str | None) -> dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def oneshot_meta_from_sidecar(sidecar: dict[str, Any]) -> dict[str, Any] | None:
    if str(sidecar.get("action") or "") != "draft_oneshot":
        return None
    router = read_router_sidecar(str(sidecar.get("router_sidecar_path") or "") or None)
    pick = (sidecar.get("model_routing") or {}).get("pick_model") or {}
    if not isinstance(pick, dict):
        pick = {}
    unverified = bool(pick.get("unverified"))
    return {
        "prompt_used": sidecar.get("prompt_used") or router.get("prompt_used"),
        "master_prompt": sidecar.get("master_prompt"),
        "negative_prompt": sidecar.get("negative_prompt"),
        "literal_text": sidecar.get("literal_text"),
        "literal_text_source": sidecar.get("literal_text_source"),
        "model": sidecar.get("model") or router.get("model"),
        "provider": sidecar.get("provider") or router.get("provider"),
        "unverified_model": unverified,
        "cost_usd": sidecar.get("cost_usd") if sidecar.get("cost_usd") is not None else router.get("cost_usd"),
        "cost_source": sidecar.get("source") or router.get("source"),
        "image_size": sidecar.get("image_size") or router.get("size"),
        "logo_source": sidecar.get("logo_source"),
        "logo_drift_warning": sidecar.get("logo_drift_warning"),
        "regen_count": sidecar.get("regen_count") or 0,
        "router_sidecar_path": sidecar.get("router_sidecar_path"),
    }
