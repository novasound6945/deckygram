"""Where media goes.

Telegram is the primary destination - it is what the plugin is named
after and what the setup wizard leads with.  Discord is the lighter
alternative for people who share screenshots in a channel and do not want
to create a bot at all; picking it skips the Telegram setup entirely.

Everything above this layer (the watcher, the sender) talks to a
Destination and never to a specific service.
"""

from . import discord, media, tg
from .errors import Unsendable   # noqa: F401  (re-exported for callers)

TELEGRAM = "telegram"
DISCORD = "discord"


class Destination:
    """Common shape: is it set up, can it take this clip, send this file."""

    name = ""

    def __init__(self, settings: dict):
        # The frame and the rate are one choice from a table, stored as
        # two keys.  The rate is used exactly as picked - scaling it by
        # the frame rate would make the label a lie - while the frame
        # rate decides how many pictures those bits have to cover, and
        # so when a clip stops being worth sending at all.
        self.fps = int(settings.get("video_fps") or media.BASE_FPS)
        self.height = media.pick_height(settings.get("clip_height"))
        self.bitrate = media.pick_bitrate(settings.get("clip_bitrate"),
                                          settings.get("clip_preset"), self.height)
        self.floor = media.floor_for(self.fps)

    def configured(self) -> bool:
        raise NotImplementedError

    def max_clip_seconds(self) -> int:
        """Longest clip worth sending here at the chosen frame rate."""
        return media.max_seconds(self.size_target(), self.floor)

    def max_height(self) -> int:
        """Frame height cap, as chosen."""
        return self.height

    def encode_args(self) -> dict:
        """What the encoder is asked for: bits, frames, and a size cap."""
        return {"bitrate": self.bitrate,
                "maxh": self.max_height(),
                "fps": self.fps,
                "floor": self.floor}

    def estimate(self, duration_sec: int = 60) -> dict:
        """What a clip of this length would weigh here - see media.estimate."""
        return media.estimate(self.size_target(), self.hard_limit(),
                              duration_sec, self.bitrate, self.floor)

    def hopeless(self, duration_sec: int) -> bool:
        """True when a clip of this length cannot fit, however encoded."""
        return media.hopeless(self.size_target(), duration_sec, self.floor)

    def size_target(self) -> int:
        """Roughly what an uploaded clip will weigh - used for queue estimates."""
        raise NotImplementedError

    def hard_limit(self) -> int:
        """The size the destination will actually refuse past."""
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
        super().__init__(settings)
        self.token = settings.get("token") or ""
        self.chat_id = settings.get("chat_id") or ""
        # Telegram re-encodes screenshots sent as photos; this asks for
        # the file as taken instead.  Discord needs no such switch - a
        # webhook upload is already the original bytes.
        self.original_photos = bool(settings.get("photo_original"))

    def configured(self):
        return bool(self.token and self.chat_id)

    def size_target(self):
        return tg.SIZE_TARGET

    def hard_limit(self):
        return tg.BOT_LIMIT

    def send(self, path, caption, **kw):
        kw.update(self.encode_args())
        tg.send_media(self.token, self.chat_id, path, caption,
                      original=self.original_photos, **kw)

    def send_album(self, paths, caption, **kw):
        tg.send_photo_album(self.token, self.chat_id, paths, caption,
                            original=self.original_photos)

    def test(self):
        tg.api_call(self.token, "sendMessage",
                    {"chat_id": self.chat_id,
                     "text": "Deckygram connected. Screenshots will arrive here."},
                    timeout=15)


class Discord(Destination):
    name = DISCORD

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.url = (settings.get("webhook_url") or "").strip()

    def configured(self):
        return discord.valid_url(self.url)

    def size_target(self):
        return discord.SIZE_TARGET

    def hard_limit(self):
        return discord.SIZE_LIMIT

    def max_height(self):
        # The budget here is a fifth of Telegram's - a minute has about
        # 1.1 Mbit/s to work with - so a taller choice than this cannot
        # pay for itself, whatever was picked.
        return min(super().max_height(), discord.HEIGHT_CAP)

    def send(self, path, caption, **kw):
        kw.update(self.encode_args())
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
