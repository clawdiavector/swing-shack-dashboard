"""
fetch_ubersuggest.py — daily rank-tracking pull for Swing Shack SEO keywords.

Runs at 04:30 SAST (just before the path2 chain at 05:00, but the data
lands in the same DATA_DIR and is merged into seo-rankings.json before
the morning brief fires at 06:30).

What it does:
    1. Reads the current data/seo-rankings.json (the canonical list of
       tracked keywords).
    2. For each keyword, calls Ubersuggest MCP `keyword_overview` to get
       current rank + search volume + SEO difficulty + CPC.
    3. Computes rank deltas vs the previous run:
         * rising_keywords  : rank went UP (smaller number = better)
         * falling_keywords : rank went DOWN (larger number = worse)
         * quick_wins       : keywords in top 20 with sub-page-2 position
    4. Atomically writes the refreshed JSON back to disk with merged
       "previous_rank" deltas preserved.

Failure modes (each handled gracefully):
    - No Ubersuggest token:                  log + exit 2 (skip; weekly refresh
                                              will create one)
    - Single keyword fetch fails:           carry forward last-known rank, log,
                                              keep going (1 failure ≠ 0 data)
    - All keywords fail:                     log + exit 1 (silent otherwise)
    - Token expired + refresh failed:       log + exit 1
    - Network unreachable:                   log + exit 1

Cost per run: 10 keywords × ~1s = ~10 seconds + 1-2 concurrent
domain_overview + backlinks_overview calls = ~15 seconds total.

Exit codes (per the launchd cron pattern):
    0 = success (some or all keywords fetched, file written)
    1 = transient error (network, auth) — cron will retry tomorrow
    2 = no credentials — run scripts/ubersuggest_oauth.py to authorize
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Reuse the wrapper module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "campaign-os"))

from _lib import ubersuggest_mcp as _us  # noqa: E402

DATA_DIR = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")
SEO_FILE = DATA_DIR / "seo-rankings.json"
DOMAIN_FILE = DATA_DIR / "ubersuggest-domain.json"  # newer, optional
LOG_FILE = Path("/Users/fivefriday/.openclaw-instance2/workspace/logs/ubersuggest-fetch.log")

# South Africa (English) per Ubersuggest's standard set
DEFAULT_LANG = "en"
# 2712 = Johannesburg (ZA) per Ubersuggest's location list
# Override via UBERSUGGEST_LOC_ID env var if you prefer a different region.
DEFAULT_LOC_ID = 2712

MAX_RETRIES_PER_KEYWORD = 2
RETRY_BACKOFF_SECONDS = 2


def _log(msg: str) -> None:
    """Log to stdout AND a rotating file (~/.openclaw/.../logs/ubersuggest-fetch.log)."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S SAST", time.localtime())
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # best-effort


def _read_seo_file() -> dict:
    """Load current seo-rankings.json (or seed with empty schema)."""
    if not SEO_FILE.exists():
        _log(f"[warn] {SEO_FILE} missing; creating fresh schema")
        return {
            "updated": None,
            "keywords": [],
            "rising_keywords": [],
            "falling_keywords": [],
            "quick_wins": [],
            "summary": {"tracked": 0, "found": 0, "not_found": 0},
            "recommendations": [],
        }
    try:
        return json.loads(SEO_FILE.read_text())
    except (OSError, ValueError):
        _log(f"[error] {SEO_FILE} corrupted; backing up + starting fresh")
        try:
            SEO_FILE.rename(SEO_FILE.with_suffix(".json.bak"))
        except OSError:
            pass
        return {
            "updated": None, "keywords": [], "rising_keywords": [],
            "falling_keywords": [], "quick_wins": [],
            "summary": {"tracked": 0, "found": 0, "not_found": 0},
            "recommendations": [],
        }


