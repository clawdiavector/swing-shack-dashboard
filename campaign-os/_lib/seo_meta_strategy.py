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
# V1.1 calibration (2026-10-01): verified live against swingshack.co.za
# post 4198 + Application Password auth. Yoast DOES accept
# _yoast_wpseo_title + _yoast_wpseo_metadesc + _yoast_wpseo_focuskw via
# the standard WP REST POST /posts meta_input (readback confirmed). The
# earlier claim that ALL Yoast keys are unsupported was wrong.
#
# Canonical (_yoast_wpseo_canonical) and schema (_yoast_wpseo_schema_*)
# ARE silently dropped on write — they require nonce-based auth or a
# custom Yoast REST bridge.
PLUGIN_BEHAVIOR = {
    "yoast": {
        "writable": ["seo_title", "meta_description", "target_query"],
        "unsupported": ["canonical", "schema"],
        # Yoast meta keys actually used on write:
        "meta_key_map": {
            "seo_title": "_yoast_wpseo_title",
            "meta_description": "_yoast_wpseo_metadesc",
            "target_query": "_yoast_wpseo_focuskw",
        },
        "notes": (
            "Yoast SEO: _yoast_wpseo_title, _yoast_wpseo_metadesc, "
            "_yoast_wpseo_focuskw are writable via REST meta_input under "
            "Application Password auth. Canonical (_yoast_wpseo_canonical) "
            "and schema (_yoast_wpseo_schema_*) are silently dropped and "
            "must be set manually in WP admin."
        ),
    },
    "rankmath": {
        "writable": ["seo_title", "meta_description", "target_query"],
        "unsupported": ["canonical", "schema"],
        "meta_key_map": {
            "seo_title": "rank_math_title",
            "meta_description": "rank_math_description",
            "target_query": "rank_math_focus_keyword",
        },
        "notes": (
            "Rank Math: rank_math_title + rank_math_description + "
            "rank_math_focus_keyword are typically writable via REST. "
            "Canonical + schema are not REST-writable."
        ),
    },
    "aioseo": {
        "writable": ["seo_title", "meta_description", "target_query"],
        "unsupported": ["canonical", "schema"],
        "meta_key_map": {
            "seo_title": "_aioseo_title",
            "meta_description": "_aioseo_description",
            "target_query": "_aioseo_keyphrases",
        },
        "notes": "AIOSEO uses similar nonce-only REST auth for some keys; title + description + keyphrase verified writable.",
    },
    "none": {
        "writable": ["seo_title", "meta_description", "canonical", "target_query"],
        "unsupported": ["schema"],
        "meta_key_map": {
            "seo_title": "seo_title",
            "meta_description": "meta_description",
            "canonical": "canonical",
            "target_query": "target_query",
        },
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

    Returns: (meta_input_dict, written_keys, unsupported_keys).

    V1.1 calibration (2026-10-01): Yoast SEO is verified writable for
    seo_title + meta_description + target_query via the standard
    /wp-json/wp/v2/posts meta_input (readback confirmed live on
    swingshack.co.za post 4198). The strategy module previously marked
    Yoast as fully unsupported — that was wrong. Canonical + schema
    are still unsupported and are surfaced as 'unsupported' for the
    operator to apply manually in WP admin.
    """
    plugin = detect_seo_plugin(brand_id) or "none"
    behavior = PLUGIN_BEHAVIOR.get(plugin, PLUGIN_BEHAVIOR["none"])
    writable = set(behavior["writable"])
    unsupported = set(behavior["unsupported"])
    # meta_key_map translates the OS field name (seo_title) to the
    # actual WP meta key (_yoast_wpseo_title).
    meta_key_map = behavior.get("meta_key_map", {})

    meta_input: dict = {}
    written: list[str] = []
    not_written: list[str] = []

    for key in ("seo_title", "meta_description", "canonical", "target_query", "schema"):
        if key not in seo_block:
            continue
        val = seo_block[key]
        if key in writable:
            # Translate OS field name to actual WP meta key via the plugin
            # meta_key_map. e.g. seo_title -> _yoast_wpseo_title.
            wp_meta_key = meta_key_map.get(key, key)
            meta_input[wp_meta_key] = val
            written.append(key)
        elif key in unsupported:
            not_written.append(key)
        else:
            # unknown key — write if no plugin, else flag unsupported
            if plugin == "none":
                wp_meta_key = meta_key_map.get(key, key)
                meta_input[wp_meta_key] = val
                written.append(key)
            else:
                not_written.append(key)
    return meta_input, written, not_written
