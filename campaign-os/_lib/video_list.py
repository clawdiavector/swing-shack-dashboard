"""video_list.py — the brand's videos in Drive, by stage, with their captions.

Drive layout (see the Drive system doc):

    Video/1-raw/                 date__topic__what__nn.mp4
    Video/2-ready-to-publish/    date__topic__format__v1.mp4  +  date__topic__format__v1.txt (caption)
    Video/3-published/           moved here once live

The folder a file sits in is its status. This module only reads: it takes a public Drive listing
(from google_drive.list_public_folder) and returns the videos grouped by stage, each with the
parts of its name and the caption from the same-named .txt. Nothing is written to Drive.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".webm"}
STAGES = (
    ("1-raw", "Raw"),
    ("2-ready-to-publish", "Ready to publish"),
    ("3-published", "Published"),
)
FORMATS = ("reel-9x16", "story-9x16", "feed-4x5", "square-1x1")
_DATE = re.compile(r"^20\d{2}-[01]\d-[0-3]\d$")
_VERSION = re.compile(r"^v\d+$")
_NUMBER = re.compile(r"^\d{2}$")
MAX_CAPTION_CHARS = 4000


def stage_of(folder: str) -> Optional[str]:
    """'Video/2-ready-to-publish' -> '2-ready-to-publish'. None for anything outside the video stages."""
    parts = (folder or "").strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "Video" and parts[1] in {s for s, _ in STAGES}:
        return parts[1]
    return None


def parse_name(name: str) -> Dict[str, Any]:
    """The parts of a video name, and whether it follows the naming rules."""
    stem = Path(name).stem
    parts = stem.split("__")
    out: Dict[str, Any] = {"date": None, "topic": None, "what": None, "format": None,
                           "version": None, "number": None, "follows_rules": False}
    if len(parts) != 4 or not _DATE.match(parts[0]):
        return out
    out["date"], out["topic"] = parts[0], parts[1]
    last = parts[3]
    if _VERSION.match(last) and parts[2] in FORMATS:
        out["format"], out["version"], out["follows_rules"] = parts[2], last, True
    elif _NUMBER.match(last):
        out["what"], out["number"], out["follows_rules"] = parts[2], last, True
    return out


def build(entries: List[Dict[str, Any]], read_text: Callable[[str], Optional[str]]) -> Dict[str, Any]:
    """Group a Drive listing into the three stages. read_text(file_id) returns a caption file's text."""
    captions: Dict[tuple, Dict[str, Any]] = {}
    for e in entries:
        stage = stage_of(e.get("folder", ""))
        if stage and Path(e["name"]).suffix.lower() == ".txt":
            captions[(stage, Path(e["name"]).stem)] = e
    stages = []
    for key, label in STAGES:
        videos = []
        for e in sorted(entries, key=lambda x: x["name"]):
            if stage_of(e.get("folder", "")) != key or Path(e["name"]).suffix.lower() not in VIDEO_EXT:
                continue
            cap = captions.get((key, Path(e["name"]).stem))
            text = None
            if cap is not None and key != "1-raw":
                text = (read_text(cap["id"]) or "")[:MAX_CAPTION_CHARS] or None
            videos.append({
                "name": e["name"], "id": e["id"],
                "url": f"https://drive.google.com/file/d/{e['id']}/view",
                "parsed": parse_name(e["name"]),
                "has_caption_file": cap is not None,
                "caption_file_id": cap["id"] if cap is not None else None,
                "caption_url": f"https://drive.google.com/file/d/{cap['id']}/view" if cap is not None else None,
                "caption": text,
            })
        stages.append({"stage": key, "label": label, "videos": videos})
    return {"stages": stages}
