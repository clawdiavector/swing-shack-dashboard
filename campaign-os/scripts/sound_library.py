#!/usr/bin/env python3
"""A folder of licensed tracks that rotates, so reels do not all share one sound.

Point add_sound.py or beat_cut.py at the folder instead of one file and they use the track
that was used longest ago, and remember it. Audio files stay in the folder (never in git).

    python3 campaign-os/scripts/sound_library.py list  "C:/Users/Juan/Music/free"
    python3 campaign-os/scripts/sound_library.py skip  "C:/Users/Juan/Music/free" track.mp3
    python3 campaign-os/scripts/sound_library.py unskip "C:/Users/Juan/Music/free" track.mp3
    python3 campaign-os/scripts/sound_library.py pick  "C:/Users/Juan/Music/free" --min-length 20

    python3 campaign-os/scripts/beat_cut.py "C:/Users/Juan/Music/free" a.mov b.mov -o reel.mp4

`list` shows each track's length, tempo and drop times (analysed once, then remembered).
`skip` takes a track out of rotation (vocals, wrong feel, a claim on it) without deleting it.

The remembered state lives in library.json inside the folder. Only licensed tracks belong here.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_sound import probe_duration  # noqa: E402

AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
INDEX = "library.json"


@dataclass
class Track:
    name: str
    path: Path
    duration: float


def _folder(folder) -> Path:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    return folder


def _load(folder: Path) -> dict:
    try:
        data = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("skip", [])
    data.setdefault("used", [])
    data.setdefault("analysis", {})
    return data


def _save(folder: Path, data: dict) -> None:
    (folder / INDEX).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _files(folder: Path) -> list:
    return sorted((p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in AUDIO and not p.name.startswith(".")),
                  key=lambda p: p.name.lower())


def scan(folder, duration_of=probe_duration) -> list:
    folder = _folder(folder)
    return [Track(p.name, p, float(duration_of(p))) for p in _files(folder)]


def pick(folder, min_length: float = 0.0, duration_of=probe_duration) -> Path:
    """The eligible track that was used longest ago (never used counts as longest). Records the choice."""
    folder = _folder(folder)
    tracks = scan(folder, duration_of)
    if not tracks:
        raise ValueError(f"no audio files in {folder}")
    data = _load(folder)
    live = [t for t in tracks if t.name not in data["skip"]]
    if not live:
        raise ValueError(f"every track in {folder} is skipped")
    fit = [t for t in live if t.duration >= min_length]
    if not fit:
        raise ValueError(f"no track in {folder} is long enough ({min_length:.0f}s needed)")
    last = {n: i for i, n in enumerate(data["used"])}
    chosen = min(fit, key=lambda t: (last.get(t.name, -1), t.name.lower()))
    data["used"] = (data["used"] + [chosen.name])[-200:]
    _save(folder, data)
    return chosen.path


def _set_skip(folder, name: str, on: bool) -> None:
    folder = _folder(folder)
    if name not in {p.name for p in _files(folder)}:
        raise ValueError(f"{name} is not in {folder}")
    data = _load(folder)
    data["skip"] = sorted(set(data["skip"]) | {name}) if on else [n for n in data["skip"] if n != name]
    _save(folder, data)


def skip(folder, name: str) -> None:
    _set_skip(folder, name, True)


def unskip(folder, name: str) -> None:
    _set_skip(folder, name, False)


def analyse_file(path) -> dict:
    import beat_cut as B
    info = B.analyse(B.load_audio(path), B.SR)
    return {"tempo": round(info.tempo, 1), "drops": [round(d, 1) for d in sorted(info.drops)]}


def describe(folder, analyse=analyse_file, duration_of=probe_duration) -> list:
    folder = _folder(folder)
    data = _load(folder)
    rows = []
    for t in scan(folder, duration_of):
        stamp = t.path.stat().st_size
        cached = data["analysis"].get(t.name)
        if not cached or cached.get("size") != stamp:
            cached = {"size": stamp, **analyse(t.path)}
            data["analysis"][t.name] = cached
        rows.append({"name": t.name, "duration": t.duration, "tempo": cached["tempo"],
                     "drops": cached["drops"], "skipped": t.name in data["skip"]})
    _save(folder, data)
    return rows


def resolve_music(arg, min_length: float = 0.0, duration_of=probe_duration) -> Path:
    """A file is used as given. A folder gives the next track in its rotation."""
    p = Path(arg)
    if p.is_dir():
        chosen = pick(p, min_length, duration_of)
        print(f"music from library: {chosen.name}", file=sys.stderr)
        return chosen
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "pick"):
        sp = sub.add_parser(name)
        sp.add_argument("folder")
        if name == "pick":
            sp.add_argument("--min-length", type=float, default=0.0)
    for name in ("skip", "unskip"):
        sp = sub.add_parser(name)
        sp.add_argument("folder")
        sp.add_argument("track")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            for r in describe(a.folder):
                m, s = divmod(int(r["duration"]), 60)
                drops = ", ".join(f"{d:.0f}s" for d in r["drops"]) or "none"
                print(f"{'SKIP ' if r['skipped'] else '     '}{r['name']:<58} {m}:{s:02d}  {r['tempo']:>5.1f} BPM  drops: {drops}")
        elif a.cmd == "pick":
            print(pick(a.folder, a.min_length))
        else:
            (skip if a.cmd == "skip" else unskip)(a.folder, a.track)
            print(f"{'skipped' if a.cmd == 'skip' else 'restored'} {a.track}")
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
