#!/usr/bin/env python3
"""Tests for refit_format_model.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent.parent
SCRIPT = ROOT / "scripts" / "refit_format_model.py"
DATA = ROOT / "data"


def test_script_imports():
    import importlib.util
    spec = importlib.util.spec_from_file_location("refit_format_model", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "classify_format")
    assert hasattr(mod, "load_json")
    print("PASS test_script_imports")


def test_classify_format():
    import importlib.util
    spec = importlib.util.spec_from_file_location("refit_format_model", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.classify_format("VIDEO") == "reel"
    assert mod.classify_format("REEL") == "reel"
    assert mod.classify_format("video") == "reel"
    assert mod.classify_format("IMAGE") == "image"
    assert mod.classify_format("image") == "image"
    assert mod.classify_format("CAROUSEL_ALBUM") == "carousel"
    assert mod.classify_format("garbage") == "other"
    print("PASS test_classify_format")


def test_runs_clean_with_real_data():
    if not (DATA / "post-conversion-score.json").exists():
        print("SKIP test_runs_clean_with_real_data (no real data file)")
        return
    if not (DATA / "ig-business-analytics.json").exists():
        print("SKIP test_runs_clean_with_real_data (no ig data file)")
        return

    out_path = DATA / "format-model-refit.json"
    backup = None
    if out_path.exists():
        backup = out_path.read_bytes()
        out_path.unlink()

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT),
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert out_path.exists(), "Output file not created"

        with open(out_path) as f:
            out = json.load(f)

        for key in ["schema", "generated_at", "scoring", "format_stats",
                    "old_format_avg_scores", "new_format_avg_scores",
                    "old_winning_format", "new_winning_format",
                    "format_flip", "verdict", "rank_movers", "posts"]:
            assert key in out, f"Missing key: {key}"

        assert "new_formula" in out["scoring"]
        assert "format_multipliers" in out["scoring"]
        assert out["scoring"]["median_conversion_efficiency"] >= 0

        posts = out["posts"]
        for i in range(len(posts) - 1):
            assert posts[i]["new_normalized"] >= posts[i + 1]["new_normalized"], \
                f"Posts not sorted at index {i}"

        assert len(out["verdict"]) > 0

        has_flip_message = any("FORMAT FLIP" in line for line in out["verdict"])
        assert out["format_flip"] == has_flip_message

        print(f"PASS test_runs_clean_with_real_data ({len(posts)} posts refit, "
              f"{out['old_winning_format']} -> {out['new_winning_format']})")
    finally:
        if backup is not None:
            out_path.write_bytes(backup)


def test_format_multiplier_computation():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "scoring_formula": "old",
            "posts_ranked": [
                {"post_id": "a", "media_type": "IMAGE", "reach": 100, "time_window_sessions": 10,
                 "direct_attributed_sessions": 0, "themes": ["a"], "is_winning_theme_combo": False,
                 "engagement_rate_pct": 1.0, "normalized_score": 50.0},
                {"post_id": "b", "media_type": "IMAGE", "reach": 100, "time_window_sessions": 10,
                 "direct_attributed_sessions": 0, "themes": ["a"], "is_winning_theme_combo": False,
                 "engagement_rate_pct": 1.0, "normalized_score": 50.0},
                {"post_id": "c", "media_type": "VIDEO", "reach": 300, "time_window_sessions": 5,
                 "direct_attributed_sessions": 0, "themes": ["a"], "is_winning_theme_combo": False,
                 "engagement_rate_pct": 1.0, "normalized_score": 50.0},
                {"post_id": "d", "media_type": "VIDEO", "reach": 300, "time_window_sessions": 5,
                 "direct_attributed_sessions": 0, "themes": ["a"], "is_winning_theme_combo": False,
                 "engagement_rate_pct": 1.0, "normalized_score": 50.0},
            ],
        }, f)
        pcs_path = f.name

    ig_data = {
        "media": [
            {"id": "a", "media_type": "IMAGE", "metrics": {"reach": 100}},
            {"id": "b", "media_type": "IMAGE", "metrics": {"reach": 100}},
            {"id": "c", "media_type": "VIDEO", "metrics": {"reach": 300}},
            {"id": "d", "media_type": "VIDEO", "metrics": {"reach": 300}},
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(ig_data, f)
        ig_path = f.name

    out_path = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("refit_format_model", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with patch.object(mod, "PCS_FILE", Path(pcs_path)), \
             patch.object(mod, "IG_FILE", Path(ig_path)), \
             patch.object(mod, "OUT_FILE", Path(tempfile.mktemp(suffix=".json"))):
            mod.main()
            out_path = str(mod.OUT_FILE)

        with open(out_path) as f:
            out = json.load(f)

        mults = out["scoring"]["format_multipliers"]
        assert "image" in mults
        assert "reel" in mults
        assert mults["reel"] < mults["image"]
        ratio = mults["image"] / mults["reel"]
        assert ratio > 5.0, f"image:reel ratio should be >5, got {ratio:.2f}"

        print(f"PASS test_format_multiplier_computation (image mult={mults['image']:.2f}, "
              f"reel mult={mults['reel']:.2f}, ratio={ratio:.2f}x)")
    finally:
        os.unlink(pcs_path)
        os.unlink(ig_path)
        if out_path and os.path.exists(out_path):
            os.unlink(out_path)


def test_handles_zero_reach():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "scoring_formula": "old",
            "posts_ranked": [
                {"post_id": "a", "media_type": "IMAGE", "reach": 0, "time_window_sessions": 5,
                 "direct_attributed_sessions": 0, "themes": [], "is_winning_theme_combo": False,
                 "engagement_rate_pct": 0, "normalized_score": 0.0},
            ],
        }, f)
        pcs_path = f.name
    ig_path = None
    out_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"media": []}, f)
            ig_path = f.name

        import importlib.util
        spec = importlib.util.spec_from_file_location("refit_format_model", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        out_temp = tempfile.mktemp(suffix=".json")
        with patch.object(mod, "PCS_FILE", Path(pcs_path)), \
             patch.object(mod, "IG_FILE", Path(ig_path)), \
             patch.object(mod, "OUT_FILE", Path(out_temp)):
            mod.main()
            out_path = out_temp

        with open(out_path) as f:
            out = json.load(f)

        assert "posts" in out
        assert len(out["posts"]) == 1
        assert out["posts"][0]["conversion_efficiency"] == 0.0

        print("PASS test_handles_zero_reach")
    finally:
        os.unlink(pcs_path)
        if ig_path and os.path.exists(ig_path):
            os.unlink(ig_path)
        if out_path and os.path.exists(out_path):
            os.unlink(out_path)


def main():
    tests = [
        test_script_imports,
        test_classify_format,
        test_runs_clean_with_real_data,
        test_format_multiplier_computation,
        test_handles_zero_reach,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
