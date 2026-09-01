"""What "delete this" resolves to, per item state.

Two failures matter here and they pull in opposite directions:

  - deleting a file that is being uploaded right now breaks that send
  - deferring a delete that will never happen drops the user's instruction

So each state is pinned explicitly rather than left to whatever the
if-chain happens to do.
"""

import unittest

from py_modules.deckygram import deletion
from py_modules.deckygram.deletion import AFTER_SEND, GONE, NOW


class Classify(unittest.TestCase):
    def test_idle_item_goes_now(self):
        self.assertEqual(NOW, deletion.classify(exists=True))

    def test_missing_file_is_gone(self):
        self.assertEqual(GONE, deletion.classify(exists=False))

    def test_in_flight_waits_for_the_send(self):
        # Pulling the file out from under an upload fails the send.
        self.assertEqual(
            AFTER_SEND, deletion.classify(exists=True, in_flight=True))

    def test_queued_with_sending_on_waits(self):
        self.assertEqual(AFTER_SEND, deletion.classify(
            exists=True, pending=True, sending_active=True))

    def test_queued_with_sending_off_goes_now(self):
        # The queue is not moving, so "after sending" would be never.
        self.assertEqual(NOW, deletion.classify(
            exists=True, pending=True, sending_active=False))

    def test_in_flight_beats_sending_switched_off(self):
        # Whatever the settings say, something is reading that file now.
        self.assertEqual(AFTER_SEND, deletion.classify(
            exists=True, in_flight=True, sending_active=False))

    def test_missing_file_beats_everything(self):
        # Nothing to delete, whatever else is true of it.
        self.assertEqual(GONE, deletion.classify(
            exists=False, in_flight=True, pending=True, sending_active=True))

    def test_not_queued_goes_now_even_while_sending_runs(self):
        # Sending being on does not by itself defer an idle item.
        self.assertEqual(NOW, deletion.classify(
            exists=True, pending=False, sending_active=True))


class Plan(unittest.TestCase):
    def state_for(self, table):
        return lambda item: table.get(item)

    def test_sorts_a_mixed_selection(self):
        table = {
            "idle": {"exists": True},
            "sending": {"exists": True, "in_flight": True},
            "queued": {"exists": True, "pending": True, "sending_active": True},
            "vanished": {"exists": False},
        }
        got = deletion.plan(
            ["idle", "sending", "queued", "vanished"], self.state_for(table))
        self.assertEqual(["idle"], got[NOW])
        self.assertEqual(["sending", "queued"], got[AFTER_SEND])
        self.assertEqual(["vanished"], got[GONE])

    def test_keeps_the_callers_order(self):
        table = {str(i): {"exists": True} for i in range(5)}
        got = deletion.plan(["3", "1", "4", "0", "2"], self.state_for(table))
        self.assertEqual(["3", "1", "4", "0", "2"], got[NOW])

    def test_unknown_item_is_treated_as_gone(self):
        # The gallery page is a snapshot; an id can be stale by now.
        got = deletion.plan(["ghost"], lambda _: None)
        self.assertEqual(["ghost"], got[GONE])

    def test_empty_selection_gives_empty_buckets(self):
        got = deletion.plan([], lambda _: {})
        self.assertEqual({NOW: [], AFTER_SEND: [], GONE: []}, got)

    def test_every_item_lands_in_exactly_one_bucket(self):
        table = {
            "a": {"exists": True},
            "b": {"exists": True, "in_flight": True},
            "c": {"exists": False},
            "d": {"exists": True, "pending": True, "sending_active": True},
        }
        items = list(table)
        got = deletion.plan(items, self.state_for(table))
        placed = got[NOW] + got[AFTER_SEND] + got[GONE]
        self.assertEqual(sorted(items), sorted(placed))
        self.assertEqual(len(items), len(placed))


if __name__ == "__main__":
    unittest.main()
