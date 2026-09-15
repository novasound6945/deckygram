"""The pairing page, spoken over a plain socket.

http.server is not always there: Decky's prerelease loader ships a
trimmed Python and importing it took the whole plugin down. These drive
the real server over a real socket, because the point of the rewrite was
that it answers a browser correctly without that module.
"""

import unittest
import urllib.error
import urllib.parse
import urllib.request

from . import context  # noqa: F401
from deckygram import pairing


class PairingTest(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.fail_with = None
        self.server = pairing.PairingServer(
            on_token=self.accept_token, on_webhook=self.accept_webhook)

    def tearDown(self):
        self.server.stop()

    def accept_token(self, token):
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        self.seen.append(token)
        return "my_test_bot"

    def accept_webhook(self, url):
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        self.seen.append(url)

    def start(self, mode="telegram"):
        state = self.server.start(mode)
        # Answer on the loopback rather than the LAN address it shows.
        rest = state["url"].split("//", 1)[1]
        hostport, _, path = rest.partition("/")
        self.port = int(hostport.split(":")[1])
        self.path = path
        return state

    def get(self, path=None):
        return self.fetch(path if path is not None else self.path)

    def post(self, fields, path=None):
        body = urllib.parse.urlencode(fields).encode()
        return self.fetch(path if path is not None else self.path, body)

    def fetch(self, path, body=None):
        url = "http://127.0.0.1:%d/%s" % (self.port, path)
        req = urllib.request.Request(url, data=body)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")


class TestServing(PairingTest):
    def test_it_starts_without_http_server(self):
        self.assertNotIn("http.server", dir(pairing))
        self.assertEqual(self.start()["status"], "waiting")

    def test_the_form_is_served_on_the_nonce(self):
        self.start()
        code, page = self.get()
        self.assertEqual(code, 200)
        self.assertIn("BotFather", page)
        self.assertIn("<form method=\"post\">", page)

    def test_any_other_path_is_a_404(self):
        self.start()
        code, page = self.get("nope")
        self.assertEqual(code, 404)
        self.assertIn("Not found", page)

    def test_a_trailing_slash_is_the_same_page(self):
        self.start()
        self.assertEqual(self.get(self.path + "/")[0], 200)

    def test_a_query_string_does_not_break_the_match(self):
        self.start()
        self.assertEqual(self.get(self.path + "?utm=1")[0], 200)

    def test_discord_mode_serves_the_webhook_page(self):
        self.start("discord")
        code, page = self.get()
        self.assertEqual(code, 200)
        self.assertIn("Copy Webhook URL", page)


class TestAccepting(PairingTest):
    def test_a_token_is_handed_over_and_the_bot_is_named(self):
        self.start()
        code, page = self.post({"token": "123:AAtoken"})
        self.assertEqual(code, 200)
        self.assertEqual(self.seen, ["123:AAtoken"])
        self.assertIn("my_test_bot", page)
        self.assertEqual(self.server.state["status"], "done")

    def test_whitespace_around_the_token_is_dropped(self):
        self.start()
        self.post({"token": "  123:AAtoken \n"})
        self.assertEqual(self.seen, ["123:AAtoken"])

    def test_a_webhook_is_handed_over(self):
        self.start("discord")
        code, page = self.post({"webhook": "https://discord.com/api/webhooks/1/t"})
        self.assertEqual(code, 200)
        self.assertEqual(self.seen, ["https://discord.com/api/webhooks/1/t"])
        self.assertEqual(self.server.state["status"], "done")

    def test_a_rejected_token_shows_the_reason_and_the_form_again(self):
        self.start()
        self.fail_with = "not a bot token"
        code, page = self.post({"token": "nonsense"})
        self.assertEqual(code, 200)
        self.assertIn("not a bot token", page)
        self.assertIn("<form method=\"post\">", page)
        self.assertEqual(self.server.state["status"], "waiting")

    def test_a_rejection_message_is_escaped(self):
        self.start()
        self.fail_with = "<script>alert(1)</script>"
        _, page = self.post({"token": "x"})
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_a_post_to_the_wrong_path_hands_nothing_over(self):
        self.start()
        self.assertEqual(self.post({"token": "123:AA"}, "nope")[0], 404)
        self.assertEqual(self.seen, [])

    def test_an_empty_form_is_still_a_rejection_not_a_crash(self):
        self.start()
        self.fail_with = "empty"
        self.assertEqual(self.post({})[0], 200)
        self.assertEqual(self.server.state["status"], "waiting")


class TestLifecycle(PairingTest):
    def test_stop_closes_the_port(self):
        self.start()
        self.server.stop()
        with self.assertRaises(Exception):
            self.get()

    def test_starting_again_moves_to_a_new_nonce(self):
        first = self.start()["url"]
        second = self.start()["url"]
        self.assertNotEqual(first, second)


class TestSurvivesATrimmedPython(unittest.TestCase):
    """One missing stdlib module must not take the plugin down.

    Decky's prerelease loader ships a Python without http.server, and
    importing it stopped Deckygram from loading at all. Anything else we
    reach for that a trimmed build might drop has to degrade instead.
    """

    def test_inotify_falls_back_to_polling_without_ctypes(self):
        from deckygram import inotify
        real, inotify.ctypes = inotify.ctypes, None
        try:
            watcher = inotify.Inotify()
            self.assertFalse(watcher.active)
            self.assertEqual(watcher.watched, 0)
            watcher.watch("/tmp")          # must not raise
            self.assertEqual(watcher.poll(0), [])
            watcher.close()
        finally:
            inotify.ctypes = real

    def test_inotify_works_normally_when_ctypes_is_there(self):
        from deckygram import inotify
        if inotify.ctypes is None:
            self.skipTest("this Python has no ctypes either")
        self.assertTrue(inotify.Inotify().active)


if __name__ == "__main__":
    unittest.main()
