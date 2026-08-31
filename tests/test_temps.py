"""Startup cleanup of abandoned compression temp files.

Clips are compressed into a temp file the sender unlinks afterwards. Stop
the plugin mid-encode and that file is orphaned; at clip sizes a handful
is real disk. The danger in sweeping them is deleting something that is
not ours, so that is what most of this checks.
"""

import os
import shutil
import tempfile
import unittest

from py_modules.deckygram import media


class ClearStaleTemps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, data=b"xyz"):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def test_removes_leftovers_and_reports_size(self):
        self.write("tmp0lxx2c_z.mp4", b"0123456789")
        self.write("tmpabc.mp4", b"012345")
        n, freed = media.clear_stale_temps(self.tmp)
        self.assertEqual(2, n)
        self.assertEqual(16, freed)
        self.assertEqual([], os.listdir(self.tmp))

    def test_leaves_state_files_alone(self):
        # These live in the same directory and losing them costs real state.
        keep = ["sent.list", "clips_done.list", "stalled.list", "stats.txt",
                "appnames.json"]
        for k in keep:
            self.write(k)
        n, _ = media.clear_stale_temps(self.tmp)
        self.assertEqual(0, n)
        self.assertEqual(sorted(keep), sorted(os.listdir(self.tmp)))

    def test_only_our_naming_pattern(self):
        self.write("tmpkeep.txt")        # temp-looking, wrong suffix
        self.write("holiday.mp4")        # a video, but not ours
        n, _ = media.clear_stale_temps(self.tmp)
        self.assertEqual(0, n)
        self.assertEqual(2, len(os.listdir(self.tmp)))

    def test_ignores_directories(self):
        os.makedirs(os.path.join(self.tmp, "tmpdir.mp4"))
        n, _ = media.clear_stale_temps(self.tmp)
        self.assertEqual(0, n)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "tmpdir.mp4")))

    def test_empty_dir_is_fine(self):
        self.assertEqual((0, 0), media.clear_stale_temps(self.tmp))

    def test_no_dir_configured_is_fine(self):
        # TMP_DIR starts as None; startup must not blow up on it.
        self.assertEqual((0, 0), media.clear_stale_temps(None))
        self.assertEqual((0, 0), media.clear_stale_temps(""))


if __name__ == "__main__":
    unittest.main()
