"""Reading Steam's own settings - notably a moved recordings folder.

Settings > Game Recording can put recordings on an SD card, and Steam
moves the whole tree when it does. Nothing in Steam's UI exposes the
real path, so it is read out of localconfig.vdf.
"""

import os
import shutil
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import steamcfg

BLOCK = '''\
\t"GameRecording"
\t{
\t\t"BackgroundRecordMode"\t\t"1"
\t\t"InstantClipDuration"\t\t"300"
%s\t}
'''
PATH_LINE = '\t\t"BackgroundRecordPath"\t\t"%s"\n'


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        steamcfg._CACHE.clear()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        steamcfg._CACHE.clear()

    def write_config(self, user="53638528", path=None):
        d = os.path.join(self.home, ".steam", "steam", "userdata",
                         user, "config")
        os.makedirs(d, exist_ok=True)
        target = os.path.join(d, "localconfig.vdf")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(BLOCK % (PATH_LINE % path if path else ""))
        return target

    def make_recordings(self, *roots):
        for root in roots:
            os.makedirs(os.path.join(root, "clips"), exist_ok=True)

    def default_root(self, user="53638528"):
        return os.path.join(self.home, ".steam", "steam", "userdata",
                            user, "gamerecordings")


class TestRecordingPath(ConfigTest):
    def test_reads_the_configured_folder(self):
        cfg = self.write_config(path="/run/media/deck/abc/New Folrec")
        self.assertEqual(steamcfg.recording_path(cfg),
                         "/run/media/deck/abc/New Folrec")

    def test_empty_when_never_changed(self):
        # Steam writes the key only once it has been set, so a stock
        # install has no line at all.
        self.assertEqual(steamcfg.recording_path(self.write_config()), "")

    def test_missing_config_is_not_an_error(self):
        self.assertEqual(steamcfg.recording_path("/nope/localconfig.vdf"), "")

    def test_reread_after_the_file_changes(self):
        cfg = self.write_config(path="/one")
        self.assertEqual(steamcfg.recording_path(cfg), "/one")
        os.utime(cfg, (1, 1))           # make the change detectable
        self.write_config(path="/two")
        self.assertEqual(steamcfg.recording_path(cfg), "/two")


class TestRecordingPaths(ConfigTest):
    def test_collects_every_user(self):
        self.write_config("111", "/a")
        self.write_config("222", "/b")
        self.assertEqual(sorted(steamcfg.recording_paths(self.home)),
                         ["/a", "/b"])

    def test_deduplicates_a_shared_folder(self):
        self.write_config("111", "/same")
        self.write_config("222", "/same")
        self.assertEqual(steamcfg.recording_paths(self.home), ["/same"])

    def test_none_configured(self):
        self.write_config()
        self.assertEqual(steamcfg.recording_paths(self.home), [])


class TestRoots(ConfigTest):
    def test_default_location_alone(self):
        self.write_config()
        self.make_recordings(self.default_root())
        self.assertEqual(steamcfg.recording_roots(self.home),
                         [self.default_root()])

    def test_keeps_the_old_root_after_a_move(self):
        # Steam leaves already-recorded clips behind, so moving the
        # folder must not hide them.
        moved = os.path.join(self.home, "sd", "New Folrec")
        self.write_config(path=moved)
        self.make_recordings(self.default_root(), moved)
        self.assertEqual(steamcfg.recording_roots(self.home),
                         sorted([self.default_root(), moved]))

    def test_clip_roots_are_the_clips_subfolders(self):
        moved = os.path.join(self.home, "sd", "New Folrec")
        self.write_config(path=moved)
        self.make_recordings(self.default_root(), moved)
        self.assertEqual(sorted(steamcfg.clip_roots(self.home)),
                         sorted([os.path.join(self.default_root(), "clips"),
                                 os.path.join(moved, "clips")]))

    def test_a_configured_folder_with_nothing_in_it_yet(self):
        # Named in the config but Steam has not recorded there yet.
        moved = os.path.join(self.home, "sd", "New Folrec")
        self.write_config(path=moved)
        self.make_recordings(self.default_root())
        os.makedirs(moved, exist_ok=True)
        self.assertEqual(steamcfg.clip_roots(self.home),
                         [os.path.join(self.default_root(), "clips")])

    def test_a_folder_that_is_gone(self):
        # An SD card that is not in the Deck right now.
        self.write_config(path="/run/media/deck/removed/rec")
        self.make_recordings(self.default_root())
        self.assertEqual(steamcfg.clip_roots(self.home),
                         [os.path.join(self.default_root(), "clips")])


class TestClipDirs(ConfigTest):
    def make_clip(self, root, name):
        d = os.path.join(root, "clips", name)
        os.makedirs(d, exist_ok=True)
        return d

    def test_clips_from_both_roots(self):
        moved = os.path.join(self.home, "sd", "New Folrec")
        self.write_config(path=moved)
        self.make_recordings(self.default_root(), moved)
        old = self.make_clip(self.default_root(), "clip_1_20260101_000000")
        new = self.make_clip(moved, "clip_2_20260101_000000")
        self.assertEqual(sorted(steamcfg.clip_dirs(self.home)),
                         sorted([old, new]))

    def test_brackets_in_the_path_still_list(self):
        # glob would treat these as a character class and find nothing.
        moved = os.path.join(self.home, "my [clips]", "rec")
        self.write_config(path=moved)
        self.make_recordings(moved)
        clip = self.make_clip(moved, "clip_3_20260101_000000")
        self.assertEqual(list(steamcfg.clip_dirs(self.home)), [clip])

    def test_loose_files_are_not_clips(self):
        self.write_config()
        self.make_recordings(self.default_root())
        with open(os.path.join(self.default_root(), "clips", "stray.txt"),
                  "w") as fh:
            fh.write("x")
        self.assertEqual(list(steamcfg.clip_dirs(self.home)), [])


class TestAwkwardPaths(ConfigTest):
    def test_space_in_the_folder_name(self):
        cfg = self.write_config(path="/run/media/deck/abc/New Folrec")
        self.assertIn(" ", steamcfg.recording_path(cfg))

    def test_brackets_survive(self):
        # These would be glob patterns if the path were ever globbed.
        cfg = self.write_config(path="/media/my [clips]/rec")
        self.assertEqual(steamcfg.recording_path(cfg), "/media/my [clips]/rec")

    def test_escaped_backslash(self):
        cfg = self.write_config(path=r"/media/a\\b")
        self.assertEqual(steamcfg.recording_path(cfg), r"/media/a\b")


if __name__ == "__main__":
    unittest.main()
