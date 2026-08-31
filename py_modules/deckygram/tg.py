"""Telegram Bot API client - the plugin's primary destination.

Stdlib only (urllib + the shared multipart encoder in net.py) so the
plugin has zero Python dependencies.  Video compression lives in
media.py, shared with the other destinations; Telegram's share of it is
just the size budget: 50 MB per upload, aimed at 45 MB for headroom.

sendVideo is always given width/height/duration/supports_streaming:
without them Telegram's player guesses the size and the aspect ratio
looks squashed.
"""

import json
import os

from . import media, net
from .errors import SendError, SetupBroken, Uncertain, Unsendable

API = "https://api.telegram.org/bot%s/%s"

# Kept as module attributes: appname.py and updates.py reach for the
# shared TLS context through here, and the plugin has been shipping that
# way since before there was a net module.
_SSL_CTX = net.SSL_CTX
_multipart = net.multipart

BOT_LIMIT = 50 * 1024 * 1024
SIZE_TARGET = 45 * 1024 * 1024   # leave headroom under the hard limit

# Media handling is shared with the other destinations; these aliases keep
# the long-standing tg.IMAGE_EXT / tg.VIDEO_EXT spellings working.
IMAGE_EXT = media.IMAGE_EXT
VIDEO_EXT = media.VIDEO_EXT


def fit_bitrate(duration_sec: int, desired: int) -> int:
    return media.fit_bitrate(SIZE_TARGET, duration_sec, desired)


def hopeless(duration_sec: int, floor: int = media.MIN_BITRATE) -> bool:
    return media.hopeless(SIZE_TARGET, duration_sec, floor)


# Telegram's errors are the shared ones; the old name stays as an alias
# because main.py and the pairing flow catch TelegramError by name.
TelegramError = SendError


# Telegram's own wording for the config-level rejections.  Codes alone are
# not enough: 400 covers both "your chat is gone" (fatal) and "this photo
# is invalid" (skip just this file).
_BROKEN_PHRASES = (
    "chat not found",
    "chat_id is empty",
    "bot was blocked",
    "user is deactivated",
    "bot was kicked",
    "peer_id_invalid",
    "not enough rights",
)


def classify(description: str, code):
    """Return the exception class to raise for a Telegram error reply."""
    low = (description or "").lower()
    if code in (401, 403) or any(p in low for p in _BROKEN_PHRASES):
        return SetupBroken
    return TelegramError


# ----------------------------------------------------------------- HTTP layer

def api_call(token: str, method: str, fields: dict = None, files: dict = None,
             timeout: int = None) -> dict:
    """`timeout` defaults to one net.py sizes from the upload itself."""
    uploading = bool(files)
    try:
        status, payload = net.request(API % (token, method), fields=fields,
                                      files=files, timeout=timeout)
    except net.Unreachable as e:
        # The request never left: no Telegram verdict, always retryable.
        raise TelegramError(str(e))
    except net.Timeout as e:
        # It did leave. If it carried a file, Telegram may have taken it
        # even though we never heard back, so resending would duplicate.
        raise (Uncertain if uploading else TelegramError)(str(e))
    if payload is None:
        if uploading and status in (502, 503, 504):
            # Same reasoning: a gateway giving up on us says nothing about
            # what the upload backend did with the file.
            raise Uncertain("HTTP %s" % status, code=status)
        raise classify("", status)("HTTP %s" % status, code=status)
    if not payload.get("ok"):
        desc = payload.get("description", "unknown error")
        code = payload.get("error_code")
        retry_after = (payload.get("parameters") or {}).get("retry_after", 0)
        raise classify(desc, code)(desc, code=code, retry_after=retry_after)
    return payload.get("result", {})


# ------------------------------------------------------------------- sending

def send_media(token: str, chat_id: str, path: str, caption: str,
               bitrate: int = 2_000_000, fps: int = 30, maxh: int = 600,
               progress=None, phase=None,
               floor: int = media.MIN_BITRATE) -> None:
    """Send one file. Raises TelegramError (retryable) or Unsendable (skip)."""
    ext = os.path.splitext(path)[1].lower()
    cleanup = None
    try:
        if ext in IMAGE_EXT:
            if os.path.getsize(path) > BOT_LIMIT:
                raise Unsendable("image over bot limit")
            api_call(token, "sendPhoto",
                     {"chat_id": chat_id, "caption": caption},
                     {"photo": path})
            return

        if ext in VIDEO_EXT:
            send_path, cleanup = media.prepare_video(
                path, BOT_LIMIT, SIZE_TARGET, bitrate, fps, maxh,
                progress, phase, floor=floor)
            # Encoding is done; the upload that follows has no percentage,
            # so hide the number instead of freezing at 99%.
            if progress:
                progress(-1)
            if phase:
                phase("uploading")
            w, h, d = media.probe(send_path)
            fields = {"chat_id": chat_id, "caption": caption,
                      "supports_streaming": "true"}
            if w and h:
                fields["width"], fields["height"] = str(w), str(h)
            if d:
                fields["duration"] = str(d)
            api_call(token, "sendVideo", fields, {"video": send_path})
            return

        if os.path.getsize(path) > BOT_LIMIT:
            raise Unsendable("file over bot limit")
        api_call(token, "sendDocument",
                 {"chat_id": chat_id, "caption": caption}, {"document": path})
    finally:
        if cleanup:
            try:
                os.unlink(cleanup)
            except OSError:
                pass


def send_photo_album(token: str, chat_id: str, paths: list, caption: str) -> None:
    """Send up to 10 photos as ONE album (one notification on the phone).

    A screenshot burst would otherwise ping the phone once per shot.
    Telegram's sendMediaGroup takes a JSON media array whose items
    reference the multipart files via attach://<name>; only the first
    item's caption is shown for the album.
    """
    if not paths:
        return
    if len(paths) == 1:
        send_media(token, chat_id, paths[0], caption)
        return

    media = []
    files = {}
    for i, p in enumerate(paths[:10]):
        name = "photo%d" % i
        item = {"type": "photo", "media": "attach://" + name}
        if i == 0:
            item["caption"] = caption
        media.append(item)
        files[name] = p

    api_call(token, "sendMediaGroup",
             {"chat_id": chat_id, "media": json.dumps(media)}, files)


# ----------------------------------------------------------------- onboarding

def get_me(token: str) -> dict:
    return api_call(token, "getMe", timeout=15)


def detect_chat_id(token: str):
    """Return (chat_id, first_name) of the newest private chat, or None.

    Two getUpdates calls cover both failure modes of one:
      - plain (no offset): the backlog, capped at 100 oldest updates
      - offset=-1: only the single newest update
    A /start buried past a 100-deep backlog is caught by the second call;
    a /start followed by an unrelated group event is caught by the first.
    The newest private chat across both wins (by update_id).

    Bots that have a webhook configured cannot use getUpdates at all;
    surface that as a readable error instead of a bare 409.
    """
    updates = []
    for fields in (None, {"offset": -1}):
        try:
            updates += api_call(token, "getUpdates", fields, timeout=15)
        except TelegramError as e:
            if "webhook" in str(e).lower():
                raise TelegramError(
                    "this bot has a webhook set; remove it (deleteWebhook) "
                    "or create a fresh bot")
            raise
    best = None
    best_id = -1
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") == "private" and chat.get("id"):
            uid = u.get("update_id", 0)
            if uid > best_id:
                best_id = uid
                best = (str(chat["id"]), chat.get("first_name", ""))
    return best
