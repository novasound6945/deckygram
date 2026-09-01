"""Cached clip posters are cleaned up when their clip goes.

A poster is generated once per clip and kept as posters/<folder>.jpg so
the gallery does not re-extract a frame on every page turn. Nothing ever
removed them, so every clip that was sent and deleted left one behind
permanently. The sweep is the fix; the risk in it is deleting a poster
whose clip is still there, which would just cost a re-extract - but the
name mangling makes that easy to get subtly wrong, so it is pinned here.
"""

import os
import shutil
import tempfile
import unittest

from py_modules.deckygram.gallery import Gallery


class SweepOrphanPosters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        self.clips = os.path.join(
            self.home, ".steam/steam/userdata/1/gamerecordings/clips")
        os.makedirs(self.clips)
        os.makedirs(self.state)
        self.g = Gallery(self.home, self.state, resolver=None)
        os.makedirs(self.g.poster_dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def clip(self, name):
        os.makedirs(os.path.join(self.clips, name))
        return name

    def poster(self, stem, data=b"jpegbytes"):
        p = os.path.join(self.g.poster_dir, stem + ".jpg")
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def test_removes_a_poster_whose_clip_is_gone(self):
        self.poster("clip_7_20260101_000000")
        n, freed = self.g.sweep_orphan_posters()
        self.assertEqual(1, n)
        self.assertEqual(9, freed)
        self.assertEqual([], os.listdir(self.g.poster_dir))

    def test_keeps_a_poster_whose_clip_is_alive(self):
        name = self.clip("clip_7_20260101_000000")
        self.poster(name)
        n, _ = self.g.sweep_orphan_posters()
        self.assertEqual(0, n)
        self.assertEqual(1, len(os.listdir(self.g.poster_dir)))

    def test_matches_the_same_name_mangling_that_wrote_it(self):
        # Poster names replace anything outside [A-Za-z0-9_.-]; comparing
        # raw folder names would delete this one on every sweep.
        name = self.clip("clip 7:20260101")
        self.poster("clip_7_20260101")
        n, _ = self.g.sweep_orphan_posters()
        self.assertEqual(0, n)

    def test_sweeps_only_the_dead_ones(self):
        alive = self.clip("clip_alive")
        self.poster(alive)
        self.poster("clip_dead")
        n, _ = self.g.sweep_orphan_posters()
        self.assertEqual(1, n)
        self.assertEqual(["clip_alive.jpg"], os.listdir(self.g.poster_dir))

    def test_ignores_non_jpg_files(self):
        with open(os.path.join(self.g.poster_dir, "notes.txt"), "wb") as fh:
            fh.write(b"x")
        n, _ = self.g.sweep_orphan_posters()
        self.assertEqual(0, n)
        self.assertEqual(["notes.txt"], os.listdir(self.g.poster_dir))

    def test_missing_poster_dir_is_fine(self):
        shutil.rmtree(self.g.poster_dir)
        self.assertEqual((0, 0), self.g.sweep_orphan_posters())

    def test_empty_poster_dir_is_fine(self):
        self.assertEqual((0, 0), self.g.sweep_orphan_posters())


class InvalidateIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.g = Gallery(self.tmp, self.tmp, resolver=None)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_invalidate_drops_the_cached_index(self):
        # Without this a delete stays listed until the TTL expires, and the
        # next page turn offers to send what is no longer there.
        self.g._index["all"] = (10 ** 9, [{"id": "stale"}])
        self.g.invalidate()
        self.assertEqual({}, self.g._index)

    def test_invalidate_on_an_empty_index_is_fine(self):
        self.g.invalidate()
        self.assertEqual({}, self.g._index)


if __name__ == "__main__":
    unittest.main()
