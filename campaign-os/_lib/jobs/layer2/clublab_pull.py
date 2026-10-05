"""ClubLab read-only stats pull — layer-2 job (GET-only + auth login)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..errors import describe_exception
from ..layer1._io import atomic_write, data_dir, utc_now_iso

SNAPSHOT_NAME = "clublab-snapshot.json"
META_NAME = "clublab-snapshot.meta.json"
SCHEMA = "campaign-os/clublab-snapshot/v1"

DEFAULT_ORIGIN = "https://clublab.app"
CREDENTIALS_FILE = Path(
    "/home/kyle/finder-workspace/repos/work/ClubLab/.cursor/skills/clublab-agent/config/credentials-external.env"
)

DENY_KEYS = frozenset(
    {
        "firstname",
        "lastname",
        "fullname",
        "email",
        "phone",
        "clientdisplayname",
        "reviewtext",
        "reviewbody",
        "comments",
        "photo",
        "imageurl",
        "bankingdetails",
        "address",
    }
)

CRM_DASHBOARD_DROP = frozenset({"topAtRisk", "top_at_risk", "topatrisk"})
FITME_SUMMARY_DROP = frozenset({"topFitters", "top_fitters", "topfitters", "facilities"})

REQUIRED_GET_PATHS = (
    "/api/v1/facilities",
    "/api/v1/crm/dashboard",
    "/api/v1/crm/reports",
    "/api/v1/crm/segments",
    "/api/v1/orderme/ordered-products",
    "/api/v1/fitme-reports/summary",
    "/api/v1/fitme-reports/equipment",
    "/api/v1/fitme-reports/timeline",
    "/api/v1/costme/catalogue",
    "/api/v1/Reports/session-summary",
)

OPTIONAL_GET_PATHS = ("/api/v1/Reports/tag-frequency",)

_http_client_factory: Callable[[], Any] | None = None


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", key).lower()


def _sanitize_value(value: Any, stripped: list[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _norm_key(k) in DENY_KEYS:
                stripped.append(k)
                continue
            out[k] = _sanitize_value(v, stripped)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item, stripped) for item in value]
    return value


def sanitize_tree(value: Any) -> tuple[Any, list[str]]:
    stripped: list[str] = []
    cleaned = _sanitize_value(value, stripped)
    return cleaned, stripped


def _drop_keys(obj: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    drop_norm = {_norm_key(k) for k in keys}
    return {k: v for k, v in obj.items() if _norm_key(k) not in drop_norm}


def _unwrap_envelope(body: Any) -> Any:
    if isinstance(body, dict) and body.get("success") is True and "data" in body:
        return body["data"]
    return body


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_clublab_env() -> None:
    """Populate CLUBLAB_* from process env or credentials file (never log values)."""
    if (os.environ.get("CLUBLAB_TOKEN") or "").strip():
        return
    if (os.environ.get("CLUBLAB_EMAIL") or "").strip() and (os.environ.get("CLUBLAB_PASSWORD") or "").strip():
        return
    parsed = _parse_env_file(CREDENTIALS_FILE)
    for key in ("CLUBLAB_EMAIL", "CLUBLAB_PASSWORD", "CLUBLAB_TOKEN", "CLUBLAB_ORIGIN"):
        if not os.environ.get(key) and parsed.get(key):
            os.environ[key] = parsed[key]


@dataclass
class HttpResponse:
    status: int
    body: Any
    url: str


class ClublabHttpClient:
    def __init__(self, origin: str, token: str, timeout: float = 60.0) -> None:
        self.origin = origin.rstrip("/")
        self.token = token
        self.timeout = timeout

    def get(self, path: str, *, facility_id: str | None = None) -> HttpResponse:
        query = f"?{urlencode({'facilityId': facility_id})}" if facility_id else ""
        url = f"{self.origin}{path}{query}"
        req = Request(url, method="GET", headers={"Authorization": f"Bearer {self.token}"})
        return self._request(req, url)

    def post_json(self, path: str, body: dict[str, Any]) -> HttpResponse:
        url = f"{self.origin}{path}"
        data = json.dumps(body).encode("utf-8")
        req = Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        return self._request(req, url)

    def _request(self, req: Request, url: str) -> HttpResponse:
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200) or 200
        except HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read().decode("utf-8")
            except Exception:  # noqa: BLE001
                raw = ""
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return HttpResponse(status=status, body=parsed, url=url)
        except URLError as exc:
            raise ClublabPullError(0, url, describe_exception(exc)) from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return HttpResponse(status=status, body=parsed, url=url)


class ClublabPullError(Exception):
    def __init__(self, status: int, url: str, detail: str = "") -> None:
        self.status = status
        self.url = url
        self.detail = detail
        super().__init__(f"HTTP {status} {url}")


def login_token(origin: str) -> str:
    token = (os.environ.get("CLUBLAB_TOKEN") or "").strip()
    if token:
        return token
    email = (os.environ.get("CLUBLAB_EMAIL") or "").strip()
    password = (os.environ.get("CLUBLAB_PASSWORD") or "").strip()
    if not email or not password:
        raise ClublabPullError(401, f"{origin}/api/v1/auth/login", "missing CLUBLAB_EMAIL or CLUBLAB_PASSWORD")
    req = Request(
        f"{origin}/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200) or 200
    except HTTPError as exc:
        raise ClublabPullError(exc.code, f"{origin}/api/v1/auth/login", "") from exc
    doc = json.loads(raw) if raw else {}
    if not isinstance(doc, dict):
        raise ClublabPullError(status, f"{origin}/api/v1/auth/login", "invalid login response")
    data = doc.get("data")
    tok = None
    if isinstance(data, dict):
        tok = data.get("accessToken") or data.get("token") or data.get("access_token")
    if not tok:
        tok = doc.get("token") or doc.get("accessToken") or doc.get("access_token")
    if not tok:
        raise ClublabPullError(status, f"{origin}/api/v1/auth/login", "no token in response")
    return str(tok)


def _build_client() -> ClublabHttpClient:
    if _http_client_factory is not None:
        return _http_client_factory()
    load_clublab_env()
    origin = (os.environ.get("CLUBLAB_ORIGIN") or DEFAULT_ORIGIN).strip()
    token = login_token(origin)
    return ClublabHttpClient(origin, token)


def _require_ok(resp: HttpResponse, path: str) -> Any:
    if resp.status >= 400:
        raise ClublabPullError(resp.status, resp.url, str(resp.body)[:200])
    return _unwrap_envelope(resp.body)


def _get_optional(client: ClublabHttpClient, path: str, *, facility_id: str) -> Any | None:
    resp = client.get(path, facility_id=facility_id)
    if resp.status == 404:
        return None
    return _require_ok(resp, path)


def _normalize_facility_refs(raw: Any) -> list[dict[str, str]]:
    items = raw if isinstance(raw, list) else []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("facilityId") or item.get("id") or "")
        name = str(item.get("name") or fid)
        if fid:
            out.append({"facilityId": fid, "name": name})
    return out


def _trim_segments(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {k: item[k] for k in ("id", "name", "slug") if k in item}
        if row:
            out.append(row)
    return out


def _normalize_ordered_products(raw: Any) -> list[dict[str, Any]]:
    items: list[Any]
    if isinstance(raw, dict):
        items = raw.get("items") if isinstance(raw.get("items"), list) else []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    products: list[dict[str, Any]] = []
    for p in items:
        if not isinstance(p, dict):
            continue
        products.append(
            {
                "productKey": p.get("productKey"),
                "name": p.get("productName") or p.get("name"),
                "category": p.get("category"),
                "quantity": p.get("totalQuantity") if p.get("totalQuantity") is not None else p.get("quantity"),
                "orderCount": p.get("orderCount"),
                "firstOrderDate": p.get("firstOrderDate"),
                "lastOrderDate": p.get("lastOrderDate"),
            }
        )
    return products


def _trim_fitme_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    trimmed = _drop_keys(raw, FITME_SUMMARY_DROP)
    keep: dict[str, Any] = {}
    for key in ("headlines", "buildPipeline", "clubTypeMix", "engagement", "alerts"):
        if key in trimmed:
            keep[key] = trimmed[key]
    return keep


def _trim_costme_catalogue(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for c in rows:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "brand": c.get("brand"),
                "model": c.get("model"),
                "component": c.get("component"),
                "category": c.get("category"),
                "sellPrice": c.get("sell") if c.get("sell") is not None else c.get("sellPrice"),
                "margin": c.get("grossMarginPercent") if c.get("grossMarginPercent") is not None else c.get("margin"),
            }
        )
    return out


def _normalize_tag_frequency(raw: Any) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    elif isinstance(raw, list):
        tags = raw
    else:
        tags = []
    out: list[dict[str, Any]] = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        out.append({"tag": t.get("label") or t.get("tag") or t.get("name"), "count": t.get("usageCount") or t.get("count")})
    return out


def _fitme_completed(summary: dict[str, Any]) -> int:
    headlines = summary.get("headlines") if isinstance(summary.get("headlines"), dict) else {}
    cf = headlines.get("completedFittings")
    if isinstance(cf, dict) and cf.get("value") is not None:
        return int(cf["value"])
    if headlines.get("completed") is not None:
        return int(headlines["completed"])
    if summary.get("completed") is not None:
        return int(summary["completed"])
    return 0


def _fitme_in_build(summary: dict[str, Any]) -> int:
    bp = summary.get("buildPipeline") if isinstance(summary.get("buildPipeline"), dict) else {}
    if bp.get("inBuild") is not None:
        return int(bp["inBuild"])
    return 0


def _crm_revenue_total(reports: dict[str, Any]) -> float:
    rev = reports.get("revenue") if isinstance(reports.get("revenue"), dict) else {}
    for key in ("periodPaidTotal", "total", "periodPaidBookingTotal"):
        val = rev.get(key)
        if val is not None:
            return float(val)
    return 0.0


def _coach_session_count(sess: dict[str, Any]) -> int:
    if not isinstance(sess, dict):
        return 0
    for key in ("totalSessions", "sessionCount", "count"):
        if sess.get(key) is not None:
            return int(sess[key])
    return 0


def _fetch_facility(client: ClublabHttpClient, facility_id: str, name: str) -> tuple[dict[str, Any], list[str]]:
    stripped_all: list[str] = []

    dash_raw = _require_ok(client.get("/api/v1/crm/dashboard", facility_id=facility_id), "crm dashboard")
    dash = _drop_keys(dash_raw if isinstance(dash_raw, dict) else {}, CRM_DASHBOARD_DROP)
    dash, s = sanitize_tree(dash)
    stripped_all.extend(s)

    reports_raw = _require_ok(client.get("/api/v1/crm/reports", facility_id=facility_id), "crm reports")
    reports, s = sanitize_tree(reports_raw if isinstance(reports_raw, dict) else {})
    stripped_all.extend(s)

    segments_raw = _require_ok(client.get("/api/v1/crm/segments", facility_id=facility_id), "crm segments")
    segments, s = sanitize_tree(_trim_segments(segments_raw))
    stripped_all.extend(s)

    order_raw = _require_ok(client.get("/api/v1/orderme/ordered-products", facility_id=facility_id), "orderme")
    products, s = sanitize_tree(_normalize_ordered_products(order_raw))
    stripped_all.extend(s)

    fit_summary_raw = _require_ok(
        client.get("/api/v1/fitme-reports/summary", facility_id=facility_id), "fitme summary"
    )
    fit_summary, s = sanitize_tree(_trim_fitme_summary(fit_summary_raw))
    stripped_all.extend(s)

    fit_equip_raw = _require_ok(
        client.get("/api/v1/fitme-reports/equipment", facility_id=facility_id), "fitme equipment"
    )
    fit_equip, s = sanitize_tree(fit_equip_raw if isinstance(fit_equip_raw, dict) else {})
    stripped_all.extend(s)

    timeline_raw = _require_ok(
        client.get("/api/v1/fitme-reports/timeline", facility_id=facility_id), "fitme timeline"
    )
    timeline, s = sanitize_tree(timeline_raw if isinstance(timeline_raw, dict) else {})
    stripped_all.extend(s)

    cost_raw = _require_ok(client.get("/api/v1/costme/catalogue", facility_id=facility_id), "costme")
    cost_rows, s = sanitize_tree(_trim_costme_catalogue(cost_raw))
    stripped_all.extend(s)

    coach_sess_raw = _require_ok(
        client.get("/api/v1/Reports/session-summary", facility_id=facility_id), "coachme sessions"
    )
    coach_sess, s = sanitize_tree(coach_sess_raw if isinstance(coach_sess_raw, dict) else {})
    stripped_all.extend(s)

    coach_tags_raw = _get_optional(client, "/api/v1/Reports/tag-frequency", facility_id=facility_id)
    coach_tags, s = sanitize_tree(_normalize_tag_frequency(coach_tags_raw))
    stripped_all.extend(s)

    row: dict[str, Any] = {
        "facilityId": facility_id,
        "name": name,
        "crm": {"dashboard": dash, "reports": reports, "segments": segments},
        "orderme": {"products": products},
        "fitme": {"summary": fit_summary, "equipment": fit_equip, "timeline": timeline},
        "costme": {"catalogue": cost_rows},
        "coachme": {"sessionSummary": coach_sess, "tagFrequency": coach_tags},
    }
    return row, stripped_all


def _compute_totals(facilities: list[dict[str, Any]]) -> dict[str, Any]:
    crm_revenue = 0.0
    order_qty = 0
    fitme_completed = 0
    fitme_in_build = 0
    costme_skus = 0
    coach_sessions = 0
    for fac in facilities:
        reports = (fac.get("crm") or {}).get("reports") or {}
        if isinstance(reports, dict):
            crm_revenue += _crm_revenue_total(reports)
        products = (fac.get("orderme") or {}).get("products") or []
        if isinstance(products, list):
            order_qty += sum(int(p.get("quantity") or 0) for p in products if isinstance(p, dict))
        fit_summary = (fac.get("fitme") or {}).get("summary") or {}
        if isinstance(fit_summary, dict):
            fitme_completed += _fitme_completed(fit_summary)
            fitme_in_build += _fitme_in_build(fit_summary)
        catalogue = (fac.get("costme") or {}).get("catalogue") or []
        if isinstance(catalogue, list):
            costme_skus += len(catalogue)
        sess = (fac.get("coachme") or {}).get("sessionSummary") or {}
        coach_sessions += _coach_session_count(sess if isinstance(sess, dict) else {})
    return {
        "facilityCount": len(facilities),
        "crmRevenueTotal": int(crm_revenue),
        "ordermeOrderCount": order_qty,
        "fitmeCompleted": fitme_completed,
        "fitmeInBuild": fitme_in_build,
        "costmeSkuCount": costme_skus,
        "coachmeSessionCount": coach_sessions,
    }


def build_snapshot(client: ClublabHttpClient) -> tuple[dict[str, Any], list[str]]:
    fac_resp = _require_ok(client.get("/api/v1/facilities"), "facilities")
    facility_refs = _normalize_facility_refs(fac_resp)
    stripped_all: list[str] = []
    facility_rows: list[dict[str, Any]] = []
    for ref in facility_refs:
        fid = ref["facilityId"]
        name = ref["name"]
        row, stripped = _fetch_facility(client, fid, name)
        stripped_all.extend(stripped)
        facility_rows.append(row)
    snapshot = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "facilities": facility_rows,
        "totals": _compute_totals(facility_rows),
    }
    snapshot, more = sanitize_tree(snapshot)
    stripped_all.extend(more)
    return snapshot, stripped_all


def write_snapshot_files(snapshot: dict[str, Any], sanitized_keys: list[str]) -> None:
    atomic_write(SNAPSHOT_NAME, snapshot)
    meta = {
        "schema": "campaign-os/clublab-snapshot-meta/v1",
        "generated_at": snapshot.get("generated_at") or utc_now_iso(),
        "sanitized_keys": sorted(set(sanitized_keys)),
    }
    atomic_write(META_NAME, meta)


def counts_summary(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Counts-only per facility for handoff evidence."""
    out: list[dict[str, Any]] = []
    for fac in snapshot.get("facilities") or []:
        if not isinstance(fac, dict):
            continue
        dash = ((fac.get("crm") or {}).get("dashboard") or {}) if isinstance(fac.get("crm"), dict) else {}
        reports = ((fac.get("crm") or {}).get("reports") or {}) if isinstance(fac.get("crm"), dict) else {}
        products = (fac.get("orderme") or {}).get("products") or []
        fit_summary = ((fac.get("fitme") or {}).get("summary") or {}) if isinstance(fac.get("fitme"), dict) else {}
        out.append(
            {
                "facility_id": fac.get("facilityId"),
                "facility_name": fac.get("name"),
                "crm_active_total": dash.get("totalActive") or dash.get("activeTotal"),
                "crm_client_count": reports.get("clientCount") if isinstance(reports, dict) else None,
                "crm_revenue_period_paid": int(_crm_revenue_total(reports)) if isinstance(reports, dict) else 0,
                "orderme_product_rows": len(products) if isinstance(products, list) else 0,
                "orderme_quantity_total": sum(int(p.get("quantity") or 0) for p in products if isinstance(p, dict)),
                "fitme_completed": _fitme_completed(fit_summary) if isinstance(fit_summary, dict) else None,
                "fitme_in_build": _fitme_in_build(fit_summary) if isinstance(fit_summary, dict) else None,
                "costme_skus": len(((fac.get("costme") or {}).get("catalogue") or [])),
                "coachme_sessions": _coach_session_count(
                    (fac.get("coachme") or {}).get("sessionSummary") or {}
                ),
            }
        )
    return out


def run() -> dict[str, Any]:
    """Pull ClubLab stats and write clublab-snapshot.json under DATA_DIR."""
    try:
        client = _build_client()
        snapshot, stripped = build_snapshot(client)
        write_snapshot_files(snapshot, stripped)
        n = len(snapshot.get("facilities") or [])
        return {
            "ok": True,
            "rows": n,
            "sanitized_keys": len(set(stripped)),
            "totals": snapshot.get("totals"),
        }
    except ClublabPullError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "http_status": exc.status,
            "endpoint": exc.url,
            "rows": 0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc), "rows": 0}


def set_http_client_factory(factory: Callable[[], Any] | None) -> None:
    global _http_client_factory
    _http_client_factory = factory
