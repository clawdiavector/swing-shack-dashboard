"""Wrap scripts/fetch_ubersuggest.py and write SEO ranking artifacts."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from ..errors import describe_exception
from ._io import data_dir, repo_root

WRITES = (
    "seo-rankings.json",
    "ubersuggest-domain.json",
    "ubersuggest-competitors.json",
    "ubersuggest-backlinks.json",
)


def _token_path() -> str | None:
    return os.environ.get("UBERSUGGEST_TOKEN_FILE")


def _token_present() -> bool:
    path = _token_path()
    if path:
        p = Path(path)
        if not p.is_file():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return bool(data.get("access_token"))
        except (OSError, json.JSONDecodeError):
            return False
    try:
        from _lib.ubersuggest_mcp import ubersuggest_credentials_present

        return ubersuggest_credentials_present()
    except ImportError:
        return False


def _load_ubersuggest_module() -> Any:
    script = repo_root() / "scripts" / "fetch_ubersuggest.py"
    if not script.is_file():
        raise FileNotFoundError(f"fetch_ubersuggest.py not found at {script}")

    campaign_os = repo_root() / "campaign-os"
    if str(campaign_os) not in sys.path:
        sys.path.insert(0, str(campaign_os))

    spec = importlib.util.spec_from_file_location("_fetch_ubersuggest_job", script)
    if spec is None or spec.loader is None:
        raise ImportError("could not load fetch_ubersuggest module spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DATA_DIR = data_dir()
    mod.CAMPAIGN_OS_DIR = campaign_os
    return mod


def _count_keywords() -> int:
    path = data_dir() / "seo-rankings.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keywords = data.get("keywords") or []
        return len(keywords) if isinstance(keywords, list) else 0
    except (OSError, json.JSONDecodeError):
        return 0


def run() -> dict:
    """Run Ubersuggest rank pull via the existing script."""
    if not _token_present():
        return {"ok": False, "error": "no ubersuggest token"}

    domain = os.environ.get("SWING_SHACK_DOMAIN", "swingshack.co.za")
    if not domain.strip():
        return {"ok": False, "error": "SWING_SHACK_DOMAIN not set"}

    try:
        mod = _load_ubersuggest_module()
        exit_code = mod.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 2:
            return {"ok": False, "error": "no ubersuggest token"}
        return {"ok": False, "error": f"ubersuggest exited with code {code}"}
    except Exception as exc:
        return {"ok": False, "error": f"ubersuggest failed: {describe_exception(exc)}"}

    rows = _count_keywords()

    if exit_code == 0:
        return {"ok": True, "rows": rows}
    if exit_code == 2:
        return {"ok": False, "error": "no ubersuggest token"}
    if exit_code == 3:
        return {"ok": True, "rows": rows, "partial": True}
    return {"ok": False, "error": f"ubersuggest exited with code {exit_code}"}
