"""Inspiration Intelligence Slice 1 — brand-scoped CRUD for watchlist profiles and saved posts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

# Resolve the _lib package from campaign-os root for local imports.
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from _lib.brand_data_paths import resolve_brand_data_path

# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------
SCHEMA_WATCHLIST = "https://campaign-os/inspiration/v1/watchlist"
SCHEMA_POSTS = "https://campaign-os/inspiration/v1/posts"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _inspiration_path(filename: str, brand_id: str) -> str:
    """Resolve the full filesystem path for an inspiration data file."""
    return resolve_brand_data_path(filename, brand_id)


def _read_json_file(path: str) -> dict | list | None:
    """Read and parse a JSON file; return None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _write_json_file(path: str, data: dict | list) -> bool:
    """Serialize data to a JSON file with pretty-printing; return True on success."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Canonical empty structures
# ---------------------------------------------------------------------------


def _canonical_watchlist(brand_id: str) -> dict:
    return {
        "schema": SCHEMA_WATCHLIST,
        "brand_id": brand_id,
        "profiles": [],
        "updated_at": _utc_now(),
    }


def _canonical_posts(brand_id: str) -> dict:
    return {
        "schema": SCHEMA_POSTS,
        "brand_id": brand_id,
        "posts": [],
        "updated_at": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Ensure (create if absent)
# ---------------------------------------------------------------------------

INSP_FILE_WATCHLIST = "inspiration-watchlist.json"
INSP_FILE_POSTS = "inspiration-posts.json"


def inspiration_ensure_watchlist(brand_id: str) -> dict | None:
    """Return the watchlist for a brand, creating the canonical empty structure if absent."""
    path = _inspiration_path(INSP_FILE_WATCHLIST, brand_id)
    existing = _read_json_file(path)
    if existing is not None:
        if isinstance(existing, dict):
            return existing
        return None  # unexpected type
    canonical = _canonical_watchlist(brand_id)
    ok = _write_json_file(path, canonical)
    return canonical if ok else None


def inspiration_ensure_posts(brand_id: str) -> dict | None:
    """Return the posts for a brand, creating the canonical empty structure if absent."""
    path = _inspiration_path(INSP_FILE_POSTS, brand_id)
    existing = _read_json_file(path)
    if existing is not None:
        if isinstance(existing, dict):
            return existing
        return None
    canonical = _canonical_posts(brand_id)
    ok = _write_json_file(path, canonical)
    return canonical if ok else None


# ---------------------------------------------------------------------------
# Read operations — return empty canonical response (HTTP 200, not 404)
# ---------------------------------------------------------------------------


def inspiration_read_watchlist(brand_id: str) -> dict:
    """Read the brand's watchlist profile data.

    Returns the canonical empty structure if the file does not yet exist.
    Returns None on error (caller may treat as 500).
    """
    path = _inspiration_path(INSP_FILE_WATCHLIST, brand_id)
    existing = _read_json_file(path)
    if existing is None:
        return _canonical_watchlist(brand_id)
    if isinstance(existing, dict):
        return existing
    return _canonical_watchlist(brand_id)


def inspiration_read_posts(brand_id: str) -> dict:
    """Read the brand's saved posts data.

    Returns the canonical empty structure if the file does not yet exist.
    Returns None on error (caller may treat as 500).
    """
    path = _inspiration_path(INSP_FILE_POSTS, brand_id)
    existing = _read_json_file(path)
    if existing is None:
        return _canonical_posts(brand_id)
    if isinstance(existing, dict):
        return existing
    return _canonical_posts(brand_id)


# ---------------------------------------------------------------------------
# Write operations — auto-create if absent
# ---------------------------------------------------------------------------


def inspiration_write_watchlist(brand_id: str, data: dict) -> bool:
    """Write the brand's watchlist profile data.

    Auto-creates the file (canonical empty structure) if absent before writing.
    Returns True on success, False on failure.
    """
    path = _inspiration_path(INSP_FILE_WATCHLIST, brand_id)
    # Ensure parent dir / file exists
    ensure = inspiration_ensure_watchlist(brand_id)
    if ensure is None:
        return False
    return _write_json_file(path, data)


def inspiration_write_posts(brand_id: str, data: dict) -> bool:
    """Write the brand's saved posts data.

    Auto-creates the file (canonical empty structure) if absent before writing.
    Returns True on success, False on failure.
    """
    path = _inspiration_path(INSP_FILE_POSTS, brand_id)
    ensure = inspiration_ensure_posts(brand_id)
    if ensure is None:
        return False
    return _write_json_file(path, data)


# -----------------------------------------------------------------------------
# Canonical analysis schema — all fields null/empty for Slice 1
# AI population is the Slice 2+ contract; schema is pre-seeded now.
# -----------------------------------------------------------------------------


ANALYSIS_SCHEMA = {
    # Structural
    "format": None,               # e.g. reel, carousel, static, story
    "content_type": None,         # e.g. educational, entertainment, testimonial, product
    "hook_type": None,            # e.g. question, stat, contrast, confession
    "human_presence": None,       # bool
    "creator_presence": None,      # bool — is the creator/brand face visible?
    "collaboration": None,        # bool
    "influencer": None,           # bool — is this an influencer post?
    "product_presence": None,     # bool
    "product_launch": None,        # bool
    # Content attributes
    "educational": None,           # bool
    "humour": None,               # bool
    "offer": None,                # bool
    "question": None,             # bool — does the hook ask a question?
    # Visual
    "visual_style": [],            # list[str] — e.g. cinematic, clean-minimal, user-gen
    "colour_characteristics": [],  # list[str] — dominant/accent colours observed
    "editing_style": [],          # list[str] — e.g. fast-cut, slow-motion, raw
    "audio_type": None,           # e.g. trending-audio, original, voice-over, no-audio
    "text_overlay": None,         # e.g. caption, graphic, animated-text
    # CTA
    "cta_type": None,             # e.g. link-in-bio, swipe-up, dm, comment, share
    # Emotional
    "primary_emotion": [],         # list[str] — e.g. curiosity, pride, awe, FOMO
    "creative_mechanic": [],       # list[str] — e.g. contrast, surprise, social-proof
    "likely_performance_drivers": [],  # list[str] — why this post may have worked
    # Assessment
    "analysis_confidence": None,   # low | medium | high
    "summary": None,              # free-text AI summary (future)
}


def _new_analysis_schema() -> dict:
    """Return a fresh copy of the canonical analysis schema with null/empty defaults."""
    return {
        "format": None,
        "content_type": None,
        "hook_type": None,
        "human_presence": None,
        "creator_presence": None,
        "collaboration": None,
        "influencer": None,
        "product_presence": None,
        "product_launch": None,
        "educational": None,
        "humour": None,
        "offer": None,
        "question": None,
        "visual_style": [],
        "colour_characteristics": [],
        "editing_style": [],
        "audio_type": None,
        "text_overlay": None,
        "cta_type": None,
        "primary_emotion": [],
        "creative_mechanic": [],
        "likely_performance_drivers": [],
        "analysis_confidence": None,
        "summary": None,
    }


# -----------------------------------------------------------------------------
# Profile CRUD
# -----------------------------------------------------------------------------


import uuid as _uuid


def _new_id() -> str:
    return _uuid.uuid4().hex[:12]


def inspiration_add_profile(brand_id: str, profile: dict) -> tuple[dict, int]:
    """Add a new profile to the brand watchlist. Returns (created_profile, status)."""
    data = inspiration_ensure_watchlist(brand_id)
    if data is None:
        return {"error": "could not ensure watchlist"}, 500
    now = _utc_now()
    caps = profile.get("captured_metrics") or {}
    new_profile = {
        "profile_id": _new_id(),
        "platform": profile.get("platform"),
        "handle": profile.get("handle"),
        "display_name": profile.get("display_name", ""),
        "profile_url": profile.get("profile_url", ""),
        "bio": profile.get("bio") or None,
        "why_tags": list(profile.get("why_tags") or []),
        "notes": profile.get("notes") or None,
        "captured_metrics": {
            "followers": caps.get("followers"),
            "following": caps.get("following"),
            "posts": caps.get("posts"),
            "avg_likes": caps.get("avg_likes"),
            "avg_comments": caps.get("avg_comments"),
        },
        "last_saved": now,
        "created_by": profile.get("created_by") or None,
        "created_at": now,
        "updated_at": now,
    }
    data["profiles"].append(new_profile)
    data["updated_at"] = now
    if inspiration_write_watchlist(brand_id, data):
        return {"ok": True, "data": new_profile}, 201
    return {"error": "write failed"}, 500


def inspiration_update_profile(brand_id: str, profile_id: str, patch: dict) -> tuple[dict, int]:
    """Update fields on an existing profile. Returns (result, status)."""
    data = inspiration_ensure_watchlist(brand_id)
    if data is None:
        return {"ok": False, "error": "not found"}, 404
    for p in data["profiles"]:
        if p["profile_id"] == profile_id:
            for field in ("display_name", "bio", "why_tags", "notes", "handle", "profile_url"):
                if field in patch:
                    p[field] = patch[field]
            if "captured_metrics" in patch:
                for mk, mv in (patch["captured_metrics"] or {}).items():
                    if mk in p["captured_metrics"]:
                        p["captured_metrics"][mk] = mv
            p["updated_at"] = _utc_now()
            data["updated_at"] = p["updated_at"]
            if inspiration_write_watchlist(brand_id, data):
                return {"ok": True, "data": p}, 200
            return {"ok": False, "error": "write failed"}, 500
    return {"ok": False, "error": "profile not found"}, 404


def inspiration_delete_profile(brand_id: str, profile_id: str) -> tuple[dict, int]:
    """Remove a profile and its associated saved posts. Returns (result, status)."""
    data = inspiration_ensure_watchlist(brand_id)
    if data is None:
        return {"ok": False, "error": "watchlist not found"}, 404
    original = len(data["profiles"])
    data["profiles"] = [p for p in data["profiles"] if p["profile_id"] != profile_id]
    if len(data["profiles"]) == original:
        return {"ok": False, "error": "profile not found"}, 404
    data["updated_at"] = _utc_now()
    ok = inspiration_write_watchlist(brand_id, data)
    if ok:
        # Cascade: remove all posts referencing this profile
        posts = inspiration_read_posts(brand_id)
        if posts and posts.get("posts"):
            posts["posts"] = [
                pt for pt in posts["posts"]
                if pt.get("source_profile", {}).get("profile_id") != profile_id
            ]
            posts["updated_at"] = _utc_now()
            inspiration_write_posts(brand_id, posts)
    return {"ok": True, "deleted": profile_id}, 200


# -----------------------------------------------------------------------------
# Post CRUD
# -----------------------------------------------------------------------------


def inspiration_add_post(brand_id: str, post: dict) -> tuple[dict, int]:
    """Save a new inspiration post. Returns (created_post, status)."""
    data = inspiration_ensure_posts(brand_id)
    if data is None:
        return {"error": "could not ensure posts file"}, 500
    now = _utc_now()

    # Normalise source_profile: plain string handle → dict, anything else → {}
    raw_sp = post.get("source_profile")
    if isinstance(raw_sp, str):
        src_profile = {"handle": raw_sp}
    elif isinstance(raw_sp, dict):
        src_profile = raw_sp
    else:
        src_profile = {}
    captured_metrics = post.get("captured_metrics") or {}
    provenance_in = post.get("provenance") or {}

    new_post = {
        "post_id": _new_id(),
        "source_profile": {
            "profile_id": src_profile.get("profile_id"),
            "handle": src_profile.get("handle"),
            "display_name": src_profile.get("display_name"),
        },
        "external_post_id": post.get("external_post_id") or None,
        "platform": post.get("platform"),
        "source_url": post.get("source_url") or post.get("post_url") or "",
        "published_at": post.get("published_at") or None,
        "media_type": post.get("media_type") or None,
        "caption": post.get("caption") or None,
        "why_tags": list(post.get("why_tags") or []),
        "why_notes": post.get("why_notes") or None,
        "captured_metrics": {
            "likes": captured_metrics.get("likes"),
            "comments": captured_metrics.get("comments"),
            "saves": captured_metrics.get("saves"),
            "shares": captured_metrics.get("shares"),
            "views": captured_metrics.get("views"),
            "engagement_rate": captured_metrics.get("engagement_rate"),
        },
        "analysis_schema": _new_analysis_schema(),
        "provenance": {
            "source_type": provenance_in.get("source_type") or None,
            "source_url": provenance_in.get("source_url") or post.get("source_url") or post.get("post_url") or None,
            "collected_at": provenance_in.get("collected_at") or now,
            "collection_method": provenance_in.get("collection_method") or "manual",
            "analysed_by": provenance_in.get("analysed_by") or None,
            "analysis_version": provenance_in.get("analysis_version") or None,
        },
        "used_in": list(post.get("used_in") or []),
        "created_by": post.get("created_by") or None,
        "created_at": now,
        "updated_at": now,
    }
    data["posts"].append(new_post)
    data["updated_at"] = now
    if inspiration_write_posts(brand_id, data):
        return {"ok": True, "data": new_post}, 201
    return {"error": "write failed"}, 500


def inspiration_update_post(brand_id: str, post_id: str, patch: dict) -> tuple[dict, int]:
    """Update fields on an existing post. Returns (result, status)."""
    data = inspiration_ensure_posts(brand_id)
    if data is None:
        return {"ok": False, "error": "posts not found"}, 404
    for p in data["posts"]:
        if p["post_id"] == post_id:
            for field in ("caption", "why_notes"):
                if field in patch:
                    p[field] = patch[field]
            if "why_tags" in patch:
                p["why_tags"] = list(patch["why_tags"])
            if "captured_metrics" in patch:
                for mk, mv in (patch["captured_metrics"] or {}).items():
                    if mk in p["captured_metrics"]:
                        p["captured_metrics"][mk] = mv
            # Support both "analysis_schema" (canonical) and "analysis" (backward compat)
            schema_patch = patch.get("analysis_schema") or patch.get("analysis") or {}
            for ak, av in schema_patch.items():
                if ak in p["analysis_schema"]:
                    p["analysis_schema"][ak] = av
            if "provenance" in patch:
                for pk, pv in (patch["provenance"] or {}).items():
                    if pk in p["provenance"]:
                        p["provenance"][pk] = pv
            if "used_in" in patch:
                p["used_in"] = list(patch["used_in"])
            p["updated_at"] = _utc_now()
            data["updated_at"] = p["updated_at"]
            if inspiration_write_posts(brand_id, data):
                return {"ok": True, "data": p}, 200
            return {"ok": False, "error": "write failed"}, 500
    return {"ok": False, "error": "post not found"}, 404


def inspiration_delete_post(brand_id: str, post_id: str) -> tuple[dict, int]:
    """Remove a post. Returns (result, status)."""
    data = inspiration_ensure_posts(brand_id)
    if data is None:
        return {"ok": False, "error": "posts not found"}, 404
    original = len(data["posts"])
    data["posts"] = [pt for pt in data["posts"] if pt["post_id"] != post_id]
    if len(data["posts"]) == original:
        return {"ok": False, "error": "post not found"}, 404
    data["updated_at"] = _utc_now()
    if inspiration_write_posts(brand_id, data):
        return {"ok": True, "deleted": post_id}, 200
    return {"ok": False, "error": "write failed"}, 500


def get_post(brand_id: str, post_id: str) -> dict | None:
    """Return a single post by ID, or None if not found."""
    data = inspiration_read_posts(brand_id)
    for post in data.get("posts", []):
        if post["post_id"] == post_id:
            return post
    return None


def get_profile(brand_id: str, profile_id: str) -> dict | None:
    """Return a single watchlist profile by ID, or None if not found."""
    data = inspiration_read_watchlist(brand_id)
    for profile in data.get("profiles", []):
        if profile["profile_id"] == profile_id:
            return profile
    return None
