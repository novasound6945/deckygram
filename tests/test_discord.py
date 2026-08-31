"""Discord webhook backend: URL validation, payload shape, error mapping."""

import json
import os
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import destinations, discord
from deckygram.errors import SendError, SetupBroken, Unsendable


class TestUrlValidation(unittest.TestCase):
    GOOD = "https://discord.com/api/webhooks/123456789012345678/abcDEF-_123"

    def test_accepts_a_normal_webhook_url(self):
        self.assertTrue(discord.valid_url(self.GOOD))

    def test_accepts_discordapp_and_versioned_paths(self):
        self.assertTrue(discord.valid_url(
            "https://discordapp.com/api/webhooks/1/tok"))
        self.assertTrue(discord.valid_url(
            "https://discord.com/api/v10/webhooks/1/tok"))

    def test_accepts_a_trailing_slash(self):
        self.assertTrue(discord.valid_url(self.GOOD + "/"))

    def test_rejects_a_channel_link(self):
        # What someone pastes if they copy the wrong thing.
        self.assertFalse(discord.valid_url(
            "https://discord.com/channels/123/456"))

    def test_rejects_plain_http(self):
        self.assertFalse(discord.valid_url(self.GOOD.replace("https", "http")))

    def test_rejects_another_host(self):
        self.assertFalse(discord.valid_url(
            "https://evil.example.com/api/webhooks/1/tok"))

    def test_rejects_empty(self):
        self.assertFalse(discord.valid_url(""))
        self.assertFalse(discord.valid_url(None))


class TestErrorMapping(unittest.TestCase):
    def test_deleted_webhook_is_fatal(self):
        # The common one: someone removed the webhook or its channel.
        with self.assertRaises(SetupBroken):
            discord._check(404, {"message": "Unknown Webhook"})

    def test_forbidden_is_fatal(self):
        with self.assertRaises(SetupBroken):
            discord._check(403, {"message": "Missing Permissions"})

    def test_too_large_is_unsendable(self):
        with self.assertRaises(Unsendable):
            discord._check(413, {"message": "Request entity too large"})

    def test_rate_limit_carries_retry_after(self):
        with self.assertRaises(SendError) as cm:
            discord._check(429, {"message": "You are being rate limited",
                                 "retry_after": 4.5})
        self.assertNotIsInstance(cm.exception, SetupBroken)
        self.assertEqual(cm.exception.retry_after, 4)

    def test_server_error_is_retryable(self):
        with self.assertRaises(SendError) as cm:
            discord._check(500, None)
        self.assertNotIsInstance(cm.exception, SetupBroken)

    def test_success_raises_nothing(self):
        self.assertIsNone(discord._check(204, None))


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, url, fields=None, files=None, json_body=None, timeout=600):
        self.calls.append({"url": url, "fields": fields or {},
                           "files": files or {}, "json": json_body})
        return 204, None


class TestPayload(unittest.TestCase):
    URL = "https://discord.com/api/webhooks/1/tok"

    def setUp(self):
        self.rec = Recorder()
        self._real = discord.net.request
        discord.net.request = self.rec
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        discord.net.request = self._real
        self.tmp.cleanup()

    def _shot(self, name="a.jpg", size=128):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(b"\xff\xd8\xff" + b"0" * size)
        return p

    def test_album_sends_numbered_file_fields(self):
        paths = [self._shot("a.jpg"), self._shot("b.jpg")]
        discord.send_album(self.URL, paths, "Steam · now (2)")
        call = self.rec.calls[-1]
        self.assertEqual(sorted(call["files"]), ["files[0]", "files[1]"])

    def test_caption_travels_in_payload_json(self):
        discord.send_album(self.URL, [self._shot(), self._shot("b.jpg")], "hello")
        payload = json.loads(self.rec.calls[-1]["fields"]["payload_json"])
        self.assertEqual(payload["content"], "hello")

    def test_mentions_are_suppressed(self):
        # A game called "@everyone" must not ping a channel.
        discord.send_album(self.URL, [self._shot(), self._shot("b.jpg")],
                           "@everyone · now")
        payload = json.loads(self.rec.calls[-1]["fields"]["payload_json"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_album_caps_at_ten(self):
        paths = [self._shot("s%d.jpg" % i) for i in range(15)]
        discord.send_album(self.URL, paths, "many")
        self.assertEqual(len(self.rec.calls[-1]["files"]), 10)

    def test_oversized_image_is_skipped_not_retried(self):
        big = os.path.join(self.tmp.name, "big.png")
        with open(big, "wb") as f:
            f.truncate(discord.SIZE_LIMIT + 1)
        with self.assertRaises(Unsendable):
            discord.send_media(self.URL, big, "cap")

    def test_album_drops_oversized_members_but_sends_the_rest(self):
        ok = self._shot("ok.jpg")
        big = os.path.join(self.tmp.name, "big.png")
        with open(big, "wb") as f:
            f.truncate(discord.SIZE_LIMIT + 1)
        discord.send_album(self.URL, [ok, big], "cap")
        self.assertEqual(list(self.rec.calls[-1]["files"]), ["files[0]"])

    def test_empty_album_sends_nothing(self):
        discord.send_album(self.URL, [], "cap")
        self.assertEqual(self.rec.calls, [])


class TestUserAgent(unittest.TestCase):
    """Cloudflare 403s (error 1010) every request that says Python-urllib."""

    def test_every_request_shape_identifies_itself(self):
        from deckygram import net
        seen = {}

        class FakeRequest:
            def __init__(self, url, data=None, headers=None):
                seen.clear()
                seen.update(headers or {})

        real = net.urllib.request.Request
        net.urllib.request.Request = FakeRequest
        try:
            for kwargs in ({"json_body": {"a": 1}}, {"fields": {"a": 1}}, {}):
                try:
                    net.request("https://discord.com/api/webhooks/1/t", **kwargs)
                except Exception:
                    pass    # urlopen will reject our fake; headers already set
                self.assertIn("User-Agent", seen, str(kwargs))
                self.assertNotIn("urllib", seen["User-Agent"].lower())
        finally:
            net.urllib.request.Request = real


class TestDestinationSelection(unittest.TestCase):
    def test_defaults_to_telegram(self):
        d = destinations.build({})
        self.assertEqual(d.name, destinations.TELEGRAM)

    def test_discord_selected_by_setting(self):
        d = destinations.build({"destination": "discord",
                                "webhook_url": "https://discord.com/api/webhooks/1/t"})
        self.assertEqual(d.name, destinations.DISCORD)
        self.assertTrue(d.configured())

    def test_discord_without_a_url_is_not_configured(self):
        self.assertFalse(destinations.build({"destination": "discord"}).configured())

    def test_telegram_needs_both_token_and_chat(self):
        self.assertFalse(destinations.build({"token": "t"}).configured())
        self.assertTrue(destinations.build({"token": "t", "chat_id": "1"}).configured())

    def test_discord_user_needs_no_telegram_setup(self):
        # The whole point: picking Discord skips the bot flow entirely.
        s = {"destination": "discord",
             "webhook_url": "https://discord.com/api/webhooks/1/t",
             "token": "", "chat_id": ""}
        self.assertTrue(destinations.build(s).configured())


if __name__ == "__main__":
    unittest.main()
