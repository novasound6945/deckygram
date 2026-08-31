"""Gallery listing, paging, and the force-send escape hatch."""

import os
import tempfile
import time
import unittest

from . import context  # noqa: F401
from deckygram.gallery import Gallery
from deckygram.qstate import QueueState


class FakeResolver:
    def resolve(self, appid):
        return {"7": "Steam", "1091500": "Cyberpunk 2077"}.get(appid, appid)


class GalleryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.shots = os.path.join(
            self.home, ".steam/steam/userdata/1/760/remote/7/screenshots")
        os.makedirs(os.path.join(self.shots, "thumbnails"))
        self.state = os.path.join(self.home, "state")
        os.makedirs(self.state)
        self.g = Gallery(self.home, self.state, FakeResolver())

    def tearDown(self):
        self.tmp.cleanup()

    def shot(self, name, age=0, thumb=True):
        p = os.path.join(self.shots, name)
        with open(p, "wb") as f:
            f.write(b"\xff\xd8\xff" + b"0" * 500)
        if thumb:
            with open(os.path.join(self.shots, "thumbnails", name), "wb") as f:
                f.write(b"\xff\xd8\xff" + b"0" * 50)
        if age:
            t = time.time() - age
            os.utime(p, (t, t))
        return p


class TestListing(GalleryCase):
    def test_lists_screenshots_with_metadata(self):
        self.shot("a.jpg")
        r = self.g.list()
        self.assertEqual(r["total"], 1)
        it = r["items"][0]
        self.assertEqual(it["kind"], "image")
        self.assertEqual(it["game"], "Steam")     # appid 7 from the path
        self.assertGreater(it["bytes"], 0)

    def test_newest_first(self):
        self.shot("old.jpg", age=3600)
        self.shot("new.jpg")
        names = [os.path.basename(i["id"]) for i in self.g.list()["items"]]
        self.assertEqual(names, ["new.jpg", "old.jpg"])

    def test_paging_walks_the_whole_library(self):
        for i in range(25):
            self.shot("s%02d.jpg" % i, age=i * 60)
        seen = []
        for off in (0, 10, 20):
            page = self.g.list(offset=off, limit=10)
            self.assertEqual(page["total"], 25)
            seen += [i["id"] for i in page["items"]]
        self.assertEqual(len(seen), 25)
        self.assertEqual(len(set(seen)), 25, "pages overlapped")

    def test_page_past_the_end_is_empty_not_an_error(self):
        self.shot("a.jpg")
        self.assertEqual(self.g.list(offset=500)["items"], [])

    def test_kind_filter(self):
        self.shot("a.jpg")
        self.assertEqual(self.g.list(kind="images")["total"], 1)
        self.assertEqual(self.g.list(kind="clips")["total"], 0)

    def test_index_is_cached_between_pages(self):
        self.shot("a.jpg")
        self.g.list()
        self.shot("b.jpg")                       # appears after the scan
        self.assertEqual(self.g.list()["total"], 1, "should serve the cache")
        self.assertEqual(self.g.list(refresh=True)["total"], 2)


class TestGameFilter(GalleryCase):
    def _other_game(self, name, age=0):
        d = os.path.join(self.home,
                         ".steam/steam/userdata/1/760/remote/1091500/screenshots")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(b"\xff\xd8\xff")
        if age:
            t = time.time() - age
            os.utime(p, (t, t))
        return p

    def test_lists_each_game_with_a_count(self):
        self.shot("a.jpg")
        self.shot("b.jpg")
        self._other_game("c.jpg")
        by_name = {g["game"]: g for g in self.g.games()}
        self.assertEqual(by_name["Steam"]["count"], 2)
        self.assertEqual(by_name["Cyberpunk 2077"]["count"], 1)
        self.assertEqual(by_name["Cyberpunk 2077"]["ids"], "1091500")

    def test_games_are_ordered_by_most_recent(self):
        self.shot("old.jpg", age=7200)
        self._other_game("new.jpg")
        self.assertEqual([g["game"] for g in self.g.games()], ["Cyberpunk 2077", "Steam"])

    def test_filtering_narrows_to_one_game(self):
        self.shot("a.jpg")
        self._other_game("c.jpg")
        r = self.g.list(appids="1091500")
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["items"][0]["game"], "Cyberpunk 2077")

    def test_filter_paging_totals_only_that_game(self):
        for i in range(12):
            self.shot("s%02d.jpg" % i, age=i * 60)
        self._other_game("c.jpg")
        r = self.g.list(offset=10, limit=10, appids="7")
        self.assertEqual(r["total"], 12)
        self.assertEqual(len(r["items"]), 2)

    def test_unknown_game_yields_nothing(self):
        self.shot("a.jpg")
        self.assertEqual(self.g.list(appids="999999")["total"], 0)


