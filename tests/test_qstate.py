import tempfile
import unittest

from . import context  # noqa: F401
from deckygram.qstate import QueueState

IMG = {".jpg", ".jpeg", ".png"}


class TestTakeReady(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.qs = QueueState(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_within_settle_window_is_held(self):
        self.qs.queue("/a/x.jpg", at=100.0)
        self.assertEqual(self.qs.take_ready(101.0, 3, IMG), [])
        self.assertIn("/a/x.jpg", self.qs.pending)

    def test_file_past_settle_window_is_released(self):
        self.qs.queue("/a/x.jpg", at=100.0)
        self.assertEqual(self.qs.take_ready(104.0, 3, IMG), ["/a/x.jpg"])
        self.assertEqual(self.qs.pending, {})

    def test_burst_holds_ready_images_while_one_settles(self):
        # x is ready, y arrived just now: hold BOTH so they album together.
        self.qs.queue("/a/x.jpg", at=100.0)
        self.qs.queue("/a/y.jpg", at=103.5)
        self.assertEqual(self.qs.take_ready(104.0, 3, IMG), [])
        # Once y settles too, both come out in the same batch.
        ready = self.qs.take_ready(107.0, 3, IMG)
        self.assertEqual(sorted(ready), ["/a/x.jpg", "/a/y.jpg"])

    def test_burst_hold_does_not_delay_videos(self):
        self.qs.queue("/a/x.mp4", at=100.0)
        self.qs.queue("/a/y.jpg", at=103.5)   # image still settling
        self.assertEqual(self.qs.take_ready(104.0, 3, IMG), ["/a/x.mp4"])

    def test_retry_backoff_via_future_timestamp(self):
        self.qs.queue("/a/x.jpg", at=200.0)   # failed send re-queued at now+30
        self.assertEqual(self.qs.take_ready(199.0, 3, IMG), [])
        self.assertEqual(self.qs.take_ready(204.0, 3, IMG), ["/a/x.jpg"])


class TestPersistence(unittest.TestCase):
    def test_sent_list_survives_reload(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.mark_sent("/a/x.jpg")
            qs.mark_clip_done("clip_1_20260831_120000")
            qs2 = QueueState(d)
            self.assertIn("/a/x.jpg", qs2.sent)
            self.assertIn("clip_1_20260831_120000", qs2.clips_done)

    def test_sent_counter_survives_reload(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.bump_sent()
            qs.bump_sent()
            self.assertEqual(QueueState(d).sent_count, 2)

    def test_mark_sent_is_idempotent_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.mark_sent("/a/x.jpg")
            qs.mark_sent("/a/x.jpg")
            with open(qs.sent_path, encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 1)


if __name__ == "__main__":
    unittest.main()
