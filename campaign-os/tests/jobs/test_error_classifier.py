"""t36 — error classifier: one real-path test per class + fingerprint stability."""

from __future__ import annotations

import errno
import json
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.errors import classify, fingerprint, normalize  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402


def _http_error(code: int) -> requests.HTTPError:
    resp = Mock()
    resp.status_code = code
    exc = requests.HTTPError(f"{code} error")
    exc.response = resp
    return exc


def test_class_timeout_status():
    cls, evidence = classify(status="TIMEOUT", message="exceeded timeout_seconds=60")
    assert cls == "timeout"
    assert evidence["matched"] == "timeout"


def test_class_timeout_exception():
    cls, _ = classify(exc=requests.Timeout("read timed out"))
    assert cls == "timeout"


def test_class_disk_enospc():
    exc = OSError(errno.ENOSPC, "No space left on device")
    cls, evidence = classify(exc=exc)
    assert cls == "disk"
    assert evidence["matched"] == "disk"


def test_class_auth_http_401():
    cls, evidence = classify(exc=_http_error(401))
    assert cls == "auth"
    assert evidence["status"] == 401


def test_class_rate_limit_429():
    cls, evidence = classify(exc=_http_error(429))
    assert cls == "rate_limit"
    assert evidence["status"] == 429


def test_class_http_5xx():
    cls, evidence = classify(exc=_http_error(503))
    assert cls == "http_5xx"
    assert evidence["status"] == 503


def test_class_http_4xx():
    cls, evidence = classify(exc=_http_error(404))
    assert cls == "http_4xx"
    assert evidence["status"] == 404


def test_class_parse_json():
    try:
        json.loads("{not-json")
    except json.JSONDecodeError as exc:
        cls, evidence = classify(exc=exc)
    assert cls == "parse"
    assert evidence["matched"] == "parse"


def test_class_missing_input(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    spec = JobSpec(
        name="insights_hooks",
        fn=lambda: {},
        every_seconds=86400,
        reads=("missing-input.json",),
    )
    cls, evidence = classify(message="job failed", spec=spec)
    assert cls == "missing_input"
    assert evidence["matched"] == "missing_input"


def test_class_empty_result():
    cls, evidence = classify(
        result={"ok": False, "error": "no videos returned"},
        message="no videos returned",
    )
    assert cls == "empty_result"
    assert evidence["matched"] == "empty_result"


def test_class_unknown():
    cls, evidence = classify(message="something inexplicable happened")
    assert cls == "unknown"
    assert evidence["matched"] == "unknown"


def test_fingerprint_stable_across_noise():
    a = fingerprint(
        "ga4_report",
        "auth",
        "invalid_grant at 2026-09-11T04:00:14Z path /tmp/abc-123/file.json uuid "
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee hex deadbeefdeadbeefdeadbeefdeadbeef",
    )
    b = fingerprint(
        "ga4_report",
        "auth",
        "invalid_grant at 2026-09-14T12:22:01Z path /var/tmp/xyz-999/other.json uuid "
        "11111111-2222-3333-4444-555555555555 hex cafeBabeCafeBabeCafeBabeCafeBabe",
    )
    assert a == b
    assert len(a) == 40


def test_fingerprint_differs_by_job_and_class():
    base = fingerprint("ga4_report", "auth", "invalid_grant")
    other_job = fingerprint("meta_refresh", "auth", "invalid_grant")
    other_class = fingerprint("ga4_report", "parse", "invalid_grant")
    assert base != other_job
    assert base != other_class


def test_classify_never_raises():
    for payload in (None, "", object(), "x" * 10000):
        if payload is None:
            cls, evidence = classify()
        elif isinstance(payload, str):
            cls, evidence = classify(message=payload)
        else:
            cls, evidence = classify(exc=payload)  # type: ignore[arg-type]
        assert cls in {
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
        }
        assert isinstance(evidence, dict)


def test_normalize_collapses_ids():
    n = normalize("Err 2026-01-02T03:04:05Z /tmp/foo/bar 42")
    assert "<ts>" in n
    assert "<path>" in n
    assert "<n>" in n
    assert "2026" not in n
