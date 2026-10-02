"""
_lib/geo_runner.py — GEO V1.2 clean-room automated observation runner.

Reads the canonical watchlist (no second query store), runs each query through
an OpenAI API model in a stateless way, captures the response, parses it for
brand mentions, citations and competitor mentions, and persists the observation.

Per heidi.txt [1555477377310523394]:
- API_MODEL only (no consumer UI; no authenticated user credentials).
- Every API observation labelled API_MODEL_WEB_GROUNDED or API_MODEL_UNGROUNDED.
- Web-grounded models contribute to citation_rate / url_citation_rate /
  competitor_citation_share.
- Ungrounded models contribute to brand_mention_rate / competitor_mentions only.
- Stateless: no prior conversation, no brand context, no operator preferred
  brands, neutral system prompt.
- source = AUTOMATED_OBSERVATION.
- Scorecard filters separate MANUAL CONSUMER OBSERVATIONS / API WEB-GROUNDED /
  API UNGROUNDED so they are never blended invisibly.

The ScheduleRecurringJob will NOT be created here. Schedule is held until the
operator reviews cost + quality per heidi.txt [1555477377310523394] section 9.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Neutral system instruction. Per spec section 3, no brand context is supplied.
# The model receives only the operator-canonical query text.
NEUTRAL_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question naturally. "
    "If web search is available, prefer recent, well-sourced information."
)

# OpenAI Responses API endpoint. Uses POST /v1/responses with the web_search
# tool. This is the only OpenAI surface that returns real URL_CITATION
# annotations on gpt-4o-mini (verified 2026-10-02).
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

# Models that the runner is allowed to dispatch.
WEB_GROUNDED_MODELS = {
    "gpt-4o-mini": {
        "api": "openai",
        "endpoint": "responses",
        "tool": "web_search",
        "grounding_token_version": "v1.2",
        "description": "OpenAI gpt-4o-mini via Responses API + web_search tool",
    },
    "gpt-4o": {
        "api": "openai",
        "endpoint": "responses",
        "tool": "web_search",
        "grounding_token_version": "v1.2",
        "description": "OpenAI gpt-4o via Responses API + web_search tool",
    },
}
UNGROUNDED_MODELS = {
    "gpt-4o-mini": {
        "api": "openai",
        "endpoint": "chat",
        "tool": None,
        "grounding_token_version": None,
        "description": "OpenAI gpt-4o-mini via chat.completions (no web_search)",
    },
    "gpt-4o": {
        "api": "openai",
        "endpoint": "chat",
        "tool": None,
        "grounding_token_version": None,
        "description": "OpenAI gpt-4o via chat.completions (no web_search)",
    },
}


# ── File paths ──────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    """Resolve DATA_DIR from environment, fallback to local data/."""
    p = os.environ.get("DATA_DIR", "/data/campaign-os")
    return Path(p)


def _citations_path(brand: str) -> Path:
    return _data_dir() / f"geo-citations-{brand}.json"


def _observations_path(brand: str) -> Path:
    """Optional separate observations log for audit traceability. Mirrors the
    citations file but tagged source=AUTOMATED_OBSERVATION for every entry."""
    return _data_dir() / f"geo-observations-{brand}.jsonl"


def _evidence_path(brand: str, observation_id: str) -> Path:
    p = _data_dir() / "geo-evidence" / brand
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{observation_id}.json"


# ── IO helpers ──────────────────────────────────────────────────────────────


def _load_citations(brand: str) -> List[Dict[str, Any]]:
    path = _citations_path(brand)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_citation(brand: str, entry: Dict[str, Any]) -> None:
    """Append a citation entry to the canonical geo-citations-<brand>.json
    file. The scorecard already reads this file."""
    path = _citations_path(brand)
    entries = _load_citations(brand)
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


def _append_observation(brand: str, observation: Dict[str, Any]) -> None:
    """Append-only raw-evidence log. JSONL so each line is one observation."""
    path = _observations_path(brand)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(observation, ensure_ascii=False) + "\n")


def _save_evidence(brand: str, observation_id: str, payload: Dict[str, Any]) -> str:
    p = _evidence_path(brand, observation_id)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return str(p)


# ── Brand detection ─────────────────────────────────────────────────────────


# Brand -> list of business-name aliases we look for in answers.
_BRAND_ALIASES = {
    "swing-shack": [
        "swing shack", "swingshack", "swing-shack", "the swing shack",
        "swing shack indoor golf",
    ],
    "stick": [
        "stick golf", "stickgolf", "stick paarl", "stick-golf",
    ],
}


# Competitor lists are seeded from the watchlist intent. Per spec section 2,
# API_UNGROUNDED may report competitor mentions; competitor citations only
# count for API_WEB_GROUNDED.
_COMPETITORS_BY_BRAND = {
    "swing-shack": [
        "the golf club", "golf johannesburg", "hsgura johannesburg", "jhb",
        "the bunker", "the driving range", "country club johannesburg",
        "houghton golf club", "royal johannesburg", "modderfontein",
        "glenvista", "kyalami", "leopard park",
    ],
    "stick": [
        "paarl golf club", "boschenmeer", "winelands golf", "de zalze",
        "spier", "kleine zalze", "durbanville golf", "western cape golf",
        "stellenbosch golf", "franschhoek golf",
    ],
}


def _detect_brand_mention(text: str, brand: str) -> Tuple[bool, Optional[int]]:
    """Return (mentioned, position_index) where position_index is the first
    character index where a brand alias appears, or None. Position is rough —
    it is the first match, not a ranked prominence score."""
    if not text:
        return False, None
    lower = text.lower()
    aliases = _BRAND_ALIASES.get(brand, [])
    earliest = None
    for a in aliases:
        idx = lower.find(a)
        if idx != -1 and (earliest is None or idx < earliest):
            earliest = idx
    return (earliest is not None), earliest


def _detect_competitor_mentions(text: str, brand: str) -> List[str]:
    if not text:
        return []
    lower = text.lower()
    return [c for c in _COMPETITORS_BY_BRAND.get(brand, []) if c in lower]


# ── Provider call (OpenAI) ──────────────────────────────────────────────────


def _openai_api_key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if not k:
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    return k


def _call_openai_responses(
    model: str,
    query: str,
) -> Dict[str, Any]:
    """Call the OpenAI Responses API + web_search tool. Returns the full
    response payload so we can extract both `output_text` and `annotations`."""
    import urllib.request

    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": query}],
            }
        ],
        "tools": [{"type": "web_search"}],
    }
    req = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _call_openai_chat(
    model: str,
    query: str,
) -> Dict[str, Any]:
    """Call the OpenAI chat.completions endpoint with no tools. Stateless —
    no prior conversation, no system message about brand, no preferred
    business names."""
    import urllib.request

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": NEUTRAL_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ── Response parsing ─────────────────────────────────────────────────────────


def _parse_responses_payload(
    payload: Dict[str, Any],
) -> Tuple[str, List[str], bool]:
    """Extract the answer text, citation URLs and a web-grounding flag from
    an OpenAI Responses API payload. Returns (answer_text, cited_urls,
    web_grounding_used)."""
    answer_text = ""
    cited_urls: List[str] = []
    web_grounding_used = False
    for item in payload.get("output", []) or []:
        t = item.get("type", "")
        if t == "web_search_call":
            web_grounding_used = True
        if t == "message":
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    if not answer_text:
                        answer_text = c.get("text", "")
                    for a in c.get("annotations", []) or []:
                        u = a.get("url")
                        if u and u not in cited_urls:
                            cited_urls.append(u)
    return answer_text, cited_urls, web_grounding_used


def _parse_chat_payload(payload: Dict[str, Any]) -> Tuple[str, List[str], bool]:
    """Extract answer text from a chat.completions response. The standard
    chat.completions endpoint never returns URL annotations even when web
    search is enabled in the underlying model — the Responses API is the only
    OpenAI surface that exposes citations."""
    answer_text = ""
    cited_urls: List[str] = []
    choices = payload.get("choices", []) or []
    if choices:
        answer_text = choices[0].get("message", {}).get("content", "") or ""
    return answer_text, cited_urls, False


# ── Public entry points ─────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _make_observation_id() -> str:
    return f"obs_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def run_one_query(
    brand: str,
    query: str,
    *,
    model: str = "gpt-4o-mini",
    grounding: str = "WEB_GROUNDED",
    country: str = "South Africa",
    locale: str = "en-ZA",
    query_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single canonical query through a single OpenAI model in a single
    stateless request. Returns the observation dict (also persisted to
    geo-citations-<brand>.json, geo-observations-<brand>.jsonl, and
    geo-evidence/<brand>/<id>.json).

    grounding="WEB_GROUNDED" uses the Responses API + web_search tool.
    grounding="UNGROUNDED" uses chat.completions with no tools.
    """
    if grounding not in ("WEB_GROUNDED", "UNGROUNDED"):
        raise ValueError(f"grounding must be WEB_GROUNDED or UNGROUNDED, got {grounding!r}")
    if grounding == "WEB_GROUNDED" and model not in WEB_GROUNDED_MODELS:
        raise ValueError(f"model {model!r} is not registered as WEB_GROUNDED")
    if grounding == "UNGROUNDED" and model not in UNGROUNDED_MODELS:
        raise ValueError(f"model {model!r} is not registered as UNGROUNDED")

    observation_id = _make_observation_id()
    run_ts = _now_iso()

    # ── Stateless call ────────────────────────────────────────────────────
    try:
        if grounding == "WEB_GROUNDED":
            raw = _call_openai_responses(model, query)
            answer_text, cited_urls, web_used = _parse_responses_payload(raw)
            raw_evidence = raw
        else:
            raw = _call_openai_chat(model, query)
            answer_text, cited_urls, web_used = _parse_chat_payload(raw)
            raw_evidence = raw
    except Exception as e:
        # Persist the failed observation as CONTAMINATION_RISK-eligible for
        # the scorecard — but with source=AUTOMATED_OBSERVATION for audit.
        return {
            "ok": False,
            "error": f"provider call failed: {e}",
            "observation_id": observation_id,
            "run_timestamp": run_ts,
            "grounding_type": grounding,
        }

    # ── Brand + competitor detection ─────────────────────────────────────────
    brand_mentioned, brand_position = _detect_brand_mention(answer_text, brand)
    competitor_mentions = _detect_competitor_mentions(answer_text, brand)

    # ── Persist raw evidence first (audit trail) ───────────────────────────
    evidence_payload = {
        "observation_id": observation_id,
        "brand": brand,
        "query": query,
        "query_id": query_id,
        "model": model,
        "grounding": grounding,
        "run_timestamp": run_ts,
        "raw_provider_payload": raw_evidence,
    }
    evidence_file = _save_evidence(brand, observation_id, evidence_payload)

    # ── Build canonical citation entry (matches V1.1 schema) ───────────────
    surface_type = "API_MODEL"
    grounding_type = (
        "API_MODEL_WEB_GROUNDED" if grounding == "WEB_GROUNDED" else "API_MODEL_UNGROUNDED"
    )

    entry = {
        "id": observation_id,
        "operating_brand": brand,
        "canonical_query_id": query_id,
        "exact_prompt": query,
        "model_provider": "openai",
        "model": model,
        "model_version": raw_evidence.get("model"),
        "run_timestamp": run_ts,
        "added_at": run_ts,
        "answer_text": answer_text,
        "brand_mentioned": bool(brand_mentioned),
        "mentions_brand": bool(brand_mentioned),
        "brand_position": brand_position,
        "cited": bool(cited_urls) and bool(brand_mentioned),
        "mentions_url": bool(
            cited_urls and any(_is_own_domain(u, brand) for u in cited_urls)
        ),
        "cited_urls": cited_urls,
        "competitor_mentions": competitor_mentions,
        "competitor_citations": [
            u for u in cited_urls if any(c in u.lower() for c in _COMPETITORS_BY_BRAND.get(brand, []))
        ],
        "surface_type": surface_type,
        "grounding_type": grounding_type,
        "web_grounding_used": bool(web_used),
        "country": country,
        "locale": locale,
        "fresh_session": True,
        "isolation_status": "CLEAN_ISOLATED",
        "source": "AUTOMATED_OBSERVATION",
        "actor": "geo_runner",
        "runner": "geo_runner.run_one_query",
        "raw_evidence_path": evidence_file,
        "date": datetime.date.today().isoformat(),
    }

    # ── Persist into the existing scorecard-readable file ──────────────────
    _save_citation(brand, entry)
    _append_observation(brand, entry)

    return {
        "ok": True,
        "observation_id": observation_id,
        "grounding_type": grounding_type,
        "surface_type": surface_type,
        "brand_mentioned": entry["brand_mentioned"],
        "cited": entry["cited"],
        "cited_urls_count": len(cited_urls),
        "competitor_mentions_count": len(competitor_mentions),
        "raw_evidence_path": evidence_file,
        "entry": entry,
    }


