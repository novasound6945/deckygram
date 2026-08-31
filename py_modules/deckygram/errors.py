"""Failure vocabulary shared by every destination.

The watcher only needs to know four things about a failed send:
  - can it be retried at all          -> SendError
  - is the setup itself refused       -> SetupBroken (stop, ask the user)
  - did it maybe already arrive       -> Uncertain (stop, do NOT resend)
  - is this one file simply impossible -> Unsendable (skip it, move on)
"""


class SendError(Exception):
    """A send failed but retrying may work (network, rate limit, 5xx).

    `code` is the HTTP/API status when there was one, `retry_after` the
    cooldown the service asked for.
    """

    def __init__(self, message, code=None, retry_after=0):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class SetupBroken(SendError):
    """The destination refuses this bot/chat/webhook outright.

    A revoked token, a deleted bot, a blocked bot, a missing chat, or a
    deleted webhook.  Retrying cannot help, so the caller must stop and
    tell the user instead of hammering the API.
    """


class Uncertain(SendError):
    """The upload went out but no verdict came back.

    A timeout or a 5xx *after the body is on the wire* does not mean the
    service refused it - Telegram in particular accepts a large file and
    still answers 504. Retrying then delivers it again: one 43 MB clip
    reached a user five times this way (2026-09-01).

    So this is the one failure that must not be retried automatically.
    Keep the media, say so, and let the user decide once they have looked
    at the chat.
    """


class Unsendable(Exception):
    """Permanently unsendable (too big even after compression) - skip it."""
