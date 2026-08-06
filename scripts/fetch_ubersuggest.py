#!/usr/bin/env python3
"""fetch_ubersuggest.py — daily rank-tracking pull for swingshack.co.za.

Live-tested 2026-08-06. Replaces the previous build that called
`keyword_overview` per-keyword (which had two problems:

  1. `keyword_overview` requires `location` as a country STRING
     (e.g. "ZA"), NOT `locId` (numeric). MCP server rejects with
     `Invalid "location" parameter.` when given `locId`.
  2. Even with a valid country, `keyword_overview` doesn't rank-track —
     it returns global search-volume/CPC numbers, not positions.
     Rank tracking lives in `project_position_info` against the
     existing Ubersuggest project.

The active Ubersuggest project for swingshack.co.za (discovered via
`list_projects()`) is configured for `loc_id=2710` (Johannesburg).

Outputs:
  data/seo-rankings.json           — full project_position_info schema,
                                     flatened into the legacy ranking shape
                                     for downstream weekly_report claim
                                     generators.
  data/ubersuggest-domain.json     — domain_overview head numbers
  data/ubersuggest-competitors.json — competitors() top list
  data/ubersuggest-backlinks.json  — backlinks_overview()

Exit codes:
  0 — success (one or more files written)
  1 — generic failure (auth, network)
  2 — token file missing (no credentials configured — silent cron)
  3 — partial failure (some but not all writes succeeded)

Environment:
  SWING_SHACK_DOMAIN        (default: swingshack.co.za)
  UBERSUGGEST_WINDOW_DAYS   (default: 60 — covers ≥2 weekly snapshots)
  UBERSUGGEST_LANG          (default: en)
  UBERSUGGEST_DEVICE        (default: desktop)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# ── Locations and constants ────────────────────────────────────────────

DEFAULT_DOMAIN = "swingshack.co.za"
DEFAULT_WINDOW_DAYS = 60
DEFAULT_LANG = "en"
DEFAULT_DEVICE = "desktop"

REPO_ROOT = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard")
DATA_DIR = REPO_ROOT / "data"
CAMPAIGN_OS_DIR = REPO_ROOT / "campaign-os"

_LOG = logging.getLogger("fetch_ubersuggest")

# ── Logging setup ──────────────────────────────────────────────────────


def _setup_logging(verbose: bool = False) -> None:
    fmt = "[%(asctime)s SAST] %(message)s"
    if verbose:
        fmt = "[%(asctime)s SAST] [%(name)s] %(levelname)s %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Path plumbing ──────────────────────────────────────────────────────


def _import_wrapper():
    """Late-import the campaign-os wrapper with sys.path adjusted."""
    sys.path.insert(0, str(CAMPAIGN_OS_DIR))
    try:
        # package import
        from _lib import ubersuggest_mcp as um  # type: ignore
    except ImportError:
        # script-style import (when cwd != repo root)
        sys.path.insert(0, str(CAMPAIGN_OS_DIR / "_lib"))
        import ubersuggest_mcp as um  # type: ignore
    return um


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically: tmp → rename. Skips writes that are byte-identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, sort_keys=True)
    if path.exists() and path.read_text() == serialized:
        _LOG.debug(f"unchanged: {path}")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialized)
    tmp.replace(path)
    _LOG.info(f"wrote {path} ({len(serialized)} bytes)")


# ── Step 1: resolve domain + window ────────────────────────────────────


def _resolve_args(args: argparse.Namespace) -> tuple[str, int, str, str]:
    domain = os.environ.get("SWING_SHACK_DOMAIN", DEFAULT_DOMAIN)
    if args.domain:
        domain = args.domain
    window = int(os.environ.get("UBERSUGGEST_WINDOW_DAYS", DEFAULT_WINDOW_DAYS))
    if args.window:
        window = int(args.window)
    lang = os.environ.get("UBERSUGGEST_LANG", DEFAULT_LANG)
    device = os.environ.get("UBERSUGGEST_DEVICE", DEFAULT_DEVICE)
    return domain, window, lang, device


# ── Step 2: get the project_id for the domain ──────────────────────────


def _resolve_project_id(um, domain: str) -> str:
    pid = um.find_project_id_for_domain(domain)
    if not pid:
        raise SystemExit(
            f"[fetch_ubersuggest] ERROR: no Ubersuggest project found for "
            f"`{domain}`. Verify domain spelling and OAuth scope contains "
            f"`projects`.\n"
            f"\n"
            f"Check: `curl -s -H 'Authorization: Bearer $(jq -r .access_token "
            f"/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/"
            f"credentials/ubersuggest-api.json)' "
            f"https://ubersuggest-mcp.neilpatelapi.com/mcp -d '{{\"jsonrpc\":"
            f"\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{{\"name\":"
            f"\"list_projects\",\"arguments\":{{}}}}}}'`"
        )
    return pid


# ── Step 3: pull the rank-tracking report ──────────────────────────────


def _pull_position_info(um, project_id: str, *, window: int, lang: str, device: str) -> dict:
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=window)).isoformat()
    _LOG.info(f"fetching project_position_info for project={project_id[:12]}... "
              f"window={start}→{end}")
    raw = um.project_position_info(
        project_id, start_date=start, end_date=end,
        language=lang, device=device,
    )
    content = (raw or {}).get("content") if isinstance(raw, dict) else None
    if not isinstance(content, list) or not content:
        raise RuntimeError(f"unexpected project_position_info response: {str(raw)[:200]}")
    text = content[0].get("text", "{}")
    return json.loads(text) if isinstance(text, str) else text


# ── Step 4: transform to legacy seo-rankings schema ────────────────────


def _flatten_to_seo_rankings(payload: dict, *, domain: str, lang: str) -> dict:
    """Reshape project_position_info into the legacy seo-rankings schema.

    Legacy schema:
      {
        "keywords": [{keyword, current_rank, previous_rank,
                       search_volume, seo_difficulty, competition,
                       previous_date, current_date, current_url, ...}],
        "rising":   [...],
        "falling":  [...],
        "quick_wins": [...],
        "summary":  {up, down, unchanged},
        "binned":   {top_3:{old,new}, top_10:{old,new}, ...},
        "average_position_trend": [{date, position}, ...],
      }
    """
    out_kw = []
    for k in (payload.get("keywords") or []):
        op = k.get("old_position") or {}
        np = k.get("new_position") or {}
        op_pos, np_pos = op.get("position"), np.get("position")
        op_date, np_date = op.get("date"), np.get("date")
        prev = op_pos if (op_pos is not None and op_date != np_date) else None
        out_kw.append({
            "keyword": k["keyword"],
            "current_rank": np_pos,
            "previous_rank": prev,
            "previous_date": op_date,
            "current_date": np_date,
            "current_url": np.get("url"),
            "previous_url": op.get("url"),
            "search_volume": k.get("volume"),
            "seo_difficulty": k.get("sd"),
            "competition": k.get("competition"),
            "loc_id": k.get("loc_id"),
            "language": k.get("language") or lang,
            "status": k.get("status"),
            "marked_unstable": k.get("marked_unstable"),
            "_has_change": (prev is not None) and (np_pos is not None) and (prev != np_pos),
        })

    rising = sorted(
        [k for k in out_kw
         if k["previous_rank"] is not None and k["current_rank"] is not None
         and k["previous_rank"] > k["current_rank"]],
        key=lambda x: x["previous_rank"] - x["current_rank"],
        reverse=True,
    )
    falling = sorted(
        [k for k in out_kw
         if k["previous_rank"] is not None and k["current_rank"] is not None
         and k["previous_rank"] < k["current_rank"]],
        key=lambda x: x["current_rank"] - x["previous_rank"],
        reverse=True,
    )
    quick_wins = [
        k for k in out_kw
        if k["current_rank"] is not None and 4 <= k["current_rank"] <= 20
    ]

    return {
        "metadata": {
            "source": "ubersuggest.project_position_info",
            "domain": domain,
            "language": lang,
            "fetched_at": date.today().isoformat(),
            "window": {
                "start": min((k["previous_date"] for k in out_kw if k["previous_date"]), default=None),
                "end": max((k["current_date"] for k in out_kw if k["current_date"]), default=None),
            },
            "next_update": payload.get("next_update"),
        },
        "summary": payload.get("summary") or {},
        "binned": payload.get("binned") or {},
        "average_position_trend": (payload.get("average_positions") or {}).get("positions") or [],
        "rising": rising,
        "falling": falling,
        "quick_wins": quick_wins,
        "keywords": out_kw,
    }


# ── Steps 5–7: supplementary pulls ─────────────────────────────────────


def _pull_domain_overview(um, domain: str) -> dict:
    _LOG.info(f"fetching domain_overview({domain})")
    raw = um.domain_overview(domain)
    content = (raw or {}).get("content") if isinstance(raw, dict) else None
    if isinstance(content, list) and content:
        return json.loads(content[0].get("text", "{}"))
    return raw or {}


def _pull_competitors(um, domain: str) -> dict:
    """`competitors` returns a list; persist as `{competitors: [...], _meta: {...}}`.

    Live-tested 2026-08-06: response shape is a JSON array, not an object.
    We wrap it so the on-disk file is consistent with the other fetchers
    (which all write top-level dicts with a sibling `_meta` block).
    """
    _LOG.info(f"fetching competitors({domain}) — async on backend, may take ~30s")
    raw = um.competitors(domain)
    content = (raw or {}).get("content") if isinstance(raw, dict) else None
    competitors_list: list = []
    if isinstance(content, list) and content and isinstance(content[0], dict):
        try:
            inner = content[0].get("text", "[]")
            parsed = json.loads(inner) if isinstance(inner, str) else inner
            if isinstance(parsed, list):
                competitors_list = parsed
            elif isinstance(parsed, dict) and "competitors" in parsed:
                competitors_list = parsed["competitors"]
            else:
                competitors_list = [parsed]
        except Exception as e:
            _LOG.warning(f"competitors() parse fallback: {e}")
    return {
        "competitors": competitors_list,
        "_meta": {
            "domain": domain,
            "fetched_at": date.today().isoformat(),
            "count": len(competitors_list),
        },
    }


def _pull_backlinks_overview(um, domain: str) -> dict:
    _LOG.info(f"fetching backlinks_overview({domain})")
    raw = um.backlinks_overview(domain)
    content = (raw or {}).get("content") if isinstance(raw, dict) else None
    if isinstance(content, list) and content:
        return json.loads(content[0].get("text", "{}"))
    return raw or {}


# ── Orchestration ─────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--domain", help=f"override Swing Shack domain (default: {DEFAULT_DOMAIN})")
    parser.add_argument("--window", type=int, help=f"override window days (default: {DEFAULT_WINDOW_DAYS})")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit (default). The plist runs with this flag.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    domain, window, lang, device = _resolve_args(args)

    # Auth gate
    try:
        um = _import_wrapper()
    except ImportError as e:
        _LOG.error(f"could not import ubersuggest_mcp: {e}")
        return 1

    if not um.ubersuggest_credentials_present():
        _LOG.warning(
            f"no Ubersuggest token at {um.DEFAULT_TOKEN_FILE}. "
            f"Run `python3 scripts/ubersuggest_oauth.py` to authorize. "
            f"Silent-cron exit code 2."
        )
        return 2

    # Resolve project
    try:
        project_id = _resolve_project_id(um, domain)
    except SystemExit:
        raise
    except Exception as e:
        _LOG.error(f"project_id lookup failed: {e}")
        return 1

    failures: list[str] = []

    # 1. Pull rank report (the primary output)
    try:
        payload = _pull_position_info(um, project_id, window=window, lang=lang, device=device)
        seo_rankings = _flatten_to_seo_rankings(payload, domain=domain, lang=lang)
        seo_rankings["metadata"]["project_id_prefix"] = project_id[:12]
        _atomic_write(DATA_DIR / "seo-rankings.json", seo_rankings)
        _LOG.info(
            f"[rank report] {len(seo_rankings['keywords'])} keywords, "
            f"{seo_rankings['summary'].get('up', 0)} up / "
            f"{seo_rankings['summary'].get('down', 0)} down / "
            f"{seo_rankings['summary'].get('unchanged', 0)} unchanged; "
            f"{len(seo_rankings['rising'])} rising / "
            f"{len(seo_rankings['falling'])} falling / "
            f"{len(seo_rankings['quick_wins'])} quick wins"
        )
    except Exception as e:
        _LOG.error(f"project_position_info failed: {e}")
        failures.append("seo-rankings")

    # 2. Domain overview
    try:
        domain_data = _pull_domain_overview(um, domain)
        domain_data["_meta"] = {
            "domain": domain,
            "fetched_at": date.today().isoformat(),
        }
        _atomic_write(DATA_DIR / "ubersuggest-domain.json", domain_data)
    except Exception as e:
        _LOG.error(f"domain_overview failed: {e}")
        failures.append("ubersuggest-domain")

    # 3. Backlinks
    try:
        bk_data = _pull_backlinks_overview(um, domain)
        bk_data["_meta"] = {
            "domain": domain,
            "fetched_at": date.today().isoformat(),
        }
        _atomic_write(DATA_DIR / "ubersuggest-backlinks.json", bk_data)
    except Exception as e:
        _LOG.error(f"backlinks_overview failed: {e}")
        failures.append("ubersuggest-backlinks")

    # 4. Competitors (optional — async, skip on slow networks)
    try:
        comp_data = _pull_competitors(um, domain)
        # _pull_competitors already sets `_meta` (including `count`); no need
        # to overwrite it here.
        _atomic_write(DATA_DIR / "ubersuggest-competitors.json", comp_data)
    except Exception as e:
        _LOG.warning(f"competitors() failed (non-fatal): {e}")

    if failures:
        _LOG.warning(f"done with partial failures: {failures}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
