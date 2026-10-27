#!/usr/bin/env python3
"""Lay licensed music and sound effects under a finished video. One command, free.

Use tracks you have a licence for (Epidemic Sound, Artlist, Meta Sound Collection).
This does not generate audio.

    python3 campaign-os/scripts/add_sound.py clip.mp4 track.mp3
    python3 campaign-os/scripts/add_sound.py clip.mp4 track.mp3 -o clip-sound.mp4 --volume 0.2
    python3 campaign-os/scripts/add_sound.py clip.mp4 track.mp3 --speech
    python3 campaign-os/scripts/add_sound.py clip.mp4 track.mp3 --sfx hit.wav@2.5 --sfx whoosh.wav@0

What it does:
    - loops the track if the video is longer, trims it to the video length
    - fades the music in and out
    - --speech keeps the video's own audio and dips the music under it
      (without it the video's own audio is dropped)
    - --sfx FILE@SECONDS drops a sound effect in at that time, as many as you like
    - sets the final loudness to about -14 LUFS, where Instagram and TikTok sit
    - copies the video untouched, so there is no quality loss

Needs ffmpeg and ffprobe on PATH. The output is a new file; the input is never changed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_VOLUME = 0.25
DEFAULT_FADE = 1.0
TARGET_LUFS = -14


def parse_sfx(spec: str) -> tuple[str, float]:
    """'hit.wav@2.5' -> ('hit.wav', 2.5). Split on the last @ so paths stay whole."""
    path, sep, secs = spec.rpartition("@")
    if not sep or not path:
        raise ValueError(f"--sfx needs FILE@SECONDS, got {spec!r}")
    try:
        return path, float(secs)
    except ValueError:
        raise ValueError(f"--sfx time must be a number of seconds, got {secs!r}") from None


def probe_duration(path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def build_command(video, music, out, duration, *, sfx=None, speech=False,
                  music_volume=DEFAULT_VOLUME, fade=DEFAULT_FADE) -> list[str]:
    sfx = list(sfx or [])
    if str(out) == str(video):
        raise ValueError("output must be a different file from the input video")
    if duration <= 0:
        raise ValueError("video duration must be above zero")
    if not 0 < music_volume <= 2:
        raise ValueError("music volume must be above 0 and at most 2")
    if fade < 0:
        raise ValueError("fade cannot be negative")
    if any(t < 0 for _, t in sfx):
        raise ValueError("sfx times cannot be negative")

    fade = min(fade, duration / 2)
    steps = [
        f"atrim=0:{duration:.3f}",
        f"afade=t=in:d={fade:.3f}",
        f"afade=t=out:st={duration - fade:.3f}:d={fade:.3f}",
        f"volume={music_volume:.2f}",
    ]
    graph = ["[1:a]" + ",".join(steps) + "[m]"]
    # Input 0 is the video, 1 the music, 2.. the effects.
    mix, n = [], 0
    if speech:
        graph.append("[0:a]asplit[sc][orig]")
        graph.append("[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        mix += ["[orig]", "[duck]"]
    else:
        mix.append("[m]")
    for i, (_, t) in enumerate(sfx):
        ms = round(t * 1000)
        graph.append(f"[{i + 2}:a]adelay={ms}|{ms}[s{i}]")
        mix.append(f"[s{i}]")
    n = len(mix)
    if n == 1:
        graph.append(f"{mix[0]}loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11[aout]")
    else:
        graph.append(f"{''.join(mix)}amix=inputs={n}:duration=first:normalize=0,"
                     f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11[aout]")

    cmd = ["ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(music)]
    for path, _ in sfx:
        cmd += ["-i", str(path)]
    cmd += ["-filter_complex", ";".join(graph), "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", str(out)]
    return cmd


def add_sound(video, music, out=None, *, sfx=None, speech=False,
              music_volume=DEFAULT_VOLUME, fade=DEFAULT_FADE) -> Path:
    video, music = Path(video), Path(music)
    out = Path(out) if out else video.with_name(video.stem + "-sound.mp4")
    for p in [video, music] + [Path(s) for s, _ in (sfx or [])]:
        if not p.exists():
            raise FileNotFoundError(p)
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise RuntimeError("ffmpeg and ffprobe are not on PATH. Install ffmpeg first.")
    cmd = build_command(video, music, out, probe_duration(video), sfx=sfx, speech=speech,
                        music_volume=music_volume, fade=fade)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + r.stderr[-1500:])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("music")
    ap.add_argument("-o", "--out", help="output file (default: <video>-sound.mp4)")
    ap.add_argument("--volume", type=float, default=DEFAULT_VOLUME, help="music level before loudness, default 0.25")
    ap.add_argument("--fade", type=float, default=DEFAULT_FADE, help="fade in/out seconds, default 1")
    ap.add_argument("--speech", action="store_true", help="keep the video's audio and duck music under it")
    ap.add_argument("--sfx", action="append", default=[], metavar="FILE@SECONDS")
    a = ap.parse_args(argv)
    try:
        out = add_sound(a.video, a.music, a.out, sfx=[parse_sfx(s) for s in a.sfx],
                        speech=a.speech, music_volume=a.volume, fade=a.fade)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
