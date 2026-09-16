import calendar
import time
import unittest

from . import context  # noqa: F401
from deckygram import captions


class FakeResolver:
    def resolve(self, appid):
        return {"1091500": "Cyberpunk 2077", "7": "Steam"}.get(appid, appid)


class TestAppidFromPath(unittest.TestCase):
    def test_screenshot_path(self):
        p = "/home/deck/.steam/steam/userdata/1/760/remote/1091500/screenshots/x.jpg"
        self.assertEqual(captions.appid_from_path(p), "1091500")

    def test_non_screenshot_path(self):
        self.assertIsNone(captions.appid_from_path("/home/deck/Videos/x.mp4"))


class TestClipCaption(unittest.TestCase):
    def test_valid_clip_id(self):
        # Steam writes the folder name in UTC; pin the caption's "local"
        # time to UTC too so the expected string stays the verbatim
        # folder time.
        cap = captions.clip_caption("clip_1091500_20260831_123456", FakeResolver(),
                                    localtime=time.gmtime)
        self.assertEqual(cap, "Cyberpunk 2077 · 2026-08-31 12:34")

    def test_malformed_clip_id(self):
        self.assertEqual(captions.clip_caption("bg_1091500_20260831", FakeResolver()),
                         "Steam Deck clip")

    def test_the_caption_converts_utc_to_local_time(self):
        # Nine zones east of UTC, so 15:30 UTC reads as 00:30 the next
        # day - the bug this guards against showed captions "five hours
        # early" for someone five zones east (2026-09-16).
        cap = captions.clip_caption("clip_1091500_20260915_153023", FakeResolver(),
                                    localtime=lambda e: time.gmtime(e + 9 * 3600))
        self.assertTrue(cap.endswith("2026-09-16 00:30"))

    def test_a_malformed_date_still_produces_a_caption(self):
        # Month 13, day 99: not a real date, but must not raise - it
        # falls back to the digits verbatim.
        cap = captions.clip_caption("clip_1_20261399_123456", FakeResolver(),
                                    localtime=time.gmtime)
        self.assertTrue(cap)


class TestClipTime(unittest.TestCase):
    def test_a_valid_clip_id_gives_the_utc_epoch(self):
        self.assertEqual(
            captions.clip_time("clip_1_20260915_153023"),
            calendar.timegm((2026, 9, 15, 15, 30, 23, 0, 0, 0)))

    def test_an_unrecognised_id_is_none(self):
        self.assertIsNone(captions.clip_time("bg_1_x"))

    def test_album_caption_has_name_and_count(self):
        cap = captions.album_caption("1091500", FakeResolver(), 5)
        self.assertTrue(cap.startswith("Cyberpunk 2077 · "))
        self.assertTrue(cap.endswith(" (5)"))


class TestMpdDuration(unittest.TestCase):
    def _mpd(self, value):
        return '<MPD mediaPresentationDuration="%s" foo="bar">' % value

    def test_seconds_only(self):
        self.assertEqual(captions.parse_mpd_duration(self._mpd("PT28.5S")), 28)

    def test_minutes_and_seconds(self):
        self.assertEqual(captions.parse_mpd_duration(self._mpd("PT1M30S")), 90)

    def test_hours(self):
        self.assertEqual(captions.parse_mpd_duration(self._mpd("PT1H2M3S")), 3723)

    def test_missing_attribute(self):
        self.assertEqual(captions.parse_mpd_duration("<MPD>"), 0)

    def test_garbage(self):
        self.assertEqual(captions.parse_mpd_duration("not xml at all"), 0)


if __name__ == "__main__":
    unittest.main()
