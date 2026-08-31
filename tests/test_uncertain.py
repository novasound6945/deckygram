"""A send with no verdict must not be retried.

Telegram accepted a 43 MB clip and still answered 504; the retry logic
read that as failure and delivered the clip five times (2026-09-01).
The rule these tests pin down: if the body was already on the wire, the
outcome is unknown, and unknown means stop - never resend.
"""

import unittest
import urllib.error

from py_modules.deckygram import net, tg
from py_modules.deckygram.errors import SendError, Uncertain


class ExceptionShape(unittest.TestCase):
    def test_uncertain_is_a_send_error(self):
        # Callers that only know SendError must still catch it.
        self.assertTrue(issubclass(Uncertain, SendError))

    def test_uncertain_is_distinct_from_plain_failure(self):
        self.assertIsNot(Uncertain, SendError)

    def test_timeout_is_not_unreachable(self):
        # The whole fix rests on telling these two apart.
        self.assertFalse(issubclass(net.Timeout, net.Unreachable))


class ApiCallClassification(unittest.TestCase):
    """tg.api_call turns transport failures into the right verdict."""

    def setUp(self):
        self.real = net.request
        self.addCleanup(setattr, net, "request", self.real)

    def fail_with(self, exc):
        def stub(*a, **kw):
            raise exc
        net.request = stub

    def respond(self, status, payload):
        def stub(*a, **kw):
            return status, payload
        net.request = stub

    def test_timeout_while_uploading_is_uncertain(self):
        self.fail_with(net.Timeout("timed out"))
        with self.assertRaises(Uncertain):
            tg.api_call("t", "sendVideo", files={"video": "x.mp4"})

    def test_timeout_without_upload_is_retryable(self):
        # No file went out, so nothing can have been delivered twice.
        self.fail_with(net.Timeout("timed out"))
        with self.assertRaises(SendError) as cm:
            tg.api_call("t", "getMe")
        self.assertNotIsInstance(cm.exception, Uncertain)

    def test_unreachable_stays_retryable_even_with_files(self):
        # The request never left the Deck.
        self.fail_with(net.Unreachable("connection refused"))
        with self.assertRaises(SendError) as cm:
            tg.api_call("t", "sendVideo", files={"video": "x.mp4"})
        self.assertNotIsInstance(cm.exception, Uncertain)

    def test_gateway_errors_while_uploading_are_uncertain(self):
        for status in (502, 503, 504):
            self.respond(status, None)
            with self.assertRaises(Uncertain, msg=str(status)):
                tg.api_call("t", "sendVideo", files={"video": "x.mp4"})

    def test_gateway_errors_without_upload_are_retryable(self):
        self.respond(504, None)
        with self.assertRaises(SendError) as cm:
            tg.api_call("t", "getMe")
        self.assertNotIsInstance(cm.exception, Uncertain)

    def test_client_errors_are_not_uncertain(self):
        # 400 is a real verdict: Telegram looked at it and said no.
        self.respond(400, None)
        with self.assertRaises(SendError) as cm:
            tg.api_call("t", "sendVideo", files={"video": "x.mp4"})
        self.assertNotIsInstance(cm.exception, Uncertain)


class RequestTimeoutMapping(unittest.TestCase):
    """net.request maps the underlying error to Timeout vs Unreachable."""

    def setUp(self):
        self.real = net.urllib.request.urlopen
        self.addCleanup(setattr, net.urllib.request, "urlopen", self.real)

    def raise_from_urlopen(self, exc):
        def stub(*a, **kw):
            raise exc
        net.urllib.request.urlopen = stub

    def test_socket_timeout_becomes_timeout(self):
        self.raise_from_urlopen(TimeoutError("timed out"))
        with self.assertRaises(net.Timeout):
            net.request("https://example.invalid/x", fields={"a": "b"})

    def test_urlerror_wrapping_a_timeout_becomes_timeout(self):
        self.raise_from_urlopen(urllib.error.URLError(TimeoutError()))
        with self.assertRaises(net.Timeout):
            net.request("https://example.invalid/x", fields={"a": "b"})

    def test_other_urlerror_stays_unreachable(self):
        self.raise_from_urlopen(urllib.error.URLError("no route to host"))
        with self.assertRaises(net.Unreachable):
            net.request("https://example.invalid/x", fields={"a": "b"})


if __name__ == "__main__":
    unittest.main()
