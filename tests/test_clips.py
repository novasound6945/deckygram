"""Assembling a Steam clip folder into ffmpeg inputs.

The bug these guard against: handing session.mpd to ffmpeg truncates
background-recorded clips to one ~3 s fragment.  See deckygram.clips.
"""

import os
import shutil
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import clips


class ClipDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write("x")

    def build(self, video=3, audio=3):
        """A clip folder shaped the way Steam writes one."""
        if video:
            self.write("init-stream0.m4s")
            for i in range(1, video + 1):
                self.write("chunk-stream0-%05d.m4s" % i)
        if audio:
            self.write("init-stream1.m4s")
            for i in range(1, audio + 1):
                self.write("chunk-stream1-%05d.m4s" % i)
        self.write("session.mpd")


class TestStreams(ClipDirTest):
    def test_finds_video_and_audio(self):
        self.build()
        self.assertEqual(clips.streams(self.dir), [0, 1])

    def test_empty_dir(self):
        self.assertEqual(clips.streams(self.dir), [])

    def test_ignores_the_manifest_and_chunks(self):
        self.write("session.mpd")
        self.write("chunk-stream0-00001.m4s")
        self.assertEqual(clips.streams(self.dir), [])


class TestChunks(ClipDirTest):
    def test_recording_order(self):
        self.build(video=3, audio=0)
        got = [os.path.basename(p) for p in clips.chunks(self.dir, 0)]
        self.assertEqual(got, ["chunk-stream0-00001.m4s",
                               "chunk-stream0-00002.m4s",
                               "chunk-stream0-00003.m4s"])

    def test_sorted_numerically_not_lexically(self):
        # Padding makes the two orders agree today; nothing guarantees
        # that past 99999 fragments, so the sort must not rely on it.
        self.write("init-stream0.m4s")
        for i in (2, 10, 1):
            self.write("chunk-stream0-%d.m4s" % i)
        got = [os.path.basename(p) for p in clips.chunks(self.dir, 0)]
        self.assertEqual(got, ["chunk-stream0-1.m4s",
                               "chunk-stream0-2.m4s",
                               "chunk-stream0-10.m4s"])

    def test_one_track_does_not_pick_up_another(self):
        self.build()
        for p in clips.chunks(self.dir, 1):
            self.assertIn("chunk-stream1-", os.path.basename(p))
        self.assertEqual(len(clips.chunks(self.dir, 1)), 3)


class TestConcatSpec(ClipDirTest):
    def test_init_comes_first(self):
        self.build(video=2, audio=0)
        spec = clips.concat_spec(self.dir, 0)
        self.assertTrue(spec.startswith("concat:"))
        parts = spec[len("concat:"):].split("|")
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].endswith("init-stream0.m4s"))
        self.assertTrue(parts[1].endswith("chunk-stream0-00001.m4s"))
        self.assertTrue(parts[2].endswith("chunk-stream0-00002.m4s"))

    def test_absolute_paths(self):
        # ffmpeg is run without a cwd of the clip folder, so every
        # fragment has to be addressable on its own.
        self.build(video=1, audio=0)
        for part in clips.concat_spec(self.dir, 0)[len("concat:"):].split("|"):
            self.assertTrue(os.path.isabs(part), part)

    def test_none_without_fragments(self):
        self.write("init-stream0.m4s")
        self.assertIsNone(clips.concat_spec(self.dir, 0))

    def test_none_without_init(self):
        self.write("chunk-stream0-00001.m4s")
        self.assertIsNone(clips.concat_spec(self.dir, 0))


class TestFfmpegInputs(ClipDirTest):
    def test_video_then_audio(self):
        self.build()
        got = clips.ffmpeg_inputs(self.dir)
        self.assertEqual(len(got), 2)
        self.assertIn("init-stream0.m4s", got[0])
        self.assertIn("init-stream1.m4s", got[1])

    def test_video_only_clip(self):
        self.build(video=3, audio=0)
        got = clips.ffmpeg_inputs(self.dir)
        self.assertEqual(len(got), 1)
        self.assertIn("init-stream0.m4s", got[0])

    def test_manifest_alone_yields_nothing(self):
        # A bookmark-only clip folder: the caller must not run ffmpeg.
        self.write("session.mpd")
        self.assertEqual(clips.ffmpeg_inputs(self.dir), [])

    def test_the_manifest_is_never_an_input(self):
        self.build()
        for spec in clips.ffmpeg_inputs(self.dir):
            self.assertNotIn("session.mpd", spec)


if __name__ == "__main__":
    unittest.main()
