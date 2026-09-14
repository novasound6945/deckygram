"""Video probing and compression, shared by every destination.

Videos are compressed before sending so they arrive fast on a phone:
  - frame rate is capped (default 30 fps)
  - bitrate is capped; if the source is already light it is sent as-is
  - files over the destination's limit get their bitrate lowered to fit

Compression uses the Deck's hardware encoder (VAAPI, H.265) end to end -
decode, scale and encode all stay on the GPU's dedicated video block, so
a running game is barely affected.  Measured on a Steam Deck: an
89-second clip encodes in ~13 s at ~7 % CPU.  Falls back to H.264 VAAPI,
then software x264, for sources the hardware cannot handle.

Every size figure is passed in rather than baked in: Telegram allows
50 MB per upload, an unboosted Discord server only 10 MB, so the same
clip is encoded to a different target depending on where it is going.
"""

import os
import subprocess
import tempfile

from .errors import Unsendable

# Where compression temp files go.  The host (main.py) points this at the
# plugin state dir on disk, because /tmp on SteamOS is RAM-backed tmpfs.
TMP_DIR = None
VAAPI_DEV = "/dev/dri/renderD128"

def clear_stale_temps(tmp_dir):
    """Delete leftover compression temp files. Returns (count, bytes).

    A clip is compressed into a NamedTemporaryFile that the sender unlinks
    when it is done. If the plugin is stopped mid-encode - a reload, a
    crash, the Deck powering off - that file is orphaned, and clips are
    large enough that a few of these are real disk (one 45 MB leftover was
    found this way, 2026-09-01).

    Only safe to call at startup: nothing of ours is encoding yet, so any
    temp file present is by definition abandoned.
    """
    n = size = 0
    if not tmp_dir:
        return (0, 0)
    for name in os.listdir(tmp_dir):
        if not name.startswith("tmp") or not name.endswith(".mp4"):
            continue
        path = os.path.join(tmp_dir, name)
        try:
            if not os.path.isfile(path):
                continue
            size += os.path.getsize(path)
            os.unlink(path)
            n += 1
        except OSError:
            pass
    return (n, size)


IMAGE_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov"}

AUDIO_BITRATE = 128_000     # generous bound for the 96k AAC track + container
MIN_BITRATE = 400_000       # below this the video is not worth watching

# How many bits a clip may spend per second, offered as a plain number
# rather than a word.  The top of the range is what a Steam Deck records
# at (measured: 12.8 Mbit/s at 1280x800), so picking it asks for the
# recording as it was made; the rest trade that away for length.
#
# Nothing here promises the clip will get it.  A size limit divided by a
# duration is a hard ceiling of its own, and the lower of the two wins -
# at 45 MB a minute cannot exceed ~6.2 Mbit/s whatever is chosen here.
# The UI says so before the choice is made: see estimate().
# No ceiling of our own: send the recording as it is and let the size
# limit be the only thing that reduces it.  Named rather than numbered,
# because the number would be a guess - Steam picks the recording
# bitrate from the game's resolution and the quality setting, so on a
# Deck's own screen it is 12, 7.5, 5.6 or 3.75 Mbit/s depending on
# which of the four qualities is chosen.
SOURCE = -1

# The rest line up with that same table so each one means something: a
# choice between two values the recording never reaches does nothing at
# all.
BITRATES = (SOURCE, 7_500_000, 6_000_000, 3_750_000)

# 6 Mbit/s is as much as a minute can actually use on Telegram (45 MB
# over 60 s is ~6.2), so it is the point where the choice and the limit
# agree - which makes it the one to start people on.
DEFAULT_BITRATE = 6_000_000

# How rough a clip may get before it is not worth sending at all.  This
# is what bounds the longest clip that can be sent, and it is deliberately
# not tied to the choice above: "unwatchable" does not move because
# someone asked for a bigger number.
FLOOR = 400_000

# What a clip is sent at, at most.  A Deck's own screen is 1280x800 and
# that is what it records handheld, so this changes nothing for most
# clips - but plugged into a monitor the same game records at 1080p or
# more, and those extra pixels would only thin out the same bitrate.
# Capping here rather than offering it as a choice: nobody wants to
# think about resolution, and there is one right answer.
DECK_HEIGHT = 800

# The frame rate FLOOR is written for.  Twice the frames at the same
# bitrate is half the bits each, so the point of giving up moves with it.
BASE_FPS = 30

# Settings written before the bitrate was a number of its own.
LEGACY_PRESETS = {"quality": SOURCE,
                  "balanced": 6_000_000,
                  "reach": 3_750_000}


def pick_bitrate(chosen, legacy_preset=None) -> int:
    """The chosen bitrate, an old preset translated, or the default."""
    try:
        n = int(chosen)
    except (TypeError, ValueError):
        n = 0
    if n in BITRATES:
        return n
    return LEGACY_PRESETS.get(legacy_preset or "", DEFAULT_BITRATE)


def floor_for(fps: int) -> int:
    """The give-up threshold at this frame rate."""
    if not fps or fps <= BASE_FPS:
        return FLOOR
    return int(FLOOR * fps / BASE_FPS)


