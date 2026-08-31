"""Orphaned-entry detection for the Steam screenshot index.

The risk here is not missing an orphan - that just leaves a broken tile
one more session. The risk is reporting a live screenshot as orphaned,
because the frontend then deletes it from the user's library for good.
Most of these tests are about that direction.
"""

import os
import shutil
import tempfile
import unittest

from py_modules.deckygram import library


class UrlToRelpath(unittest.TestCase):
    def test_strips_the_screenshots_prefix(self):
        self.assertEqual(
            os.path.join("7", "screenshots", "a.jpg"),
            library.url_to_relpath("screenshots/7/screenshots/a.jpg"),
        )

    def test_accepts_a_url_without_the_prefix(self):
        # The vdf stores the same path without it; be forgiving.
        self.assertEqual(
            os.path.join("7", "screenshots", "a.jpg"),
            library.url_to_relpath("7/screenshots/a.jpg"),
        )

    def test_rejects_traversal(self):
        for bad in ("screenshots/../../etc/passwd",
                    "screenshots/7/../../../x.jpg",
                    "../x.jpg"):
            self.assertIsNone(library.url_to_relpath(bad), bad)

    def test_rejects_empty_and_non_strings(self):
        for bad in ("", "   ", "screenshots/", None, 5, []):
            self.assertIsNone(library.url_to_relpath(bad), repr(bad))


class FindOrphans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "remote")
        self.shots = os.path.join(self.root, "7", "screenshots")
        os.makedirs(self.shots)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self, name):
        p = os.path.join(self.shots, name)
        with open(p, "wb") as fh:
            fh.write(b"x")
        return "screenshots/7/screenshots/" + name

    def test_present_file_is_not_an_orphan(self):
        url = self.make("live.jpg")
        self.assertEqual([], library.find_orphans([url], [self.root]))

    def test_missing_file_is_an_orphan(self):
        url = self.make("gone.jpg")
        os.unlink(os.path.join(self.shots, "gone.jpg"))
        self.assertEqual([url], library.find_orphans([url], [self.root]))

    def test_reports_only_the_missing_ones(self):
        live = self.make("live.jpg")
        gone = self.make("gone.jpg")
        os.unlink(os.path.join(self.shots, "gone.jpg"))
        self.assertEqual([gone], library.find_orphans([live, gone], [self.root]))

    def test_found_in_any_root_counts_as_present(self):
        # Two Steam accounts on one Deck: the entry belongs to whichever
        # root actually holds it.
        other = os.path.join(self.tmp, "remote2")
        os.makedirs(os.path.join(other, "7", "screenshots"))
        url = self.make("live.jpg")
        self.assertEqual([], library.find_orphans([url], [other, self.root]))

    def test_unmounted_tree_reports_nothing(self):
        # The directory the file belongs in does not exist at all, so we
        # cannot tell deleted from unavailable - leave the library alone.
        url = "screenshots/999/screenshots/whatever.jpg"
        self.assertEqual([], library.find_orphans([url], [self.root]))

    def test_no_roots_reports_nothing(self):
        self.assertEqual([], library.find_orphans(["screenshots/7/x.jpg"], []))
        self.assertEqual([], library.find_orphans(["screenshots/7/x.jpg"], [None]))

    def test_a_directory_is_not_a_file(self):
        # A folder where the screenshot should be must not read as present.
        os.makedirs(os.path.join(self.shots, "folder.jpg"))
        url = "screenshots/7/screenshots/folder.jpg"
        self.assertEqual([url], library.find_orphans([url], [self.root]))

    def test_bad_urls_are_skipped_not_reported(self):
        self.assertEqual(
            [], library.find_orphans(["", None, "screenshots/../x.jpg"], [self.root])
        )


class FindMissingClips(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "clips")
        os.makedirs(self.root)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self, name):
        os.makedirs(os.path.join(self.root, name))
        return name

    def test_present_clip_is_not_missing(self):
        cid = self.make("clip_7_20260101_000000")
        self.assertEqual([], library.find_missing_clips([cid], [self.root]))

    def test_deleted_clip_is_missing(self):
        self.assertEqual(
            ["clip_7_gone"], library.find_missing_clips(["clip_7_gone"], [self.root])
        )

    def test_reports_only_the_deleted_ones(self):
        live = self.make("clip_live")
        self.assertEqual(
            ["clip_gone"],
            library.find_missing_clips([live, "clip_gone"], [self.root]),
        )

    def test_no_clips_directory_reports_nothing(self):
        # Steam's data is not where we expect; do not declare every clip dead.
        self.assertEqual(
            [], library.find_missing_clips(["clip_a"], [os.path.join(self.tmp, "nope")])
        )
        self.assertEqual([], library.find_missing_clips(["clip_a"], []))

    def test_ids_with_separators_are_skipped(self):
        # A clip id is one folder name; anything else is not ours to act on.
        for bad in ("../escape", "a/b", "a\\b", ".", "..", "", None, 7):
            self.assertEqual(
                [], library.find_missing_clips([bad], [self.root]), repr(bad)
            )

    def test_found_in_any_root_counts_as_present(self):
        other = os.path.join(self.tmp, "clips2")
        os.makedirs(other)
        cid = self.make("clip_live")
        self.assertEqual([], library.find_missing_clips([cid], [other, self.root]))

    def test_a_file_is_not_a_clip_folder(self):
        with open(os.path.join(self.root, "clip_file"), "wb") as fh:
            fh.write(b"x")
        self.assertEqual(
            ["clip_file"], library.find_missing_clips(["clip_file"], [self.root])
        )


if __name__ == "__main__":
    unittest.main()
