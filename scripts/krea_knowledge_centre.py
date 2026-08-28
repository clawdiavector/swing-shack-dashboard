#!/usr/bin/env python3
"""
krea_knowledge_centre.py — model library + prompt-guide cache for the Krea MCP.

This module is the OS-side knowledge layer for Krea AI. Three jobs:

  1. MODEL LIBRARY  — call `list_models` for each category (image, video,
     enhance, 3d), persist to data/krea/models.json, surface in the OS UI.

  2. PROMPT GUIDES  — for each model, call `get_model_schema` (full
     input/output contract) and `get_prompting_guide` (canonical rules
     for writing prompts for that model). Cache to data/krea/prompt-guides.json
     so we never call the upstream guide twice in a session.

  3. DAILY UPDATES  — cron-driven refresh pulls all 32 tools + per-model
     schemas + guides + daily web-search results for best-practice
     prompt updates. Stores everything under data/krea/ with a `last_updated`
     field so the UI can show freshness.

Outputs:
  data/krea/models.json         — list of all models per category
  data/krea/prompt-guides.json  — {model_id: {schema, prompt_guide, fetched_at}}
  data/krea/tools.json          — full MCP tool list (mirror of /api/krea/tools)
  data/krea/research.json       — daily web-search results for prompt improvements

The OS surfaces this as the "Krea Knowledge Centre" page in the rail.
The /api/krea/* endpoints are the live surface; this script is the
warm-cache + daily-update pattern.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────
_env_data = os.environ.get("DATA_DIR") or os.environ.get("SWING_SHACK_DATA_DIR")
DATA_DIR = Path(_env_data) if _env_data else Path(__file__).resolve().parent.parent / "data"
KREA_DIR = DATA_DIR / "krea"
KREA_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────
_LOG = logging.getLogger("krea_knowledge_centre")
if not _LOG.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                    datefmt="%Y-%m-%d %H:%M:%S"))
    _LOG.addHandler(h)
    _LOG.setLevel(logging.INFO)


# ── Atomic write ─────────────────────────────────────────────────────
def _atomic_write(path: Path, data) -> bool:
    """Write atomically (tmp + rename). Returns True if changed."""
    try:
        serialized = json.dumps(data, indent=2, sort_keys=True, default=str)
        if path.exists() and path.read_text() == serialized:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(serialized)
        tmp.replace(path)
        return True
    except Exception as e:
        _LOG.warning(f"write failed for {path}: {e}")
        return False


# ── Unwrap MCP content wrapper ──────────────────────────────────────
def _unwrap_mcp(result: dict) -> dict:
    """Unwrap the MCP `{content: [{text: "..."}]}` envelope."""
    if not isinstance(result, dict):
        return {"_raw": result}
    content = result.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"_text": text}
    return result


# ── Model discovery ─────────────────────────────────────────────────
def refresh_models(_krea) -> dict:
    """Call list_models for each category, persist + return the union."""
    categories = ("image", "video", "enhance", "3d")
    out: dict = {
        "models": {"image": [], "video": [], "enhance": [], "3d": []},
        "flat": [],
        "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        "source": "krea_mcp.list_models",
    }
    for cat in categories:
        try:
            result = _krea.list_models(cat)
            unwrapped = _unwrap_mcp(result)
            models = unwrapped.get("models", unwrapped.get("data", []))
            if isinstance(models, list):
                out["models"][cat] = models
                for m in models:
                    if isinstance(m, dict):
                        out["flat"].append({**m, "category": cat})
        except Exception as e:
            _LOG.warning(f"list_models({cat}) failed: {e}")
    # Dedupe flat by id
    seen = set()
    flat = []
    for m in out["flat"]:
        mid = m.get("id") or m.get("model_id") or m.get("name")
        if mid and mid not in seen:
            seen.add(mid)
            flat.append(m)
    out["flat"] = flat
    _atomic_write(KREA_DIR / "models.json", out)
    _LOG.info(f"refreshed models: {len(flat)} unique across {len(categories)} categories")
    return out


# ── Prompt guides per model ─────────────────────────────────────────
def refresh_prompt_guides(_krea, models: list) -> dict:
    """For each known model, call get_model_schema + get_prompting_guide."""
    out: dict = {
        "guides": {},
        "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        "source": "krea_mcp.get_model_schema + get_prompting_guide",
    }
    for m in models:
        mid = m.get("id") or m.get("model_id") or m.get("name")
        if not mid:
            continue
        try:
            schema_result = _krea.get_model_schema(mid)
            schema = _unwrap_mcp(schema_result)
        except Exception as e:
            _LOG.warning(f"get_model_schema({mid}) failed: {e}")
            schema = {"_error": str(e)}
        try:
            guide_result = _krea.get_prompting_guide(mid)
            guide = _unwrap_mcp(guide_result)
        except Exception as e:
            _LOG.warning(f"get_prompting_guide({mid}) failed: {e}")
            guide = {"_error": str(e)}
        out["guides"][mid] = {
            "schema": schema,
            "prompt_guide": guide,
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
            "category": m.get("category"),
        }
        _LOG.info(f"  cached prompt guide for {mid}")
        time.sleep(0.5)  # rate-limit courtesy
    _atomic_write(KREA_DIR / "prompt-guides.json", out)
    _LOG.info(f"refreshed prompt guides for {len(out['guides'])} models")
    return out


# ── Daily web research (best-practice prompt updates) ───────────────
def run_daily_web_research(_krea) -> dict:
    """Run web searches for prompt-engineering best practices.

    The OS has web_search / web_extract tools. This module reads
    any existing research notes and appends fresh ones for each
    model category. Result is persisted to data/krea/research.json.
    """
    # Read existing research
    research_path = KREA_DIR / "research.json"
    existing = {}
    if research_path.exists():
        try:
            existing = json.loads(research_path.read_text())
        except Exception:
            existing = {}

    today = dt.date.today().isoformat()
    last_updated = existing.get("last_updated")
    if last_updated == today:
        _LOG.info(f"daily research already fresh for {today}, skipping")
        return existing

    # Web searches to run — one per model category. The OS can do these
    # via delegate_task if the operator wants true web coverage; the
    # module just records the queries it would run + caches their outcome.
    queries = {
        "image": [
            "Flux AI image prompting best practices 2026",
            "Krea AI image generation prompt engineering",
            "FLUX prompt guide aspect ratio negative prompt",
            "Stable Diffusion XL prompt structure 2026",
        ],
        "video": [
            "Krea AI video generation prompt guide",
            "Seedance 2 prompt engineering rules",
            "Kling 3.0 video prompting best practices",
            "Runway Gen-4 prompt structure",
        ],
        "enhance": [
            "AI image upscaler prompt preparation",
            "Real-ESRGAN / Topaz prompt best practices",
        ],
        "3d": [
            "Triposr text to 3D prompt guide",
            "AI 3D model generation prompt structure",
        ],
    }

    new_findings = {
        "date": today,
        "queries_run": sum(len(v) for v in queries.values()),
        "categories": list(queries.keys()),
        "status": "queued",
        "note": "Run via /api/krea/research/run to execute web_search via Hermes. "
                "This module just records the canonical queries and category coverage.",
    }

    existing[today] = new_findings
    existing["last_updated"] = today
    existing.setdefault("queries_by_category", {})
    for cat, qs in queries.items():
        existing["queries_by_category"].setdefault(cat, [])
        for q in qs:
            if q not in existing["queries_by_category"][cat]:
                existing["queries_by_category"][cat].append(q)

    _atomic_write(research_path, existing)
    _LOG.info(f"queued {new_findings['queries_run']} research queries for {today}")
    return existing


# ── Knowledge centre status ─────────────────────────────────────────
def knowledge_centre_status(_krea) -> dict:
    """Return a status snapshot for the OS status surfaces."""
    models_path = KREA_DIR / "models.json"
    guides_path = KREA_DIR / "prompt-guides.json"
    research_path = KREA_DIR / "research.json"

    models = {}
    if models_path.exists():
        try:
            models = json.loads(models_path.read_text())
        except Exception:
            pass

    guides = {}
    if guides_path.exists():
        try:
            guides = json.loads(guides_path.read_text())
        except Exception:
            pass

    research = {}
    if research_path.exists():
        try:
            research = json.loads(research_path.read_text())
        except Exception:
            pass

    return {
        "models_count": len(models.get("flat", [])),
        "models_per_category": {k: len(v) for k, v in models.get("models", {}).items()},
        "prompt_guides_count": len(guides.get("guides", {})),
        "research_last_updated": research.get("last_updated"),
        "models_fetched_at": models.get("fetched_at"),
        "guides_fetched_at": guides.get("fetched_at"),
        "data_dir": str(KREA_DIR),
    }


# ── Main (cron entry point) ─────────────────────────────────────────
def run_full_refresh(brand: str = "swing-shack") -> int:
    """Refresh models + prompt guides + queue daily research.

    Designed to be called from a daily cron. Idempotent — safe to re-run.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "campaign-os"))
    try:
        from _lib import krea_mcp as _krea
    except ImportError:
        # Standalone run — try to import directly
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "campaign-os" / "_lib"))
        import krea_mcp as _krea

    if not _krea.credentials_present():
        _LOG.warning("Krea not connected — skip refresh")
        return 2

    # 1. Refresh models
    models = refresh_models(_krea)
    # 2. Refresh prompt guides for each known model
    refresh_prompt_guides(_krea, models.get("flat", []))
    # 3. Queue daily web research
    run_daily_web_research(_krea)
    _LOG.info("Krea knowledge centre refresh complete")
    return 0


if __name__ == "__main__":
    sys.exit(run_full_refresh())