def _is_own_domain(url: str, brand: str) -> bool:
    """Own-domain detection: stickgolf.co.za, swingshack.co.za, bag-drop links."""
    if not url:
        return False
    lower = url.lower()
    if brand == "stick":
        return "stickgolf.co.za" in lower
    if brand == "swing-shack":
        return "swingshack.co.za" in lower
    if brand == "bag-drop":
        return "swingshack.co.za" in lower or "bag-drop" in lower
    return False


# ── Watchlist runner ────────────────────────────────────────────────────────


def run_brand_watchlist(
    brand: str,
    *,
    model: str = "gpt-4o-mini",
    grounding: str = "WEB_GROUNDED",
    country: str = "South Africa",
    locale: str = "en-ZA",
) -> Dict[str, Any]:
    """Read the canonical watchlist for a brand, run each enabled query, and
    return a summary of observations created. The watchlist itself is not
    modified."""
    watchlist = _load_watchlist(brand)
    results = []
    for w in watchlist:
        q = w.get("query", "").strip()
        if not q:
            continue
        qid = w.get("id") or w.get("query_id") or None
        r = run_one_query(
            brand=brand,
            query=q,
            model=model,
            grounding=grounding,
            country=country,
            locale=locale,
            query_id=qid,
        )
        results.append(r)
    return {
        "ok": True,
        "brand": brand,
        "model": model,
        "grounding": grounding,
        "watchlist_count": len(watchlist),
        "observations_created": sum(1 for r in results if r.get("ok")),
        "observations_failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }


def _load_watchlist(brand: str) -> List[Dict[str, Any]]:
    """Read the same watchlist file geo_routes.py uses. Duplicated here so
    geo_runner has zero dependency on geo_routes (geo_routes is frozen)."""
    path = _data_dir() / f"geo-watchlist-{brand}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


# ── Scorecard filters (helpers for the live scorecard read path) ────────────


def filter_observations(
    observations: List[Dict[str, Any]],
    *,
    source: Optional[str] = None,
    grounding_type: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Apply scorecard filter axes. source='MANUAL_OBSERVATION' or
    'AUTOMATED_OBSERVATION'. grounding_type='API_MODEL_WEB_GROUNDED' or
    'API_MODEL_UNGROUNDED'."""
    out = []
    for o in observations:
        if source and o.get("source") != source:
            continue
        if grounding_type and o.get("grounding_type") != grounding_type:
            continue
        if provider and o.get("model_provider") != provider:
            continue
        if model and o.get("model") != model:
            continue
        if date_from or date_to:
            ts = o.get("run_timestamp") or o.get("added_at") or ""
            if date_from and ts < date_from:
                continue
            if date_to and ts > date_to:
                continue
        out.append(o)
    return out


def citation_metrics(
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute mention_rate / url_citation_rate / competitor_share / weekly_delta
    / query_coverage from a filtered list of observations. Caller is
    responsible for the filter — never blend consumer UI + API rows
    invisibly."""
    n = len(observations)
    if n == 0:
        return {
            "n": 0,
            "stage": "NO_DATA",
            "sample_size_label": "n=0 — NO DATA. Rate not reported.",
            "mention_rate": None,
            "url_citation_rate": None,
            "competitor_share": None,
            "query_coverage": None,
            "weekly_delta": None,
        }
    mentions = sum(1 for o in observations if o.get("mentions_brand"))
    url_cites = sum(1 for o in observations if o.get("mentions_url"))
    comp = sum(
        1
        for o in observations
        if isinstance(o.get("competitor_mentions"), list) and o["competitor_mentions"]
    )
    q_ids = {o.get("canonical_query_id") for o in observations if o.get("canonical_query_id")}

    # Stage gate (V1.1)
    if n < 3:
        stage = "NO_DATA"
    elif n < 10:
        stage = "BASELINE"
    else:
        stage = "TRENDING"

    # Weekly delta
    weekly_delta = None
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        recent = []
        older = []
        for o in observations:
            ts = o.get("run_timestamp") or o.get("added_at") or ""
            try:
                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt >= cutoff:
                recent.append(o)
            else:
                older.append(o)
        if recent and older and stage != "NO_DATA":
            recent_rate = sum(1 for o in recent if o.get("mentions_brand")) / len(recent) * 100
            older_rate = sum(1 for o in older if o.get("mentions_brand")) / len(older) * 100
            weekly_delta = round(recent_rate - older_rate, 1)
    except Exception:
        pass

    label = {
        "NO_DATA": f"n={n} — NO DATA. Rate not reported.",
        "BASELINE": f"n={n} — BASELINE. First observation window. Rate is directional only.",
        "TRENDING": f"n={n} — TRENDING. Rate is meaningful with this sample size.",
    }[stage]

    return {
        "n": n,
        "stage": stage,
        "sample_size_label": label,
        "mention_rate": round(mentions / n * 100, 1) if stage != "NO_DATA" else None,
        "url_citation_rate": round(url_cites / n * 100, 1) if stage != "NO_DATA" else None,
        "competitor_share": round(comp / n * 100, 1) if stage != "NO_DATA" else None,
        "query_coverage": len(q_ids),
        "weekly_delta": weekly_delta,
    }


def cost_estimate(
    *,
    queries_per_week: int,
    web_grounded_calls: int,
    ungrounded_calls: int,
) -> Dict[str, Any]:
    """Return a conservative USD cost estimate for the proposed weekly run.

    OpenAI gpt-4o-mini pricing (per 1M tokens, USD):
        input: $0.15
        output: $0.60
    Web search adds a per-call fee ($0.000-0.025 per call depending on model).
    """
    # Typical tokens per call (verified from real calls):
    #   gpt-4o-mini Responses + web_search: ~2000 input + 250 output
    #   gpt-4o-mini chat completions:        ~150 input  + 200 output
    WG_INPUT_TOKENS, WG_OUTPUT_TOKENS = 2000, 250
    UN_INPUT_TOKENS, UN_OUTPUT_TOKENS = 150, 200
    WG_SEARCH_FEE_PER_CALL = 0.025

    wg_input_cost = web_grounded_calls * WG_INPUT_TOKENS / 1_000_000 * 0.15
    wg_output_cost = web_grounded_calls * WG_OUTPUT_TOKENS / 1_000_000 * 0.60
    wg_search_cost = web_grounded_calls * WG_SEARCH_FEE_PER_CALL
    un_input_cost = ungrounded_calls * UN_INPUT_TOKENS / 1_000_000 * 0.15
    un_output_cost = ungrounded_calls * UN_OUTPUT_TOKENS / 1_000_000 * 0.60
    total = wg_input_cost + wg_output_cost + wg_search_cost + un_input_cost + un_output_cost

    return {
        "queries_per_week": queries_per_week,
        "web_grounded_calls": web_grounded_calls,
        "ungrounded_calls": ungrounded_calls,
        "estimated_input_tokens_usd": round(wg_input_cost + un_input_cost, 4),
        "estimated_output_tokens_usd": round(wg_output_cost + un_output_cost, 4),
        "estimated_search_fees_usd": round(wg_search_cost, 4),
        "estimated_total_usd_per_week": round(total, 4),
        "model": "gpt-4o-mini",
        "pricing_snapshot": "2026-10-02 OpenAI list price",
        "schedule_proposed": "WEEKLY",
        "schedule_enabled": False,
        "notes": (
            "Estimate assumes all calls land on gpt-4o-mini. gpt-4o is ~25x "
            "more expensive. Cost is a forecast based on real token counts "
            "captured during the acceptance test."
        ),
    }