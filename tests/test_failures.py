"""Error classification and the retry budget.

These cover the cases a user actually hits when something changes on the
Telegram side: a regenerated token, a deleted or blocked bot, rate
limiting, and plain "the Wi-Fi dropped".
"""

import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import tg
from deckygram.qstate import QueueState
from deckygram.sender import Sender, MAX_ATTEMPTS


class TestClassify(unittest.TestCase):
    def test_unauthorized_is_fatal(self):
        # Token regenerated in BotFather, or the bot was deleted.
        self.assertIs(tg.classify("Unauthorized", 401), tg.SetupBroken)

    def test_blocked_by_user_is_fatal(self):
        self.assertIs(tg.classify("Forbidden: bot was blocked by the user", 403),
                      tg.SetupBroken)

    def test_chat_not_found_is_fatal_despite_400(self):
        self.assertIs(tg.classify("Bad Request: chat not found", 400),
                      tg.SetupBroken)

    def test_other_bad_requests_stay_retryable(self):
        self.assertIs(tg.classify("Bad Request: group send failed", 400),
                      tg.TelegramError)

    def test_rate_limit_is_retryable(self):
        self.assertIs(tg.classify("Too Many Requests: retry after 30", 429),
                      tg.TelegramError)

    def test_server_error_is_retryable(self):
        self.assertIs(tg.classify("Internal Server Error", 500), tg.TelegramError)

    def test_setup_broken_is_catchable_as_telegram_error(self):
        # Existing `except tg.TelegramError` handlers must still fire.
        self.assertTrue(issubclass(tg.SetupBroken, tg.TelegramError))


class SenderHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.qs = QueueState(self.tmp.name)
        self.notes = []
        self.status = {"failed": 0, "last_error": "", "setup_broken": ""}
        self.sender = Sender(
            self.qs, self.tmp.name,
            lambda: {"token": "t", "chat_id": "1"},
            resolver=None,
            notify=lambda *a: self.notes.append(a),
            status=self.status)

    def tearDown(self):
        self.tmp.cleanup()


class TestFailureHandling(SenderHarness):
    def test_network_error_is_not_fatal(self):
        fatal = self.sender._note_failure(tg.TelegramError("<urlopen error>"))
        self.assertFalse(fatal)
        self.assertEqual(self.status["setup_broken"], "")
        self.assertFalse(self.sender.blocked())

    def test_network_error_message_is_readable(self):
        self.sender._note_failure(tg.TelegramError("<urlopen error timed out>"))
        self.assertIn("Network error", self.status["last_error"])

    def test_broken_setup_suspends_sending(self):
        fatal = self.sender._note_failure(tg.SetupBroken("Unauthorized", code=401))
        self.assertTrue(fatal)
        self.assertTrue(self.sender.blocked())
        self.assertEqual(self.status["setup_broken"], "Unauthorized")

    def test_broken_setup_notifies_once(self):
        for _ in range(3):
            self.sender._note_failure(tg.SetupBroken("Unauthorized", code=401))
        self.assertEqual(len(self.notes), 1)

    def test_clear_broken_resumes(self):
        self.sender._note_failure(tg.SetupBroken("Unauthorized", code=401))
        self.sender.clear_broken()
        self.assertFalse(self.sender.blocked())
        self.assertEqual(self.status["setup_broken"], "")

    def test_rate_limit_pauses_for_the_requested_time(self):
        self.sender._note_failure(
            tg.TelegramError("Too Many Requests", code=429, retry_after=30))
        self.assertTrue(self.sender.blocked())


class TestRetryBudget(SenderHarness):
    def test_attempts_are_counted_per_item(self):
        for i in range(1, 4):
            self.assertEqual(self.qs.note_attempt("/a/x.jpg"), i)
        self.assertEqual(self.qs.note_attempt("/a/y.jpg"), 1)

    def test_give_up_keeps_the_item_unsent(self):
        self.qs.queue("/a/x.jpg")
        self.qs.give_up("/a/x.jpg")
        self.assertNotIn("/a/x.jpg", self.qs.pending)   # no more auto retries
        self.assertNotIn("/a/x.jpg", self.qs.sent)      # but NOT written off
        self.assertEqual(self.qs.stalled(), 1)

    def test_revive_all_forgets_the_budget(self):
        self.qs.note_attempt("/a/x.jpg")
        self.qs.give_up("/a/x.jpg")
        self.qs.revive_all()
        self.assertEqual(self.qs.stalled(), 0)
        self.assertEqual(self.qs.note_attempt("/a/x.jpg"), 1)

    def test_success_clears_the_budget(self):
        self.qs.note_attempt("/a/x.jpg")
        self.qs.give_up("/a/x.jpg")
        self.qs.mark_sent("/a/x.jpg")
        self.assertEqual(self.qs.stalled(), 0)
        self.assertNotIn("/a/x.jpg", self.qs.attempts)

    def test_budget_is_five(self):
        self.assertEqual(MAX_ATTEMPTS, 5)


class TestStalledPersistence(unittest.TestCase):
    """A restart must not silently write off media we promised to keep."""

    def test_stalled_list_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.give_up("/a/x.jpg")
            self.assertIn("/a/x.jpg", QueueState(d).gave_up)

    def test_delivering_it_later_clears_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.give_up("/a/x.jpg")
            qs.mark_sent("/a/x.jpg")
            fresh = QueueState(d)
            self.assertEqual(fresh.gave_up, set())
            self.assertIn("/a/x.jpg", fresh.sent)

    def test_skip_all_clears_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            qs = QueueState(d)
            qs.give_up("/a/x.jpg")
            qs.revive_all()
            self.assertEqual(QueueState(d).gave_up, set())


if __name__ == "__main__":
    unittest.main()
