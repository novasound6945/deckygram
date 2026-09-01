"""Deleting an item must take its queue bookkeeping with it.

Removing the file is the visible half. The invisible half is that the
item can still be sitting in the pending queue, the stalled list, the
retry counters and the delete-after-send promise. A pending entry is
harmless - the sender discards it when the file turns out to be missing -
but a stalled one keeps counting towards "N items gave up" and keeps its
line in stalled.list, pointing at a file that no longer exists.
"""

import os
import shutil
import tempfile
import unittest

from py_modules.deckygram.qstate import QueueState


class ForgetItem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.qs = QueueState(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_clears_a_pending_entry(self):
        self.qs.queue("/x/a.jpg", 0)
        self.qs.forget_item("/x/a.jpg")
        self.assertNotIn("/x/a.jpg", self.qs.pending)

    def test_clears_the_stalled_entry_and_the_count(self):
        self.qs.give_up("/x/a.jpg")
        self.assertEqual(1, self.qs.stalled())
        self.qs.forget_item("/x/a.jpg")
        self.assertEqual(0, self.qs.stalled())

    def test_rewrites_the_stalled_file(self):
        # Left behind, the line outlives the file it names.
        self.qs.give_up("/x/a.jpg")
        self.qs.give_up("/x/b.jpg")
        self.qs.forget_item("/x/a.jpg")
        with open(self.qs.stalled_path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(["/x/b.jpg"], lines)

    def test_clears_the_retry_counter(self):
        self.qs.note_attempt("/x/a.jpg")
        self.qs.note_attempt("/x/a.jpg")
        self.qs.forget_item("/x/a.jpg")
        self.assertEqual(1, self.qs.note_attempt("/x/a.jpg"))

    def test_clears_the_hand_picked_flag(self):
        self.qs.force("/x/a.jpg")
        self.qs.forget_item("/x/a.jpg")
        self.assertFalse(self.qs.is_forced("/x/a.jpg"))

    def test_clears_the_delete_after_send_promise(self):
        self.qs.want_delete("/x/a.jpg")
        self.qs.forget_item("/x/a.jpg")
        self.assertFalse(self.qs.wants_delete("/x/a.jpg"))

    def test_clears_a_clip_backoff_keyed_by_folder_name(self):
        # clip_retry_at is keyed by the folder name, not the full path -
        # the same mismatch that once made a clip resend forever.
        self.qs.clip_retry_at["clip_7_20260101"] = 10 ** 9
        self.qs.forget_item("/clips/clip_7_20260101")
        self.assertNotIn("clip_7_20260101", self.qs.clip_retry_at)

    def test_clears_the_no_album_mark(self):
        self.qs.no_album.add("/x/a.jpg")
        self.qs.forget_item("/x/a.jpg")
        self.assertNotIn("/x/a.jpg", self.qs.no_album)

    def test_leaves_other_items_alone(self):
        self.qs.queue("/x/a.jpg", 0)
        self.qs.queue("/x/b.jpg", 0)
        self.qs.give_up("/x/c.jpg")
        self.qs.forget_item("/x/a.jpg")
        self.assertIn("/x/b.jpg", self.qs.pending)
        self.assertEqual(1, self.qs.stalled())

    def test_forgetting_an_unknown_item_is_harmless(self):
        self.qs.forget_item("/x/never-seen.jpg")   # must not raise

    def test_survives_a_reload(self):
        # The stalled and delete-after-send lists are on disk; a restart
        # must not bring the forgotten item back.
        self.qs.give_up("/x/a.jpg")
        self.qs.want_delete("/x/a.jpg")
        self.qs.forget_item("/x/a.jpg")
        fresh = QueueState(self.tmp)
        self.assertEqual(0, fresh.stalled())
        self.assertFalse(fresh.wants_delete("/x/a.jpg"))


class DeleteAfterSendPromise(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.qs = QueueState(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_promise_persists_across_a_reload(self):
        # Pressing delete on a queued item, then a plugin reload before it
        # sends, must not silently drop the instruction.
        self.qs.want_delete("/x/a.jpg")
        self.assertTrue(QueueState(self.tmp).wants_delete("/x/a.jpg"))

    def test_promise_is_cleared_once_kept(self):
        self.qs.want_delete("/x/a.jpg")
        self.qs.delete_done("/x/a.jpg")
        self.assertFalse(self.qs.wants_delete("/x/a.jpg"))
        self.assertFalse(QueueState(self.tmp).wants_delete("/x/a.jpg"))

    def test_promising_twice_is_idempotent(self):
        self.qs.want_delete("/x/a.jpg")
        self.qs.want_delete("/x/a.jpg")
        self.qs.delete_done("/x/a.jpg")
        self.assertFalse(QueueState(self.tmp).wants_delete("/x/a.jpg"))

    def test_unknown_item_is_not_promised(self):
        self.assertFalse(self.qs.wants_delete("/x/nope.jpg"))

    def test_promises_for_vanished_media_are_pruned(self):
        # The file can leave by other routes - Steam's own media tab, the
        # desktop, a card swap - and then nothing would ever clear this.
        self.qs.want_delete("/x/gone.jpg")
        self.qs.want_delete("/x/here.jpg")
        n = self.qs.prune_delete_promises(exists=lambda p: p == "/x/here.jpg")
        self.assertEqual(1, n)
        self.assertFalse(self.qs.wants_delete("/x/gone.jpg"))
        self.assertTrue(self.qs.wants_delete("/x/here.jpg"))

    def test_pruning_rewrites_the_file(self):
        self.qs.want_delete("/x/gone.jpg")
        self.qs.want_delete("/x/here.jpg")
        self.qs.prune_delete_promises(exists=lambda p: p == "/x/here.jpg")
        fresh = QueueState(self.tmp)
        self.assertFalse(fresh.wants_delete("/x/gone.jpg"))
        self.assertTrue(fresh.wants_delete("/x/here.jpg"))

    def test_pruning_nothing_is_a_no_op(self):
        self.qs.want_delete("/x/here.jpg")
        self.assertEqual(0, self.qs.prune_delete_promises(exists=lambda p: True))
        self.assertTrue(self.qs.wants_delete("/x/here.jpg"))

    def test_pruning_an_empty_list_is_fine(self):
        self.assertEqual(0, self.qs.prune_delete_promises(exists=lambda p: False))


if __name__ == "__main__":
    unittest.main()
