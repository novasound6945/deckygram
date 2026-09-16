"""The 16-row quality table: one choice of frame and rate, not two.

Every stored value is the literal number the encoder uses - the 800p
reference ladder scaled by pixel count to the other three heights.
"""

import unittest

from . import context  # noqa: F401
from deckygram import media

EXPECTED = {
    800: (12_800_000, 7_500_000, 6_000_000, 3_750_000),
    720: (10_370_000, 6_080_000, 4_860_000, 3_040_000),
    600: (7_200_000, 4_220_000, 3_380_000, 2_110_000),
    480: (4_610_000, 2_700_000, 2_160_000, 1_350_000),
}

FRAMES = {800: (1280, 800), 720: (1152, 720), 600: (960, 600), 480: (768, 480)}


class TestBitratesForHeight(unittest.TestCase):
    def test_every_height_matches_the_expected_ladder(self):
        for h, expected in EXPECTED.items():
            self.assertEqual(media.bitrates_for(h), expected)


class TestFrameFor(unittest.TestCase):
    def test_every_height_gets_its_16x10_frame(self):
        for h, expected in FRAMES.items():
            self.assertEqual(media.frame_for(h), expected)


class TestMbPerMinute(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(media.mb_per_minute(6_000_000), 44)
        self.assertEqual(media.mb_per_minute(2_160_000), 16)
        self.assertEqual(media.mb_per_minute(12_800_000), 92)


class TestMbitLabel(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(media.mbit_label(6_000_000), "6")
        self.assertEqual(media.mbit_label(3_750_000), "3.75")
        self.assertEqual(media.mbit_label(2_160_000), "2.16")
        self.assertEqual(media.mbit_label(12_800_000), "12.8")
        self.assertEqual(media.mbit_label(10_370_000), "10.37")


class TestQualityTable(unittest.TestCase):
    def test_sixteen_rows(self):
        self.assertEqual(len(media.quality_table()), 16)

    def test_four_rows_per_height_in_heights_order(self):
        rows = media.quality_table()
        heights = [r["height"] for r in rows]
        expected = []
        for h in media.HEIGHTS:
            expected += [h] * 4
        self.assertEqual(heights, expected)

    def test_rates_descend_within_a_height(self):
        rows = media.quality_table()
        for h in media.HEIGHTS:
            rates = [r["bitrate"] for r in rows if r["height"] == h]
            self.assertEqual(rates, sorted(rates, reverse=True))

    def test_mbit_and_mb_per_min_agree_with_the_helpers(self):
        for row in media.quality_table():
            self.assertEqual(row["mbit"], media.mbit_label(row["bitrate"]))
            self.assertEqual(row["mb_per_min"], media.mb_per_minute(row["bitrate"]))


class TestPickBitrate(unittest.TestCase):
    def test_an_offered_value_at_that_height_is_taken(self):
        self.assertEqual(media.pick_bitrate(2_160_000, None, 480), 2_160_000)

    def test_an_old_800p_value_is_scaled_to_the_smaller_frame(self):
        self.assertEqual(media.pick_bitrate(6_000_000, None, 480), 2_160_000)

    def test_source_lands_on_the_top_row_at_480(self):
        self.assertEqual(media.pick_bitrate(-1, None, 480), 4_610_000)

    def test_source_lands_on_the_top_row_at_800(self):
        self.assertEqual(media.pick_bitrate(-1, None, 800), 12_800_000)

    def test_an_old_preset_is_translated_at_the_chosen_height(self):
        self.assertEqual(media.pick_bitrate(None, "balanced", 480), 2_160_000)
        self.assertEqual(media.pick_bitrate(None, "quality", 800), 12_800_000)

    def test_garbage_falls_back_to_the_default_scaled(self):
        self.assertEqual(media.pick_bitrate("garbage", None, 720), 4_860_000)

    def test_an_unoffered_number_snaps_to_the_nearest_row(self):
        self.assertEqual(media.pick_bitrate(2_200_000, None, 480), 2_160_000)

    def test_a_row_value_at_its_own_height_is_returned_unchanged(self):
        self.assertEqual(media.pick_bitrate(7_500_000, None, 800), 7_500_000)


if __name__ == "__main__":
    unittest.main()
