"""Caption text and clip-metadata parsing.

Pure logic (no Telegram, no threads) so it can be unit-tested directly.
The resolver argument is anything with .resolve(appid) -> str.
"""

import calendar
import os
import re
import time

APPID_RE = re.compile(r"/760/remote/(\d+)/screenshots/")
CLIP_ID_RE = re.compile(r"clip_(\d+)_(\d{8})_(\d{6})")
MPD_DURATION_RE = re.compile(
    r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?"')


def appid_from_path(path: str):
    """Appid embedded in a screenshot path, or None."""
    m = APPID_RE.search(path)
    return m.group(1) if m else None


def caption_for(path: str, resolver) -> str:
    appid = appid_from_path(path)
    name = resolver.resolve(appid) if appid else os.path.splitext(
        os.path.basename(path))[0]
    try:
        when = time.strftime("%Y-%m-%d %H:%M",
                             time.localtime(os.path.getmtime(path)))
    except OSError:
        when = time.strftime("%Y-%m-%d %H:%M")
    return "%s · %s" % (name, when)


def album_caption(appid: str, resolver, count: int) -> str:
    name = resolver.resolve(appid)
    when = time.strftime("%Y-%m-%d %H:%M")
    return "%s · %s (%d)" % (name, when, count)


def clip_time(clip_id: str):
    """When a clip was taken, as an epoch - or None for a name we do not know.

    Steam writes the folder name in UTC, not local time: on a Deck set
    to Asia/Seoul a clip named 20260915_153023 had its first fragment
    written at 2026-09-16 00:30:26, nine hours on, and a user five zones
    east of UTC reported captions "five hours early" (2026-09-16).
    """
    m = CLIP_ID_RE.match(clip_id)
    if not m:
        return None
    try:
        parsed = time.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return calendar.timegm(parsed)


def clip_caption(clip_id: str, resolver, localtime=time.localtime) -> str:
    m = CLIP_ID_RE.match(clip_id)
    if not m:
        return "Steam Deck clip"
    name = resolver.resolve(m.group(1))
    when = clip_time(clip_id)
    if when is None:
        d, t = m.group(2), m.group(3)
        return "%s · %s-%s-%s %s:%s" % (name, d[:4], d[4:6], d[6:8], t[:2], t[2:4])
    return "%s · %s" % (name, time.strftime("%Y-%m-%d %H:%M", localtime(when)))


def parse_mpd_duration(text: str) -> int:
    """Seconds from a DASH manifest's mediaPresentationDuration, 0 if absent."""
    m = MPD_DURATION_RE.search(text)
    if not m:
        return 0
    h, mi, s = (float(x) if x else 0 for x in m.groups())
    return int(h * 3600 + mi * 60 + s)
