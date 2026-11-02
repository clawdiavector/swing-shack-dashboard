"""asset_qc must not QC job state files that live next to the sidecars (2026-11-02 fleet tick:
draft-assets/_image-jobs.json failed QC as "invalid brand_id")."""

from __future__ import annotations

import json


def test_load_sidecars_skips_underscore_files(tmp_path, monkeypatch):
    from _lib.jobs.layer5 import asset_qc

    root = tmp_path / "draft-assets"
    root.mkdir()
    (root / "_image-jobs.json").write_text(json.dumps({"jobs": {}}), encoding="utf-8")
    (root / "asset-1.json").write_text(json.dumps({"asset_id": "asset-1"}), encoding="utf-8")
    monkeypatch.setattr(asset_qc, "_data_dir", lambda: tmp_path)
    names = [p.name for p, _ in asset_qc._load_sidecars()]
    assert names == ["asset-1.json"]
