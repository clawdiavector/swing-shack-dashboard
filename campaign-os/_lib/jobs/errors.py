"""Error classifier + fingerprint for Campaign OS jobs (t35/t36)."""

from __future__ import annotations

import errno
import hashlib
import json
import re
import socket
from typing import Any, Optional
from xml.etree import ElementTree

import requests

# Transient for alert semantics; runner retries only RETRYABLE (see plan §3.1).
TRANSIENT = frozenset({"http_5xx", "rate_limit", "timeout"})
# runner abandons the worker thread on timeout — retry would race JobSpec.writes.
RETRYABLE = frozenset({"http_5xx", "rate_limit"})

ERROR_CLASSES = (
    "auth",
    "rate_limit",
    "http_5xx",
    "http_4xx",
    "timeout",
    "parse",
    "empty_result",
    "missing_input",
    "disk",
    "unknown",
)

_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[tT ][\d:.]+z?", re.I)
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
_HEX_RE = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
_PATH_RE = re.compile(r"/[^\s'\"]+/[^\s'\"]+")
_NUM_RE = re.compile(r"\b\d+\b")
_TIMEOUT_MSG = re.compile(r"timed?\s*out", re.I)
_DISK_MSG = re.compile(r"no space left|read-only file system|permission denied", re.I)
_AUTH_MSG = re.compile(
    r"invalid_grant|OAuthException|RefreshError|unauthorized|forbidden|expired token|"
    r"missing [A-Z0-9_]*(TOKEN|KEY|SECRET)",
    re.I,
)
_RATE_MSG = re.compile(r"rate.?limit|quota|too many requests", re.I)
_HTTP5_MSG = re.compile(r"HTTPError\(5\d\d\)")
_HTTP_STATUS_MSG = re.compile(r"HTTPError\((\d{3})\)")
_PARSE_MSG = re.compile(r"parse|decode|expecting value|not well-formed|selector", re.I)
_MISSING_MSG = re.compile(r"missing input|no such file", re.I)
_EMPTY_MSG = re.compile(r"no (videos|articles|rows|data|results)|empty|0 rows", re.I)

_DISK_ERRNOS = {
    errno.ENOSPC,
    errno.EACCES,
    errno.EROFS,
}
if hasattr(errno, "EDQUOT"):
    _DISK_ERRNOS.add(errno.EDQUOT)


def describe_exception(exc: BaseException) -> str:
    """Compact, redaction-safe exception label: 'HTTPError(429)'. Never the body."""
    name = type(exc).__name__
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{name}({status})" if status is not None else name


def normalize(message: Optional[str]) -> str:
    text = str(message or "").lower()
    text = _TS_RE.sub("<ts>", text)
    text = _UUID_RE.sub("<uuid>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _PATH_RE.sub("<path>", text)
    text = _NUM_RE.sub("<n>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def fingerprint(job_id: str, error_class: str, message: Optional[str]) -> str:
    payload = f"{job_id}|{error_class}|{normalize(message)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _http_status(exc: Optional[BaseException], message: str) -> Optional[int]:
    if exc is not None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
        if isinstance(code, int):
            return code
    m = _HTTP_STATUS_MSG.search(message)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _is_timeout_exc(exc: Optional[BaseException]) -> bool:
    if exc is None:
        return False
    if isinstance(exc, (TimeoutError, socket.timeout, requests.Timeout)):
        return True
    # requests may wrap
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return True
    return False


def _is_disk_exc(exc: Optional[BaseException]) -> bool:
    if isinstance(exc, OSError):
        return getattr(exc, "errno", None) in _DISK_ERRNOS
    return False


def _is_parse_exc(exc: Optional[BaseException]) -> bool:
    if exc is None:
        return False
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ElementTree.ParseError)):
        return True
    try:
        import csv

        if isinstance(exc, csv.Error):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _missing_reads(spec: Any) -> bool:
    if spec is None:
        return False
    reads = getattr(spec, "reads", ()) or ()
    if not reads:
        return False
    import os

    base = os.environ.get("DATA_DIR") or "/data"
    for rel in reads:
        path = os.path.join(base, rel)
        if not os.path.exists(path):
            return True
    return False


def classify(
    *,
    exc: Optional[BaseException] = None,
    message: Optional[str] = None,
    spec: Any = None,
    result: Any = None,
    status: Optional[str] = None,
) -> tuple[str, dict]:
    """Return (error_class, evidence). Never raises."""
    try:
        msg = ""
        if message is not None:
            msg = str(message)
        elif exc is not None:
            msg = str(exc)
        elif isinstance(result, dict) and result.get("error") is not None:
            msg = str(result.get("error"))
        msg = msg[:10000]

        http = _http_status(exc, msg)

        # 1 timeout
        if status == "TIMEOUT" or _is_timeout_exc(exc) or _TIMEOUT_MSG.search(msg):
            return "timeout", {"matched": "timeout", "status": http}

        # 2 disk
        if _is_disk_exc(exc) or _DISK_MSG.search(msg):
            return "disk", {"matched": "disk", "status": http}

        # 3 auth
        if http in (401, 403) or _AUTH_MSG.search(msg):
            return "auth", {"matched": "auth", "status": http}

        # 4 rate_limit
        if http == 429 or _RATE_MSG.search(msg):
            return "rate_limit", {"matched": "rate_limit", "status": http}

        # 5 http_5xx
        if (http is not None and 500 <= http <= 599) or _HTTP5_MSG.search(msg):
            return "http_5xx", {"matched": "http_5xx", "status": http}

        # 6 http_4xx
        if http is not None and 400 <= http <= 499:
            return "http_4xx", {"matched": "http_4xx", "status": http}

        # 7 parse
        if _is_parse_exc(exc) or _PARSE_MSG.search(msg):
            return "parse", {"matched": "parse", "status": http}

        # 8 missing_input
        if _missing_reads(spec) or _MISSING_MSG.search(msg):
            return "missing_input", {"matched": "missing_input", "status": http}

        # 9 empty_result
        if isinstance(result, dict):
            if result.get("ok") is False and _EMPTY_MSG.search(msg):
                return "empty_result", {"matched": "empty_result", "status": http}
            if (
                result.get("ok") is True
                and result.get("rows") == 0
                and spec is not None
                and not getattr(spec, "best_effort", False)
            ):
                return "empty_result", {"matched": "empty_result_ok_zero", "status": http}
        elif _EMPTY_MSG.search(msg):
            return "empty_result", {"matched": "empty_result", "status": http}

        return "unknown", {"matched": "unknown", "status": http}
    except Exception:  # noqa: BLE001 — classify never raises
        return "unknown", {"matched": "classify_guard", "status": None}