class TestNonSteamIdsAreMerged(GalleryCase):
    """One shortcut, two ids: screenshots use 24 bits, clips 64.

    Listing them separately showed the same game twice in the filter.
    """

    RAW = 2307312975
    SHOT_ID = str(RAW & 0xFFFFFF)
    CLIP_ID = str(RAW << 32 | 2)

    def setUp(self):
        super().setUp()
        both = {self.SHOT_ID: "Eden", self.CLIP_ID: "Eden"}
        self.g.resolver = type("R", (), {"resolve": lambda _s, a: both.get(a, a)})()

    def _shot_for(self, appid, name):
        d = os.path.join(self.home,
                         ".steam/steam/userdata/1/760/remote/%s/screenshots" % appid)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(b"\xff\xd8\xff")
        return p

    def _clip_for(self, clip_id):
        d = os.path.join(self.home,
                         ".steam/steam/userdata/1/gamerecordings/clips",
                         "clip_%s_20260101_120000" % clip_id)
        os.makedirs(os.path.join(d, "inner"), exist_ok=True)
        with open(os.path.join(d, "inner", "session.mpd"), "w") as f:
            f.write('<MPD mediaPresentationDuration="PT10S">')
        return d

    def test_one_entry_not_two(self):
        self._shot_for(self.SHOT_ID, "a.jpg")
        self._clip_for(self.CLIP_ID)
        names = [g["game"] for g in self.g.games()]
        self.assertEqual(names.count("Eden"), 1, names)

    def test_the_entry_counts_both(self):
        self._shot_for(self.SHOT_ID, "a.jpg")
        self._clip_for(self.CLIP_ID)
        eden = next(g for g in self.g.games() if g["game"] == "Eden")
        self.assertEqual(eden["count"], 2)

    def test_filtering_by_it_returns_both(self):
        self._shot_for(self.SHOT_ID, "a.jpg")
        self._clip_for(self.CLIP_ID)
        eden = next(g for g in self.g.games() if g["game"] == "Eden")
        self.assertEqual(self.g.list(appids=eden["ids"])["total"], 2)


class TestBookmarkClipsAreFlagged(GalleryCase):
    """Folders with only a clip.pb hold no fragments and cannot be sent.

    They are still listed - Steam shows them, so hiding them reads as a
    missing clip - but marked unsendable so the UI can grey them out.
    """

    def _clip(self, name, with_mpd=True):
        d = os.path.join(self.home,
                         ".steam/steam/userdata/1/gamerecordings/clips", name)
        os.makedirs(os.path.join(d, "inner"), exist_ok=True)
        with open(os.path.join(d, "clip.pb"), "wb") as f:
            f.write(b"\x00")
        if with_mpd:
            with open(os.path.join(d, "inner", "session.mpd"), "w") as f:
                f.write('<MPD mediaPresentationDuration="PT12S">')
        return d

    def test_exportable_clip_is_sendable(self):
        self._clip("clip_7_20260101_120000")
        self.assertTrue(self.g.list(kind="clips")["items"][0]["sendable"])

    def test_bookmark_only_clip_is_listed_but_not_sendable(self):
        self._clip("clip_7_20260101_130000", with_mpd=False)
        r = self.g.list(kind="clips")
        self.assertEqual(r["total"], 1)
        self.assertFalse(r["items"][0]["sendable"])

    def test_mixed_library_flags_each_correctly(self):
        self._clip("clip_7_20260101_120000")
        self._clip("clip_7_20260101_130000", with_mpd=False)
        by_id = {os.path.basename(i["id"]): i for i in self.g.list(kind="clips")["items"]}
        self.assertTrue(by_id["clip_7_20260101_120000"]["sendable"])
        self.assertFalse(by_id["clip_7_20260101_130000"]["sendable"])


class TestThumbnails(GalleryCase):
    def test_prefers_steams_own_thumbnail(self):
        p = self.shot("a.jpg")
        thumb = os.path.join(self.shots, "thumbnails", "a.jpg")
        data = self.g.thumbnail(p)
        self.assertTrue(data.startswith("data:image/jpeg;base64,"))
        # The small file, not the big one.
        import base64
        raw = base64.b64decode(data.split(",", 1)[1])
        self.assertEqual(len(raw), os.path.getsize(thumb))

    def test_falls_back_to_the_screenshot_itself(self):
        p = self.shot("b.jpg", thumb=False)
        self.assertTrue(self.g.thumbnail(p).startswith("data:image/jpeg;base64,"))

    def test_missing_file_returns_empty_not_an_exception(self):
        self.assertEqual(self.g.thumbnail("/nope/gone.jpg"), "")


class TestForcedSend(unittest.TestCase):
    """Hand-picked items must send even though they are already 'sent'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.qs = QueueState(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_forcing_marks_the_item(self):
        self.qs.force("/a/x.jpg")
        self.assertTrue(self.qs.is_forced("/a/x.jpg"))

    def test_unforced_items_are_untouched(self):
        self.assertFalse(self.qs.is_forced("/a/y.jpg"))

    def test_delivering_clears_the_flag(self):
        self.qs.force("/a/x.jpg")
        self.qs.mark_sent("/a/x.jpg")
        self.assertFalse(self.qs.is_forced("/a/x.jpg"))

    def test_unforce_clears_a_path_keyed_flag(self):
        # Clips are flagged by path but recorded as done by folder name;
        # without an explicit unforce they were re-sent on every scan.
        self.qs.force("/clips/clip_1_x")
        self.qs.mark_clip_done("clip_1_x")          # name only
        self.assertTrue(self.qs.is_forced("/clips/clip_1_x"))
        self.qs.unforce("/clips/clip_1_x")
        self.assertFalse(self.qs.is_forced("/clips/clip_1_x"))

    def test_force_is_not_persisted(self):
        # A deliberate one-off: a restart must not re-send it forever.
        self.qs.force("/a/x.jpg")
        self.assertFalse(QueueState(self.tmp.name).is_forced("/a/x.jpg"))


if __name__ == "__main__":
    unittest.main()
