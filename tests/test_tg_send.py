"""Album/photo API shaping - no network: api_call is stubbed out."""

import json
import os
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import tg


class Recorder:
    """Stand-in for tg.api_call that records what would have been sent."""

    def __init__(self):
        self.calls = []

    def __call__(self, token, method, fields=None, files=None, timeout=600):
        self.calls.append((method, fields or {}, files or {}))
        return {}

    @property
    def method(self):
        return self.calls[-1][0]

    @property
    def fields(self):
        return self.calls[-1][1]

    @property
    def files(self):
        return self.calls[-1][2]


class SendTestCase(unittest.TestCase):
    def setUp(self):
        self.rec = Recorder()
        self._real = tg.api_call
        tg.api_call = self.rec

    def tearDown(self):
        tg.api_call = self._real


class TestSinglePhoto(SendTestCase):
    def setUp(self):
        super().setUp()
        # send_media stats the file before choosing an API method.
        self.tmp = tempfile.TemporaryDirectory()
        self.jpg = os.path.join(self.tmp.name, "shot.jpg")
        with open(self.jpg, "wb") as f:
            f.write(b"\xff\xd8\xff" + b"0" * 128)

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_default_uses_sendphoto(self):
        tg.send_media("t", "1", self.jpg, "cap")
        self.assertEqual(self.rec.method, "sendPhoto")
        self.assertIn("photo", self.rec.files)

    def test_oversized_image_is_unsendable(self):
        big = os.path.join(self.tmp.name, "big.png")
        with open(big, "wb") as f:
            f.truncate(tg.BOT_LIMIT + 1)
        with self.assertRaises(tg.Unsendable):
            tg.send_media("t", "1", big, "cap")


class TestAlbum(SendTestCase):
    PATHS = ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"]

    def test_album_is_a_media_group_of_photos(self):
        tg.send_photo_album("t", "1", self.PATHS, "cap")
        self.assertEqual(self.rec.method, "sendMediaGroup")
        self.assertEqual(sorted(self.rec.files), ["photo0", "photo1", "photo2"])

    def test_media_items_reference_their_attachments(self):
        tg.send_photo_album("t", "1", self.PATHS, "cap")
        media = json.loads(self.rec.fields["media"])
        self.assertTrue(all(i["type"] == "photo" for i in media))
        for item in media:
            self.assertIn(item["media"].replace("attach://", ""), self.rec.files)

    def test_only_first_item_carries_the_caption(self):
        tg.send_photo_album("t", "1", self.PATHS, "cap")
        media = json.loads(self.rec.fields["media"])
        self.assertEqual(media[0]["caption"], "cap")
        self.assertFalse(any("caption" in i for i in media[1:]))

    def test_album_caps_at_ten(self):
        tg.send_photo_album("t", "1", ["/a/%d.jpg" % i for i in range(15)], "cap")
        self.assertEqual(len(self.rec.files), 10)

    def test_single_path_falls_back_to_send_media(self):
        # send_media stats the file, so this one has to exist.
        with tempfile.TemporaryDirectory() as d:
            jpg = os.path.join(d, "shot.jpg")
            with open(jpg, "wb") as f:
                f.write(b"\xff\xd8\xff")
            tg.send_photo_album("t", "1", [jpg], "cap")
        self.assertEqual(self.rec.method, "sendPhoto")

    def test_empty_list_sends_nothing(self):
        tg.send_photo_album("t", "1", [], "cap")
        self.assertEqual(self.rec.calls, [])


if __name__ == "__main__":
    unittest.main()
