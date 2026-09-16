"""Daily Windsor.ai pull → meta-ads.json + google-ads.json."""

from __future__ import annotations

from ._io import atomic_write

META_OUT = "meta-ads.json"
GOOGLE_OUT = "google-ads.json"


def run() -> dict:
    """Fetch paid media via Windsor and write ad correlation JSON files."""
    try:
        from _lib import windsor_client as _w  # noqa: PLC0415
        from _lib.windsor_fetcher import build_google_ads, build_meta_ads  # noqa: PLC0415
    except ImportError as exc:
        return {"ok": False, "error": f"windsor_fetcher import failed: {exc}"}

    api_key = _w.read_api_key()
    if not api_key:
        return {"ok": False, "error": "WINDSOR_API_KEY not configured"}

    meta_payload = build_meta_ads(api_key)
    ga_payload = build_google_ads(api_key)
    atomic_write(META_OUT, meta_payload)
    atomic_write(GOOGLE_OUT, ga_payload)

    live = int(bool(meta_payload.get("live"))) + int(bool(ga_payload.get("live")))
    if live == 0:
        err = meta_payload.get("error") or ga_payload.get("error") or "both connectors failed"
        return {"ok": False, "error": str(err)[:300]}

    rows = int(meta_payload.get("_meta", {}).get("campaigns_count", 0)) + int(
        ga_payload.get("_meta", {}).get("campaigns_count", 0)
    )
    return {
        "ok": True,
        "rows": rows,
        "meta_live": bool(meta_payload.get("live")),
        "google_live": bool(ga_payload.get("live")),
    }
