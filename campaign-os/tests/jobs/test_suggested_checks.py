"""t37 — suggested_checks coverage over 11 jobs × 10 classes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.errors import ERROR_CLASSES  # noqa: E402
from _lib.jobs.suggested_checks import checks_for  # noqa: E402


@pytest.fixture()
def job_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    return app_module


def test_coverage_110_pairs(job_app):
    from _lib.jobs.registry import JOBS

    assert len(JOBS) == 11
    missing = []
    for job_id in JOBS:
        for error_class in ERROR_CLASSES:
            checks = checks_for(error_class, job_id)
            if len(checks) < 1:
                missing.append((error_class, job_id))
            for c in checks:
                assert len(c) >= 30, f"too short: {error_class}/{job_id}"
    assert not missing


CONSOLE_ALLOWLIST = (
    "Google Cloud Console",
    "Meta Business Suite",
    "Ubersuggest",
    "Google Business Profile",
    "Railway",
    "Campaign OS",
    "GET /api/jobs",
)


def test_console_named_for_credential_jobs(job_app):
    from _lib.jobs.registry import JOBS

    credential_jobs = [n for n, s in JOBS.items() if s.credentials]
    assert credential_jobs
    for job_id in credential_jobs:
        for error_class in ("auth", "rate_limit", "http_4xx", "http_5xx"):
            checks = checks_for(error_class, job_id)
            joined = " ".join(checks)
            assert any(name in joined for name in CONSOLE_ALLOWLIST), (
                f"no console named for {job_id}/{error_class}"
            )


_FORBIDDEN = re.compile(r"echo \$|print.*TOKEN|cat .*\.env", re.I)


def test_no_secret_print_instructions(job_app):
    from _lib.jobs.registry import JOBS

    for job_id in JOBS:
        for error_class in ERROR_CLASSES:
            for check in checks_for(error_class, job_id):
                assert not _FORBIDDEN.search(check), f"forbidden instruction in {job_id}/{error_class}"
