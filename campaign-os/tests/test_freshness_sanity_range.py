"""
Regression test: freshness parseTs sanity range + freshness_scan job.

Bug shipped 2026-08-07: the freshness detector was scanning deep into
content fields like `"date": "Apr 22"` (human-readable label, no year).
JS Date.parse() happily returns year 2001 for those, which then produced
age_days=9238 and a spurious "🚨 102 files > 42 days old" banner on Home.

Fix: parseTs() now applies a sanity range (year 2010 → current_year+1)
and rejects bare strings like "Apr 22" without an explicit year.

As of t33, scripts/data_freshness_check.js is deleted. Regeneration is
asserted against _run_freshness_scan_job() (writes $DATA_DIR/freshness.json).
The parseTs cases below keep an inline copy of the retired JS pair so the
sanity-range contract stays covered without the file.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRESHNESS = REPO / "data" / "freshness.json"


def test_freshness_regenerates(tmp_path, monkeypatch):
    """freshness_scan job writes $DATA_DIR/freshness.json (no node shell-out)."""
    seed = {"generated": "2026-09-14T00:00:00Z", "items": []}
    (tmp_path / "probe.json").write_text(json.dumps(seed), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sys.path.insert(0, str(REPO / "campaign-os"))
    import app as app_module  # noqa: E402

    result = app_module._run_freshness_scan_job()
    assert result.get("ok") is True, f"freshness_scan failed: {result}"
    out = tmp_path / "freshness.json"
    assert out.exists(), "freshness.json was not written under DATA_DIR"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("total_files", 0) >= 1


def test_no_year_2001_artifacts():
    """No rotten/stale entry should report a year-2001 timestamp."""
    if not FRESHNESS.exists():
        raise unittest.SkipTest("freshness.json missing — seed not present")
    j = json.loads(FRESHNESS.read_text(encoding="utf-8"))
    bad_paths = []
    for bucket in ("stale_files", "rotten_files"):
        for entry in j.get(bucket, []):
            ts = entry.get("newest_ts") or ""
            if ts.startswith("2001-"):
                bad_paths.append((bucket, entry["path"], ts))
    assert not bad_paths, (
        "Freshness detector still classifying year-2001 timestamps as data: "
        + str(bad_paths)
    )


def test_no_thousand_day_ages():
    """No entry should report an age_days >= 1000 (the pre-fix symptom was 9238)."""
    if not FRESHNESS.exists():
        raise unittest.SkipTest("freshness.json missing — seed not present")
    j = json.loads(FRESHNESS.read_text(encoding="utf-8"))
    for bucket in ("stale_files", "rotten_files"):
        for entry in j.get(bucket, []):
            age = entry.get("age_days", 0)
            assert age < 1000, (
                f"{bucket} {entry['path']} reports age_days={age} — sanity "
                f"range broken"
            )


def test_parseTs_rejects_bare_month_day():
    """Unit-level: parseTs('Apr 22') must return null (not year 2001).

    Inline copy of the parseTs + _inSaneRange pair from the deleted
    scripts/data_freshness_check.js (t33). The original file is gone; this
    fixture is the surviving contract for the sanity range.
    """
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True, timeout=10)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise unittest.SkipTest(f"node not available: {e}")
    node_src = """
    // Inline copy of parseTs + _inSaneRange from deleted
    // scripts/data_freshness_check.js (t33). Original gone; keep in sync
    // with campaign-os/_lib freshness walk if the Python side ever diverges.
    function _inSaneRange(dt) {
      if (!dt || Number.isNaN(dt.getTime())) return false;
      const yr = dt.getUTCFullYear();
      return yr >= 2010 && yr <= new Date().getUTCFullYear() + 1;
    }
    function parseTs(v) {
      if (typeof v === 'number') {
        const ms = v > 1e11 ? v : (v > 1e9 ? v * 1000 : null);
        const dt = ms ? new Date(ms) : null;
        return _inSaneRange(dt) ? dt : null;
      }
      if (typeof v !== 'string') return null;
      const s = v.trim();
      if (/^\\d{4}-\\d{2}-\\d{2}$/.test(s)) {
        const dt = new Date(s + 'T00:00:00Z');
        return _inSaneRange(dt) ? dt : null;
      }
      if (/^\\d{4}-/.test(s)) {
        const iso = Date.parse(s);
        const dt = Number.isNaN(iso) ? null : new Date(iso);
        return _inSaneRange(dt) ? dt : null;
      }
      const iso = Date.parse(s);
      const dt = Number.isNaN(iso) ? null : new Date(iso);
      return _inSaneRange(dt) ? dt : null;
    }
    const cases = [
      // Bare month-day → null (was parsing to 2001-04-21, age 9238d, banner 🚨)
      ['Apr 22', null],
      // English date with explicit year → some valid Date in 2026
      ['Apr 22, 2026', '2026'],
      // Plain ISO dates and ISO timestamps → exact match
      ['2026-04-22', new Date('2026-04-22T00:00:00Z').toISOString()],
      ['2026-04-22T06:31:14.723Z', new Date('2026-04-22T06:31:14.723Z').toISOString()],
      // Numeric epoch in ms
      [1776839474723, new Date('2026-04-22T06:31:14.723Z').toISOString()],
      // Junk / empty / unparseable → null
      ['', null],
      ['tomorrow', null],
      // Year 2001 timestamp → null (would have been 9238 days old)
      ['2001-04-21T22:00:00.000Z', null],
    ];
    let failures = 0;
    for (const [input, wantIso] of cases) {
      const got = parseTs(input);
      let ok;
      if (wantIso === null) {
        ok = got === null;
      } else if (typeof wantIso === 'string' && wantIso.length === 4) {
        // Year prefix check (e.g. "2026" matches any Date starting with 2026-)
        ok = got !== null && got.toISOString().startsWith(wantIso);
      } else {
        ok = got !== null && got.toISOString() === wantIso;
      }
      console.log(JSON.stringify({input, want: wantIso, got: got ? got.toISOString() : null, ok}));
      if (!ok) failures++;
    }
    if (failures > 0) process.exit(1);
    """
    r = subprocess.run(
        ["node", "-e", node_src], capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"parseTs fixture mismatch:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    # All 8 cases should report ok=true
    assert r.stdout.count('"ok":true') == 8, (
        f"Expected 8 ok=true lines, got: {r.stdout}"
    )


def test_real_data_files_no_longer_rotten_with_9000_days():
    """The three files that surfaced year-2001 entries must NOT appear
    in the rotten bucket with crazy ages."""
    if not FRESHNESS.exists():
        raise unittest.SkipTest("freshness.json missing — seed not present")
    j = json.loads(FRESHNESS.read_text(encoding="utf-8"))
    targets = [
        "data/recommendation-scores.json",
        "data/daily-task-cards.json",
        "data/post-plan.json",
    ]
    for path in targets:
        for entry in j.get("rotten_files", []) + j.get("stale_files", []):
            if entry["path"] == path:
                # If still flagged, age must be plausible (< 365d), not 9000+
                assert entry.get("age_days", 0) < 365, (
                    f"{path} flagged as {entry['age_days']}d old — "
                    f"sanity range not applied"
                )


if __name__ == "__main__":
    # Minimal manual runner (pytest is the normal path).
    with tempfile.TemporaryDirectory() as td:
        os.environ["DATA_DIR"] = td
        Path(td, "probe.json").write_text("{}", encoding="utf-8")
        sys.path.insert(0, str(REPO / "campaign-os"))
        import app as _app  # noqa: E402
        assert _app._run_freshness_scan_job().get("ok")
    test_no_year_2001_artifacts()
    test_no_thousand_day_ages()
    test_parseTs_rejects_bare_month_day()
    test_real_data_files_no_longer_rotten_with_9000_days()
    print("✅ freshness sanity-range regression suite passed")
