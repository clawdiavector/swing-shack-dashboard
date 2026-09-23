"""meta-live-fetch.yml — per-brand POSTs, no ?all=1, no code-push trigger."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
WF = REPO_ROOT / ".github" / "workflows" / "meta-live-fetch.yml"

if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("COS_FLAT_FALLBACK", "1")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs") or mod.startswith("_lib.brand"):
            del sys.modules[mod]
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    yield tmp_path
    clear_brands_cache()


def _workflow_text() -> str:
    return WF.read_text(encoding="utf-8")


def _on_block(text: str) -> str:
    m = re.search(r"^on:\n", text, re.M)
    assert m is not None
    j = re.search(r"^jobs:\n", text, re.M)
    assert j is not None
    return text[m.start() : j.start()]


def _meta_brands_from_registry() -> set[str]:
    reg = json.loads((REPO_ROOT / "data" / "brands.json").read_text(encoding="utf-8"))
    out: list[str] = []
    for bid, brand in (reg.get("brands") or {}).items():
        if not brand.get("active", True):
            continue
        scope = (brand.get("integration_scope") or {}).get("meta")
        if scope is None or scope.get("applies") is False:
            continue
        out.append(bid)
    return set(out)


def test_workflow_posts_per_brand():
    text = _workflow_text()
    assert "meta_refresh?brand=" in text


def test_workflow_has_no_all_fanout():
    text = _workflow_text()
    assert re.search(r'api/jobs/run/meta_refresh\?[^"\s]*all=1', text) is None


def test_workflow_has_no_code_push_trigger():
    text = _workflow_text()
    on_block = _on_block(text)
    assert re.search(r"^\s+push:", on_block, re.M) is None


def test_assert_ok_is_per_brand_file():
    text = _workflow_text()
    assert 'assert-ok "$out"' in text
    assert "/tmp/meta-fetch.json" not in text


def test_workflow_waits_for_health_before_fanout():
    text = _workflow_text()
    health_idx = text.find("Preflight — wait for /api/health")
    post_idx = text.find("name: POST /api/jobs/run/meta_refresh per brand")
    assert health_idx != -1 and post_idx != -1
    assert health_idx < post_idx


def test_workflow_retries_a_lane_once():
    text = _workflow_text()
    assert "Retrying brand=" in text
    assert "attempt 2" in text


def test_workflow_brand_filter_matches_registry(job_env):
    from _lib.jobs.brand_lanes import resolve_brands, skipped_brands
    from _lib.jobs.registry import JOBS

    spec = JOBS["meta_refresh"]
    expected = set(resolve_brands(spec)) | set(skipped_brands(spec))
    assert _meta_brands_from_registry() == expected
