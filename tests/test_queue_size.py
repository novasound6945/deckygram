"""What the panel says is waiting to go out.

The figure is an estimate of the UPLOAD, not of the recording on disk -
a DASH folder is far heavier than the file we send. The one that bit:
"as recorded" is a sentinel rather than a bitrate, and feeding it
straight into the arithmetic made a minute of video look like 0.7 MB.
"""

import os
import shutil
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import media, tg
from deckygram.qstate import QueueState
from deckygram.watcher import Watcher

TG = {"token": "123:AA", "chat_id": "42", "enabled": True}


class QueueSizeTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.settings = dict(TG)
        self.clips = []

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def watcher(self, **over):
        self.settings.update(over)
        w = Watcher(self.home, self.state, lambda: dict(self.settings),
                    _Resolver())
        w._all_clip_dirs = lambda: list(self.clips)
        w._collect_media = lambda: []
        w.sender.clip_duration = lambda d: self.durations[d]
        w.qs = QueueState(self.state)
        return w

    def add_clip(self, seconds, megabytes):
        d = os.path.join(self.home, "clip_%d" % len(self.clips))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "chunk.m4s"), "wb") as fh:
            fh.write(b"x" * int(megabytes * 1024 * 1024))
        self.clips.append(d)
        self.durations = getattr(self, "durations", {})
        self.durations[d] = seconds
        return d

    def bytes_for(self, **over):
        w = self.watcher(**over)
        return w.queue_info()["queued_clips_bytes"]


class _Resolver:
    def resolve(self, appid):
        return "Game"


class TestAsRecorded(QueueSizeTest):
    """The sentinel must never reach the arithmetic."""

    def test_a_minute_is_not_reported_as_a_megabyte(self):
        # 60 s of a 12 Mbit/s recording is ~86 MB on disk; what goes out
        # is whatever fits. Either way it is not 0.7 MB.
        self.add_clip(60, 86)
        got = self.bytes_for(clip_bitrate=media.SOURCE)
        self.assertGreater(got, 10 * 1024 * 1024)

    def test_a_heavy_recording_is_quoted_at_the_limit(self):
        self.add_clip(60, 86)
        self.assertLessEqual(self.bytes_for(clip_bitrate=media.SOURCE),
                             tg.SIZE_TARGET)

    def test_a_light_recording_is_quoted_at_its_own_size(self):
        # Nothing of ours reduces it, so it goes out as it is.
        self.add_clip(60, 8)
        got = self.bytes_for(clip_bitrate=media.SOURCE)
        self.assertLess(got, 10 * 1024 * 1024)

    def test_two_clips_add_up(self):
        self.add_clip(60, 8)
        self.add_clip(60, 8)
        self.assertGreater(self.bytes_for(clip_bitrate=media.SOURCE),
                           14 * 1024 * 1024)


class TestAChosenBitrate(QueueSizeTest):
    def test_the_estimate_follows_the_choice(self):
        self.add_clip(60, 86)
        low = self.bytes_for(clip_bitrate=3_750_000)
        high = self.bytes_for(clip_bitrate=7_500_000)
        self.assertLess(low, high)

    def test_a_minute_at_six_is_about_forty_megabytes(self):
        self.add_clip(60, 86)
        got = self.bytes_for(clip_bitrate=6_000_000)
        self.assertGreater(got, 40 * 1024 * 1024)
        self.assertLessEqual(got, tg.SIZE_TARGET)

    def test_never_over_the_size_target(self):
        self.add_clip(600, 900)
        self.assertLessEqual(self.bytes_for(clip_bitrate=7_500_000),
                             tg.SIZE_TARGET)

    def test_a_clip_of_unknown_length_is_counted_but_not_sized(self):
        d = self.add_clip(0, 40)
        self.assertEqual(self.bytes_for(clip_bitrate=6_000_000), 0)
        self.assertIn(d, self.clips)


if __name__ == "__main__":
    unittest.main()
