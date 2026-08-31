"""Telegram Bot API client and media preparation.

Stdlib only (urllib + a small multipart encoder) so the plugin has zero
Python dependencies.

Videos are compressed before sending so they arrive fast on a phone:
  - frame rate is capped (default 30 fps)
  - bitrate is capped; if the source is already light it is sent as-is
  - files over the 50 MB bot limit get their bitrate lowered to fit

Compression uses the Deck's hardware encoder (VAAPI, H.265) end to end -
decode, scale and encode all stay on the GPU's dedicated video block, so
a running game is barely affected.  Measured on a Steam Deck: an
89-second clip encodes in ~13 s at ~7 % CPU.  Falls back to H.264 VAAPI,
then software x264, for sources the hardware cannot handle.

sendVideo is always given width/height/duration/supports_streaming:
without them Telegram's player guesses the size and the aspect ratio
looks squashed.
"""

import json
import mimetypes
import os
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid

API = "https://api.telegram.org/bot%s/%s"

# Decky Loader ships its own bundled Python which does not know where
# SteamOS keeps its CA certificates, so default HTTPS verification fails
# with CERTIFICATE_VERIFY_FAILED.  Point the SSL context at the system
# bundle explicitly, falling back to library defaults.
_CA_CANDIDATES = (
    "/etc/ssl/certs/ca-certificates.crt",   # SteamOS / Arch / Debian
    "/etc/pki/tls/certs/ca-bundle.crt",     # Fedora
    "/etc/ssl/cert.pem",                    # others
)


def _make_ssl_context() -> ssl.SSLContext:
    for path in _CA_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:
                pass
    return ssl.create_default_context()


_SSL_CTX = _make_ssl_context()

# Where compression temp files go.  The host (main.py) points this at the
# plugin state dir on disk, because /tmp on SteamOS is RAM-backed tmpfs.
TMP_DIR = None
BOT_LIMIT = 50 * 1024 * 1024
SIZE_TARGET = 45 * 1024 * 1024   # leave headroom under the hard limit
VAAPI_DEV = "/dev/dri/renderD128"

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov"}

AUDIO_BITRATE = 128_000     # generous bound for the 96k AAC track + container
MIN_BITRATE = 400_000       # below this the video is not worth watching


def fit_bitrate(duration_sec: int, desired: int) -> int:
    """Highest video bitrate that keeps `duration_sec` under SIZE_TARGET."""
    fit = SIZE_TARGET * 8 // duration_sec - AUDIO_BITRATE
    return min(desired, fit)


def hopeless(duration_sec: int) -> bool:
    """True when no watchable bitrate can fit the clip under the bot limit."""
    return duration_sec > 0 and \
        SIZE_TARGET * 8 // duration_sec - AUDIO_BITRATE < MIN_BITRATE


class TelegramError(Exception):
    pass


class Unsendable(Exception):
    """Permanently unsendable (too big even after compression) - skip, don't retry."""


# ----------------------------------------------------------------- HTTP layer

def _multipart(fields: dict, files: dict):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, name, value)).encode("utf-8")
    for name, path in files.items():
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                 "Content-Type: %s\r\n\r\n"
                 % (boundary, name, os.path.basename(path), ctype)).encode("utf-8")
        with open(path, "rb") as f:
            body += f.read()
        body += b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    return bytes(body), "multipart/form-data; boundary=%s" % boundary


def api_call(token: str, method: str, fields: dict = None, files: dict = None,
             timeout: int = 600) -> dict:
    url = API % (token, method)
    if files:
        body, ctype = _multipart(fields or {}, files)
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype})
    elif fields:
        body = json.dumps(fields).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            payload = json.load(e)
        except Exception:
            raise TelegramError("HTTP %s" % e.code)
    except Exception as e:
        raise TelegramError(str(e))
    if not payload.get("ok"):
        raise TelegramError(payload.get("description", "unknown error"))
    return payload.get("result", {})


# ------------------------------------------------------------------- ffprobe

