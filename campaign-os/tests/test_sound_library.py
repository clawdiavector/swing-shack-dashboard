"""sound_library: a folder of licensed tracks that rotates, so reels do not all share one sound.

Durations are injected, so no audio files or ffmpeg are needed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import sound_library as L  # noqa: E402

DURATIONS = {"a.mp3": 90.0, "b.mp3": 150.0, "c.mp3": 60.0}


def dur(path):
    return DURATIONS[Path(path).name]


class Library(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        for name in DURATIONS:
            (self.dir / name).write_bytes(b"x")
        (self.dir / "notes.txt").write_text("not audio")
        (self.dir / ".hidden.mp3").write_bytes(b"x")
        self.addCleanup(self._tmp.cleanup)

    def pick(self, **kw):
        return L.pick(self.dir, duration_of=dur, **kw).name

    def test_scan_lists_only_audio_files_in_name_order(self):
        self.assertEqual([t.name for t in L.scan(self.dir, duration_of=dur)], ["a.mp3", "b.mp3", "c.mp3"])

    def test_pick_rotates_through_every_track_before_repeating(self):
        self.assertEqual([self.pick() for _ in range(4)], ["a.mp3", "b.mp3", "c.mp3", "a.mp3"])

    def test_rotation_is_remembered_between_runs(self):
        self.pick()
        data = json.loads((self.dir / "library.json").read_text())
        self.assertEqual(data["used"], ["a.mp3"])
        self.assertEqual(self.pick(), "b.mp3")

    def test_pick_skips_tracks_too_short_for_the_video(self):
        self.assertEqual(self.pick(min_length=100.0), "b.mp3")
        self.assertEqual(self.pick(min_length=100.0), "b.mp3")  # the only one long enough

    def test_skipped_tracks_are_never_picked_until_restored(self):
        L.skip(self.dir, "a.mp3")
        self.assertEqual([self.pick() for _ in range(3)], ["b.mp3", "c.mp3", "b.mp3"])
        L.unskip(self.dir, "a.mp3")
        self.assertEqual(self.pick(), "a.mp3")

    def test_no_eligible_track_is_an_error_that_says_why(self):
        with self.assertRaisesRegex(ValueError, "long enough"):
            self.pick(min_length=999.0)

    def test_skip_of_an_unknown_name_is_an_error(self):
        with self.assertRaises(ValueError):
            L.skip(self.dir, "nope.mp3")

    def test_empty_folder_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "no audio"):
                L.pick(d, duration_of=dur)

    def test_resolve_music_passes_a_file_through_and_picks_from_a_folder(self):
        f = self.dir / "b.mp3"
        self.assertEqual(L.resolve_music(f, duration_of=dur), f)
        self.assertEqual(L.resolve_music(self.dir, duration_of=dur).name, "a.mp3")

    def test_resolve_music_missing_path_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            L.resolve_music(self.dir / "gone.mp3")

    def test_describe_analyses_each_track_once_and_caches_it(self):
        calls = []

        def fake(path):
            calls.append(Path(path).name)
            return {"tempo": 100.0, "drops": [10.0, 20.0]}

        rows = L.describe(self.dir, analyse=fake, duration_of=dur)
        L.describe(self.dir, analyse=fake, duration_of=dur)
        self.assertEqual(sorted(calls), ["a.mp3", "b.mp3", "c.mp3"])
        self.assertEqual(rows[0]["tempo"], 100.0)
        self.assertEqual(rows[0]["drops"], [10.0, 20.0])
        self.assertFalse(rows[0]["skipped"])

    def test_describe_reanalyses_a_file_that_changed(self):
        calls = []

        def fake(path):
            calls.append(Path(path).name)
            return {"tempo": 90.0, "drops": []}

        L.describe(self.dir, analyse=fake, duration_of=dur)
        (self.dir / "a.mp3").write_bytes(b"changed and longer")
        L.describe(self.dir, analyse=fake, duration_of=dur)
        self.assertEqual(calls.count("a.mp3"), 2)
        self.assertEqual(calls.count("b.mp3"), 1)


if __name__ == "__main__":
    unittest.main()