def fit_bitrate(size_target: int, duration_sec: int, desired: int) -> int:
    """Highest video bitrate that keeps `duration_sec` under `size_target`.

    A `desired` of SOURCE means no ceiling was asked for, so the size
    limit is the only thing deciding.
    """
    fit = size_target * 8 // duration_sec - AUDIO_BITRATE
    if desired <= 0:
        return fit
    return min(desired, fit)


def estimate(size_target: int, hard_limit: int, duration_sec: int,
             bitrate: int, floor: int = FLOOR) -> dict:
    """What a clip of this length weighs, and what will happen to it.

    `full_seconds` is the length this bitrate survives intact - past it
    the size limit takes over and the clip gets whatever fits.  That is
    the number worth showing: it tells someone what their choice buys
    without assuming how long their clips are.  A 12.8 Mbit/s pick is
    not a mistake because a minute would not fit; it is exactly right
    for the thirty-second one they had in mind.

    `mb` is what a clip of `duration_sec` would actually weigh, offered
    as a reference point rather than a verdict.
    """
    if duration_sec <= 0:
        return {}
    real = fit_bitrate(size_target, duration_sec, bitrate)
    if bitrate <= 0:
        # Nothing of ours to overrun: how long a clip survives intact
        # depends on how heavy the recording is, which is Steam's to
        # decide and not something we can quote here.
        return {"seconds": duration_sec, "source": True,
                "bitrate": real, "sendable": real >= floor}
    asked = (bitrate + AUDIO_BITRATE) * duration_sec // 8
    return {
        "seconds": duration_sec,
        "source": False,
        "full_seconds": int(size_target * 8 // (bitrate + AUDIO_BITRATE)),
        "asked_bitrate": bitrate,
        "asked_mb": round(asked / 1024 / 1024, 1),
        "fits": asked <= hard_limit,
        "bitrate": real,
        "mb": round((real + AUDIO_BITRATE) * duration_sec / 8 / 1024 / 1024, 1),
        "sendable": real >= floor,
    }


def hopeless(size_target: int, duration_sec: int, floor: int = MIN_BITRATE) -> bool:
    """True when nothing above `floor` can fit the clip under the limit."""
    return duration_sec > 0 and \
        size_target * 8 // duration_sec - AUDIO_BITRATE < floor


def max_seconds(size_target: int, floor: int = MIN_BITRATE) -> int:
    """Longest clip that still fits above `floor` - quoted in the UI."""
    return max(0, size_target * 8 // (floor + AUDIO_BITRATE))


# ------------------------------------------------------------------- ffprobe

def _ratio(text: str) -> float:
    """ffprobe's "num/den" as a float; 0 for anything unusable."""
    num, _, den = text.strip().partition("/")
    try:
        bottom = float(den) if den else 1.0
        return float(num) / bottom if bottom else 0.0
    except ValueError:
        return 0.0


def source_fps(path: str) -> float:
    """Frames actually written per second, 0 when unknown.

    Deliberately `avg_frame_rate` and not `r_frame_rate`.  The latter is
    the lowest rate that can express every timestamp in the file, so a
    little jitter doubles it: a Steam clip measured here reported
    r_frame_rate=120 while carrying 554 frames across 18.46 s - 30 fps.
    Believing that number is how frames get duplicated, which is exactly
    what this reading exists to prevent.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return 0.0
    return _ratio(out)


def probe(path: str):
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
            if key in ("out_time_us", "out_time_ms"):   # both are µs
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
    w, h, dur = probe(src)
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


def prepare_video(path: str, hard_limit: int, size_target: int, bitrate: int,
                  fps: int, maxh: int, progress=None, phase=None,
                  floor: int = MIN_BITRATE):
    """Return (path_to_send, temp_file_to_delete_or_None).

    Raises Unsendable when the file cannot be brought under the limit.
    """
    size = os.path.getsize(path)
    _, _, dur = probe(path)

    # Never ask for more frames than were recorded.  The fps filter would
    # duplicate them and the encoder would spend real bits doing it -
    # measured on a 30 fps source asked for 60: 44.8 MB against 25.2 MB
    # for a file that looks exactly the same.  The extra budget that came
    # with the higher rate goes back too, so the result matches what the
    # preset promises at the rate actually being written.
    src_fps = source_fps(path)
    if src_fps and fps > src_fps + 0.5:
        give_back = src_fps / fps
        bitrate = int(bitrate * give_back)
        floor = int(floor * give_back)
        fps = max(1, int(round(src_fps)))

    if dur <= 0:
        if size > hard_limit:
            raise Unsendable("cannot read duration of oversized video")
        return path, None

    src_br = size * 8 // dur
    target = fit_bitrate(size_target, dur, bitrate)

    # Already light enough (within 15 % of the cap): send as-is.
    if size <= hard_limit and src_br <= target * 115 // 100:
        return path, None

    if target < floor:
        raise Unsendable("video too long to fit at watchable quality")

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=TMP_DIR)
    tmp.close()
    if phase:
        phase("encoding")
    if not _encode(path, tmp.name, target, fps, maxh, progress):
        os.unlink(tmp.name)
        raise Unsendable("all encoders failed")

    new = os.path.getsize(tmp.name)
    if new == 0 or new > hard_limit:
        os.unlink(tmp.name)
        raise Unsendable("compressed output still over the limit")
    if new >= size and size <= hard_limit:
        os.unlink(tmp.name)     # compression did not help; keep the original
        return path, None
    return tmp.name, tmp.name