def _probe(path: str):
    """Return (width, height, duration_sec) - zeros when unknown."""
    def run(args):
        try:
            out = subprocess.run(["ffprobe", "-v", "error"] + args,
                                 capture_output=True, text=True, timeout=30)
            return out.stdout.strip()
        except Exception:
            return ""

    dims = run(["-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x", path])
    dur = run(["-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    w = h = d = 0
    if "x" in dims:
        try:
            w, h = (int(x) for x in dims.split("x")[:2])
        except ValueError:
            pass
    try:
        d = int(float(dur))
    except ValueError:
        pass
    return w, h, d


# --------------------------------------------------------------- compression

def _run_ffmpeg(cmd, duration: int, progress=None) -> bool:
    """Run one ffmpeg command, feeding percent updates to `progress`.

    ffmpeg's machine-readable "-progress" stream reports out_time_us
    (microseconds of output written); against the known source duration
    that yields a live percentage.
    """
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
        for line in proc.stdout:
            if not progress or duration <= 0:
                continue
            key, _, val = line.strip().partition("=")
            us = None
            if key == "out_time_us":
                try:
                    us = int(val)
                except ValueError:
                    pass
            elif key == "out_time_ms":     # historic quirk: value is also µs
                try:
                    us = int(val)
                except ValueError:
                    pass
            if us is not None and us >= 0:
                progress(min(99, int(us / (duration * 1_000_000) * 100)))
        proc.wait(timeout=1800)
        return proc.returncode == 0
    except Exception:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return False


def _encode(src: str, dst: str, bitrate: int, fps: int, maxh: int,
            progress=None) -> bool:
    """Try full-GPU H.265, then GPU with CPU decode, then software x264."""
    w, h, dur = _probe(src)
    scale_hw = ""
    scale_sw = ""
    if maxh and h > maxh and w:
        tw = (w * maxh // h) // 2 * 2
        scale_hw = ",scale_vaapi=w=%d:h=%d" % (tw, maxh)
        scale_sw = ",scale=-2:%d" % maxh

    nice = ["nice", "-n", "19", "ionice", "-c", "3"] if os.name != "nt" else []
    prog = ["-progress", "pipe:1", "-nostats"]
    attempts = [
        nice + ["ffmpeg", "-y", "-loglevel", "error"] + prog + [
                "-hwaccel", "vaapi", "-hwaccel_device", VAAPI_DEV,
                "-hwaccel_output_format", "vaapi", "-i", src,
                "-vf", "fps=%d%s" % (fps, scale_hw),
                "-c:v", "hevc_vaapi", "-b:v", str(bitrate), "-maxrate", str(bitrate),
                "-compression_level", "1", "-tag:v", "hvc1",
                "-c:a", "aac", "-b:a", "96k", dst],
        nice + ["ffmpeg", "-y", "-loglevel", "error"] + prog + [
                "-vaapi_device", VAAPI_DEV, "-i", src,
                "-vf", "fps=%d%s,format=nv12,hwupload" % (fps, scale_sw),
                "-c:v", "hevc_vaapi", "-b:v", str(bitrate), "-maxrate", str(bitrate),
                "-compression_level", "1", "-tag:v", "hvc1",
                "-c:a", "aac", "-b:a", "96k", dst],
        nice + ["ffmpeg", "-y", "-loglevel", "error"] + prog + [
                "-vaapi_device", VAAPI_DEV, "-i", src,
                "-vf", "fps=%d%s,format=nv12,hwupload" % (fps, scale_sw),
                "-c:v", "h264_vaapi", "-b:v", str(bitrate), "-maxrate", str(bitrate),
                "-c:a", "aac", "-b:a", "96k", dst],
        nice + ["ffmpeg", "-y", "-loglevel", "error"] + prog + [
                "-i", src,
                "-vf", "fps=%d%s" % (fps, scale_sw),
                "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", str(bitrate), "-maxrate", str(bitrate),
                "-bufsize", str(bitrate * 2),
                "-c:a", "aac", "-b:a", "96k", dst],
    ]
    for cmd in attempts:
        if _run_ffmpeg(cmd, dur, progress):
            try:
                if os.path.getsize(dst) > 0:
                    return True
            except OSError:
                pass
    return False


def _prepare_video(path: str, bitrate: int, fps: int, maxh: int,
                   progress=None, phase=None):
    """Return path to send (original or a compressed temp file).

    Raises Unsendable when the file cannot be brought under the bot limit.
    """
    size = os.path.getsize(path)
    _, _, dur = _probe(path)

    if dur <= 0:
        if size > BOT_LIMIT:
            raise Unsendable("cannot read duration of oversized video")
        return path, None

    src_br = size * 8 // dur
    target = fit_bitrate(dur, bitrate)

    # Already light enough (within 15 % of the cap): send as-is.
    if size <= BOT_LIMIT and src_br <= target * 115 // 100:
        return path, None

    if target < MIN_BITRATE:
        raise Unsendable("video too long to fit under 50 MB at watchable quality")

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=TMP_DIR)
    tmp.close()
    if phase:
        phase("encoding")
    if not _encode(path, tmp.name, target, fps, maxh, progress):
        os.unlink(tmp.name)
        raise Unsendable("all encoders failed")

    new = os.path.getsize(tmp.name)
    if new == 0 or new > BOT_LIMIT:
        os.unlink(tmp.name)
        raise Unsendable("compressed output still over the limit")
    if new >= size and size <= BOT_LIMIT:
        os.unlink(tmp.name)     # compression did not help; keep the original
        return path, None
    return tmp.name, tmp.name


# ------------------------------------------------------------------- sending

def send_media(token: str, chat_id: str, path: str, caption: str,
               bitrate: int = 2_000_000, fps: int = 30, maxh: int = 600,
               progress=None, phase=None, original: bool = False) -> None:
    """Send one file. Raises TelegramError (retryable) or Unsendable (skip).

    original=True sends images as documents: Telegram re-compresses every
    sendPhoto server-side, sendDocument delivers the file byte-for-byte.
    """
    ext = os.path.splitext(path)[1].lower()
    cleanup = None
    try:
        if ext in IMAGE_EXT:
            if os.path.getsize(path) > BOT_LIMIT:
                raise Unsendable("image over bot limit")
            if original:
                # Without disable_content_type_detection Telegram sniffs the
                # upload, recognises an image and converts it back into a
                # compressed photo - defeating the whole point.  (Album
                # sends force this off already, single sends must ask.)
                api_call(token, "sendDocument",
                         {"chat_id": chat_id, "caption": caption,
                          "disable_content_type_detection": "true"},
                         {"document": path})
            else:
                api_call(token, "sendPhoto",
                         {"chat_id": chat_id, "caption": caption},
                         {"photo": path})
            return

        if ext in VIDEO_EXT:
            send_path, cleanup = _prepare_video(path, bitrate, fps, maxh,
                                                progress, phase)
            # Encoding is done; the upload that follows has no percentage,
            # so hide the number instead of freezing at 99%.
            if progress:
                progress(-1)
            if phase:
                phase("uploading")
            w, h, d = _probe(send_path)
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


def send_photo_album(token: str, chat_id: str, paths: list, caption: str,
                     as_document: bool = False) -> None:
    """Send up to 10 photos as ONE album (one notification on the phone).

    A screenshot burst would otherwise ping the phone once per shot.
    Telegram's sendMediaGroup takes a JSON media array whose items
    reference the multipart files via attach://<name>; only the first
    item's caption is shown for the album.

    as_document=True groups them as files instead (original quality; a
    media group must be all-photo or all-document, never mixed).
    """
    if not paths:
        return
    if len(paths) == 1:
        send_media(token, chat_id, paths[0], caption, original=as_document)
        return

    kind = "document" if as_document else "photo"
    media = []
    files = {}
    for i, p in enumerate(paths[:10]):
        name = "%s%d" % (kind, i)
        item = {"type": kind, "media": "attach://" + name}
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
