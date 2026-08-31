"""Failure vocabulary shared by every destination.

The watcher only needs to know three things about a failed send:
  - can it be retried at all          -> SendError
  - is the setup itself refused       -> SetupBroken (stop, ask the user)
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


class Unsendable(Exception):
    """Permanently unsendable (too big even after compression) - skip it."""
