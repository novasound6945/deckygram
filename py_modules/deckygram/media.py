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

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov"}

AUDIO_BITRATE = 128_000     # generous bound for the 96k AAC track + container
MIN_BITRATE = 400_000       # below this the video is not worth watching

# The one real tradeoff in clip sending: a fixed size budget buys either a
# good-looking short clip or a rough long one.  Rather than ask people for
# numbers they cannot judge, offer three points on that curve.
#
# ceiling  how much bitrate to spend when the budget is generous (short
#          clips) - without it a 30 s clip on Telegram would use 2 Mbps
#          out of the 12 it could afford
# floor    how rough it may get before we give up and skip the clip
# height   frame height cap
# Tuned around the length people actually send - roughly a minute. At 60 s
# Telegram's budget affords ~6 Mbit/s, but H.265 stops paying for itself
# well before that on an 800p capture, so the ceiling stops at 3 Mbit/s
# rather than spending the whole budget for no visible gain.
# Destinations may cap the height further: see discord.HEIGHT_CAP.
PRESETS = {
    "quality":  {"ceiling": 3_000_000, "floor": 900_000, "height": 800},
    "balanced": {"ceiling": 2_000_000, "floor": 400_000, "height": 600},
    "reach":    {"ceiling": 1_200_000, "floor": 200_000, "height": 480},
}
DEFAULT_PRESET = "balanced"


def preset(name) -> dict:
    """Preset settings by name, falling back to balanced."""
    return PRESETS.get(name or DEFAULT_PRESET, PRESETS[DEFAULT_PRESET])


def fit_bitrate(size_target: int, duration_sec: int, desired: int) -> int:
    """Highest video bitrate that keeps `duration_sec` under `size_target`."""
    fit = size_target * 8 // duration_sec - AUDIO_BITRATE
    return min(desired, fit)


def hopeless(size_target: int, duration_sec: int, floor: int = MIN_BITRATE) -> bool:
    """True when nothing above `floor` can fit the clip under the limit."""
    return duration_sec > 0 and \
        size_target * 8 // duration_sec - AUDIO_BITRATE < floor


def max_seconds(size_target: int, floor: int = MIN_BITRATE) -> int:
    """Longest clip that still fits above `floor` - quoted in the UI."""
    return max(0, size_target * 8 // (floor + AUDIO_BITRATE))


# ------------------------------------------------------------------- ffprobe

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
