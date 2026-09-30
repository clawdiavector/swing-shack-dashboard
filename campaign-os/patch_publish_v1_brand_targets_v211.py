"""
patch_publish_v1_brand_targets_v211.py — Seed brand→CMS publishing target config.

Bootstrap-on-first-run pattern (same as brand-bible / important-dates):
  DATA_DIR/publishing-targets/<brand>.json   (volume, persistent)
  data/publishing-targets/<brand>.json       (baked in image, fallback)

For each brand, the canonical operating_brand → wp_api_base mapping is seeded.
Stick is configured with live WordPress credentials (env-driven). Swing-shack
and bag-drop are configured with target placeholders (no creds yet — flagged
in the target as `enabled: false`).

Idempotent. Marker: DATA_DIR/.publish-v1-brand-targets-v211-applied.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")
MARKER = Path(DATA_DIR) / ".publish-v1-brand-targets-v211-applied"
BAKED_DIR = Path("/app/data/publishing-targets")
BAKED_FALLBACK = Path(__file__).resolve().parent.parent / "data" / "publishing-targets"


# Canonical target template. Per brand only the wp_user_env / wp_app_password_env
# names differ; those map to env vars on Railway.
TARGETS: dict[str, dict] = {
    "stick": {
        "brand_id": "stick",
        "operating_brand": "stick",
        "cms_target": "stickgolf.co.za",
        "cms_kind": "wordpress",
        "wp_api_base": "https://stickgolf.co.za/wp-json/wp/v2",
        "wp_user_env": "STICKGOLF_WP_USER",
        "wp_app_password_env": "STICKGOLF_WP_APP_PASSWORD",
        "default_post_type": "post",
        "default_status_on_stage": "draft",
        "timezone": "Africa/Johannesburg",
        "internal_link_allowlist": [
            "https://stickgolf.co.za/",
            "https://swingshack.co.za/",
        ],
        "seo_metadata_supported": True,
        "scheduling_supported": True,
        "media_upload_supported": True,
        "enabled": True,
        "source": "operator directive (Discord, 2026-09-30, msg 1554476057191645236)",
        "updated": "2026-09-30",
    },
    "swing-shack": {
        "brand_id": "swing-shack",
        "operating_brand": "swing-shack",
        "cms_target": "swingshack.co.za",
        "cms_kind": "wordpress",
        "wp_api_base": "https://swingshack.co.za/wp-json/wp/v2",
        "wp_user_env": "SWINGSHACK_WP_USER",
        "wp_app_password_env": "SWINGSHACK_WP_APP_PASSWORD",
        "default_post_type": "post",
        "default_status_on_stage": "draft",
        "timezone": "Africa/Johannesburg",
        "internal_link_allowlist": [
            "https://swingshack.co.za/",
            "https://stickgolf.co.za/",
        ],
        "seo_metadata_supported": True,
        "scheduling_supported": True,
        "media_upload_supported": True,
        "enabled": False,
        "source": "operator directive (Discord, 2026-09-30, msg 1554476057191645236) — credentials pending",
        "updated": "2026-09-30",
    },
    "bag-drop": {
        "brand_id": "bag-drop",
        "operating_brand": "bag-drop",
        "cms_target": "swingshack.co.za",
        "cms_kind": "wordpress",
        "wp_api_base": "https://swingshack.co.za/wp-json/wp/v2",
        "wp_user_env": "SWINGSHACK_WP_USER",
        "wp_app_password_env": "SWINGSHACK_WP_APP_PASSWORD",
        "default_post_type": "post",
        "default_status_on_stage": "draft",
        "timezone": "Africa/Johannesburg",
        "internal_link_allowlist": [
            "https://swingshack.co.za/",
            "https://stickgolf.co.za/",
        ],
        "seo_metadata_supported": True,
        "scheduling_supported": True,
        "media_upload_supported": True,
        "enabled": False,
        "source": "operator directive (Discord, 2026-09-30, msg 1554476057191645236) — bag-drop test brand; not currently routed to a CMS",
        "updated": "2026-09-30",
    },
}


def _write_target(brand_id: str, target: dict) -> bool:
    """Write a single target JSON to volume if missing or changed. Returns True if written."""
    vol_dir = Path(DATA_DIR) / "publishing-targets"
    vol_dir.mkdir(parents=True, exist_ok=True)
    vol_path = vol_dir / f"{brand_id}.json"
    # Always rewrite if not yet applied (idempotent; safe re-runs OK).
    if vol_path.exists() and MARKER.exists():
        return False
    vol_path.write_text(json.dumps(target, indent=2, ensure_ascii=False))
    return True


def _bake_targets_to_repo_fallback() -> None:
    """Bake each target to data/publishing-targets/<brand>.json so the Docker image
    has a fallback when the volume is fresh.
    """
    BAKED_FALLBACK.mkdir(parents=True, exist_ok=True)
    for brand_id, target in TARGETS.items():
        path = BAKED_FALLBACK / f"{brand_id}.json"
        if not path.exists():
            path.write_text(json.dumps(target, indent=2, ensure_ascii=False))


def main() -> int:
    _bake_targets_to_repo_fallback()
    written = 0
    for brand_id, target in TARGETS.items():
        if _write_target(brand_id, target):
            written += 1
            print(f"[v2.11/publish-v1-brand-targets] seeded {brand_id} → {target['cms_target']}", flush=True)
    if not MARKER.exists():
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(f"written={written}\n")
        print(f"[v2.11/publish-v1-brand-targets] done ({written} new) → {MARKER}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
