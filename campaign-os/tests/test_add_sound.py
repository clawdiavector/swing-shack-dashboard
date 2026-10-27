"""add_sound: lay licensed music and sound effects under a finished video.

The script builds one ffmpeg command. These tests pin the command it builds
(no ffmpeg needed) and, when ffmpeg is installed, run it on a generated clip.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import add_sound as A  # noqa: E402


def _graph(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


class BuildCommand(unittest.TestCase):
    def build(self, **kw):
        base = dict(video="in.mp4", music="track.mp3", out="out.mp4", duration=20.0)
        base.update(kw)
        return A.build_command(**base)

    def test_video_is_copied_not_reencoded(self):
        cmd = self.build()
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")

    def test_music_loops_so_a_short_track_covers_a_long_video(self):
        cmd = self.build()
        i = cmd.index("track.mp3")
        self.assertEqual(cmd[i - 3 : i], ["-stream_loop", "-1", "-i"])

    def test_output_is_trimmed_to_the_video_length(self):
        cmd = self.build(duration=20.0)
        self.assertEqual(cmd[cmd.index("-t") + 1], "20.000")

    def test_music_fades_in_and_out_at_the_end(self):
        g = _graph(self.build(duration=20.0, fade=1.5))
        self.assertIn("afade=t=in:d=1.500", g)
        self.assertIn("afade=t=out:st=18.500:d=1.500", g)

    def test_fade_never_exceeds_half_the_video(self):
        g = _graph(self.build(duration=2.0, fade=3.0))
        self.assertIn("afade=t=in:d=1.000", g)
        self.assertIn("afade=t=out:st=1.000:d=1.000", g)

    def test_loudness_is_normalised_for_social(self):
        self.assertIn("loudnorm=I=-14", _graph(self.build()))

    def test_music_volume_is_applied(self):
        self.assertIn("volume=0.30", _graph(self.build(music_volume=0.3)))

    def test_no_speech_means_no_ducking_and_original_audio_dropped(self):
        g = _graph(self.build(speech=False))
        self.assertNotIn("sidechaincompress", g)
        self.assertNotIn("0:a", g)

    def test_speech_keeps_original_audio_and_ducks_music_under_it(self):
        g = _graph(self.build(speech=True))
        self.assertIn("sidechaincompress", g)
        self.assertIn("[0:a]", g)

    def test_sfx_is_delayed_to_its_timestamp(self):
        g = _graph(self.build(sfx=[("hit.wav", 2.5), ("whoosh.wav", 0.0)]))
        self.assertIn("adelay=2500|2500", g)
        self.assertIn("adelay=0|0", g)

    def test_sfx_inputs_follow_music_input(self):
        cmd = self.build(sfx=[("hit.wav", 2.5)])
        self.assertLess(cmd.index("track.mp3"), cmd.index("hit.wav"))

    def test_output_cannot_overwrite_the_input(self):
        with self.assertRaises(ValueError):
            self.build(out="in.mp4")

    def test_bad_values_are_refused(self):
        for kw in ({"duration": 0}, {"music_volume": 0}, {"music_volume": 2.5},
                   {"fade": -1}, {"sfx": [("hit.wav", -1)]}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.build(**kw)


class ParseSfx(unittest.TestCase):
    def test_file_at_seconds(self):
        self.assertEqual(A.parse_sfx("hit.wav@2.5"), ("hit.wav", 2.5))

    def test_windows_path_keeps_its_drive_colon(self):
        self.assertEqual(A.parse_sfx(r"C:\sfx\hit.wav@1"), (r"C:\sfx\hit.wav", 1.0))

    def test_missing_time_is_an_error(self):
        with self.assertRaises(ValueError):
            A.parse_sfx("hit.wav")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
class EndToEnd(unittest.TestCase):
    def test_adds_an_audio_stream_of_the_right_length(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video, music, out = d / "v.mp4", d / "m.wav", d / "o.mp4"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=4",
                            "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=440:d=1", str(music)],
                           check=True, capture_output=True)
            A.add_sound(video, music, out)
            streams = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                check=True, capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])
            self.assertAlmostEqual(A.probe_duration(out), 4.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
