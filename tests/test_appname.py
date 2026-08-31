import unittest

from . import context  # noqa: F401
from deckygram import appname


def vdf_entry(appid: int, name: bytes) -> bytes:
    """One shortcuts.vdf entry, reduced to the fields the parser reads."""
    return (b"\x02appid\x00" + appid.to_bytes(4, "little")
            + b"\x01AppName\x00" + name + b"\x00"
            + b"\x01Exe\x00/usr/bin/thing\x00")


class TestIdMatches(unittest.TestCase):
    RAW = 2307312975   # value as stored in shortcuts.vdf

    def test_exact_match(self):
        self.assertTrue(appname.id_matches(self.RAW, self.RAW))

    def test_screenshot_folder_is_low_24_bits(self):
        self.assertTrue(appname.id_matches(self.RAW, self.RAW & 0xFFFFFF))

    def test_clip_folder_carries_appid_in_high_32_bits(self):
        self.assertTrue(appname.id_matches(self.RAW, self.RAW << 32 | 0x02))

    def test_unrelated_id_does_not_match(self):
        self.assertFalse(appname.id_matches(self.RAW, 12345))


class TestShortcutNameFromVdf(unittest.TestCase):
    def test_finds_matching_entry(self):
        data = vdf_entry(111, b"RetroDECK") + vdf_entry(2307312975, b"Eden")
        self.assertEqual(appname.shortcut_name_from_vdf(data, 2307312975), "Eden")

    def test_matches_via_screenshot_folder_id(self):
        data = vdf_entry(2307312975, b"Eden")
        self.assertEqual(
            appname.shortcut_name_from_vdf(data, 2307312975 & 0xFFFFFF), "Eden")

    def test_no_match_returns_none(self):
        data = vdf_entry(111, b"RetroDECK")
        self.assertIsNone(appname.shortcut_name_from_vdf(data, 999))

    def test_lowercase_appname_key(self):
        data = (b"\x02appid\x00" + (111).to_bytes(4, "little")
                + b"\x01appname\x00Lowercase\x00")
        self.assertEqual(appname.shortcut_name_from_vdf(data, 111), "Lowercase")

    def test_garbage_data_returns_none(self):
        self.assertIsNone(appname.shortcut_name_from_vdf(b"\x00\x01\x02", 1))


if __name__ == "__main__":
    unittest.main()
