"""Where media goes.

Telegram is the primary destination - it is what the plugin is named
after and what the setup wizard leads with.  Discord is the lighter
alternative for people who share screenshots in a channel and do not want
to create a bot at all; picking it skips the Telegram setup entirely.

Everything above this layer (the watcher, the sender) talks to a
Destination and never to a specific service.
"""

from . import discord, tg
from .errors import Unsendable   # noqa: F401  (re-exported for callers)

TELEGRAM = "telegram"
DISCORD = "discord"


class Destination:
    """Common shape: is it set up, can it take this clip, send this file."""

    name = ""

    def configured(self) -> bool:
        raise NotImplementedError

    def hopeless(self, duration_sec: int) -> bool:
        """True when a clip of this length cannot fit, however encoded."""
        raise NotImplementedError

    def size_target(self) -> int:
        """Roughly what an uploaded clip will weigh - used for queue estimates."""
        raise NotImplementedError

    def send(self, path, caption, **kw) -> None:
        raise NotImplementedError

    def send_album(self, paths, caption, **kw) -> None:
        raise NotImplementedError

    def test(self) -> None:
        """Send a hello message; raises on failure."""
        raise NotImplementedError


class Telegram(Destination):
    name = TELEGRAM

    def __init__(self, settings: dict):
        self.token = settings.get("token") or ""
        self.chat_id = settings.get("chat_id") or ""

    def configured(self):
        return bool(self.token and self.chat_id)

    def hopeless(self, duration_sec):
        return tg.hopeless(duration_sec)

    def size_target(self):
        return tg.SIZE_TARGET

    def send(self, path, caption, **kw):
        tg.send_media(self.token, self.chat_id, path, caption, **kw)

    def send_album(self, paths, caption, **kw):
        tg.send_photo_album(self.token, self.chat_id, paths, caption)

    def test(self):
        tg.api_call(self.token, "sendMessage",
                    {"chat_id": self.chat_id,
                     "text": "Deckygram connected. Screenshots will arrive here."},
                    timeout=15)


class Discord(Destination):
    name = DISCORD

    def __init__(self, settings: dict):
        self.url = (settings.get("webhook_url") or "").strip()

    def configured(self):
        return discord.valid_url(self.url)

    def hopeless(self, duration_sec):
        return discord.hopeless(duration_sec)

    def size_target(self):
        return discord.SIZE_TARGET

    def send(self, path, caption, **kw):
        discord.send_media(self.url, path, caption, **kw)

    def send_album(self, paths, caption, **kw):
        discord.send_album(self.url, paths, caption)

    def test(self):
        discord.send_test(self.url)


def build(settings: dict) -> Destination:
    """Destination for the current settings; Telegram unless told otherwise."""
    if (settings.get("destination") or TELEGRAM) == DISCORD:
        return Discord(settings)
    return Telegram(settings)
