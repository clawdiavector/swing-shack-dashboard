"""t39 — planted-secret redaction merge gate. Never interpolate secret values in asserts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.diagnostics import build_bundle, read_bundle, write_bundle  # noqa: E402
from _lib.jobs.redaction import redact, redact_obj  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402

# Planted labels — assertion failures name the label, never the value.
# Values must match env-strip (≥8 + TOKEN name) or a generic shape so redact() removes them.
PLANTS = {
    "message": "PLANTEDMSGSECRETaa11bb22cc33dd44ee55ff66778899aabb",  # hex-shaped
    "traceback_tail": "PLANTEDTBSECRETaa11bb22cc33dd44ee55ff66778899aabbcc",  # hex-shaped
    "stderr_tail": "cGxhbnRlZHN0ZGVyclNFQ1JFVHZhbHVlMTIzNDU2Nzg5MGFiY2RlZg==",  # b64
    "body_head": "EAAplantedBodyHeadTokenValueABCDEFGHIJKLMNOPQR",  # meta
    "env": "PLANTED_ENV_SECRET_meta_system_user_token_xyz",
}

SHAPES = {
    "bearer": "Bearer plantedbearerTOKEN_ABCDEFGH12345678",
    "meta": "EAAplantedMetaTokenValueABCDEFGHIJKLMNOP",
    "pem": "-----BEGIN PRIVATE KEY-----\nPLANTEDPEMSECRETVALUEABCDEF\n-----END PRIVATE KEY-----",
    "google": "AIzaplantedGoogleApiKeyValueABCDEFGH1234",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwbGFudGVkIn0.plantedSignatureValueABCDEF",
    "hex": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "b64": "cGxhbnRlZGJhc2U2NHNlY3JldHZhbHVlMTIzNDU2Nzg5MA==",
}


def _assert_absent(blob: str, planted_value: str, field_label: str) -> None:
    if planted_value in blob:
        raise AssertionError(f"planted secret survived in field={field_label}")


def test_redact_generic_shapes():
    for label, value in SHAPES.items():
        out = redact(f"prefix {value} suffix")
        _assert_absent(out, value, label)
        assert "«redacted" in out


def test_env_value_strip(monkeypatch):
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", PLANTS["env"])
    out = redact(f"token was {PLANTS['env']} here")
    _assert_absent(out, PLANTS["env"], "env")
    assert "«redacted:META_SYSTEM_USER_TOKEN»" in out


def test_min_length_guard_short_env(monkeypatch):
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "1")
    out = redact("count is 1 and true")
    assert "1" in out
    assert "true" in out


def test_planted_secrets_in_bundle_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", PLANTS["env"])

    spec = JobSpec(
        name="meta_refresh",
        fn=lambda: {"ok": False},
        every_seconds=43200,
        criticality="HIGH",
        credentials=("META_SYSTEM_USER_TOKEN",),
        writes=("ig-analytics.json",),
    )

    class Boom(Exception):
        pass

    # Plant env secret + shape secrets into free-text fields (labels only in asserts).
    msg = f"{PLANTS['message']} {PLANTS['env']} {SHAPES['bearer']} {SHAPES['google']}"
    exc = Boom(msg)
    bundle = build_bundle(
        spec=spec,
        run_id="20260914T000000Z-meta_refresh-abc123",
        attempt=1,
        status="FAILED",
        started="2026-09-14T00:00:00Z",
        finished="2026-09-14T00:00:01Z",
        duration_s=1.0,
        error=msg,
        exc=exc,
        result={
            "ok": False,
            "upstream": [
                {
                    "url": "https://example.test",
                    "method": "GET",
                    "status": 401,
                    "latency_ms": 10,
                    "body_head": f"{PLANTS['body_head']} {SHAPES['meta']} {SHAPES['jwt']}",
                }
            ],
        },
    )
    # Force stderr / traceback with remaining shapes + planted labels
    bundle["stderr_tail"] = PLANTS["stderr_tail"] + " " + SHAPES["hex"]
    bundle["exception"]["traceback_tail"] = (
        PLANTS["traceback_tail"] + "\n" + SHAPES["pem"] + "\n" + SHAPES["b64"]
    )
    bundle = redact_obj(bundle)

    blob = json.dumps(bundle)
    for label, value in PLANTS.items():
        _assert_absent(blob, value, label)
    for label, value in SHAPES.items():
        _assert_absent(blob, value, label)

    for v in bundle["credentials"].values():
        assert isinstance(v, bool)

    assert len(bundle["exception"]["message"]) <= 500


def test_truncation_limits():
    long_msg = "x" * 2000
    obj = redact_obj(
        {
            "exception": {
                "type": "Err",
                "message": long_msg,
                "traceback_tail": "\n".join(f"line-{i}" for i in range(50)),
            },
            "stderr_tail": "y" * 8000,
            "upstream": [{"body_head": "z" * 500}],
        }
    )
    assert len(obj["exception"]["message"]) <= 500
    assert len(obj["exception"]["traceback_tail"].splitlines()) <= 30
    assert len(obj["stderr_tail"]) <= 4096
    assert len(obj["upstream"][0]["body_head"]) <= 200


def test_write_and_read_redacts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", PLANTS["env"])
    spec = JobSpec(
        name="meta_refresh",
        fn=lambda: {"ok": False},
        every_seconds=43200,
        credentials=("META_SYSTEM_USER_TOKEN",),
        writes=("ig-analytics.json",),
    )
    run_id = "20260914T010101Z-meta_refresh-plant1"
    path = write_bundle(
        spec=spec,
        run_id=run_id,
        attempt=1,
        status="FAILED",
        started="2026-09-14T01:01:01Z",
        finished="2026-09-14T01:01:02Z",
        duration_s=1.0,
        error=f"auth failed {PLANTS['env']} {SHAPES['bearer']}",
    )
    assert path
    raw = Path(path).read_text()
    _assert_absent(raw, PLANTS["env"], "env")
    _assert_absent(raw, SHAPES["bearer"].split()[-1], "bearer-token")
    loaded = read_bundle(run_id)
    assert loaded is not None
    blob = json.dumps(loaded)
    _assert_absent(blob, PLANTS["env"], "env-reread")
