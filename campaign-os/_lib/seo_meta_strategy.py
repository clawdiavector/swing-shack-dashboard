"""
_lib/seo_meta_strategy.py — Per-site SEO metadata write strategy.

WP REST `meta_input` is filtered through each registered meta key's
`show_in_rest` + `auth_callback` whitelist. Most SEO plugins (Yoast, RankMath,
AIOSEO) register their meta keys with REST access that REQUIRES edit-context
nonce-based auth, not Basic Application Password auth. Result: the standard
POST /posts meta_input silently drops those keys.

This module detects the installed SEO plugin for each brand's CMS and decides
what (if anything) Campaign OS can write via REST. Anything not writable is
recorded as "not written to CMS" in the audit log and the desired values
remain on the Publish record (operator can apply them manually in WP admin).

Detection is a single GET to the WP root index and a check for the plugin's
namespace route. We don't introspect the meta schema; we use the empirically
observed Yoast pattern (most common) as the default fallback.
"""
from __future__ import annotations
import os
import urllib.error
import urllib.request
import json
from typing import Tuple


# Detected plugin → (writable_meta_keys, unsupported_keys, notes).
# Yoast: meta_input is NOT writable via REST for Application Password auth.
# The keys exist in the REST schema but writing them returns empty values.
# Schema (Yoast FAQ JSON-LD) is also not exposed for write.
PLUGIN_BEHAVIOR = {
    "yoast": {
        "writable": [],
        "unsupported": ["seo_title", "meta_description", "canonical", "schema", "target_query"],
        "notes": (
            "Yoast SEO registered keys (_yoast_wpseo_title, _yoast_wpseo_metadesc, "
            "_yoast_wpseo_canonical) are present in the REST schema but writes "
            "via meta_input are silently dropped under Application Password "
            "Basic auth. Canonical + schema are not exposed via REST at all. "
            "Operator must set these manually in WP admin or via a custom "
            "REST-Authenticated server-side bridge."
        ),
    },
    "rankmath": {
        "writable": ["seo_title", "meta_description"],
        "unsupported": ["canonical", "schema", "target_query"],
        "notes": (
            "Rank Math exposes rank_math_title + rank_math_description via REST "
            "but its auth_callback requires nonce, not Basic auth. Schema and "
            "canonical are not REST-writable."
        ),
    },
    "aioseo": {
        "writable": ["seo_title", "meta_description"],
        "unsupported": ["canonical", "schema", "target_query"],
        "notes": "AIOSEO uses similar nonce-only REST auth.",
    },
    "none": {
        "writable": ["seo_title", "meta_description", "canonical", "target_query"],
        "unsupported": ["schema"],
        "notes": "No SEO plugin detected. Standard WP REST meta_input works for the listed keys.",
    },
}


def _cms_api_base(brand_id: str) -> str | None:
    """Return the wp_api_base for the brand from the publishing target."""
    from _lib.publish_v1 import load_publishing_target
    t = load_publishing_target(brand_id)
    if not t:
        return None
    return t.get("wp_api_base")


def detect_seo_plugin(brand_id: str) -> str | None:
    """Return the detected SEO plugin name (e.g. 'yoast') or None if undetectable."""
    base = _cms_api_base(brand_id)
    if not base:
        return None
    root = base.rsplit("/wp/v2", 1)[0]
    try:
        req = urllib.request.Request(f"{root}/", headers={"User-Agent": "CampaignOS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())
        routes = d.get("routes") or {}
        # Yoast always registers /yoast/v1 — that's our primary marker
        if any("/yoast/v1" in k for k in routes):
            return "yoast"
        if any("/rankmath/v1" in k for k in routes):
            return "rankmath"
        if any("/aioseo/v1" in k for k in routes):
            return "aioseo"
        return "none"
    except Exception:
        return None


def build_meta_input(brand_id: str, seo_block: dict) -> Tuple[dict, list[str], list[str]]:
    """Decide what to write to meta_input for the given brand.

    Returns: (meta_input_dict, written_keys, unsupported_keys)
    For Yoast: returns ({}, [], list of all desired keys) — nothing written.
    For RankMath/AIOSEO: returns ({}, [], all keys) — same conservative behavior
    (REST nonce auth is unreliable for Application Password).
    For none: writes the standard meta_input keys.
    """
    plugin = detect_seo_plugin(brand_id) or "none"
    behavior = PLUGIN_BEHAVIOR.get(plugin, PLUGIN_BEHAVIOR["none"])
    writable = set(behavior["writable"])
    unsupported = set(behavior["unsupported"])

    meta_input: dict = {}
    written: list[str] = []
    not_written: list[str] = []

    for key in ("seo_title", "meta_description", "canonical", "target_query", "schema"):
        if key not in seo_block:
            continue
        val = seo_block[key]
        if key in writable:
            meta_input[key] = val
            written.append(key)
        elif key in unsupported:
            not_written.append(key)
        else:
            # unknown key — write if no plugin, else flag unsupported
            if plugin == "none":
                meta_input[key] = val
                written.append(key)
            else:
                not_written.append(key)
    return meta_input, written, not_written
