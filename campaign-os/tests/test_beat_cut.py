"""beat_cut: cut a set of clips so scene changes land on the music's beats and drops.

Synthetic tracks stand in for real music: a soft hat on every beat, then at the
"drop" a kick with an accent on beat one of each bar plus a sustained bass.
120 BPM means a beat every 0.5 s and a bar every 2.0 s.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import beat_cut as B  # noqa: E402

SR = 22050
FPS = 30


def synth_track(bpm=120, seconds=20.0, drop_at=9.0, sr=SR):
    n = int(seconds * sr)
    x = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(1)
    beat = 60.0 / bpm
    t = np.arange(int(0.12 * sr)) / sr
    kick = (np.sin(2 * np.pi * 55 * t) * np.exp(-t * 28)).astype(np.float32)
    hat = (rng.standard_normal(int(0.03 * sr)) * np.exp(-np.arange(int(0.03 * sr)) / (0.006 * sr))).astype(np.float32)
    i = 0
    while i * beat < seconds - 0.2:
        s = int(i * beat * sr)
        x[s:s + len(hat)] += 0.15 * hat[: n - s][: len(hat)]
        if i * beat >= drop_at:
            amp = 1.0 if i % 4 == 0 else 0.6
            seg = kick[: n - s]
            x[s:s + len(seg)] += amp * seg
        i += 1
    d = int(drop_at * sr)
    tb = np.arange(n - d) / sr
    x[d:] += 0.25 * np.sin(2 * np.pi * 45 * tb).astype(np.float32)
    return x / max(1e-9, float(np.abs(x).max()))


def write_wav(path, x, sr=SR):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


class Analyse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = B.analyse(synth_track(), SR)

    def test_tempo_is_found(self):
        self.assertAlmostEqual(self.info.tempo, 120.0, delta=2.5)

    def test_beats_sit_on_the_grid(self):
        true = np.arange(0, 19.5, 0.5)
        miss = [min(abs(true - b)) for b in self.info.beats]
        self.assertGreater(len(self.info.beats), 30)
        self.assertLess(float(np.median(miss)), 0.04)
        self.assertLess(max(miss), 0.08)

    def test_downbeats_are_every_fourth_beat_on_the_kick_accent(self):
        for d in self.info.downbeats:
            self.assertLess(abs((d / 2.0) - round(d / 2.0)), 0.04, f"{d} is not a bar line")

    def test_the_drop_is_found_and_ranked_first(self):
        self.assertTrue(self.info.drops)
        self.assertAlmostEqual(self.info.drops[0], 9.0, delta=0.3)


class PlanCuts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = B.analyse(synth_track(), SR)

    def plan(self, **kw):
        base = dict(length=14.0, every="bar", min_shot=1.0, fps=FPS)
        base.update(kw)
        return B.plan_cuts(self.info, **base)

    def test_starts_at_zero_and_ends_at_length(self):
        cuts = self.plan()
        self.assertEqual(cuts[0], 0.0)
        self.assertAlmostEqual(cuts[-1], 14.0, delta=1 / FPS)

    def test_every_inner_cut_is_on_a_beat(self):
        for c in self.plan(every="beat")[1:-1]:
            self.assertLess(min(abs(self.info.beats - c)), 1.5 / FPS, f"{c} is off the beat")

    def test_shots_are_never_shorter_than_the_minimum(self):
        cuts = self.plan(every="beat", min_shot=1.4)
        self.assertGreaterEqual(min(np.diff(cuts)), 1.4 - 1 / FPS)

    def test_a_cut_lands_on_the_drop_even_when_it_is_not_a_bar_line(self):
        cuts = self.plan(every="bar")
        self.assertLess(min(abs(np.array(cuts) - 9.0)), 1.5 / FPS)

    def test_slower_cutting_gives_fewer_shots(self):
        self.assertLess(len(self.plan(every="2bars")), len(self.plan(every="beat")))

    def test_cuts_are_on_the_frame_grid(self):
        for c in self.plan(every="beat"):
            self.assertAlmostEqual(c * FPS, round(c * FPS), places=6)

    def test_start_offset_moves_the_window_into_the_track(self):
        cuts = self.plan(start=8.0, length=6.0)
        self.assertEqual(cuts[0], 0.0)
        self.assertLess(min(abs(np.array(cuts) - 1.0)), 1.5 / FPS)  # drop at 9.0 is 1.0 s in


class Assign(unittest.TestCase):
    def test_rotates_clips_and_matches_shot_lengths(self):
        segs = B.assign_segments([0, 2, 4, 6], [3.0, 5.0, 2.5])
        self.assertEqual([s.clip for s in segs], [0, 1, 2])
        self.assertEqual([round(s.dur, 3) for s in segs], [2.0, 2.0, 2.0])

    def test_never_runs_past_the_end_of_a_clip(self):
        segs = B.assign_segments([0, 2, 4, 6, 8, 10, 12], [6.0, 3.0])
        for s in segs:
            self.assertLessEqual(s.start + s.dur, [6.0, 3.0][s.clip] + 1e-6)

    def test_repeat_use_of_a_clip_moves_forward_so_shots_differ(self):
        segs = B.assign_segments([0, 2, 4, 6], [6.0])
        self.assertEqual([round(s.start, 3) for s in segs], [0.0, 2.0, 4.0, 0.0])

    def test_a_shot_longer_than_every_clip_is_an_error(self):
        with self.assertRaises(ValueError):
            B.assign_segments([0, 4], [2.0, 3.0])


class BuildCommand(unittest.TestCase):
    def cmd(self, **kw):
        segs = B.assign_segments([0, 2, 4], [5.0, 5.0])
        base = dict(clips=["a.mov", "b.mov"], segments=segs, music="m.mp3", out="o.mp4",
                    music_start=0.0, length=4.0, size=(1080, 1920), fps=FPS)
        base.update(kw)
        return B.build_command(**base)

    def graph(self, cmd):
        return cmd[cmd.index("-filter_complex") + 1]

    def test_one_trim_per_shot_and_one_concat(self):
        g = self.graph(self.cmd())
        self.assertEqual(g.count("trim=start="), 2)
        self.assertIn("concat=n=2:v=1:a=0", g)

    def test_frames_are_cropped_to_fill_the_target_size(self):
        g = self.graph(self.cmd(size=(1080, 1920)))
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase", g)
        self.assertIn("crop=1080:1920", g)

    def test_music_is_seeked_faded_and_the_output_is_trimmed(self):
        c = self.cmd(music_start=8.0)
        self.assertEqual(c[c.index("-ss") + 1], "8.000")
        self.assertIn("afade=t=out", self.graph(c))
        self.assertEqual(c[c.index("-t") + 1], "4.000")

    def test_output_is_h264_and_aac(self):
        c = self.cmd()
        self.assertEqual(c[c.index("-c:v") + 1], "libx264")
        self.assertEqual(c[c.index("-c:a") + 1], "aac")

    def test_output_cannot_overwrite_an_input(self):
        with self.assertRaises(ValueError):
            self.cmd(out="a.mov")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
class EndToEnd(unittest.TestCase):
    def test_makes_a_video_of_the_requested_length_with_audio(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_wav(d / "m.wav", synth_track(seconds=16.0, drop_at=5.0))
            clips = []
            for i, (colour, secs) in enumerate([("red", 5), ("blue", 6), ("green", 4)]):
                p = d / f"c{i}.mp4"
                subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=640x360:r=30:d={secs}",
                                "-pix_fmt", "yuv420p", str(p)], check=True, capture_output=True)
                clips.append(p)
            out = B.beat_cut(d / "m.wav", clips, d / "o.mp4", length=10.0, every="bar", size=(360, 640))
            self.assertAlmostEqual(B.probe_duration(out), 10.0, delta=0.2)
            streams = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                check=True, capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])


if __name__ == "__main__":
    unittest.main()
