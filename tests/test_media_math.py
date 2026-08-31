import unittest

from . import context  # noqa: F401
from deckygram import discord, media, tg


class TestFitBitrate(unittest.TestCase):
    def test_short_clip_keeps_desired_bitrate(self):
        # 30 s: SIZE_TARGET allows ~12 Mbit/s, far above the 2M default.
        self.assertEqual(tg.fit_bitrate(30, 2_000_000), 2_000_000)

    def test_long_clip_is_capped_to_fit(self):
        # 10 min: 45 MB * 8 / 600 s = 629k gross, minus audio headroom.
        expected = tg.SIZE_TARGET * 8 // 600 - media.AUDIO_BITRATE
        self.assertEqual(tg.fit_bitrate(600, 2_000_000), expected)
        self.assertLess(expected, 2_000_000)

    def test_capped_bitrate_actually_fits(self):
        for dur in (60, 300, 600, 900):
            video = tg.fit_bitrate(dur, 2_000_000)
            total_bytes = (video + 96_000) * dur // 8
            self.assertLessEqual(total_bytes, tg.SIZE_TARGET)


class TestHopeless(unittest.TestCase):
    def test_zero_duration_is_not_hopeless(self):
        # Unknown duration: let the real pipeline decide.
        self.assertFalse(tg.hopeless(0))

    def test_short_clip_is_fine(self):
        self.assertFalse(tg.hopeless(120))

    def test_very_long_clip_is_hopeless(self):
        self.assertTrue(tg.hopeless(3600))

    def test_boundary_matches_fit_bitrate(self):
        # hopeless() must flip exactly where fit_bitrate drops below the
        # watchable floor - they encode the same limit.
        for dur in range(60, 3601, 30):
            fits = tg.fit_bitrate(dur, 10**9) >= media.MIN_BITRATE
            self.assertEqual(tg.hopeless(dur), not fits, "dur=%d" % dur)


class TestPerDestinationBudget(unittest.TestCase):
    """The same clip is encoded to a different target per destination."""

    def test_discord_target_is_much_smaller(self):
        self.assertLess(discord.SIZE_TARGET, tg.SIZE_TARGET)

    def test_discord_target_fits_its_hard_limit(self):
        self.assertLessEqual(discord.SIZE_TARGET, discord.SIZE_LIMIT)

    def test_same_clip_gets_a_lower_bitrate_on_discord(self):
        dur = 60
        tg_br = media.fit_bitrate(tg.SIZE_TARGET, dur, 2_000_000)
        dc_br = media.fit_bitrate(discord.SIZE_TARGET, dur, 2_000_000)
        self.assertLess(dc_br, tg_br)

    def test_discord_gives_up_on_clips_telegram_would_take(self):
        # ~5 minutes: fine for a 45 MB budget, hopeless for a 9 MB one.
        self.assertFalse(tg.hopeless(300))
        self.assertTrue(discord.hopeless(300))

    def test_short_clips_still_work_on_discord(self):
        self.assertFalse(discord.hopeless(30))

    def test_discord_encodes_to_fit(self):
        for dur in (10, 30, 60, 120):
            video = media.fit_bitrate(discord.SIZE_TARGET, dur, 2_000_000)
            if video < media.MIN_BITRATE:
                continue
            total = (video + 96_000) * dur // 8
            self.assertLessEqual(total, discord.SIZE_TARGET, "dur=%d" % dur)


if __name__ == "__main__":
    unittest.main()
