"""Discord webhook destination - screenshots only.

Deliberately smaller than the Telegram backend.  Telegram is the primary
destination (it is what the plugin is named after); Discord exists for
people who share screenshots in a Discord channel and do not want to set
up a bot at all.

Why webhooks rather than a bot: a webhook URL *is* the credential, so
setup is "make a webhook in the channel, paste the URL" - no application
to register, no OAuth, no invite flow.  The tradeoff is that a webhook
posts to one channel of one server, and uploads are capped by that
server's boost tier (10 MB on a free server, and it follows the SERVER's
tier, not the poster's Nitro).

Clips work too, but the budget is a quarter of Telegram's, so they are
encoded harder (lower bitrate, 480p instead of 600p) and anything long
enough to be hopeless at that size is skipped up front - roughly three
minutes on a free server.
"""

import os
import re

from . import media, net
from .errors import SendError, SetupBroken, Unsendable

# A webhook URL looks like
#   https://discord.com/api/webhooks/<id>/<token>
# discordapp.com still works and ptb/canary subdomains exist, so accept
# the family rather than one literal host.
URL_RE = re.compile(
    r"^https://(?:\w+\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]+/?$")

# Free (unboosted) servers cap attachments at 10 MB.  Staying under it is
# the safe default; a boosted server would allow more but the plugin has
# no way to find that out before uploading.
SIZE_LIMIT = 10 * 1024 * 1024
SIZE_TARGET = 9 * 1024 * 1024    # headroom for the multipart envelope
MAX_HEIGHT = 480                 # smaller frame to spend the bitrate better
MAX_FILES = 10                   # per message, matching our album size


def valid_url(url: str) -> bool:
    return bool(URL_RE.match((url or "").strip()))


def _check(status: int, payload):
    """Turn a webhook response into our shared exception vocabulary."""
    if 200 <= status < 300:
        return
    msg = ""
    retry_after = 0
    if isinstance(payload, dict):
        msg = str(payload.get("message") or payload.get("error") or "")
        try:
            retry_after = int(float(payload.get("retry_after") or 0))
        except (TypeError, ValueError):
            retry_after = 0
    if status in (401, 403, 404):
        # 404 is the common one: the webhook (or its channel) was deleted.
        raise SetupBroken(msg or "webhook rejected (HTTP %d)" % status, code=status)
    if status == 413:
        raise Unsendable("file too large for this Discord server")
    raise SendError(msg or "HTTP %d" % status, code=status, retry_after=retry_after)


def _post(url: str, content: str, paths: list, timeout: int = 300):
    files = {"files[%d]" % i: p for i, p in enumerate(paths[:MAX_FILES])}
    # payload_json carries everything that is not a file.  allowed_mentions
    # is pinned to nothing so a game title containing @everyone cannot ping
    # a channel.
    payload = ('{"content": %s, "allowed_mentions": {"parse": []}}'
               % _json_str(content))
    try:
        status, body = net.request(url, fields={"payload_json": payload},
                                   files=files, timeout=timeout)
    except net.Unreachable as e:
        raise SendError(str(e))
    _check(status, body)


def _json_str(s: str) -> str:
    import json
    return json.dumps(s or "")


def hopeless(duration_sec: int) -> bool:
    return media.hopeless(SIZE_TARGET, duration_sec)


def send_media(url: str, path: str, caption: str, bitrate: int = 2_000_000,
               fps: int = 30, maxh: int = MAX_HEIGHT,
               progress=None, phase=None) -> None:
    """Send one file. Images go as-is; videos are compressed to fit."""
    ext = os.path.splitext(path)[1].lower()
    cleanup = None
    try:
        if ext in media.VIDEO_EXT:
            send_path, cleanup = media.prepare_video(
                path, SIZE_LIMIT, SIZE_TARGET, bitrate, fps,
                min(maxh or MAX_HEIGHT, MAX_HEIGHT), progress, phase)
            # Encoding is done; the upload that follows has no percentage.
            if progress:
                progress(-1)
            if phase:
                phase("uploading")
            _post(url, caption, [send_path])
            return

        if os.path.getsize(path) > SIZE_LIMIT:
            raise Unsendable("file over the Discord server's upload limit")
        _post(url, caption, [path])
    finally:
        if cleanup:
            try:
                os.unlink(cleanup)
            except OSError:
                pass


def send_album(url: str, paths: list, caption: str) -> None:
    """Several screenshots as ONE message (Discord shows them as a grid)."""
    if not paths:
        return
    keep = []
    for p in paths[:MAX_FILES]:
        try:
            if os.path.getsize(p) <= SIZE_LIMIT:
                keep.append(p)
        except OSError:
            pass
    if not keep:
        raise Unsendable("all images over the Discord server's upload limit")
    _post(url, caption, keep)


def send_test(url: str) -> None:
    try:
        status, body = net.request(
            url, json_body={"content": "Deckygram connected. "
                                       "Screenshots will arrive here.",
                            "allowed_mentions": {"parse": []}},
            timeout=15)
    except net.Unreachable as e:
        raise SendError(str(e))
    _check(status, body)
