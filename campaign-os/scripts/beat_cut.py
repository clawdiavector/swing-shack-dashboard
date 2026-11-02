#!/usr/bin/env python3
"""Cut a set of clips to a track so scene changes land on its beats and drops. Free, no model.

    python3 campaign-os/scripts/beat_cut.py track.mp3 a.mov b.mov c.mov -o reel.mp4
    python3 campaign-os/scripts/beat_cut.py track.mp3 a.mov b.mov --length 15 --start 42 --cut 2beats
    python3 campaign-os/scripts/beat_cut.py track.mp3 --info          # tempo, bar lines, drops; no video

What it does:
    - finds the tempo, the beat grid, the bar lines and the "drops" (where the bass comes back)
    - puts a scene change on every bar (default), or --cut beat / 2beats / bar / 2bars
    - always puts a scene change on a drop, so the picture hits when the music does
    - rotates through your clips, taking a different stretch each time a clip comes round again
    - crops every shot to fill 1080x1920 (--size 1080x1350 for 4:5, 1920x1080 for wide)
    - fades the music in and out and sets the loudness to about -14 LUFS

A shot is never shorter than --min-shot (default 1 s) and never longer than its clip.

Tempo is found by listening for repeated hits, and the bar line is a best guess from where the
bass is strongest. If it picks double or half the tempo, pass --bpm. If the bar lines feel off,
use --cut beat or 2beats. Run with --info first and pick --start so a drop lands where you want.

This cuts video. It does not generate or alter any picture. Needs ffmpeg and ffprobe on PATH,
plus numpy and scipy. The output is a new file; the inputs are never changed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, uniform_filter1d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_sound import TARGET_LUFS, probe_duration  # noqa: E402,F401

SR = 22050
N_FFT = 1024
HOP = 256
LOW_HZ = 150.0
EVERY = {"beat": 1, "2beats": 2, "bar": 4, "2bars": 8}


@dataclass
class BeatInfo:
    tempo: float
    beats: np.ndarray
    downbeats: np.ndarray
    drops: list = field(default_factory=list)
    duration: float = 0.0


@dataclass
class Segment:
    clip: int
    start: float
    dur: float


def load_audio(path, sr: int = SR) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def _spectrogram(x: np.ndarray, sr: int):
    """Magnitude spectrogram, one row per frame. Frame i is centred on (i * HOP + N_FFT / 2) / sr."""
    if len(x) < N_FFT * 2:
        raise ValueError("track is too short to analyse")
    win = np.hanning(N_FFT).astype(np.float32)
    view = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP]
    out = np.empty((len(view), N_FFT // 2 + 1), dtype=np.float32)
    for i in range(0, len(view), 2000):
        out[i:i + 2000] = np.abs(np.fft.rfft(view[i:i + 2000] * win, axis=1))
    return out


def _norm(v: np.ndarray) -> np.ndarray:
    top = np.percentile(v, 99)
    return v / top if top > 0 else v


def analyse(x: np.ndarray, sr: int = SR, bpm: float | None = None) -> BeatInfo:
    mag = _spectrogram(x, sr)
    fps = sr / HOP
    centre = (np.arange(len(mag)) * HOP + N_FFT / 2) / sr
    n_low = max(2, int(LOW_HZ / (sr / N_FFT)))

    rise = np.clip(np.diff(np.log1p(mag * 10), axis=0, prepend=np.log1p(mag[:1] * 10)), 0, None)
    onset = 0.5 * _norm(rise.mean(axis=1)) + _norm(rise[:, :n_low].mean(axis=1))
    onset = np.clip(onset - uniform_filter1d(onset, max(3, int(0.5 * fps))), 0, None)
    env = gaussian_filter1d(onset, 1.0)

    # Coarse tempo: autocorrelation of the onset curve, nudged toward 120 BPM.
    e = onset - onset.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(e, 2 * len(e))) ** 2)[: len(e)]
    if bpm:
        coarse = float(bpm)
    else:
        bpms = np.arange(60.0, 200.0, 0.5)
        lags = np.round(60.0 / bpms * fps).astype(int)
        score = ac[lags] * np.exp(-0.5 * np.log2(bpms / 120.0) ** 2)
        coarse = float(bpms[int(np.argmax(score))])

    # Fine tempo and phase: slide a comb of beats over the onset curve and keep the best fit.
    duration = len(x) / sr
    best = (-1.0, 60.0 / coarse, 0.0)
    for p in (60.0 / coarse) * np.arange(0.93, 1.07, 0.001):
        phases = np.arange(0.0, p, 0.004)
        k = np.arange(0, int(duration / p) + 1)
        t = phases[:, None] + k[None, :] * p
        s = np.interp(t, centre, env, right=0.0).sum(axis=1)
        j = int(np.argmax(s))
        if s[j] > best[0]:
            best = (float(s[j]), float(p), float(phases[j]))
    _, period, phase = best
    beats = np.arange(phase, duration - 0.05, period)

    # Bar line: the one beat in four with the heaviest bass.
    low = mag[:, :n_low].mean(axis=1)
    strength = np.array([low[(centre >= b - 0.02) & (centre <= b + 0.08)].max(initial=0.0) for b in beats])
    cls = np.arange(len(beats)) % 4
    first = int(np.argmax([strength[cls == c].mean() if (cls == c).any() else 0.0 for c in range(4)]))
    downbeats = beats[cls == first]

    return BeatInfo(tempo=60.0 / period, beats=beats, downbeats=downbeats,
                    drops=_find_drops(low, centre, beats, period), duration=duration)


def _find_drops(low: np.ndarray, centre: np.ndarray, beats: np.ndarray, period: float) -> list:
    """Beats where the bass level jumps up compared with the bar before: breakdown into drop."""
    if len(beats) < 8:
        return []
    low = uniform_filter1d(low, 5)
    win = 4 * period
    scored = []
    for b in beats:
        if b < 2 * period or b + 2 * period > centre[-1]:
            continue
        before = low[(centre >= b - win) & (centre < b)].mean()
        after = low[(centre >= b) & (centre < b + win)].mean()
        scored.append((after - before, float(b)))
    floor = 0.6 * float(low.mean())
    drops: list = []
    for diff, b in sorted(scored, reverse=True):
        if diff < floor:
            break
        if all(abs(b - d) >= win for d in drops):
            drops.append(b)
        if len(drops) >= 8:
            break
    return drops


def _snap(t: float, fps: int) -> float:
    return round(t * fps) / fps


def plan_cuts(info: BeatInfo, length: float, every: str = "bar", min_shot: float = 1.0,
              fps: int = 30, start: float = 0.0) -> list:
    """Cut times in seconds from the start of the video: 0, scene changes on beats, then the end."""
    if every not in EVERY:
        raise ValueError(f"--cut must be one of {', '.join(EVERY)}")
    if length <= 0 or min_shot <= 0:
        raise ValueError("length and min shot must be above zero")
    end = _snap(length, fps)

    beats = np.asarray(info.beats)
    step = EVERY[every]
    d0 = 0
    if len(info.downbeats):
        d0 = int(np.argmin(np.abs(beats - info.downbeats[0])))
    picked = beats[(np.arange(len(beats)) - d0) % step == 0]

    def inside(ts):
        return sorted({_snap(float(t) - start, fps) for t in ts if 0 < float(t) - start < length})

    accepted: list = []
    ok = lambda t: abs(t - 0.0) >= min_shot - 1e-9 and end - t >= min_shot - 1e-9 \
        and all(abs(t - a) >= min_shot - 1e-9 for a in accepted)
    for t in inside(info.drops):          # drops first: they are the ones that must hit
        if ok(t):
            accepted.append(t)
    for t in inside(picked):
        if ok(t):
            accepted.append(t)
    return [0.0] + sorted(accepted) + [end]


def assign_segments(cuts, clip_durations) -> list:
    """Give each shot a clip and an in-point. Clips rotate; a reused clip moves on so shots differ."""
    n = len(clip_durations)
    cursor = [0.0] * n
    segs: list = []
    prev = -1
    eps = 1e-6
    for a, b in zip(cuts[:-1], cuts[1:]):
        dur = b - a
        order = [(prev + 1 + i) % n for i in range(n)]
        pick = next((c for c in order if cursor[c] + dur <= clip_durations[c] + eps), None)
        if pick is not None:
            start = cursor[pick]
        else:
            pick = next((c for c in order if dur <= clip_durations[c] + eps), None)
            if pick is None:
                raise ValueError(f"a {dur:.2f}s shot is longer than every clip; use a faster --cut or longer clips")
            start = 0.0
        cursor[pick] = start + dur
        segs.append(Segment(pick, start, dur))
        prev = pick
    return segs


def build_command(clips, segments, music, out, music_start, length, size=(1080, 1920), fps=30) -> list:
    if str(out) in {str(c) for c in clips} or str(out) == str(music):
        raise ValueError("output must be a different file from every input")
    w, h = size
    graph = []
    for i, s in enumerate(segments):
        graph.append(f"[{s.clip}:v]trim=start={s.start:.3f}:duration={s.dur:.3f},setpts=PTS-STARTPTS,fps={fps},"
                     f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p[v{i}]")
    graph.append("".join(f"[v{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0[vout]")
    fade = min(1.2, length / 2)
    graph.append(f"[{len(clips)}:a]atrim=0:{length:.3f},afade=t=in:d=0.300,"
                 f"afade=t=out:st={length - fade:.3f}:d={fade:.3f},loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11[aout]")
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-ss", f"{music_start:.3f}", "-i", str(music), "-filter_complex", ";".join(graph),
            "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-t", f"{length:.3f}",
            "-movflags", "+faststart", str(out)]
    return cmd


def beat_cut(music, clips, out, *, length=15.0, start=0.0, every="bar", min_shot=1.0,
             size=(1080, 1920), fps=30, bpm=None) -> Path:
    from sound_library import resolve_music  # a folder of tracks rotates; a file is used as given
    music, clips, out = resolve_music(music, min_length=start + length), [Path(c) for c in clips], Path(out)
    for p in [music] + clips:
        if not p.exists():
            raise FileNotFoundError(p)
    if not clips:
        raise ValueError("give at least one clip")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise RuntimeError("ffmpeg and ffprobe are not on PATH. Install ffmpeg first.")
    info = analyse(load_audio(music), SR, bpm=bpm)
    if start + length > info.duration + 0.05:
        raise ValueError(f"the track is {info.duration:.1f}s: --start {start} plus --length {length} runs past the end")
    cuts = plan_cuts(info, length, every=every, min_shot=min_shot, fps=fps, start=start)
    segs = assign_segments(cuts, [probe_duration(c) for c in clips])
    r = subprocess.run(build_command(clips, segs, music, out, start, cuts[-1], size, fps),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + r.stderr[-1500:])
    return out


def _size(text: str):
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("size looks like 1080x1920") from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("music")
    ap.add_argument("clips", nargs="*")
    ap.add_argument("-o", "--out", help="output file (default: reel-beat.mp4 beside the first clip)")
    ap.add_argument("--length", type=float, default=15.0, help="video length in seconds, default 15")
    ap.add_argument("--start", type=float, default=0.0, help="start this many seconds into the track")
    ap.add_argument("--cut", choices=list(EVERY), default="bar", help="how often to change scene, default bar")
    ap.add_argument("--min-shot", type=float, default=1.0, help="shortest shot in seconds, default 1")
    ap.add_argument("--size", type=_size, default=(1080, 1920), help="default 1080x1920")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--bpm", type=float, help="force the tempo if it picked double or half")
    ap.add_argument("--info", action="store_true", help="only print the tempo, bar lines and drops")
    a = ap.parse_args(argv)
    try:
        if a.info or not a.clips:
            if Path(a.music).is_dir():
                raise ValueError("--info needs one track. For a folder, run sound_library.py list FOLDER")
            info = analyse(load_audio(a.music), SR, bpm=a.bpm)
            print(f"track {info.duration:.1f}s  tempo {info.tempo:.1f} BPM  beats {len(info.beats)}  bars {len(info.downbeats)}")
            print("drops at: " + (", ".join(f"{d:.1f}s" for d in sorted(info.drops)) or "none found"))
            return 0
        out = a.out or str(Path(a.clips[0]).with_name("reel-beat.mp4"))
        print(beat_cut(a.music, a.clips, out, length=a.length, start=a.start, every=a.cut,
                       min_shot=a.min_shot, size=a.size, fps=a.fps, bpm=a.bpm))
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
