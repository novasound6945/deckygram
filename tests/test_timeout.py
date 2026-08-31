"""Upload timeouts scale with the payload.

This is an inactivity timeout, so the only thing that matters is that a
small upload cannot hold the sender for minutes while a big one still
gets room to finish on a slow link. A flat 600s did the first badly: a
200 KB screenshot could leave the panel on "Sending" for ten minutes
before failing over to a retry (reported 2026-09-01).
"""

import unittest

from py_modules.deckygram import net


class TimeoutFor(unittest.TestCase):
    def test_small_upload_fails_fast(self):
        # A screenshot must not be able to stall the queue for minutes.
        self.assertLessEqual(net.timeout_for(200_000), 60)

    def test_empty_body_gets_the_floor(self):
        self.assertEqual(net.MIN_TIMEOUT, net.timeout_for(0))

    def test_grows_with_size(self):
        self.assertLess(net.timeout_for(1_000_000), net.timeout_for(20_000_000))

    def test_large_clip_still_gets_room(self):
        # 45 MB on a bad link needs minutes, not seconds.
        self.assertGreaterEqual(net.timeout_for(45_000_000), 300)

    def test_never_exceeds_the_cap(self):
        for n in (10**9, 10**12):
            self.assertEqual(net.MAX_TIMEOUT, net.timeout_for(n))

    def test_never_below_the_floor(self):
        for n in (0, -5, -10**9):
            self.assertGreaterEqual(net.timeout_for(n), net.MIN_TIMEOUT)

    def test_junk_input_does_not_raise(self):
        # Callers pass len(...) of something; a None slipping through must
        # not take the sender thread down.
        for bad in (None, "abc", object()):
            self.assertEqual(net.MIN_TIMEOUT, net.timeout_for(bad))

    def test_returns_an_int(self):
        # urlopen wants a number it can hand to the socket layer.
        self.assertIsInstance(net.timeout_for(1_234_567), int)


if __name__ == "__main__":
    unittest.main()
