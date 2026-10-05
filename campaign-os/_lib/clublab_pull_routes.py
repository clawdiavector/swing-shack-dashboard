"""Flask routes for ClubLab pull lab page and snapshot API."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from _lib.jobs.layer2 import clublab_pull

CAMPAIGN_OS_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_NAME = clublab_pull.SNAPSHOT_NAME
META_NAME = clublab_pull.META_NAME


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _snapshot_path() -> Path:
    return _data_dir() / SNAPSHOT_NAME


def _meta_path() -> Path:
    return _data_dir() / META_NAME


def _job_token_ok() -> bool:
    token = os.environ.get("COS_JOB_TOKEN", "")
    if not token:
        return False
    auth = request.headers.get("Authorization", "")
    return auth.startswith("Bearer ") and auth[len("Bearer ") :] == token


def register_routes(app) -> None:
    bp = Blueprint("clublab_pull", __name__)

    @bp.route("/clublab-pull", methods=["GET"])
    def clublab_pull_page():
        return send_from_directory(str(CAMPAIGN_OS_DIR), "clublab-pull.html")

    @bp.route("/api/clublab-snapshot", methods=["GET"])
    def clublab_snapshot_api():
        path = _snapshot_path()
        if not path.is_file():
            return jsonify({"ok": False, "error": "snapshot missing", "schema": clublab_pull.SCHEMA}), 404
        with path.open(encoding="utf-8") as fh:
            doc = json.load(fh)
        meta_path = _meta_path()
        meta = {}
        if meta_path.is_file():
            with meta_path.open(encoding="utf-8") as fh:
                meta = json.load(fh)
        return jsonify({"ok": True, "snapshot": doc, "meta": meta})

    @bp.route("/api/clublab-pull/run", methods=["POST"])
    def clublab_pull_run():
        if not _job_token_ok():
            try:
                from app import _is_authed  # noqa: PLC0415

                if not _is_authed():
                    return jsonify({"ok": False, "error": "authentication required"}), 401
            except Exception:  # noqa: BLE001
                return jsonify({"ok": False, "error": "authentication required"}), 401
        result = clublab_pull.run()
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    app.register_blueprint(bp)