def _write_atomic(path: Path, data: dict) -> None:
    """Atomic write — tmp + rename — so a concurrent reader never sees a half-written file."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".seo-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if Path(tmp).exists():
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def _fetch_keyword_overview(keyword: str, *, loc_id: int, lang: str) -> dict:
    """Call keyword_overview with up to MAX_RETRIES_PER_KEYWORD retries.

    Returns the raw `result` dict from the MCP call. Raises UbersuggestAuthError
    (don't retry), UbersuggestUpstreamError (retry once), UbersuggestNetworkError
    (retry backoff).
    """
    import os
    last_exc = None
    for attempt in range(1, MAX_RETRIES_PER_KEYWORD + 2):  # 1 initial + N retries
        try:
            return _us.keyword_overview(keyword, loc_id=loc_id, lang=lang)
        except _us.UbersuggestUpstreamError as e:
            if attempt > MAX_RETRIES_PER_KEYWORD:
                raise
            _log(f"[warn] keyword_overview({keyword!r}, attempt {attempt}) upstream {e.code}: {e}; retrying")
            last_exc = e
        except _us.UbersuggestNetworkError as e:
            if attempt > MAX_RETRIES_PER_KEYWORD:
                raise
            _log(f"[warn] keyword_overview({keyword!r}, attempt {attempt}) network: {e}; retrying after {RETRY_BACKOFF_SECONDS}s")
            time.sleep(RETRY_BACKOFF_SECONDS)
            last_exc = e
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable: keyword_overview loop exited without result or raise")


def _extract_rank_metrics(raw_result: dict) -> dict:
    """Map the raw MCP `keyword_overview` response into our internal schema.

    The MCP server returns text content blocks per tool result; we pull the
    JSON out of `content[0].text` (the shape we saw live).
    """
    # Defensive unpacking — never raise from here.
    rank: int | None = None
    search_volume: int | None = None
    cpc: float | None = None
    seo_difficulty: int | None = None
    paid_difficulty: int | None = None

    try:
        content = raw_result.get("content") or []
        if content and isinstance(content, list):
            from json import loads
            text = content[0].get("text") if isinstance(content[0], dict) else None
            if text and isinstance(text, str):
                parsed = loads(text)
                if isinstance(parsed, dict):
                    rank = parsed.get("rank")
                    search_volume = parsed.get("searchVolume")
                    seo_difficulty = parsed.get("seoDifficulty") or parsed.get("keywordDifficulty")
                    paid_difficulty = parsed.get("paidDifficulty")
                    cpc = parsed.get("cpc")
                elif isinstance(parsed, list) and parsed:
                    # Some MCP servers return a list of keyword dicts.
                    k0 = parsed[0] if isinstance(parsed[0], dict) else {}
                    rank = k0.get("rank")
                    search_volume = k0.get("searchVolume")
                    seo_difficulty = k0.get("seoDifficulty") or k0.get("keywordDifficulty")
                    paid_difficulty = k0.get("paidDifficulty")
                    cpc = k0.get("cpc")
    except Exception:
        pass

    return {
        "rank": rank,
        "search_volume": search_volume,
        "seo_difficulty": seo_difficulty,
        "paid_difficulty": paid_difficulty,
        "cpc": cpc,
    }


def _compute_deltas(previous_keywords: dict, current_keywords: list) -> tuple:
    """Compare current run to previous, output rising/falling/quick_wins."""
    rising, falling, quick_wins = [], [], []
    for kw_entry in current_keywords:
        kw = kw_entry.get("keyword")
        curr_rank = kw_entry.get("current_rank")
        prev_rank = (previous_keywords.get(kw) or {}).get("current_rank")
        if curr_rank is None or prev_rank is None:
            continue
        if curr_rank < prev_rank and prev_rank > 0:
            rising.append({
                "keyword": kw,
                "previous_rank": prev_rank,
                "current_rank": curr_rank,
                "delta": prev_rank - curr_rank,
            })
        elif curr_rank > prev_rank and curr_rank > 0:
            falling.append({
                "keyword": kw,
                "previous_rank": prev_rank,
                "current_rank": curr_rank,
                "delta": curr_rank - prev_rank,
            })
        if isinstance(curr_rank, int) and 0 < curr_rank <= 10:
            quick_wins.append({
                "keyword": kw,
                "current_rank": curr_rank,
                "search_volume": kw_entry.get("search_volume"),
            })
    # Sort by impact
    rising.sort(key=lambda x: -x["delta"])
    falling.sort(key=lambda x: -x["delta"])
    quick_wins.sort(key=lambda x: x["current_rank"])
    return rising, falling, quick_wins


def _build_recommendations(keywords: list[dict]) -> list[dict]:
    """Generate action items for not-ranked keywords."""
    recs = []
    for k in keywords:
        if k.get("current_rank") is None:
            recs.append({
                "type": "not_indexed",
                "keyword": k.get("keyword"),
                "action": f"Create or optimize page targeting \"{k.get('keyword')}\"",
                "priority": "high",
            })
        elif isinstance(k.get("current_rank"), int) and k["current_rank"] > 50:
            recs.append({
                "type": "page_2_plus",
                "keyword": k.get("keyword"),
                "action": f"Currently at position {k['current_rank']}; needs content + links to push to page 1",
                "priority": "medium",
            })
    return recs


def main() -> int:
    if not _us.ubersuggest_credentials_present():
        _log("[skip] no Ubersuggest credentials — "
             "run scripts/ubersuggest_oauth.py to authorize")
        return 2

    loc_id = int(os.environ.get("UBERSUGGEST_LOC_ID", str(DEFAULT_LOC_ID)))
    lang = os.environ.get("UBERSUGGEST_LANG", DEFAULT_LANG)

    seo = _read_seo_file()
    tracked = seo.get("keywords") or []
    if not tracked:
        _log("[warn] seo-rankings.json has no keywords array; nothing to do")
        return 0

    # Build a quick previous-ranks lookup for delta computation.
    previous_keywords = {k.get("keyword"): k for k in tracked if k.get("keyword")}

    _log(f"fetching {len(tracked)} keywords from Ubersuggest (loc_id={loc_id}, lang={lang})")

    updated_keywords: list[dict] = []
    failures: list[tuple[str, str]] = []
    for idx, k in enumerate(tracked, 1):
        kw = k.get("keyword")
        if not kw:
            continue
        try:
            raw = _fetch_keyword_overview(kw, loc_id=loc_id, lang=lang)
            metrics = _extract_rank_metrics(raw)
            updated = {
                **k,  # carry over target_url, search_intent, etc.
                "current_rank": metrics["rank"],
                "search_volume": metrics["search_volume"],
                "seo_difficulty": metrics["seo_difficulty"],
                "paid_difficulty": metrics["paid_difficulty"],
                "cpc": metrics["cpc"],
                "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            updated_keywords.append(updated)
            _log(f"[{idx}/{len(tracked)}] {kw}: rank={metrics['rank']}, "
                 f"vol={metrics['search_volume']}, cpc={metrics['cpc']}")
        except _us.UbersuggestAuthError as e:
            _log(f"[fatal] keyword {kw!r} — auth error: {e}")
            return 2
        except (_us.UbersuggestUpstreamError, _us.UbersuggestNetworkError) as e:
            _log(f"[warn] keyword {kw!r} fetch failed: {e}; carrying forward last-known rank")
            failures.append((kw, str(e)))
            updated_keywords.append({**k, "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            continue
        except Exception as e:
            _log(f"[warn] keyword {kw!r} unexpected error: {e}; carrying forward last-known rank")
            failures.append((kw, repr(e)))
            updated_keywords.append({**k, "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            continue

    # Compute deltas + summary
    rising, falling, quick_wins = _compute_deltas(previous_keywords, updated_keywords)
    recommendations = _build_recommendations(updated_keywords)
    found_count = sum(1 for k in updated_keywords if isinstance(k.get("current_rank"), int))
    not_found_count = len(updated_keywords) - found_count

    # Domain overview (domain_overview + backlinks_overview) — best-effort,
    # doesn't affect keyword ordering.
    domain_section = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "errors": []}
    try:
        domain_overview_resp = _us.domain_overview("swingshack.co.za")
        domain_section["domain_overview"] = domain_overview_resp
    except Exception as e:
        domain_section["errors"].append(f"domain_overview: {e!s}")
    try:
        backlinks_resp = _us.backlinks_overview("swingshack.co.za")
        domain_section["backlinks_overview"] = backlinks_resp
    except Exception as e:
        domain_section["errors"].append(f"backlinks_overview: {e!s}")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _write_atomic(DOMAIN_FILE, domain_section)
    except OSError as e:
        _log(f"[warn] could not write {DOMAIN_FILE}: {e}")

    # Reassemble + write seo-rankings.json (atomic)
    output = {
        **seo,  # carry over top-level fields we didn't touch
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "keywords": updated_keywords,
        "rising_keywords": rising,
        "falling_keywords": falling,
        "quick_wins": quick_wins,
        "summary": {
            "tracked": len(updated_keywords),
            "found": found_count,
            "not_found": not_found_count,
            "fetch_failures": len(failures),
        },
        "recommendations": recommendations,
    }
    try:
        _write_atomic(SEO_FILE, output)
    except OSError as e:
        _log(f"[fatal] could not write {SEO_FILE}: {e}")
        return 1

    _log(f"[done] wrote {len(updated_keywords)} keywords to {SEO_FILE}; "
         f"{len(rising)} rising, {len(falling)} falling, "
         f"{len(quick_wins)} quick wins; {len(failures)} failures")
    if failures and len(failures) == len(tracked):
        _log("[error] ALL keywords failed — treat as transient and retry tomorrow")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _log("[interrupted]")
        sys.exit(130)
